import asyncio
import json
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.hub_spoke.router import (
    KeywordMetricInput,
    KeywordWorkspaceRequest,
    _basic_clean,
    _context_with_seed_keywords,
    _hub_spoke_context,
    _keyword_records,
    delete_hub_spoke_history,
)
from nlp.hub_spoke_agent import build_site_architecture, normalize_keyword_records, validate_architecture


def specialist_payload() -> dict:
    return {
        "site_strategy": "Build one tool hub and a separate educational spoke.",
        "master_hub": {
            "article_title": "Circuit Diagram Maker",
            "target_keyword": "circuit diagram maker",
            "search_intent": "create a circuit diagram online",
            "ranking_role": "master_hub",
            "page_type": "tool",
            "content_brief": "Let users create circuit diagrams.",
            "h2_sections": [], "faq_schema_questions": [], "entity_terms": [],
            "internal_links": ["circuit diagram symbols"], "tool_functions": ["diagram editor"],
        },
        "spokes": [{
            "spoke_category": "Reference guides",
            "article_title": "Circuit Diagram Symbols",
            "target_keyword": "circuit diagram symbols",
            "search_intent": "identify circuit diagram symbols",
            "ranking_role": "supporting_spoke",
            "page_type": "article",
            "content_brief": "Explain common symbols.",
            "h2_sections": [], "faq_schema_questions": [], "entity_terms": [],
            "internal_links": ["circuit diagram maker"], "tool_functions": [],
        }],
        "keyword_assignments": [
            {"keyword": "circuit diagram maker", "disposition": "page_target", "assigned_to": "circuit diagram maker", "placement": "title", "reason": "Central creation intent."},
            {"keyword": "circuit diagram online", "disposition": "supporting", "assigned_to": "circuit diagram maker", "placement": "feature", "reason": "Same creation intent."},
            {"keyword": "circuit diagram symbols", "disposition": "page_target", "assigned_to": "circuit diagram symbols", "placement": "title", "reason": "Distinct reference intent."},
            {"keyword": "celebrity news", "disposition": "discard", "assigned_to": None, "placement": None, "reason": "Outside the electronics site scope."},
        ],
        "interlinking_strategy": "The reference spoke links to the creation tool and the hub links back.",
    }


class HubWorkspaceTests(unittest.TestCase):
    def test_keyword_metrics_survive_input_hygiene(self):
        body = KeywordWorkspaceRequest(
            keywords=["lunar age", "lunar age calculator"],
            keyword_data=[
                KeywordMetricInput(phrase="lunar age", search_volume=12000, difficulty=76),
                KeywordMetricInput(phrase="lunar age calculator", search_volume=900, difficulty=18),
            ],
        )
        records = _keyword_records(body)
        lookup = {item["phrase"]: item for item in records}
        self.assertEqual(lookup["lunar age calculator"]["search_volume"], 900)
        self.assertEqual(lookup["lunar age calculator"]["difficulty"], 18)

    def test_competitor_profile_is_removed_from_site_context(self):
        context = _hub_spoke_context(json.dumps({
            "primary_keyword": "lunar age calculator",
            "competitor_profile": "broad astronomy sites",
            "hard_boundaries": ["moon phase tracking"],
        }))
        parsed = json.loads(context)
        self.assertNotIn("competitor_profile", parsed)
        self.assertEqual(parsed["primary_keyword"], "lunar age calculator")

    def test_basic_clean_only_normalizes_and_deduplicates(self):
        self.assertEqual(
            _basic_clean(['Keyword,Volume', '"circuit diagram",100', 'circuit diagram', '###']),
            ['keyword', 'circuit diagram'],
        )

    def test_specialist_accounts_for_every_keyword_and_exposes_discards(self):
        records = normalize_keyword_records([
            {"phrase": "circuit diagram maker"},
            {"phrase": "circuit diagram online"},
            {"phrase": "circuit diagram symbols"},
            {"phrase": "celebrity news"},
        ])
        with (
            patch("nlp.hub_spoke_agent.is_ai_configured", return_value=True),
            patch(
                "nlp.hub_spoke_agent._achat_json",
                new=AsyncMock(side_effect=[specialist_payload(), {"passed": True, "conflicts": []}]),
            ),
        ):
            mapping = asyncio.run(build_site_architecture(
                records, context="Electronics design website", primary_keyword="circuit diagram maker",
            ))
        self.assertEqual(validate_architecture(mapping, records), [])
        self.assertEqual(mapping["filtered_irrelevant_keywords"], ["celebrity news"])
        self.assertIn("circuit diagram online", mapping["master_hub"]["targeted_keywords"])
        self.assertEqual(len(mapping["hubs"][0]["layers"]["Reference guides"]), 1)

    def test_duplicate_intents_are_rejected(self):
        records = normalize_keyword_records([
            {"phrase": "circuit diagram maker"}, {"phrase": "circuit diagram symbols"},
            {"phrase": "circuit diagram online"}, {"phrase": "celebrity news"},
        ])
        payload = specialist_payload()
        payload["spokes"][0]["search_intent"] = payload["master_hub"]["search_intent"]
        from nlp.hub_spoke_agent import _normalize_plan
        errors = validate_architecture(_normalize_plan(payload, records), records)
        self.assertIn("two pages have the same declared search intent", errors)

    def test_semantic_intent_conflict_forces_a_revised_plan(self):
        records = normalize_keyword_records([
            {"phrase": "circuit diagram maker"},
            {"phrase": "circuit diagram online"},
            {"phrase": "circuit diagram symbols"},
            {"phrase": "celebrity news"},
        ])
        provider = AsyncMock(side_effect=[
            specialist_payload(),
            {
                "passed": False,
                "conflicts": [{
                    "page_a": "circuit diagram maker",
                    "page_b": "circuit diagram symbols",
                    "reason": "The proposed briefs overlap.",
                    "resolution": "Clarify the reference page.",
                }],
            },
            specialist_payload(),
            {"passed": True, "conflicts": []},
        ])
        with (
            patch("nlp.hub_spoke_agent.is_ai_configured", return_value=True),
            patch("nlp.hub_spoke_agent._achat_json", new=provider),
        ):
            mapping = asyncio.run(build_site_architecture(
                records, context="Electronics design website", primary_keyword="circuit diagram maker",
            ))
        self.assertEqual(provider.await_count, 4)
        self.assertEqual(mapping["master_hub"]["target_keyword"], "circuit diagram maker")

    def test_imported_seeds_are_preserved_in_context(self):
        context = _context_with_seed_keywords(
            json.dumps({"primary_keyword": "circuit diagram maker"}),
            ["circuit diagram maker", "pcb design software"],
        )
        self.assertEqual(json.loads(context)["seed_keywords"], ["circuit diagram maker", "pcb design software"])


class HubWorkspaceDeleteTests(unittest.IsolatedAsyncioTestCase):
    async def test_history_delete_is_scoped_to_the_current_user(self):
        db = AsyncMock()
        db.execute.return_value = SimpleNamespace(rowcount=1)
        await delete_hub_spoke_history(uuid.uuid4(), SimpleNamespace(id=uuid.uuid4()), db)
        sql = str(db.execute.await_args.args[0])
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
