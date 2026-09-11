from unittest import TestCase
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Keyword, Project, User
from nlp.dataforseo import (
    KeywordResearchResult,
    _cache_key,
    _credentials,
    _normalize_items,
    _research_seeds,
    dataforseo_account_status,
    collect_keyword_research,
    search_competitors,
)
from workers.pipeline import _process_dataforseo_keywords


def response_for(keyword, volume=100, difficulty=25, cost=0.01):
    return {
        "status_code": 20000,
        "cost": cost,
        "tasks": [{
            "status_code": 20000,
            "result": [{
                "items": [{
                    "keyword": keyword,
                    "keyword_info": {"search_volume": volume},
                    "keyword_properties": {"keyword_difficulty": difficulty},
                    "search_intent_info": {"main_intent": "informational"},
                }],
            }],
        }],
    }


def wrapped_response_for(keyword):
    """DataForSEO Labs endpoints may wrap metrics in keyword_data."""
    return {
        "tasks": [{
            "result": [{
                "items": [{
                    "keyword_data": {
                        "keyword": keyword,
                        "keyword_info": {"search_volume": 260},
                        "keyword_properties": {"keyword_difficulty": 14},
                        "search_intent_info": {"main_intent": "commercial"},
                    },
                }],
            }],
        }],
    }


