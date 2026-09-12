from unittest import TestCase
from unittest.mock import MagicMock, patch

from app.config import Settings
from scraping.apify_client_module import apify_account_status, search_google_via_apify


class ApifyClientTests(TestCase):
    def test_account_status_validates_token_without_running_an_actor(self):
        client = MagicMock()
        client.user.return_value.get.return_value = {"id": "user-1"}
        with (
            patch("scraping.apify_client_module.is_apify_configured", return_value=True),
            patch("scraping.apify_client_module._get_client", return_value=client),
        ):
            status = apify_account_status(force=True)

        self.assertTrue(status["authenticated"])
        client.actor.assert_not_called()

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
            results = search_google_via_apify("moon nodes calculator", max_results=5)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://competitor.example/tool")
        # Should call the scraperlink actor for 2 pages
        self.assertEqual(actor.call.call_count, 2)
        first_call_kwargs = actor.call.call_args_list[0].kwargs
        self.assertEqual(first_call_kwargs["timeout_secs"], 90)
        self.assertEqual(first_call_kwargs["wait_secs"], 100)
        # Verify the actor name used
        client.actor.assert_called_with("scraperlink/google-search-results-serp-scraper")
        # Verify input format uses 'keyword' not 'queries'
        first_call_input = actor.call.call_args_list[0].kwargs["run_input"]
        self.assertIn("keyword", first_call_input)
        self.assertNotIn("queries", first_call_input)

