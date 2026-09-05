from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch
import uuid

from nlp.openrouter import extract_keywords_from_urls_ai, filter_keyword_gap_recommendations
from workers.pipeline import (
    _discover_content_urls,
    _search_result_urls,
    _with_source_url_ids,
)


class PipelineFilterTests(TestCase):
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
