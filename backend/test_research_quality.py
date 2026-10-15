"""Research quantity must come from broader evidence, not lowered quality gates."""
import asyncio
import json
import unittest
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from app.database import Base
from app.models import Keyword, Project, ScanJob, Url, User
from nlp.research_quality import balanced_pages, focused_review_context, research_excerpt, review_candidates
from nlp.openrouter import _keyword_generation_support_is_valid, generate_ai_keywords, generate_ai_keywords_sync
from nlp.keywords import is_publishable_keyword
from scraping.autocomplete import research_autocomplete
from workers.pipeline import (_discover_content_urls, _own_content_keyword_phrases,
                              _process_autocomplete_keywords, _queue_url, _remove_covered_keywords,
                              _review_provider_keywords, _store_owned_inventory)


def decision(item, keep=True):
    return {"source_phrase": item["phrase"], "phrase": item["phrase"], "decision": "keep" if keep else "reject",
            "reason": "Supported reader question" if keep else "Unrelated intent", "type": "long-tail"}


def pending_from_prompt(kwargs):
    return json.loads(kwargs["user_prompt"].split("Candidates: ", 1)[1].split("\n\nRules:", 1)[0])


class ResearchQualityTests(unittest.TestCase):
    def test_large_inventory_reviews_every_keyword_in_bounded_batches(self):
        rows = [{"phrase": f"{animal} personality {aspect}", "evidence": {"excerpt": f"{animal} traits"}}
                for animal in ("wolf", "owl", "bear", "fox", "eagle", "deer", "lion")
                for aspect in ("traits", "strengths", "weaknesses", "compatibility", "meaning", "symbolism", "relationships", "leadership", "communication", "habits")]
        calls = []
        def chat(**kwargs):
            batch = pending_from_prompt(kwargs)
            calls.append(batch)
            return {"decisions": [decision(row) for row in batch]}
        stats = {}
        result = review_candidates(["spirit animal quiz"], rows, "Animal personality profiles", 100, chat, stats)
        self.assertEqual([len(batch) for batch in calls], [25, 25, 20])
        self.assertEqual(len(result), 70)
        self.assertEqual(stats["reviewed"], 70)
        self.assertEqual(stats["unreviewed"], 0)
        self.assertEqual(result[-1]["evidence"], rows[-1]["evidence"])

    def test_omitted_decisions_are_retried_without_repeating_approved_keywords(self):
        rows = [{"phrase": "wolf personality traits"}, {"phrase": "owl personality traits"}, {"phrase": "fox food guide"}]
        calls = []
        def chat(**kwargs):
            batch = pending_from_prompt(kwargs)
            calls.append(batch)
            return {"decisions": [decision(rows[0])]} if len(calls) == 1 else {"decisions": [decision(rows[1]), decision(rows[2], False)]}
        stats = {}
        result = review_candidates(["spirit animal quiz"], rows, "Animal profiles", 50, chat, stats)
        self.assertEqual([row["phrase"] for row in calls[1]], [row["phrase"] for row in rows[1:]])
        self.assertEqual(len(result), 2)
        self.assertEqual(stats["rejected"], 1)
        self.assertEqual(stats["reviewed"], 3)

    def test_missing_or_conflicting_decisions_never_approve_unreviewed_rows(self):
        rows = [{"phrase": "wolf personality traits"}]
        for payload in ({"decisions": []}, {"decisions": [decision(rows[0]), decision(rows[0], False)]}):
            chat = MagicMock(return_value=payload)
            stats = {}
            self.assertIsNone(review_candidates(["animal quiz"], rows, "", 10, chat, stats))
            self.assertEqual(chat.call_count, 2)
            self.assertEqual(stats["unreviewed"], 1)
            self.assertEqual(stats["rejected"], 0)

    def test_provider_volume_cannot_be_attached_to_a_rewritten_phrase(self):
        row = {"phrase": "wolf personality traits", "search_volume": 0, "difficulty": 0}
        changed = {**decision(row), "phrase": "wolf personality strengths"}
        self.assertIsNone(review_candidates(["animal quiz"], [row], "", 10, MagicMock(return_value={"decisions": [changed]})))
        result = review_candidates(["animal quiz"], [row], "", 10, MagicMock(return_value={"decisions": [decision(row)]}))
        self.assertEqual(result[0]["search_volume"], 0)
        self.assertEqual(result[0]["difficulty"], 0)

    def test_literal_audit_evidence_is_required_not_two_overlapping_words(self):
        self.assertFalse(_keyword_generation_support_is_valid(
            {"support_source": "audit", "support_phrase": "lunar age premium subscription"},
            ["lunar age calculator"], [], json.dumps({"capabilities": ["calculate lunar age"]})))

    def test_sync_and_async_generation_keep_evidence_for_the_quality_reviewer(self):
        item = {"phrase": "wolf personality traits", "type": "long-tail", "support_source": "audit", "support_phrase": "wolf personality profiles"}
        for asynchronous in (False, True):
            with self.subTest(asynchronous=asynchronous):
                with patch("nlp.openrouter.is_ai_configured", return_value=True), patch(
                    "nlp.openrouter._achat_json" if asynchronous else "nlp.openrouter._chat_json", return_value=[item],
                ), patch("nlp.openrouter.filter_keyword_gap_recommendations", side_effect=lambda seeds, rows, **kw: rows) as review:
                    kwargs = {"audit_summary": json.dumps({"capabilities": ["wolf personality profiles"]}),
                              "topic_terms": {"__related__wolf|personality"}}
                    result = asyncio.run(generate_ai_keywords(["spirit animal quiz"], **kwargs)) if asynchronous else generate_ai_keywords_sync(["spirit animal quiz"], **kwargs)
                self.assertEqual(result[0]["support_phrase"], item["support_phrase"])
                self.assertEqual(review.call_args.args[1][0]["evidence"]["excerpt"], item["support_phrase"])

    def test_balanced_research_uses_later_domains_and_later_content(self):
        pages = [{"url": f"https://{domain}.example/{index}", "text": "text"}
                 for domain in ("alpha", "beta", "gamma", "delta") for index in range(12)]
        selected = balanced_pages(pages, limit=8, per_domain=6)
        self.assertEqual([page["url"] for page in selected[:4]], [f"https://{domain}.example/0" for domain in ("alpha", "beta", "gamma", "delta")])
        excerpt = research_excerpt("intro " * 1500 + "Wolf personality strengths and communication styles.", limit=1500)
        self.assertIn("Wolf personality strengths", excerpt)
        self.assertLessEqual(len(excerpt), 1500)
        self.assertIn("excerpt break", excerpt)

    def test_complete_long_question_is_not_a_fragment(self):
        self.assertTrue(is_publishable_keyword("how can i find my spirit animal using my birthday"))
        self.assertFalse(is_publishable_keyword("how can i find my spirit animal using my birthday and"))

    def test_heading_extraction_does_not_join_words_across_removed_stopwords(self):
        from nlp.keywords import extract_heading_keywords
        phrases = extract_heading_keywords("What can a wolf teach us about leadership", [], [])
        self.assertIn("what can a wolf teach us about leadership", phrases)
        self.assertNotIn("wolf teach leadership", phrases)
        self.assertNotIn("wolf leadership", phrases)

    def test_review_context_prioritizes_relevant_late_owned_pages_and_keeps_boundaries(self):
        pages = [{"url": f"https://example.com/topic-{i}", "heading": "Other profile", "text": "Other subject"} for i in range(200)]
        wolf = {"url": "https://example.com/wolf", "heading": "Wolf Personality Traits", "text": "Wolf profile"}
        context = {"OWN SITE COVERAGE": [*pages, wolf], "OWN PAGE INVENTORY": [page["url"] for page in [*pages, wolf]],
                   "hard_boundaries": ["No unrelated wildlife services"]}
        focused = json.loads(focused_review_context(json.dumps(context), [{"phrase": "wolf personality traits"}]))
        self.assertEqual(focused["OWN SITE COVERAGE"][0], wolf)
        self.assertEqual(len(focused["OWN SITE COVERAGE"]), 8)
        self.assertEqual(len(focused["OWN PAGE INVENTORY"]), 120)
        self.assertEqual(focused["hard_boundaries"], context["hard_boundaries"])

    def test_own_coverage_preserves_direction_and_negation(self):
        accumulator = {phrase: {} for phrase in ("usd to eur", "eur to usd", "calculate lunar age without birth time")}
        _remove_covered_keywords(accumulator, {"usd to eur", "calculate lunar age with birth time"})
        self.assertEqual(set(accumulator), {"eur to usd", "calculate lunar age without birth time"})

    def test_own_inventory_is_complete_even_when_scraping_is_bounded(self):
        urls = [f"https://own.example/animals/{animal}" for animal in ("wolf", "owl", "bear", "fox", "eagle", "deer")]
        inventory = []
        found = _discover_content_urls("https://own.example", None, MagicMock(return_value=urls + ["https://outside.example/wolf"]),
                                      MagicMock(), 2, {"spirit"}, source_type="own", include_homepage=True, inventory_out=inventory)
        self.assertEqual(len(found), 2)
        self.assertEqual(set(inventory), {"https://own.example", *urls})


