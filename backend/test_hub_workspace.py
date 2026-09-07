import unittest
from unittest.mock import patch

from app.hub_spoke.router import _basic_clean, _clean_with_context
from nlp.openrouter import _validate_hub_and_spoke


class HubWorkspaceTests(unittest.TestCase):
    def test_basic_clean_handles_csv_text_and_duplicates(self):
        self.assertEqual(
            _basic_clean(['Keyword,Volume', '"circuit diagram",100', 'circuit diagram', '###']),
            ['keyword', 'circuit diagram'],
        )

    def test_uploaded_keywords_build_without_ai(self):
        from nlp.openrouter import cluster_hub_and_spoke
        import asyncio

        keywords = [{"phrase": f"circuit diagram topic {index}", "type": "long-tail"} for index in range(100)]
        with patch("nlp.openrouter.is_ai_configured", return_value=False):
            mapping = asyncio.run(cluster_hub_and_spoke(keywords, "circuit diagram"))
        self.assertIsNotNone(mapping)
        self.assertIsNone(_validate_hub_and_spoke(
            mapping,
            len(keywords),
            "circuit diagram",
            {item["phrase"] for item in keywords},
        ))

    def test_context_cleaner_strictly_removes_other_topics_without_ai(self):
        import asyncio

        with patch("app.hub_spoke.router.is_ai_configured", return_value=False):
            cleaned = asyncio.run(_clean_with_context(
                ["circuit diagram symbols", "electronic circuit tutorial", "car insurance quotes", "celebrity news"],
                "Circuit diagram software and electronics education for engineering students.",
            ))
        self.assertEqual(cleaned, ["circuit diagram symbols", "electronic circuit tutorial"])


if __name__ == "__main__":
    unittest.main()
