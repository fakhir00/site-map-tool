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
from nlp.hub_spoke_agent import (
    _apply_tool_roi_rules,
    _coerce_object,
    _generated_page,
    _normalize_plan,
    _repair_plan_consistency,
    build_site_architecture,
    normalize_keyword_records,
    validate_architecture,
)
from nlp.openrouter import _parse_json_payload


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
    def test_provider_wrappers_and_json_strings_are_unwrapped(self):
        payload = {"master_target": "circuit diagram maker", "pages": []}
        self.assertEqual(_coerce_object({"result": json.dumps(payload)}), payload)
        self.assertEqual(_coerce_object([payload]), payload)
        self.assertIsNone(_coerce_object([{"fragment": 1}, {"fragment": 2}]))

    def test_provider_prose_around_complete_json_is_parsed_as_one_object(self):
        payload = {"master_target": "circuit diagram maker", "pages": [{"target_keyword": "x"}]}
        content = "Here is the requested architecture:\n```json\n" + json.dumps(payload) + "\n```"
        self.assertEqual(_parse_json_payload(content), payload)

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

    def test_tool_and_reference_spoke_are_preserved_as_distinct_intents(self):
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
        ])
        with (
            patch("nlp.hub_spoke_agent.is_ai_configured", return_value=True),
            patch("nlp.hub_spoke_agent._achat_json", new=provider),
        ):
            mapping = asyncio.run(build_site_architecture(
                records, context="Electronics design website", primary_keyword="circuit diagram maker",
            ))
        self.assertEqual(provider.await_count, 2)
        self.assertEqual(mapping["master_hub"]["target_keyword"], "circuit diagram maker")
        self.assertEqual(mapping["master_hub"]["slug"], "/")
        self.assertEqual(len(mapping["spokes"]), 1)
        symbol_decision = next(
            item for item in mapping["keyword_assignments"]
            if item["keyword"] == "circuit diagram symbols"
        )
        self.assertEqual(symbol_decision["disposition"], "page_target")
        self.assertEqual(symbol_decision["assigned_to"], "circuit diagram symbols")

    def test_compact_provider_schema_builds_the_dashboard_mapping(self):
        compact = {
            "site_strategy": "One creation hub and one reference page.",
            "master_target": "circuit diagram maker",
            "pages": [
                {
                    "target_keyword": "circuit diagram maker",
                    "search_intent": "create a circuit diagram",
                    "spoke_category": "Tools",
                    "article_title": "Circuit Diagram Maker",
                    "page_type": "tool",
                    "content_brief": "Interactive creation tool.",
                },
                {
                    "target_keyword": "circuit diagram symbols",
                    "search_intent": "identify circuit symbols",
                    "spoke_category": "Reference guides",
                    "article_title": "Circuit Diagram Symbols",
                    "page_type": "article",
                    "content_brief": "Symbol reference guide.",
                },
            ],
            "keyword_decisions": [
                ["circuit diagram maker", "page_target", "circuit diagram maker", "title", "Main tool intent."],
                ["circuit diagram online", "supporting", "circuit diagram maker", "feature", "Same creation goal."],
                ["circuit diagram symbols", "page_target", "circuit diagram symbols", "title", "Reference intent."],
                ["celebrity news", "discard", None, None, "Outside site scope."],
            ],
            "interlinking_strategy": "Link the tool and reference guide.",
        }
        records = normalize_keyword_records([
            {"phrase": "circuit diagram maker"}, {"phrase": "circuit diagram online"},
            {"phrase": "circuit diagram symbols"}, {"phrase": "celebrity news"},
        ])
        with (
            patch("nlp.hub_spoke_agent.is_ai_configured", return_value=True),
            patch(
                "nlp.hub_spoke_agent._achat_json",
                new=AsyncMock(side_effect=[{"result": json.dumps(compact)}, {"passed": True, "conflicts": []}]),
            ),
        ):
            mapping = asyncio.run(build_site_architecture(
                records,
                primary_keyword="circuit diagram maker",
                site_domain="https://www.circuitDiagramMaker.com/tools",
            ))
        self.assertEqual(validate_architecture(mapping, records), [])
        self.assertEqual(mapping["site_domain"], "circuitdiagrammaker.com")
        self.assertEqual(mapping["hubs"][0]["hub_title"], "MASTER HUB: circuitdiagrammaker.com")
        self.assertEqual(mapping["filtered_irrelevant_keywords"], ["celebrity news"])

    def test_lunar_node_calculator_and_manual_guide_remain_separate(self):
        secondary = "how to calculate lunar nodes manually vs calculator"
        payload = {
            "site_strategy": "Lead with the calculator.",
            "master_target": "moon nodes calculator",
            "pages": [
                {"target_keyword": "moon nodes calculator", "search_intent": "calculate lunar nodes", "article_title": "Moon Nodes Calculator", "page_type": "tool", "content_brief": "Calculate placements."},
                {"target_keyword": secondary, "search_intent": "compare manual and calculator methods", "article_title": "Manual vs Calculator", "page_type": "article", "content_brief": "Explain both methods."},
            ],
            "keyword_decisions": [
                ["moon nodes calculator", "page_target", "moon nodes calculator", "title", "Core tool."],
                [secondary, "page_target", secondary, "title", "Comparison query."],
            ],
            "interlinking_strategy": "One cluster.",
        }
        conflict = {"passed": False, "conflicts": [{
            "page_a": "moon nodes calculator", "page_b": secondary,
            "reason": "Both pages serve users obtaining lunar node placements.",
            "resolution": "Merge the comparison into the calculator page.",
        }]}
        records = normalize_keyword_records([
            {"phrase": "moon nodes calculator", "search_volume": 900},
            {"phrase": secondary, "search_volume": 20},
        ])
        with (
            patch("nlp.hub_spoke_agent.is_ai_configured", return_value=True),
            patch(
                "nlp.hub_spoke_agent._achat_json",
                new=AsyncMock(side_effect=[payload, conflict]),
            ),
        ):
            mapping = asyncio.run(build_site_architecture(records, primary_keyword="moon nodes calculator"))
        self.assertEqual(mapping["master_hub"]["slug"], "/")
        self.assertEqual(len(mapping["spokes"]), 1)
        decision = next(item for item in mapping["keyword_assignments"] if item["keyword"] == secondary)
        self.assertEqual(decision["disposition"], "page_target")
        self.assertEqual(decision["assigned_to"], secondary)

    def test_large_inventory_cannot_be_collapsed_into_one_page(self):
        records = normalize_keyword_records([{"phrase": f"topic keyword {index}"} for index in range(36)])
        payload = {
            "master_target": "topic keyword 0",
            "pages": [{
                "target_keyword": "topic keyword 0", "search_intent": "serve every topic",
                "article_title": "Topic", "page_type": "tool", "spoke_category": "Tools",
            }],
            "keyword_decisions": [
                [item["phrase"], "page_target" if index == 0 else "supporting", "topic keyword 0", "h2", "Same topic."]
                for index, item in enumerate(records)
            ],
        }
        from nlp.hub_spoke_agent import _normalize_plan
        plan = _normalize_plan(payload, records, "topic keyword 0")
        errors = validate_architecture(plan, records, "topic keyword 0")
        self.assertTrue(any("topical authority is too shallow" in error for error in errors))
        self.assertTrue(any("absorbs 36 of 36" in error for error in errors))

    def test_model_page_consistency_errors_are_repaired_before_validation(self):
        records = normalize_keyword_records([
            {"phrase": "moon nodes calculator"},
            {"phrase": "north node meaning"},
            {"phrase": "south node meaning"},
            {"phrase": "north node true meaning"},
        ])
        malformed = {
            "master_target": "moon nodes calculator",
            "pages": [
                {"target_keyword": "moon nodes calculator", "search_intent": "informational", "article_title": "Calculator", "page_type": "tool"},
                {"target_keyword": "north node meanings", "search_intent": "informational", "article_title": "North Node Meaning", "page_type": "article"},
                {"target_keyword": "north node meanings", "search_intent": "informational", "article_title": "Duplicate", "page_type": "article"},
            ],
            "keyword_decisions": [
                ["moon nodes calculator", "supporting", "north node meanings", "h2", "Incorrect model decision."],
                ["north node meaning", "page_target", "north node meaning", "title", "Meaning page."],
                ["south node meaning", "page_target", "south node meaning", "title", "Meaning page."],
                ["north node true meaning", "supporting", "north node meanings", "h2", "Close variant."],
            ],
        }
        plan = _repair_plan_consistency(
            _normalize_plan(malformed, records, "moon nodes calculator"),
            records,
            "moon nodes calculator",
        )
        self.assertEqual(validate_architecture(plan, records, "moon nodes calculator"), [])
        self.assertEqual(plan["master_hub"]["slug"], "/")
        targets = [plan["master_hub"]["target_keyword"], *(page["target_keyword"] for page in plan["spokes"])]
        self.assertEqual(len(targets), len(set(targets)))
        self.assertIn("south node meaning", targets)

    def test_spoke_tool_requires_enough_search_volume_for_the_effort(self):
        records = normalize_keyword_records([
            {"phrase": "widget calculator", "search_volume": 5000, "difficulty": 30},
            {"phrase": "advanced widget calculator", "search_volume": 1200, "difficulty": 35},
            {"phrase": "tiny widget calculator", "search_volume": 20, "difficulty": 10},
            {"phrase": "widget calculation guide", "search_volume": 2000, "difficulty": 20},
        ])
        metrics = {item["phrase"]: item for item in records}
        plan = {
            "master_hub": _generated_page("widget calculator", metrics),
            "spokes": [
                _generated_page("advanced widget calculator", metrics),
                _generated_page("tiny widget calculator", metrics),
                _generated_page("widget calculation guide", metrics),
            ],
        }
        plan = _apply_tool_roi_rules(plan, records)
        page_types = {page["target_keyword"]: page["page_type"] for page in plan["spokes"]}
        self.assertEqual(page_types["advanced widget calculator"], "tool")
        self.assertEqual(page_types["tiny widget calculator"], "article")
        self.assertEqual(page_types["widget calculation guide"], "article")

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