class AutocompleteResearchTests(unittest.TestCase):
    def test_observed_queries_keep_unknown_metrics_and_filter_unrelated_topics(self):
        response = MagicMock(status_code=200)
        response.json.return_value = ["wolf personality traits", ["wolf personality traits in humans", "wolf personality traits minecraft", "owl food"]]
        with patch("scraping.autocomplete.requests.get", return_value=response):
            rows = research_autocomplete(["wolf personality traits"], set(), {"minecraft"})
        self.assertEqual([row["phrase"] for row in rows], ["wolf personality traits in humans"])
        self.assertIsNone(rows[0]["search_volume"])
        self.assertIsNone(rows[0]["difficulty"])
        self.assertEqual(rows[0]["evidence"]["query"], "wolf personality traits")

    def test_throttling_and_mismatched_responses_stop_without_fabricating_results(self):
        for response in (MagicMock(status_code=429), MagicMock(status_code=200)):
            response.json.return_value = ["unrelated query", ["wolf personality traits"]]
            with patch("scraping.autocomplete.requests.get", return_value=response) as request:
                notes = []
                result = research_autocomplete(["wolf personality traits", "owl personality traits"], set(), set(), diagnostics=notes)
            self.assertEqual(result, [])
            request.assert_called_once()
            self.assertTrue(notes)


class ResearchPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = Session(self.engine, expire_on_commit=False)
        self.addCleanup(self.engine.dispose)
        self.addCleanup(self.db.close)
        user = User(email="research@example.com")
        self.db.add(user)
        self.db.flush()
        self.project = Project(user_id=user.id, name="Animals", domain="https://own.example")
        self.db.add(self.project)
        self.db.flush()
        self.job = ScanJob(project_id=self.project.id)
        self.db.add(self.job)
        self.db.commit()

    def test_body_mentions_are_not_complete_coverage_and_inventory_survives(self):
        self.db.add(Url(project_id=self.project.id, url="https://own.example/quiz", source_type="own", status="scraped",
                        h1="Spirit Animal Quiz", scraped_text="You might also explore wolf personality traits or owl symbolism."))
        self.db.commit()
        phrases = _own_content_keyword_phrases(self.db, self.project.id, set(), set())
        self.assertIn("spirit animal quiz", phrases)
        self.assertNotIn("wolf personality traits", phrases)
        urls = ["https://own.example/quiz", "https://own.example/wolf-personality-traits"]
        _store_owned_inventory(self.db, self.project.id, self.job.id, "https://own.example", urls)
        _store_owned_inventory(self.db, self.project.id, self.job.id, "https://own.example", urls)
        rows = self.db.execute(select(Url)).scalars().all()
        self.assertEqual(len(rows), 2)
        self.assertEqual({row.status for row in rows}, {"scraped", "discovered"})
        self.assertIn("wolf personality traits", _own_content_keyword_phrases(self.db, self.project.id, set(), set()))
        _queue_url(self.db, self.project.id, self.job.id, urls[1], "own", "https://own.example")
        self.db.commit()
        self.db.expire_all()
        self.assertEqual(self.db.execute(select(Url.status).where(Url.url == urls[1])).scalar_one(), "pending")

    def test_autocomplete_only_saves_reviewed_observed_queries_with_real_source(self):
        raw = [{"phrase": "wolf personality traits"}, {"phrase": "wolf personality weaknesses"}]
        reviewed = [{**raw[0], "review_reason": "Supported personality question"}, {"phrase": "invented animal page"}]
        with patch("workers.pipeline.settings.ENABLE_AUTOCOMPLETE_RESEARCH", True), patch("nlp.openrouter.is_ai_configured", return_value=True), patch(
            "scraping.autocomplete.research_autocomplete", return_value=raw,
        ), patch("nlp.openrouter.filter_keyword_gap_recommendations", return_value=reviewed):
            count = _process_autocomplete_keywords(self.db, self.project.id, ["spirit animal quiz"], set(), set(), "Animal personality profiles")
        self.assertEqual(count, 1)
        keyword = self.db.execute(select(Keyword)).scalar_one()
        self.assertEqual(keyword.phrase, raw[0]["phrase"])
        self.assertIsNone(keyword.search_volume)
        source = self.db.execute(select(Url)).scalar_one()
        self.assertEqual(source.source_domain, "Google Autocomplete")

    def test_provider_review_cannot_rewrite_or_invent_measured_keywords(self):
        raw = [{"phrase": "wolf personality traits", "search_volume": 50}]
        with patch("nlp.openrouter.is_ai_configured", return_value=True), patch(
            "nlp.openrouter.filter_keyword_gap_recommendations", return_value=[{"phrase": "owl personality traits", "search_volume": 50000}],
        ):
            rows = _review_provider_keywords(self.db, self.project.id, ["spirit animal quiz"], raw, set(), set(), "", "Apify")
        self.assertEqual(rows, [])
