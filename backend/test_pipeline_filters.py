from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, patch
import uuid
import json
import asyncio

from app.keywords.router import _is_displayable_keyword
from app.models import Keyword
from nlp.openrouter import (
    _balanced_keyword_candidates,
    _keyword_generation_support_is_valid,
    extract_keywords_from_urls_ai,
    filter_keyword_gap_recommendations,
    generate_ai_keywords_sync,
    generate_ai_keywords,
    research_keyword_queries_from_pages,
    judge_competitor_domains,
)
from nlp.keywords import (
    has_past_year,
    has_external_platform_modifier,
    has_unrelated_leading_entity,
    is_publishable_keyword,
    keyword_matches_emd_entity,
    looks_incomplete_search_query,
)
from workers.pipeline import (
    _balanced_competitor_domains,
    _build_ai_refined_accumulator,
    _crawl_limit_per_domain,
    _discover_competitor_domains,
    _discover_content_urls,
    _domains_to_discover,
    _clean_seed_keywords,
    _keyword_matches_topic,
    _llm_filter_competitor_domains,
    _order_seeds_by_emd,
    _phrase_mentions_unrelated_source_brand,
    _scan_seed_keywords,
    _search_result_urls,
    _scrape_chunk_size,
    _semantic_terms,
    _with_source_url_ids,
)


