from unittest import TestCase
from unittest.mock import MagicMock, patch
from datetime import timedelta
from pydantic import BaseModel, Field

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import Base
from app.models import Keyword, Project, User
from scraping.apify_client_module import (
    apify_account_status,
    research_keywords_via_apify,
    search_google_via_apify,
)
from workers.pipeline import _process_apify_keywords


class ApifyClientTests(TestCase):
    def test_v3_actor_timeouts_and_typed_response_support_flat_results(self):
        class Run(BaseModel):
            status: str
            default_dataset_id: str = Field(alias='defaultDatasetId')
        class Actor:
            def call(self, *, run_input, run_timeout, wait_duration):
                self.run_timeout, self.wait_duration = run_timeout, wait_duration
                return Run(status='SUCCEEDED', defaultDatasetId='dataset-v3')
        actor = Actor()
        client = MagicMock()
        client.actor.return_value = actor
        client.dataset.return_value.iterate_items.return_value = iter([
            {'url': 'https://specialist.example/', 'title': 'Lunar Age Calculator', 'description': 'Calculate lunar age'},
        ])
        with patch('scraping.apify_client_module.is_apify_configured', return_value=True), patch(
            'scraping.apify_client_module._get_client', return_value=client,
        ):
            results = search_google_via_apify('lunar age calculator', max_results=10)
        self.assertEqual(actor.run_timeout, timedelta(seconds=90))
        self.assertEqual(actor.wait_duration, timedelta(seconds=100))
        client.dataset.assert_called_once_with('dataset-v3')
        self.assertEqual(results[0]['url'], 'https://specialist.example/')
        self.assertEqual(results[0]['snippet'], 'Calculate lunar age')

    def test_v3_account_models_and_paid_plan_actor_failures_are_reported(self):
        class User(BaseModel):
            id: str
            plan: dict
        class Run(BaseModel):
            default_dataset_id: str = Field(alias='defaultDatasetId')
        client = MagicMock()
        client.user.return_value.get.return_value = User(id='test-user', plan={'tier': 'PAID'})
        client.actor.return_value.runs.return_value.list.return_value.items = [Run(defaultDatasetId='failed-dataset')]
        client.dataset.return_value.iterate_items.return_value = iter([{'error': 'Actor quota reached'}])
        with patch('scraping.apify_client_module.is_apify_configured', return_value=True), patch(
            'scraping.apify_client_module._get_client', return_value=client,
        ):
            status = apify_account_status(force=True)
        self.assertTrue(status['authenticated'])
        self.assertFalse(status['available'])
        self.assertIn('Actor quota reached', status['message'])

    def test_account_status_validates_token_without_running_an_actor(self):
        client = MagicMock()
        client.user.return_value.get.return_value = {"id": "user-1"}
        client.actor.return_value.runs.return_value.list.return_value.items = []
        with (
            patch("scraping.apify_client_module.is_apify_configured", return_value=True),
            patch("scraping.apify_client_module._get_client", return_value=client),
        ):
            status = apify_account_status(force=True)

        self.assertTrue(status["authenticated"])
        client.actor.return_value.call.assert_not_called()
        client.actor.return_value.start.assert_not_called()

    def test_common_apify_environment_aliases_are_accepted(self):
        configured = Settings(
            _env_file=None,
            APIFY_API_TOKEN="",
            APIFY_API_KEY="alternate-token",
        )
        self.assertEqual(configured.APIFY_API_TOKEN, "alternate-token")

    def test_search_uses_current_apify_client_timeout_arguments(self):
        actor = MagicMock()
        actor.call.return_value = {
            "status": "SUCCEEDED",
            "defaultDatasetId": "dataset-1",
        }
        dataset = MagicMock()
        dataset.iterate_items.return_value = iter([{
            "results": [{
                "position": 1,
                "url": "https://competitor.example/tool",
                "title": "Moon Nodes Calculator",
                "description": "Calculate moon nodes",
            }],
            "next_page": 2,
            "next_start": 10,
        }])
        client = MagicMock()
        client.actor.return_value = actor
        client.dataset.return_value = dataset

        with (
            patch("scraping.apify_client_module.is_apify_configured", return_value=True),
            patch("scraping.apify_client_module._get_client", return_value=client),
        ):
            results = search_google_via_apify("moon nodes calculator", max_results=30)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://competitor.example/tool")
        self.assertEqual(actor.call.call_count, 3)
        first_call_kwargs = actor.call.call_args_list[0].kwargs
        self.assertEqual(first_call_kwargs["timeout_secs"], 90)
        self.assertEqual(first_call_kwargs["wait_secs"], 100)
        client.actor.assert_called_with("563JCPLOqM1kMmbbP")
        # Verify input format uses 'keyword' not 'queries'
        first_call_input = actor.call.call_args_list[0].kwargs["run_input"]
        self.assertIn("keyword", first_call_input)
        self.assertNotIn("queries", first_call_input)

    def test_search_reports_actor_error_rows_and_stops_pagination(self):
        actor = MagicMock()
        actor.call.return_value = {
            "status": "SUCCEEDED",
            "defaultDatasetId": "dataset-1",
        }
        dataset = MagicMock()
        dataset.iterate_items.return_value = iter([{
            "keyword": "moon nodes calculator",
            "error": "Free tier limit reached (100 searches). An Apify paid plan is required to continue.",
        }])
        client = MagicMock()
        client.actor.return_value = actor
        client.dataset.return_value = dataset
        diagnostics = []

        with (
            patch("scraping.apify_client_module.is_apify_configured", return_value=True),
            patch("scraping.apify_client_module._get_client", return_value=client),
        ):
            results = search_google_via_apify(
                "moon nodes calculator", max_results=30, diagnostics=diagnostics,
            )

        self.assertEqual(results, [])
        self.assertEqual(actor.call.call_count, 1)
        self.assertIn("Free tier limit reached", diagnostics[0])

    def test_account_status_exposes_latest_free_plan_actor_error(self):
        client = MagicMock()
        client.user.return_value.get.return_value = {
            "id": "user-1",
            "plan": {"tier": "FREE"},
        }
        client.actor.return_value.runs.return_value.list.return_value.items = [{
            "defaultDatasetId": "dataset-1",
        }]
        client.dataset.return_value.iterate_items.return_value = iter([{
            "error": "Free tier limit reached (100 searches).",
        }])
        with (
            patch("scraping.apify_client_module.is_apify_configured", return_value=True),
            patch("scraping.apify_client_module._get_client", return_value=client),
        ):
            status = apify_account_status(force=True)

        self.assertTrue(status["authenticated"])
        self.assertFalse(status["available"])
        self.assertIn("Free tier limit reached", status["message"])

    def test_keyword_research_runs_every_seed_and_merges_duplicates(self):
        actor = MagicMock()
        actor.call.side_effect = [
            {"status": "SUCCEEDED", "defaultDatasetId": "dataset-1"},
            {"status": "SUCCEEDED", "defaultDatasetId": "dataset-2"},
        ]
        first_dataset = MagicMock()
        first_dataset.iterate_items.return_value = iter([
            {"keyword": "shared keyword idea", "volume": 100, "sd": 22, "intent": "informational"},
        ])
        second_dataset = MagicMock()
        second_dataset.iterate_items.return_value = iter([
            {"keyword": "shared keyword idea", "volume": 250, "sd": 18, "intent": "commercial"},
            {"keyword": "second seed idea", "volume": 80, "sd": 12},
        ])
        client = MagicMock()
        client.actor.return_value = actor
        client.dataset.side_effect = [first_dataset, second_dataset]

        with (
            patch("scraping.apify_client_module.is_apify_configured", return_value=True),
            patch("scraping.apify_client_module._get_client", return_value=client),
        ):
            results = research_keywords_via_apify(
                ["first seed", "second seed"],
                country_code="US",
                max_results_per_seed=30,
            )

        self.assertEqual(actor.call.call_count, 2)
        self.assertEqual([call.kwargs["run_input"]["keyword"] for call in actor.call.call_args_list], ["first seed", "second seed"])
        shared = next(item for item in results if item["phrase"] == "shared keyword idea")
        self.assertEqual(shared["search_volume"], 250)
        self.assertEqual(shared["seed_keywords"], ["first seed", "second seed"])
        client.actor.assert_called_with("qt4rCkNegFVRVWugm")

    def test_pipeline_stores_relevant_apify_metrics_and_intent(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        sessions = sessionmaker(engine, expire_on_commit=False)
        with sessions() as db:
            user = User(email="apify-test@example.com")
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

            researched = [
                {
                    "phrase": "lunar age calculator by birth date",
                    "search_volume": 880,
                    "difficulty": 18.0,
                    "cpc": 1.25,
                    "intent": "commercial",
                    "seed_keywords": ["lunar age calculator"],
                },
                {
                    "phrase": "dog age calculator",
                    "search_volume": 50000,
                    "difficulty": 60.0,
                    "seed_keywords": ["lunar age calculator"],
                },
            ]
            with (
                patch("scraping.apify_client_module.is_apify_configured", return_value=True),
                patch("scraping.apify_client_module.research_keywords_via_apify", return_value=researched),
            ):
                count = _process_apify_keywords(
                    db,
                    project.id,
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
            self.assertEqual(rows[0].seo_recommendation, "Search intent: commercial; CPC: $1.25")
        engine.dispose()
