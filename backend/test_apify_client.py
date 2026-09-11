from unittest import TestCase
from unittest.mock import MagicMock, patch

from app.config import Settings
from scraping.apify_client_module import search_google_via_apify


class ApifyClientTests(TestCase):
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
            "organicResults": [{
                "url": "https://competitor.example/tool",
                "title": "Moon Nodes Calculator",
                "description": "Calculate moon nodes",
            }],
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
        actor.call.assert_called_once()
        kwargs = actor.call.call_args.kwargs
        self.assertEqual(kwargs["timeout_secs"], 90)
        self.assertEqual(kwargs["wait_secs"], 100)
        self.assertNotIn("run_timeout", kwargs)
        self.assertNotIn("wait_duration", kwargs)