class PipelineFilterTests(TestCase):
    def test_branded_ranking_pages_are_not_dropped_before_review(self):
        project = SimpleNamespace(own_domain='https://own.example', domain='https://own.example',
                                  search_locale='us', audit_summary='A lunar age calculator')
        results = [
            {'url': 'https://specialist.example/', 'title': 'Lunar Age Calculator',
             'snippet': 'Calculate your age with the lunar calendar.'},
            {'url': 'https://other.example/tools/123', 'title': 'Lunar Age Calculator',
             'snippet': 'Calculate your lunar age.'},
            {'url': 'https://reddit.com/lunar-age-calculator', 'title': 'Lunar Age Calculator'},
            {'url': 'https://unrelated.example/', 'title': 'Lunar news', 'snippet': 'Space launches'},
            {'url': 'https://own.example/', 'title': 'Lunar Age Calculator'},
        ]
        ranking = {}
        with (
            patch('scraping.apify_client_module.is_apify_configured', return_value=True),
            patch('scraping.apify_client_module.search_google_via_apify', return_value=results),
            patch('workers.pipeline._llm_filter_competitor_domains', return_value=[]) as judge,
        ):
            domains = _discover_competitor_domains(project, ['lunar age calculator'], ranking_urls_out=ranking)
        self.assertEqual(domains, ['https://specialist.example', 'https://other.example'])
        self.assertEqual(ranking['https://other.example'], ['https://other.example/tools/123'])
        self.assertIn('https://specialist.example', [item['domain'] for item in judge.call_args.args[2]])

    def test_title_fallback_preserves_numeric_product_identity(self):
        from workers.pipeline import _ranking_page_matches_seed
        self.assertFalse(_ranking_page_matches_seed(
            {'title': 'Dental Pro 9 Reviews', 'snippet': 'Review of Dental Pro 9'}, 'dental pro 7 reviews'))
        self.assertTrue(_ranking_page_matches_seed(
            {'title': 'Dental Pro 7 Reviews', 'snippet': 'Product analysis'}, 'dental pro 7 reviews'))

    def test_statistical_extraction_preserves_source_adjacency(self):
        from nlp.keywords import extract_statistical_keywords
        phrases = dict(extract_statistical_keywords(
            "Chinese age increases on your birthday. Nominal age matters.", 100
        ))
        self.assertIn("nominal age", phrases)
        self.assertNotIn("chinese age increases birthday", phrases)
        self.assertNotIn("birthday nominal age", phrases)
        self.assertNotIn("increases birthday", phrases)

    def test_extensions_and_multiple_extractors_do_not_create_false_evidence(self):
        page = SimpleNamespace(
            id=uuid.uuid4(), url="https://example.com/chinese-age-calculator.php",
            h1="Chinese age calculator", scraped_text="Chinese age calculator",
        )
        extracted = SimpleNamespace(
            primary=[("chinese age calculator", 1)],
            lsi=[("chinese age calculator", 1)], entities=[],
            heading_keywords=["chinese age calculator"],
        )
        with patch("nlp.keywords.extract_keywords_from_page", return_value=extracted):
            results = extract_keywords_from_urls_ai(["chinese age calculator"], [page, page])
        self.assertEqual([r["phrase"] for r in results], ["chinese age calculator"])
        self.assertEqual(results[0]["frequency"], 1)

    def test_full_own_slug_is_covered(self):
        from workers.pipeline import _url_keyword_candidates, _remove_covered_keywords
        phrase = "chinese age calculator gender predictor"
        own = _url_keyword_candidates(
            "https://example.com/chinese-age-calculator-gender-predictor/",
            {"chinese", "age", "gender"}, set(), True,
        )
        candidates = {phrase: {"count": 1}}
        _remove_covered_keywords(candidates, own)
        self.assertEqual(candidates, {})

    def test_competitor_review_rejection_and_failure_never_publish_raw_candidates(self):
        from unittest.mock import MagicMock
        from workers.pipeline import _process_competitor_keyword_gaps
        db = MagicMock()
        db.execute.return_value.scalar.return_value = 1
        page = SimpleNamespace(url="https://own.example/tool", h1="Own tool", scraped_text="Existing answer")
        db.execute.return_value.scalars.return_value.all.return_value = [page]
        extracted = [{"phrase": "lunar age calculator", "url_ids": [str(uuid.uuid4())]}]
        for verdict in ([], None):
            review = MagicMock(return_value=verdict)
            with patch("workers.pipeline._store_keywords") as store:
                args = (db, uuid.uuid4(), ["lunar age calculator"], {"lunar", "age"}, set(),
                        "Site scope", MagicMock(return_value=extracted), review, MagicMock(), MagicMock())
                if verdict is None:
                    with self.assertRaisesRegex(RuntimeError, "quality review unavailable"):
                        _process_competitor_keyword_gaps(*args)
                else:
                    self.assertEqual(_process_competitor_keyword_gaps(*args), 0)
                store.assert_not_called()
                self.assertIn("Existing answer", review.call_args.kwargs["audit_summary"])

    def test_resume_queues_new_competitors_when_only_own_urls_exist(self):
        queued = _domains_to_discover(
            "https://own.example",
            ["https://direct.example"],
            True,
            {("own", "https://own.example")},
        )

        self.assertEqual(queued, [("https://direct.example", "competitor")])

    def test_competitor_judge_requires_direct_page_and_site_scope(self):
        payload = [
            {
                "domain": "https://general.example",
                "verdict": "accept",
                "page_match": True,
                "site_scope_match": False,
                "confidence": 95,
            },
            {
                "domain": "https://direct.example",
                "verdict": "accept",
                "page_match": True,
                "site_scope_match": True,
                "confidence": 90,
            },
        ]
        with (
            patch("nlp.openrouter.is_ai_configured", return_value=True),
            patch("nlp.openrouter._chat_json", return_value=payload),
        ):
            result = judge_competitor_domains(
                ["dental pro 7 reviews"],
                "https://dentalpro7.reviews",
                [{"domain": "https://general.example"}, {"domain": "https://direct.example"}],
            )

        self.assertEqual([item["domain"] for item in result], ["https://direct.example"])

    def test_competitor_extraction_uses_exact_ranking_page_slug(self):
        page = SimpleNamespace(
            id=uuid.uuid4(),
            url="https://example.com/moon-nodes-calculator",
            h1="Welcome",
            scraped_text=("unrelated navigation wording " * 20),
        )

        results = extract_keywords_from_urls_ai(
            ["moon nodes calculator"],
            [page],
            topic_terms={"moon", "nodes"},
            negative_terms=set(),
        )

        self.assertIn("moon nodes calculator", {item["phrase"] for item in results})

    def test_render_crawl_and_live_batch_have_hard_memory_caps(self):
        with (
            patch("workers.pipeline.settings.MAX_CONTENT_URLS_PER_DOMAIN", 500),
            patch("workers.pipeline.settings.MAX_URLS_PER_SCAN", 5000),
        ):
            self.assertEqual(_crawl_limit_per_domain([f"d{i}.example" for i in range(20)]), 12)
            self.assertEqual(_scrape_chunk_size(), 2)

    def test_extraction_artifacts_are_not_publishable_keywords(self):
        self.assertFalse(is_publishable_keyword("age korean age", min_words=2))
        self.assertFalse(is_publishable_keyword("traditional korean traditional", min_words=2))
        self.assertFalse(is_publishable_keyword("what dental", min_words=2))
        self.assertFalse(is_publishable_keyword("teeth whitening side", min_words=2))
        self.assertFalse(is_publishable_keyword("dental pro comes", min_words=2))
        self.assertFalse(is_publishable_keyword("reviews people saying", min_words=2))
        self.assertFalse(is_publishable_keyword("dental pro reviewthe", min_words=2))
        self.assertTrue(is_publishable_keyword("lunar age in korea", min_words=2))
        self.assertTrue(is_publishable_keyword("what causes gum recession", min_words=2))
        self.assertTrue(looks_incomplete_search_query("what dental"))

    def test_past_year_keywords_are_not_publishable(self):
        self.assertTrue(has_past_year("best circuit software 1974", current_year=2026))
        self.assertTrue(has_past_year("best circuit software 2024", current_year=2026))
        self.assertFalse(has_past_year("best circuit software 2026", current_year=2026))
        self.assertFalse(has_past_year("best circuit software 2027", current_year=2026))
        self.assertFalse(is_publishable_keyword("best circuit software 1974", min_words=2))
        self.assertFalse(is_publishable_keyword("best circuit software 2024", min_words=2))
        self.assertTrue(is_publishable_keyword("best circuit software 2027", min_words=2))
        self.assertTrue(is_publishable_keyword("circuit simulator 555 timer", min_words=2))

    def test_past_year_top_picks_are_hidden_from_existing_results(self):
        stale = Keyword(phrase="best circuit software 2024", keyword_type="top-pick")
        current = Keyword(phrase="best circuit software 2026", keyword_type="top-pick")

        self.assertFalse(_is_displayable_keyword(stale))
        self.assertTrue(_is_displayable_keyword(current))

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

    def test_empty_second_ai_filter_respects_rejection(self):
        payload = [{
            "phrase": "lunar age calculator by birth date",
            "type": "long-tail",
            "support_source": "seed",
            "support_phrase": "lunar age calculator",
        }]
        with (
            patch("nlp.openrouter.is_ai_configured", return_value=True),
            patch("nlp.openrouter._chat_json", side_effect=[payload, []]),
        ):
            result = generate_ai_keywords_sync(
                ["lunar age calculator"],
                topic_terms={"lunar", "age", "birth", "date"},
                apply_gap_filter=True,
            )

        self.assertEqual(result, [])

    def test_ai_generation_repairs_a_fully_rejected_first_response(self):
        invalid = [{
            "phrase": "age of planets",
            "type": "long-tail",
            "support_source": "seed",
            "support_phrase": "lunar age calculator",
        }]
        repaired = [{
            "phrase": "lunar age calculator for newborns",
            "type": "long-tail",
        }]
        with (
            patch("nlp.openrouter.is_ai_configured", return_value=True),
            patch("nlp.openrouter._chat_json", side_effect=[invalid, repaired]),
        ):
            result = generate_ai_keywords_sync(
                ["lunar age calculator"],
                topic_terms={"lunar", "age", "newborns"},
                apply_gap_filter=False,
            )

        self.assertEqual(result, [{
            "phrase": "lunar age calculator for newborns",
            "type": "long-tail",
        }])

    def test_ai_duplicate_only_batch_requests_new_alternatives_in_both_paths(self):
        duplicate = {'phrase': 'lunar age calculator by birth date', 'type': 'long-tail'}
        replacement = {'phrase': 'how to calculate lunar age', 'type': 'long-tail',
                       'support_source': 'seed', 'support_phrase': 'lunar age calculator'}
        for async_mode in (False, True):
            with self.subTest(async_mode=async_mode), patch('nlp.openrouter.is_ai_configured', return_value=True), patch(
                'nlp.openrouter._achat_json' if async_mode else 'nlp.openrouter._chat_json',
                side_effect=[[duplicate], [replacement]],
            ) as chat:
                kwargs = dict(apply_gap_filter=False, exclude_phrases={duplicate['phrase']})
                result = asyncio.run(generate_ai_keywords(['lunar age calculator'], **kwargs)) if async_mode else generate_ai_keywords_sync(['lunar age calculator'], **kwargs)
                self.assertEqual([item['phrase'] for item in result], [replacement['phrase']])
                self.assertEqual(chat.call_count, 2)

    def test_ai_keeps_observed_queries_when_legacy_output_omits_citations(self):
        with patch('nlp.openrouter.is_ai_configured', return_value=True), patch(
            'nlp.openrouter._chat_json', return_value=[{'phrase': 'lunar age leap month', 'type': 'long-tail'}],
        ):
            result = generate_ai_keywords_sync(['lunar age calculator'],
                evidence_phrases=['lunar age leap month'], apply_gap_filter=False)
        self.assertEqual([item['phrase'] for item in result], ['lunar age leap month'])
        self.assertFalse(_keyword_generation_support_is_valid(
            {'phrase': 'lunar age pricing'}, ['lunar age calculator'], ['lunar age leap month'], None))

    def test_question_seed_accepts_subject_preserving_provider_variations(self):
        seed = ['how to convert english to katakana']
        self.assertTrue(_keyword_matches_topic('english names in katakana', seed, set(), set()))
        self.assertFalse(_keyword_matches_topic('english names in arabic', seed, set(), set()))
        self.assertFalse(_keyword_matches_topic('english grammar course', seed, set(), set()))

    def test_ai_repair_can_shorten_a_long_question_without_losing_its_subject(self):
        seed = 'how to convert english to katakana'
        with patch('nlp.openrouter.is_ai_configured', return_value=True), patch(
            'nlp.openrouter._chat_json', side_effect=[[], [{
                'phrase': 'english names in katakana', 'type': 'long-tail',
                'support_source': 'seed', 'support_phrase': seed,
            }]],
        ):
            result = generate_ai_keywords_sync([seed], apply_gap_filter=False)
        self.assertEqual([item['phrase'] for item in result], ['english names in katakana'])

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

    def test_apify_searches_every_gold_hunter_seed(self):
        project = SimpleNamespace(
            own_domain="https://own.example",
            domain="https://own.example",
            search_locale="us",
            audit_summary="A focused calculator",
        )
        seeds = ["alpha calculator", "beta calculator", "gamma calculator", "delta calculator", "epsilon calculator"]
        calls = []

        def search(query, **kwargs):
            calls.append(query)
            return [{
                "url": f"https://{query.split()[0]}.example/{query.replace(' ', '-')}",
                "title": query,
                "snippet": f"A focused site for {query}",
            }]

        with (
            patch("scraping.apify_client_module.is_apify_configured", return_value=True),
            patch("scraping.apify_client_module.search_google_via_apify", side_effect=search),
            patch("workers.pipeline._llm_filter_competitor_domains", return_value=None),
        ):
            _discover_competitor_domains(project, seeds)

        self.assertEqual(calls, seeds)

    def test_competitor_discovery_returns_up_to_thirty_direct_domains(self):
        project = SimpleNamespace(
            own_domain="https://own.example",
            domain="https://own.example",
            search_locale="us",
            audit_summary="A focused circuit calculator",
        )
        results = [{
            "url": f"https://circuit{index}.example/alpha-circuit-calculator",
            "title": "Alpha circuit calculator",
            "snippet": "Calculate alpha circuits online",
        } for index in range(35)]

        with (
            patch("scraping.apify_client_module.is_apify_configured", return_value=True),
            patch("scraping.apify_client_module.search_google_via_apify", return_value=results),
            patch("workers.pipeline._llm_filter_competitor_domains", return_value=None),
            patch("workers.pipeline.settings.MAX_COMPETITOR_DOMAINS", 30),
            patch("workers.pipeline.settings.GOOGLE_SERP_RESULT_LIMIT", 30),
        ):
            domains = _discover_competitor_domains(project, ["alpha circuit calculator"])

        self.assertEqual(len(domains), 30)

    def test_competitor_discovery_never_runs_broad_modifier_queries(self):
        project = SimpleNamespace(
            own_domain="https://own.example",
            domain="https://own.example",
            search_locale="us",
            audit_summary="A focused lunar age calculator",
        )
        calls = []

        def search(query, **kwargs):
            calls.append(query)
            return [f"https://direct-{len(calls)}.example/{query.replace(' ', '-')}"]

        with (
            patch("scraping.apify_client_module.is_apify_configured", return_value=False),
            patch("workers.pipeline._search_result_urls", side_effect=search),
            patch("workers.pipeline._llm_filter_competitor_domains", return_value=None),
        ):
            _discover_competitor_domains(
                project,
                ["lunar age calculator", "chinese lunar age"],
            )

        self.assertEqual(calls, ["lunar age calculator", "chinese lunar age"])

    def test_balancer_round_robins_seed_candidates(self):
        domains = ["a1", "a2", "b1", "b2", "c1", "c2"]
        signals = {
            domain: {"queries": [domain[0]]} for domain in domains
        }
        self.assertEqual(
            _balanced_competitor_domains(domains, signals, ["a", "b", "c"], 6),
            ["a1", "b1", "c1", "a2", "b2", "c2"],
        )

    def test_competitor_judge_can_reject_junk_for_a_seed(self):
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
        self.assertEqual(result, ["https://alpha.example"])

    def test_competitor_judge_rejecting_everything_does_not_restore_junk(self):
        candidates = [{
            "domain": "https://broad-portal.example",
            "queries": ["lunar age calculator"],
            "sources": ["apify_page_1"],
        }]
        with (
            patch("nlp.openrouter.is_ai_configured", return_value=True),
            patch("nlp.openrouter.judge_competitor_domains", return_value=[]),
        ):
            result = _llm_filter_competitor_domains(
                ["lunar age calculator"], "https://own.example", candidates, 10,
            )
        self.assertEqual(result, [])

    def test_exact_seed_emd_survives_over_strict_competitor_judge(self):
        project = SimpleNamespace(
            own_domain="https://moonnodescalculator.com",
            domain="https://moonnodescalculator.com",
            search_locale="us",
            audit_summary="A moon nodes calculation tool",
        )
        results = [{
            "url": "https://moonnodescalculator.example/moon-nodes-calculator",
            "title": "Moon Nodes Calculator",
            "snippet": "Calculate your north and south moon nodes",
        }]
        with (
            patch("scraping.apify_client_module.is_apify_configured", return_value=True),
            patch("scraping.apify_client_module.search_google_via_apify", return_value=results),
            patch("workers.pipeline._llm_filter_competitor_domains", return_value=[]),
        ):
            domains = _discover_competitor_domains(project, ["moon nodes calculator"])

        self.assertEqual(domains, ["https://moonnodescalculator.example"])

    def test_emd_recovery_seed_repairs_stale_review_project(self):
        seeds = _scan_seed_keywords(
            ["dentitox pro ingredients label"],
            "https://dentalpro7.reviews",
            json.dumps({"primary_keyword": "dentitox pro ingredients"}),
        )

        self.assertEqual(seeds[0], "dentalpro 7 reviews")
        self.assertNotIn("dentitox pro ingredients label", seeds)

    def test_coupon_platform_is_blocked_even_when_subdomain_matches_seed(self):
        project = SimpleNamespace(
            own_domain="https://dentalpro7.reviews",
            domain="https://dentalpro7.reviews",
            search_locale="us",
            audit_summary="A focused Dental Pro 7 review site",
        )
        results = [
            {
                "url": "https://dental-pro-7.tenereteam.com/",
                "title": "Dental Pro 7 Reviews",
                "snippet": "Customer ratings and coupon offers",
            },
            {
                "url": "https://dentalpro7reviews.com/",
                "title": "Dental Pro 7 Reviews - Does It Work?",
                "snippet": "Independent Dental Pro 7 analysis",
            },
        ]
        with (
            patch("scraping.apify_client_module.is_apify_configured", return_value=True),
            patch("scraping.apify_client_module.search_google_via_apify", return_value=results),
            patch("workers.pipeline._llm_filter_competitor_domains", return_value=[]),
        ):
            domains = _discover_competitor_domains(project, ["dental pro 7 reviews"])

        self.assertEqual(domains, ["https://dentalpro7reviews.com"])

    def test_emd_competitor_supplements_partial_ai_judgment(self):
        project = SimpleNamespace(
            own_domain="https://dentalpro7.reviews",
            domain="https://dentalpro7.reviews",
            search_locale="us",
            audit_summary="A focused Dental Pro 7 review site",
        )
        results = [
            {"url": "https://specialist.example/review", "title": "Dental Pro 7 review", "snippet": "Product analysis"},
            {"url": "https://dentalpro7reviews.com/", "title": "Dental Pro 7 Reviews", "snippet": "Focused review site"},
        ]
        with (
            patch("scraping.apify_client_module.is_apify_configured", return_value=True),
            patch("scraping.apify_client_module.search_google_via_apify", return_value=results),
            patch("workers.pipeline._llm_filter_competitor_domains", return_value=["https://specialist.example"]),
        ):
            domains = _discover_competitor_domains(project, ["dental pro 7 reviews"])

        self.assertEqual(domains, ["https://specialist.example", "https://dentalpro7reviews.com"])

    def test_exact_seed_serp_does_not_force_general_competitors(self):
        project = SimpleNamespace(
            own_domain="https://dentalpro7.reviews",
            domain="https://dentalpro7.reviews",
            search_locale="us",
            audit_summary="A product review website",
        )
        results = [
            {
                "url": f"https://review-{index}.example/product-page",
                "title": f"Independent product review {index}",
                "snippet": "Product ingredients, effectiveness, and customer feedback",
            }
            for index in range(1, 5)
        ]
        with (
            patch("scraping.apify_client_module.is_apify_configured", return_value=True),
            patch("scraping.apify_client_module.search_google_via_apify", return_value=results),
            patch("workers.pipeline._llm_filter_competitor_domains", return_value=[]),
        ):
            domains = _discover_competitor_domains(project, ["dental pro 7 reviews"])

        self.assertEqual(domains, [])

    def test_exact_seed_ranking_page_survives_over_strict_site_judge(self):
        project = SimpleNamespace(
            own_domain="https://linearextrapolationcalculator.com",
            domain="https://linearextrapolationcalculator.com",
            search_locale="us",
            audit_summary="A focused linear extrapolation calculator",
        )
        results = [{
            "url": "https://specialist.example/tools/linear-extrapolation-calculator",
            "title": "Linear Extrapolation Calculator",
            "snippet": "Calculate extrapolated linear values online",
        }]
        with (
            patch("scraping.apify_client_module.is_apify_configured", return_value=True),
            patch("scraping.apify_client_module.search_google_via_apify", return_value=results),
            patch("workers.pipeline._llm_filter_competitor_domains", return_value=[]),
        ):
            domains = _discover_competitor_domains(project, ["linear extrapolation calculator"])

        self.assertEqual(domains, ["https://specialist.example"])

    def test_competitor_discovery_preserves_exact_ranking_urls(self):
        project = SimpleNamespace(
            own_domain="https://own.example",
            domain="https://own.example",
            search_locale="us",
            audit_summary="A focused circuit calculator",
        )
        ranking_urls = {}
        result_url = "https://competitor.example/calculator"
        with (
            patch("scraping.apify_client_module.is_apify_configured", return_value=True),
            patch("scraping.apify_client_module.search_google_via_apify", return_value=[{
                "url": result_url,
                "title": "Circuit Calculator",
                "snippet": "Calculate a circuit",
            }]),
            patch("workers.pipeline._llm_filter_competitor_domains", return_value=["https://competitor.example"]),
        ):
            domains = _discover_competitor_domains(
                project, ["circuit calculator"], ranking_urls_out=ranking_urls,
            )

        self.assertEqual(domains, ["https://competitor.example"])
        self.assertEqual(ranking_urls, {"https://competitor.example": [result_url]})

    def test_competitor_judge_cannot_add_an_unobserved_domain(self):
        candidates = [{
            "domain": "https://observed.example",
            "queries": ["lunar age calculator"],
            "sources": ["apify_page_1"],
        }]
        with (
            patch("nlp.openrouter.is_ai_configured", return_value=True),
            patch("nlp.openrouter.judge_competitor_domains", return_value=[
                {"domain": "https://invented.example"},
                {"domain": "https://observed.example"},
            ]),
        ):
            result = _llm_filter_competitor_domains(
                ["lunar age calculator"], "https://own.example", candidates, 10,
            )
        self.assertEqual(result, ["https://observed.example"])

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

    def test_entity_plus_tool_seed_accepts_close_provider_variations(self):
        self.assertTrue(_keyword_matches_topic(
            "calculate north and south moon nodes",
            ["moon nodes calculator"],
            {"moon", "nodes"},
            set(),
        ))
        self.assertFalse(_keyword_matches_topic(
            "moon phase calendar",
            ["moon nodes calculator"],
            {"moon", "nodes"},
            set(),
        ))

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

    def test_close_variations_of_every_verified_seed_are_kept(self):
        seeds = ["lunar age calculator", "chinese lunar age", "korean lunar age"]
        topic_terms = {"__anchor__lunar", "__scope__age", "__scope__calendar"}

        self.assertTrue(_keyword_matches_topic(
            "chinese age system explained", seeds, topic_terms, set(),
        ))
        self.assertTrue(_keyword_matches_topic(
            "korean age counting method", seeds, topic_terms, set(),
        ))
        self.assertFalse(_keyword_matches_topic(
            "dog age counting method", seeds, topic_terms, set(),
        ))

    def test_audit_hard_boundaries_survive_ai_term_failure(self):
        audit = json.dumps({
            "primary_keyword": "lunar age calculator",
            "core_action": "convert a birth date into lunar age",
            "capabilities": ["compare lunar and solar ages"],
            "hard_boundaries": [
                "does not provide astrological readings",
                "does not track planets or moon phases",
            ],
        })
        with patch(
            "nlp.openrouter.generate_core_domain_terms",
            new=AsyncMock(side_effect=RuntimeError("provider unavailable")),
        ):
            _topic_terms, negative_terms = _semantic_terms(
                ["lunar age calculator"], audit,
            )

        self.assertTrue({"astrological", "reading", "planet", "phase"} & negative_terms)
        self.assertNotIn("lunar", negative_terms)
        self.assertNotIn("solar", negative_terms)

    def test_emd_seed_is_promoted_to_primary_topic_boundary(self):
        self.assertEqual(
            _order_seeds_by_emd(
                ["moon calendar guide", "lunar age calculator", "chinese age systems"],
                "https://lunaragecalculator.com",
            )[0],
            "lunar age calculator",
        )

    def test_brand_domain_keeps_audited_main_topic_ahead_of_trivia_pages(self):
        seeds = _scan_seed_keywords(['wolf trivia quiz', 'owl trivia quiz'], 'https://animalsoulquiz.com',
                                   json.dumps({'primary_keyword': 'spirit animal quiz'}))
        self.assertEqual(seeds[0], 'spirit animal quiz')

    def test_competitor_research_retains_useful_query_depth_with_real_quotes(self):
        animals = ['wolf', 'owl', 'bear', 'eagle', 'fox', 'deer', 'lion', 'butterfly']
        pages = [{"id": str(uuid.uuid4()), "url": f'https://competitor.example/{animal}',
                  "heading": f'{animal} spirit animal',
                  "text": f'The {animal} spirit animal represents personality traits, strengths and growth areas.'}
                 for animal in animals]
        def response(**kwargs):
            # Follow the same six-page batching contract as the real provider.
            page_batch = json.loads(kwargs['user_prompt'].split('Pages: ', 1)[1].split('\nExtract up to', 1)[0])
            return {'keywords': [
                {'phrase': f"{page['heading']} {suffix}", 'page_id': page['id'],
                 'source_quote': page['text'], 'type': 'long-tail'}
                for page in page_batch for suffix in ('meaning', 'personality traits', 'strengths')
            ]}
        with patch('nlp.openrouter.is_ai_configured', return_value=True), patch(
            'nlp.openrouter._chat_json', side_effect=response,
        ) as chat:
            result = research_keyword_queries_from_pages(['spirit animal quiz'], pages, 'Spirit animal profiles')
        self.assertEqual(len(result), 24)
        self.assertEqual(chat.call_count, 2)
        self.assertTrue(all(item['url_ids'] and item['evidence']['excerpt'] for item in result))

    def test_competitor_research_rejects_invented_quotes_and_unknown_sources(self):
        page = {'id': 'observed', 'url': 'https://competitor.example/wolf',
                'heading': 'Wolf spirit animal', 'text': 'Wolves represent loyalty and intelligence.'}
        payload = {'keywords': [
            {'phrase': 'wolf spirit animal meaning', 'page_id': 'invented', 'source_quote': page['text']},
            {'phrase': 'wolf spirit animal traits', 'page_id': 'observed', 'source_quote': 'Invented text about wolves'},
            {'phrase': 'dog food delivery', 'page_id': 'observed', 'source_quote': page['text']},
        ]}
        with patch('nlp.openrouter.is_ai_configured', return_value=True), patch(
            'nlp.openrouter._chat_json', return_value=payload,
        ):
            self.assertEqual(research_keyword_queries_from_pages(['spirit animal quiz'], [page], ''), [])

    def test_ai_quality_review_can_reject_existing_trivia_even_when_it_is_a_seed(self):
        candidate = {'phrase': 'wolf trivia quiz', 'type': 'primary',
                     'support_source': 'seed', 'support_phrase': 'wolf trivia quiz'}
        with patch('nlp.openrouter.is_ai_configured', return_value=True), patch(
            'nlp.openrouter._chat_json', side_effect=[[candidate], []],
        ) as chat:
            result = generate_ai_keywords_sync(['spirit animal quiz', 'wolf trivia quiz'],
                audit_summary='OWN SITE COVERAGE: Wolf Trivia Quiz already exists. Primary purpose: spirit animal profiles.',
                apply_gap_filter=True)
        self.assertEqual(result, [])
        self.assertEqual(chat.call_count, 2)

    def test_emd_entity_fence_rejects_homonyms_and_broad_niche_terms(self):
        self.assertTrue(keyword_matches_emd_entity("chinese lunar age", "lunar age calculator"))
        self.assertTrue(keyword_matches_emd_entity("north node meaning", "moon nodes calculator"))
        self.assertTrue(keyword_matches_emd_entity("dental pro ingredients", "dental pro 7 reviews"))
        self.assertFalse(keyword_matches_emd_entity("lunar client", "lunar age calculator"))
        self.assertFalse(keyword_matches_emd_entity("dental implants", "dental pro 7 reviews"))
        self.assertTrue(has_external_platform_modifier(
            "dental pro 7 reviews reddit", "dental pro 7 reviews",
        ))
        self.assertTrue(has_unrelated_leading_entity(
            "call nature dental pro 7 reviews", "dental pro 7 reviews",
        ))
        self.assertFalse(has_unrelated_leading_entity(
            "best dental pro 7 reviews", "dental pro 7 reviews",
        ))

    def test_provider_keywords_cannot_pass_with_external_platform_or_prefixed_company(self):
        topic_terms = {"dental", "pro", "reviews", "ingredients"}
        seeds = ["dental pro 7 reviews"]
        self.assertFalse(_keyword_matches_topic(
            "dental pro 7 reviews reddit", seeds, topic_terms, set(),
        ))
        self.assertFalse(_keyword_matches_topic(
            "call nature dental pro 7 reviews", seeds, topic_terms, set(),
        ))
        self.assertTrue(_keyword_matches_topic(
            "dental pro 7 ingredients", seeds, topic_terms, set(),
        ))

    def test_scan_seeds_cannot_redefine_the_emd_topic(self):
        seeds = _scan_seed_keywords(
            ["lunar client", "chinese lunar age", "lunar age calculator", "advent calendar"],
            "https://lunaragecalculator.com",
            json.dumps({"primary_keyword": "lunar age calculator"}),
        )

        self.assertEqual(seeds[0], "lunar age calculator")
        self.assertIn("chinese lunar age", seeds)
        self.assertNotIn("lunar client", seeds)
        self.assertNotIn("advent calendar", seeds)

    def test_source_domain_brands_are_removed_before_gap_ai(self):
        primary = "dental pro 7 reviews"
        self.assertTrue(_phrase_mentions_unrelated_source_brand(
            "call nature dental pro 7 reviews", ["https://callnature.com"], primary,
        ))
        self.assertTrue(_phrase_mentions_unrelated_source_brand(
            "amd dental clinic", ["https://amddentalclinic.com"], primary,
        ))
        self.assertFalse(_phrase_mentions_unrelated_source_brand(
            "dental pro 7 ingredients", ["https://dentalpro7ingredients.com"], primary,
        ))
        self.assertFalse(_phrase_mentions_unrelated_source_brand(
            "dental pro 7 vs oramd", ["https://oramd.com"], primary,
        ))

    def test_gap_ai_cannot_rewrite_a_relevant_source_into_an_unrelated_homonym(self):
        refined = _build_ai_refined_accumulator(
            {
                "lunar age guide": {
                    "count": 1,
                    "url_ids": {uuid.uuid4()},
                },
            },
            [{
                "source_phrase": "lunar age guide",
                "phrase": "lunar client",
                "type": "primary",
            }],
            ["lunar age calculator"],
            {"lunar", "age", "client"},
            set(),
        )

        self.assertEqual(refined, {})

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

    def test_discover_content_urls_keeps_exact_serp_page_without_blog_path(self):
        ranking_url = "https://example.com/calculator"
        urls = _discover_content_urls(
            "https://example.com",
            patterns=[r"/blog/"],
            extract_all_urls_from_domain=lambda *args, **kwargs: ["https://example.com/"],
            filter_blog_urls=lambda urls, **kwargs: [],
            limit=2,
            required_terms={"calculator"},
            ranking_terms={"calculator"},
            negative_terms=set(),
            source_type="competitor",
            ranking_urls=[ranking_url],
        )

        self.assertEqual(urls, [ranking_url])

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
        self.assertEqual(results[0]["evidence"]["excerpt"], "page one text")
        self.assertEqual(results[0]["evidence"]["heading"], "Circuit Diagram Tool")

    def test_extraction_includes_bounded_evidence_near_the_keyword(self):
        page = SimpleNamespace(id=uuid.uuid4(), url='https://example.com/circuit',
                               h1='Circuit design', scraped_text=('Navigation ' * 100) +
                               'Circuit diagram tool helps draw accurate schematics. ' + ('Footer ' * 100))
        keywords = SimpleNamespace(primary=[('circuit diagram tool', 1)], lsi=[], entities=[], heading_keywords=[])
        with patch('nlp.keywords.extract_keywords_from_page', return_value=keywords):
            results = extract_keywords_from_urls_ai(['circuit diagram'], [page])
        evidence = next(item['evidence'] for item in results if item['phrase'] == 'circuit diagram tool')
        self.assertIn('helps draw accurate schematics', evidence['excerpt'])
        self.assertLessEqual(len(evidence['excerpt']), 480)
        self.assertEqual(evidence['url'], page.url)

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
