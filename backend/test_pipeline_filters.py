from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import uuid
import json

from nlp.openrouter import (
    _balanced_keyword_candidates,
    _keyword_generation_support_is_valid,
    extract_keywords_from_urls_ai,
    filter_keyword_gap_recommendations,
    generate_ai_keywords_sync,
)
from nlp.keywords import is_publishable_keyword
from workers.pipeline import (
    _balanced_competitor_domains,
    _discover_competitor_domains,
    _discover_content_urls,
    _clean_seed_keywords,
    _keyword_matches_topic,
    _llm_filter_competitor_domains,
    _order_seeds_by_emd,
    _search_result_urls,
    _with_source_url_ids,
)


class PipelineFilterTests(TestCase):
    def test_extraction_artifacts_are_not_publishable_keywords(self):
        self.assertFalse(is_publishable_keyword("age korean age", min_words=2))
        self.assertFalse(is_publishable_keyword("traditional korean traditional", min_words=2))
        self.assertTrue(is_publishable_keyword("lunar age in korea", min_words=2))

    def test_comma_separated_seeds_are_scanned_individually(self):
        self.assertEqual(
            _clean_seed_keywords(["circuit diagrams, wiring diagrams; pcb layouts"]),
            ["circuit diagrams", "wiring diagrams", "pcb layouts"],
        )

    def test_generated_keywords_require_real_input_support(self):
        seeds = ["lunar age calculator"]
        audit = "Core action: compare lunar and solar ages"
        evidence = ["lunar age in years months and days"]

        self.assertTrue(_keyword_generation_support_is_valid(
            {"support_source": "seed", "support_phrase": "lunar age calculator"},
            seeds, evidence, audit,
        ))
        self.assertTrue(_keyword_generation_support_is_valid(
            {"support_source": "competitor", "support_phrase": evidence[0]},
            seeds, evidence, audit,
        ))
        self.assertTrue(_keyword_generation_support_is_valid(
            {"support_source": "audit", "support_phrase": "compare lunar and solar ages"},
            seeds, evidence, audit,
        ))
        self.assertFalse(_keyword_generation_support_is_valid(
            {"support_source": "competitor", "support_phrase": "lunar age pricing"},
            seeds, evidence, audit,
        ))
        self.assertTrue(_keyword_generation_support_is_valid(
            {"phrase": "lunar age calculator by birth date"},
            seeds, evidence, audit,
        ))
        self.assertFalse(_keyword_generation_support_is_valid(
            {"phrase": "korean age calculator"},
            seeds, evidence, audit,
        ))

    def test_generator_accepts_legacy_schema_for_exact_seed_long_tails(self):
        with (
            patch("nlp.openrouter.is_ai_configured", return_value=True),
            patch("nlp.openrouter._chat_json", return_value=[{
                "phrase": "lunar age calculator by birth date",
                "type": "long-tail",
            }]),
        ):
            result = generate_ai_keywords_sync(
                ["lunar age calculator"],
                topic_terms={"lunar", "age", "birth", "date"},
                apply_gap_filter=False,
            )

        self.assertEqual(result, [{
            "phrase": "lunar age calculator by birth date",
            "type": "long-tail",
        }])

    def test_generator_discards_keywords_with_fabricated_support(self):
        payload = [
            {
                "phrase": "lunar age leap month",
                "type": "long-tail",
                "support_source": "audit",
                "support_phrase": "impact of leap months",
            },
            {
                "phrase": "lunar age pricing",
                "type": "long-tail",
                "support_source": "competitor",
                "support_phrase": "lunar age pricing",
            },
        ]
        with (
            patch("nlp.openrouter.is_ai_configured", return_value=True),
            patch("nlp.openrouter._chat_json", return_value=payload),
        ):
            result = generate_ai_keywords_sync(
                ["lunar age calculator"],
                topic_terms={"lunar", "age", "leap", "month"},
                audit_summary="Content opportunity: impact of leap months",
                evidence_phrases=["lunar age years months days"],
                apply_gap_filter=False,
            )

        self.assertEqual(result, [{"phrase": "lunar age leap month", "type": "long-tail"}])

    def test_ai_generation_uses_gold_summary_and_requests_easy_wins(self):
        audit = json.dumps({
            "primary_keyword": "lunar age calculator",
            "industry_niche": "east asian lunar age conversion tools",
            "core_action": "convert a birth date into lunar age",
            "capabilities": ["compare lunar and solar ages"],
            "content_opportunities": ["impact of leap months on lunar age"],
            "hard_boundaries": ["planet age calculations"],
        })
        payload = [{
            "phrase": "lunar age leap month guide",
            "type": "long-tail",
            "support_source": "audit",
            "support_phrase": "impact of leap months on lunar age",
        }]
        with (
            patch("nlp.openrouter.is_ai_configured", return_value=True),
            patch("nlp.openrouter._chat_json", return_value=payload) as chat,
        ):
            result = generate_ai_keywords_sync(
                ["lunar age calculator", "chinese lunar age"],
                topic_terms={"__anchor__lunar", "__scope__age", "__scope__month"},
                audit_summary=audit,
                apply_gap_filter=False,
            )

        self.assertEqual(result[0]["phrase"], "lunar age leap month guide")
        prompt = chat.call_args.kwargs["user_prompt"]
        self.assertIn("impact of leap months on lunar age", prompt)
        self.assertIn("Prioritize easy-to-rank opportunities", prompt)
        self.assertIn("no seed may be ignored", prompt)

    def test_competitor_discovery_runs_every_seed_and_balances_results(self):
        project = SimpleNamespace(
            own_domain="https://own.example",
            domain="https://own.example",
            search_locale="us",
            audit_summary="A focused circuit design tool",
        )
        calls = []

        def search(query, **kwargs):
            calls.append(query)
            slug = query.split()[0]
            return [f"https://{slug}{index}.example/blog/{slug}" for index in range(10)]

        with (
            patch("scraping.apify_client_module.is_apify_configured", return_value=False),
            patch("workers.pipeline._search_result_urls", side_effect=search),
            patch("workers.pipeline._llm_filter_competitor_domains", return_value=None),
        ):
            domains = _discover_competitor_domains(
                project,
                ["alpha circuit", "beta circuit", "gamma circuit"],
            )

        self.assertTrue({"alpha circuit", "beta circuit", "gamma circuit"}.issubset(calls))
        self.assertTrue(any("alpha" in domain for domain in domains))
        self.assertTrue(any("beta" in domain for domain in domains))
        self.assertTrue(any("gamma" in domain for domain in domains))

    def test_balancer_round_robins_seed_candidates(self):
        domains = ["a1", "a2", "b1", "b2", "c1", "c2"]
        signals = {
            domain: {"queries": [domain[0]]} for domain in domains
        }
        self.assertEqual(
            _balanced_competitor_domains(domains, signals, ["a", "b", "c"], 6),
            ["a1", "b1", "c1", "a2", "b2", "c2"],
        )

    def test_competitor_judge_cannot_drop_an_entire_seed(self):
        candidates = [
            {"domain": "https://alpha.example", "queries": ["alpha seed"], "source": "apify_page_1"},
            {"domain": "https://beta.example", "queries": ["beta seed"], "source": "apify_page_1"},
        ]
        with (
            patch("nlp.openrouter.is_ai_configured", return_value=True),
            patch("nlp.openrouter.judge_competitor_domains", return_value=[{"domain": "https://alpha.example"}]),
        ):
            result = _llm_filter_competitor_domains(
                ["alpha seed", "beta seed"], "https://own.example", candidates, 10,
            )
        self.assertEqual(result, ["https://alpha.example", "https://beta.example"])

    def test_keyword_candidates_are_balanced_across_seeds(self):
        candidates = [
            *({"phrase": f"alpha topic {index}"} for index in range(5)),
            *({"phrase": f"beta topic {index}"} for index in range(5)),
            *({"phrase": f"gamma topic {index}"} for index in range(5)),
        ]
        result = _balanced_keyword_candidates(["alpha", "beta", "gamma"], candidates, 6)
        self.assertEqual(
            [item["phrase"].split()[0] for item in result],
            ["alpha", "beta", "gamma", "alpha", "beta", "gamma"],
        )

    def test_keyword_relevance_allows_semantic_support_but_rejects_drift(self):
        topic_terms = {
            "circuit", "schematic", "electrical", "wiring",
            "__anchor__electrical", "__scope__board", "__scope__wiring",
        }
        self.assertTrue(_keyword_matches_topic("circuit board tutorial", ["circuit diagram"], topic_terms, set()))
        self.assertTrue(_keyword_matches_topic("electrical wiring guide", ["circuit diagram"], topic_terms, set()))
        self.assertFalse(_keyword_matches_topic("fishbone diagram template", ["circuit diagram"], topic_terms, set()))
        self.assertFalse(_keyword_matches_topic("electrical fitness guide", ["circuit diagram"], topic_terms, set()))

    def test_generic_age_overlap_cannot_redefine_lunar_age_topic(self):
        topic_terms = {
            "lunar", "calendar", "age", "chinese", "korean", "solar",
            "__anchor__moon", "__scope__age", "__scope__calendar",
            "__scope__conversion",
        }
        self.assertTrue(_keyword_matches_topic("lunar age in korea", ["lunar age calculator"], topic_terms, set()))
        self.assertTrue(_keyword_matches_topic("moon calendar conversion", ["lunar age calculator"], topic_terms, set()))
        self.assertFalse(_keyword_matches_topic("korean age calculator", ["lunar age calculator"], topic_terms, set()))
        self.assertFalse(_keyword_matches_topic("dog age in human years", ["lunar age calculator"], topic_terms, set()))
        self.assertFalse(_keyword_matches_topic("age milliseconds calculator", ["lunar age calculator"], topic_terms, set()))
        for phrase in (
            "age of planets in the solar system",
            "age of planets in our solar system",
            "birth of the solar system video",
            "solar system 100 planets",
            "mars after 100 years",
            "solar system size calculator australia",
            "solar system planet position calculator",
            "100 facts about solar system",
            "lunar eclipse calendar",
        ):
            self.assertFalse(_keyword_matches_topic(
                phrase, ["lunar age calculator"], topic_terms,
                {"planet", "planets", "mars", "eclipse", "astronomy", "orbit"},
            ), phrase)

    def test_emd_seed_is_promoted_to_primary_topic_boundary(self):
        self.assertEqual(
            _order_seeds_by_emd(
                ["moon calendar guide", "lunar age calculator", "chinese age systems"],
                "https://lunaragecalculator.com",
            )[0],
            "lunar age calculator",
        )

    def test_search_result_urls_stops_after_google_has_enough_results(self):
        with (
            patch(
                "workers.pipeline._search_google_result_urls",
                return_value=["https://alpha.example/blog/a", "https://beta.example/blog/b"],
            ) as google,
            patch("workers.pipeline._search_bing_result_urls") as bing,
            patch("workers.pipeline._search_duckduckgo_html_urls") as duckduckgo,
        ):
            urls = _search_result_urls("circuit diagram", include_google=True, max_results=2)

        self.assertEqual(urls, ["https://alpha.example/blog/a", "https://beta.example/blog/b"])
        google.assert_called_once()
        bing.assert_not_called()
        duckduckgo.assert_not_called()

    def test_discover_content_urls_prefers_topical_urls_when_enough_exist(self):
        all_urls = [
            "https://example.com/blog/random-company-update",
            "https://example.com/blog/circuit-diagram-guide",
            "https://example.com/blog/circuit-board-basics",
        ]

        urls = _discover_content_urls(
            "https://example.com",
            patterns=None,
            extract_all_urls_from_domain=lambda *args, **kwargs: all_urls,
            filter_blog_urls=lambda urls, **kwargs: urls,
            limit=2,
            required_terms={"circuit"},
            ranking_terms={"circuit", "diagram"},
            negative_terms=set(),
            source_type="competitor",
        )

        self.assertEqual(
            urls,
            [
                "https://example.com/blog/circuit-diagram-guide",
                "https://example.com/blog/circuit-board-basics",
            ],
        )

    def test_with_source_url_ids_keeps_evidence_after_normalization(self):
        source_id = str(uuid.uuid4())
        result = _with_source_url_ids(
            [
                {
                    "source_phrase": "awkward circuit diagram phrase",
                    "phrase": "circuit diagram tool",
                    "type": "primary",
                    "volume": "High",
                }
            ],
            [
                {
                    "phrase": "awkward circuit diagram phrase",
                    "url_ids": [source_id],
                    "frequency": 3,
                }
            ],
        )

        self.assertEqual(result[0]["url_ids"], [source_id])
        self.assertEqual(result[0]["frequency"], 3)

    def test_extract_keywords_from_urls_ai_aggregates_duplicate_phrases(self):
        first_id = uuid.uuid4()
        second_id = uuid.uuid4()
        pages = [
            SimpleNamespace(id=first_id, scraped_text="page one text", h1="Circuit Diagram Tool"),
            SimpleNamespace(id=second_id, scraped_text="page two text", h1="Circuit Diagram Tool"),
        ]
        keyword_result = SimpleNamespace(
            primary=[("circuit diagram tool", 1.0)],
            lsi=[],
            entities=[],
            heading_keywords=[],
        )

        with patch("nlp.keywords.extract_keywords_from_page", return_value=keyword_result):
            results = extract_keywords_from_urls_ai(
                ["circuit diagram"],
                pages,
                topic_terms={"circuit", "diagram"},
                negative_terms=set(),
            )

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["phrase"], "circuit diagram tool")
        self.assertEqual(set(results[0]["url_ids"]), {str(first_id), str(second_id)})
        self.assertEqual(results[0]["frequency"], 2)

    def test_gap_filter_preserves_source_metadata(self):
        source_id = str(uuid.uuid4())
        with (
            patch("nlp.openrouter.is_ai_configured", return_value=True),
            patch(
                "nlp.openrouter._chat_json",
                return_value=[
                    {
                        "source_phrase": "circuit diagram tool",
                        "phrase": "circuit diagram tool",
                        "type": "primary",
                        "volume": "High",
                    }
                ],
            ),
        ):
            result = filter_keyword_gap_recommendations(
                ["circuit diagram"],
                [
                    {
                        "phrase": "circuit diagram tool",
                        "type": "primary",
                        "url_ids": [source_id],
                        "frequency": 2,
                    }
                ],
            )

        self.assertEqual(result[0]["url_ids"], [source_id])
        self.assertEqual(result[0]["frequency"], 2)


if __name__ == "__main__":
    import unittest

    unittest.main()
