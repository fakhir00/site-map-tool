from unittest import TestCase
from unittest.mock import patch

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Keyword, Project, User
from nlp.dataforseo import KeywordResearchResult, _normalize_items, _research_seeds, collect_keyword_research
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
    def test_audit_opportunities_expand_one_anchored_provider_request(self):
        audit = '''{
          "primary_keyword": "lunar age calculator",
          "content_opportunities": [
            "impact of leap months on age calculation",
            "lunar calendar vs solar calendar differences"
          ],
          "hard_boundaries": ["moon phase tracking"]
        }'''
        seeds = _research_seeds(["lunar age calculator"], audit)

        self.assertIn("lunar age calculator impact leap months age calculation", seeds)
        self.assertIn("lunar calendar vs solar calendar differences", seeds)
        self.assertFalse(any("phase" in seed for seed in seeds))

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

    def test_batches_all_seeds_then_collects_domain_with_cache_accounting(self):
        responses = [
            (response_for("lunar age calculator"), 0.01, False),
            (response_for("lunar calendar age"), 0.0, True),
        ]
        with (
            patch("nlp.dataforseo.is_dataforseo_configured", return_value=True),
            patch("nlp.dataforseo._cached_response", return_value=None),
            patch("nlp.dataforseo._request", side_effect=responses) as request,
            patch("nlp.dataforseo.settings.DATAFORSEO_MAX_COST_PER_SCAN", 0.08),
        ):
            result = collect_keyword_research(
                object(), "example.com", ["lunar age calculator", "calculate lunar age"],
            )

        self.assertEqual(request.call_count, 2)
        first_payload = request.call_args_list[0].args[2]
        self.assertEqual(first_payload["keywords"], ["lunar age calculator", "calculate lunar age"])
        self.assertEqual(result.requests, 1)
        self.assertEqual(result.cache_hits, 1)
        self.assertAlmostEqual(result.spent, 0.01)
        self.assertEqual(len(result.keywords), 2)

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