class DataForSeoTests(TestCase):
    def test_credentials_never_mix_two_render_account_pairs(self):
        with (
            patch("nlp.dataforseo.settings.DATAFORSEO_LOGIN", "old-login"),
            patch("nlp.dataforseo.settings.DATAFORSEO_PASSWORD", ""),
            patch("nlp.dataforseo.settings.DATAFORSEO_API_LOGIN", "new-login"),
            patch("nlp.dataforseo.settings.DATAFORSEO_API_PASSWORD", "new-password"),
        ):
            self.assertEqual(_credentials(), ("new-login", "new-password"))

    def test_cache_is_isolated_when_dataforseo_account_changes(self):
        with (
            patch("nlp.dataforseo.settings.DATAFORSEO_LOGIN", "first@example.com"),
            patch("nlp.dataforseo.settings.DATAFORSEO_PASSWORD", "password"),
        ):
            first = _cache_key("endpoint", {"keywords": ["lunar age"]})
        with (
            patch("nlp.dataforseo.settings.DATAFORSEO_LOGIN", "second@example.com"),
            patch("nlp.dataforseo.settings.DATAFORSEO_PASSWORD", "password"),
        ):
            second = _cache_key("endpoint", {"keywords": ["lunar age"]})

        self.assertNotEqual(first, second)

    def test_account_status_reports_rejected_credentials_without_exposing_them(self):
        with (
            patch("nlp.dataforseo.requests.get") as request,
            patch("nlp.dataforseo.settings.DATAFORSEO_LOGIN", "account@example.com"),
            patch("nlp.dataforseo.settings.DATAFORSEO_PASSWORD", "secret"),
            patch("nlp.dataforseo._STATUS_CACHE", None),
        ):
            request.return_value.status_code = 401
            status = dataforseo_account_status(force=True)

        self.assertTrue(status["configured"])
        self.assertFalse(status["authenticated"])
        self.assertNotIn("account@example.com", str(status))
        self.assertNotIn("secret", str(status))

    def test_only_exact_gold_hunter_seeds_reach_the_provider(self):
        audit = '''{
          "primary_keyword": "lunar age calculator",
          "content_opportunities": [
            "impact of leap months on age calculation",
            "lunar calendar vs solar calendar differences"
          ],
          "hard_boundaries": ["moon phase tracking"]
        }'''
        seeds = _research_seeds(["lunar age calculator"], audit)

        self.assertEqual(seeds, ["lunar age calculator"])

    def test_normalizes_real_metrics_from_nested_response(self):
        self.assertEqual(_normalize_items(response_for("Lunar Age Calculator")), [{
            "phrase": "lunar age calculator",
            "type": "long-tail",
            "search_volume": 100,
            "difficulty": 25.0,
            "intent": "informational",
            "source": "dataforseo",
        }])

    def test_normalizes_keyword_data_wrapper(self):
        self.assertEqual(_normalize_items(wrapped_response_for("Lunar Calendar Age Tool")), [{
            "phrase": "lunar calendar age tool",
            "type": "long-tail",
            "search_volume": 260,
            "difficulty": 14.0,
            "intent": "commercial",
            "source": "dataforseo",
        }])

    def test_batches_all_seeds_without_importing_domain_ranking_junk(self):
        with (
            patch("nlp.dataforseo.is_dataforseo_configured", return_value=True),
            patch("nlp.dataforseo._cached_response", return_value=None),
            patch("nlp.dataforseo._request", return_value=(response_for("lunar age calculator"), 0.01, False)) as request,
            patch("nlp.dataforseo.settings.DATAFORSEO_MAX_COST_PER_SCAN", 0.08),
            patch("nlp.dataforseo.settings.DATAFORSEO_RESULT_LIMIT", 500),
        ):
            result = collect_keyword_research(
                object(), "example.com", ["lunar age calculator", "calculate lunar age"],
            )

        self.assertEqual(request.call_count, 1)
        first_payload = request.call_args_list[0].args[2]
        self.assertEqual(first_payload["keywords"], ["lunar age calculator", "calculate lunar age"])
        self.assertTrue(first_payload["closely_variants"])
        self.assertEqual(first_payload["limit"], 200)
        self.assertEqual(result.requests, 1)
        self.assertEqual(result.cache_hits, 0)
        self.assertAlmostEqual(result.spent, 0.01)
        self.assertEqual(len(result.keywords), 1)

    def test_pipeline_stores_only_relevant_provider_keywords_and_metrics(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        sessions = sessionmaker(engine, expire_on_commit=False)
        with sessions() as db:
            user = User(email="dfs-test@example.com")
            db.add(user)
            db.flush()
            project = Project(
                user_id=user.id,
                name="Lunar age",
                domain="https://example.com",
                target_keywords=["lunar age calculator"],
            )
            db.add(project)
            db.commit()

            research = KeywordResearchResult([
                {
                    "phrase": "lunar age calculator by birth date",
                    "type": "long-tail",
                    "search_volume": 880,
                    "difficulty": 18.0,
                },
                {
                    "phrase": "dog age calculator",
                    "type": "long-tail",
                    "search_volume": 50000,
                    "difficulty": 60.0,
                },
                {
                    "phrase": "age of planets in the solar system",
                    "type": "long-tail",
                    "search_volume": 30,
                    "difficulty": 26.0,
                },
                {
                    "phrase": "solar system planet position calculator",
                    "type": "long-tail",
                    "search_volume": 10,
                    "difficulty": 12.0,
                },
            ], 0.01, 1, 0)
            with (
                patch("nlp.dataforseo.is_dataforseo_configured", return_value=True),
                patch("nlp.dataforseo.collect_keyword_research", return_value=research),
            ):
                count = _process_dataforseo_keywords(
                    db,
                    project.id,
                    project.domain,
                    ["lunar age calculator"],
                    {"lunar", "age", "calendar"},
                    set(),
                )

            rows = db.execute(select(Keyword)).scalars().all()
            self.assertEqual(count, 1)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].phrase, "lunar age calculator by birth date")
            self.assertEqual(rows[0].search_volume, 880)
            self.assertEqual(rows[0].difficulty, 18.0)
        engine.dispose()

    def test_competitor_serp_extracts_only_organic_results(self):
        response = {
            "tasks": [{"result": [{"items": [
                {"type": "organic", "url": "https://direct.example/tool", "title": "Moon Nodes Calculator", "description": "Calculate moon nodes"},
                {"type": "people_also_ask", "url": "https://noise.example/question"},
            ]}]}],
        }
        with (
            patch("nlp.dataforseo.is_dataforseo_configured", return_value=True),
            patch("nlp.dataforseo._request", return_value=(response, 0.003, False)),
        ):
            results = search_competitors(object(), "moon nodes calculator")

        self.assertEqual(results, [{
            "url": "https://direct.example/tool",
            "title": "Moon Nodes Calculator",
            "snippet": "Calculate moon nodes",
        }])

    def test_provider_task_error_is_returned_for_scan_diagnostics(self):
        with (
            patch("nlp.dataforseo.is_dataforseo_configured", return_value=True),
            patch("nlp.dataforseo._cached_response", return_value=None),
            patch("nlp.dataforseo._request", side_effect=RuntimeError("Please verify your account before using the API.")),
            patch("nlp.dataforseo.settings.DATAFORSEO_MAX_COST_PER_SCAN", 0.08),
        ):
            result = collect_keyword_research(object(), "example.com", ["moon nodes calculator"])

        self.assertEqual(result.keywords, [])
        self.assertEqual(result.errors, ["Please verify your account before using the API."])
