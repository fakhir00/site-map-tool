from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import uuid

from nlp.openrouter import _balanced_keyword_candidates, extract_keywords_from_urls_ai, filter_keyword_gap_recommendations
from workers.pipeline import (
    _balanced_competitor_domains,
    _discover_competitor_domains,
    _discover_content_urls,
    _clean_seed_keywords,
    _keyword_matches_topic,
    _llm_filter_competitor_domains,
    _search_result_urls,
    _seed_anchored_keyword_expansions,
    _with_source_url_ids,
)


class PipelineFilterTests(TestCase):
    def test_comma_separated_seeds_are_scanned_individually(self):
        self.assertEqual(
            _clean_seed_keywords(["circuit diagrams, wiring diagrams; pcb layouts"]),
            ["circuit diagrams", "wiring diagrams", "pcb layouts"],
        )

    def test_generic_seed_expansion_still_reaches_100_relevant_phrases(self):
        seeds = ["diagram maker"]
        expanded = _seed_anchored_keyword_expansions(seeds, set(), 100)
        self.assertEqual(len(expanded), 100)
        self.assertTrue(all(
            _keyword_matches_topic(item["phrase"], seeds, set(), set())
            for item in expanded
        ))

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
        topic_terms = {"circuit", "schematic", "electrical", "wiring"}
        self.assertTrue(_keyword_matches_topic("circuit board tutorial", ["circuit diagram"], topic_terms, set()))
        self.assertTrue(_keyword_matches_topic("electrical wiring guide", ["circuit diagram"], topic_terms, set()))
        self.assertFalse(_keyword_matches_topic("fishbone diagram template", ["circuit diagram"], topic_terms, set()))
        self.assertFalse(_keyword_matches_topic("electrical fitness guide", ["circuit diagram"], topic_terms, set()))

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
