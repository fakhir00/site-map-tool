import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.hub_spoke.router import (
    _basic_clean,
    _clean_with_context,
    _mechanical_relevance_filter,
    delete_hub_spoke_history,
)
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

    def test_mechanical_filter_rejects_an_unrelated_keyword_group(self):
        cleaned = _mechanical_relevance_filter(
            [
                "circuit diagram maker",
                "electronic circuit symbols",
                "circuit drawing software",
                "car insurance quotes",
                "cheap vehicle insurance",
            ],
            "A circuit design tool for electronics students and engineers.",
        )
        self.assertEqual(cleaned, [
            "circuit diagram maker",
            "electronic circuit symbols",
            "circuit drawing software",
        ])

    def test_mechanical_filter_runs_after_ai_selection(self):
        import asyncio

        candidates = ["circuit diagram symbols", "electronic circuit tutorial", "celebrity news today"]
        with (
            patch("app.hub_spoke.router.is_ai_configured", return_value=True),
            patch("app.hub_spoke.router._achat_json", new=AsyncMock(return_value={"keywords": candidates})),
        ):
            cleaned = asyncio.run(_clean_with_context(
                candidates,
                "Circuit diagram software and electronics education.",
            ))
        self.assertEqual(cleaned, ["circuit diagram symbols", "electronic circuit tutorial"])


class HubWorkspaceDeleteTests(unittest.IsolatedAsyncioTestCase):
    async def test_history_delete_is_scoped_to_the_current_user(self):
        db = AsyncMock()
        db.execute.return_value = SimpleNamespace(rowcount=1)
        history_id = uuid.uuid4()
        user_id = uuid.uuid4()

        await delete_hub_spoke_history(history_id, SimpleNamespace(id=user_id), db)

        statement = db.execute.await_args.args[0]
        sql = str(statement)
        self.assertIn("hub_spoke_history.id", sql)
        self.assertIn("hub_spoke_history.user_id", sql)

    async def test_missing_or_unowned_history_returns_not_found(self):
        db = AsyncMock()
        db.execute.return_value = SimpleNamespace(rowcount=0)

        with self.assertRaises(HTTPException) as raised:
            await delete_hub_spoke_history(uuid.uuid4(), SimpleNamespace(id=uuid.uuid4()), db)

        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
