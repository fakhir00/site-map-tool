from architecture_test_fixtures import approved_review
import asyncio
import json
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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
    ArchitectureAgentError,
    _apply_tool_roi_rules,
    _coerce_object,
    _generated_page,
    _has_unrelated_leading_brand,
    _is_core_entity_relevant,
    _is_protected_emd_entity,
    _looks_incomplete_keyword,
    _mechanical_causal_conflicts,
    _merge_intent_conflicts,
    _normalize_plan,
    _repair_plan_consistency,
    _source_domain_brand_rejections,
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
    def test_complete_plan_recovers_from_temporary_failure_in_each_ai_stage(self):
        from nlp import providers
        payload = specialist_payload()
        records = [{'phrase': item['keyword']} for item in payload['keyword_assignments']]

        def response(content):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(content)))])

        for failed_stage in range(3):
            with self.subTest(stage=('discovery', 'planning', 'review')[failed_stage]):
                replies = [response({'proposals': []}), response(payload), response(approved_review(payload))]
                replies.insert(failed_stage, TimeoutError())
                create = AsyncMock(side_effect=replies)
                client = MagicMock()
                client.__aenter__ = AsyncMock(return_value=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
                client.__aexit__ = AsyncMock(return_value=False)
                with (
                    patch.dict(providers._status, {}, clear=True),
                    patch('nlp.providers.configured_providers', return_value=[
                        ('DeepSeek', 'https://offline.example', 'offline-key', 'deepseek-chat'),
                    ]),
                    patch('nlp.providers.AsyncOpenAI', return_value=client),
                    patch('nlp.providers.asyncio.sleep', new=AsyncMock()),
                ):
                    plan = asyncio.run(build_site_architecture(
                        records, primary_keyword='circuit diagram maker', discover_topics=True,
                    ))
                self.assertEqual(plan['_semantic_audit_status'], 'passed')
                self.assertEqual(len(plan['spokes']), 1)
                self.assertEqual(create.await_count, 4)

    def test_planning_and_review_pass_deadlines_to_provider_failover(self):
        payload = specialist_payload()
        records = [{'phrase': item['keyword']} for item in payload['keyword_assignments']]
        chat = AsyncMock(side_effect=[payload, approved_review(payload)])
        with patch('nlp.hub_spoke_agent.is_ai_configured', return_value=True), patch(
            'nlp.hub_spoke_agent._achat_json', new=chat,
        ):
            asyncio.run(build_site_architecture(records, primary_keyword='circuit diagram maker'))
        self.assertGreater(chat.call_args_list[0].kwargs['request_timeout'], 45)
        self.assertLessEqual(chat.call_args_list[0].kwargs['request_timeout'], 120)
        self.assertLessEqual(chat.call_args_list[1].kwargs['request_timeout'], 45)

    def test_exhausted_provider_failure_is_not_sent_back_as_a_plan_validation_error(self):
        from nlp.providers import ProviderUnavailableError
        chat = AsyncMock(side_effect=ProviderUnavailableError('AI unavailable. DeepSeek: request timed out.'))
        with patch('nlp.hub_spoke_agent.is_ai_configured', return_value=True), patch(
            'nlp.hub_spoke_agent._achat_json', new=chat,
        ):
            with self.assertRaisesRegex(ArchitectureAgentError, 'previous saved map is unchanged'):
                asyncio.run(build_site_architecture([{'phrase': 'circuit diagram maker'}]))
        chat.assert_awaited_once()

    def test_product_review_emd_keeps_product_terms_without_admitting_broad_dental_noise(self):
        primary = "dental pro 7 reviews"
        self.assertTrue(_is_core_entity_relevant("dental pro ingredients", primary))
        self.assertFalse(_is_protected_emd_entity("dental pro 7 reviews reddit", primary))
        self.assertFalse(_is_protected_emd_entity("dental-pro-7-redit-reviews", primary))
        self.assertFalse(_is_protected_emd_entity("dental pro 7 reviews trustpilot", primary))
        self.assertFalse(_is_protected_emd_entity("dental pro 7 reviews amazon", primary))
        self.assertTrue(_is_protected_emd_entity("dental pro 7 vs oramd", primary))
        self.assertFalse(_is_core_entity_relevant("dental implants", primary))
        self.assertFalse(_is_core_entity_relevant("amd dental clinic", primary))
        self.assertFalse(_is_protected_emd_entity("natures smile reviews", primary))
        self.assertTrue(_has_unrelated_leading_brand("call nature dental pro 7 reviews", primary))
        self.assertFalse(_has_unrelated_leading_brand("best dental pro 7 reviews", primary))

    def test_source_domain_brand_names_are_rejected_but_core_entity_and_comparisons_remain(self):
        primary = "dental pro 7 reviews"
        records = normalize_keyword_records([
            {"phrase": primary, "source_domains": ["https://dentalpro7reviews.com"]},
            {"phrase": "call nature dental pro 7 reviews", "source_domains": ["https://callnature.com"]},
            {"phrase": "dental pro 7 ingredients", "source_domains": ["https://dentalpro7ingredients.com"]},
            {"phrase": "dental pro 7 vs oramd", "source_domains": ["https://oramd.com"]},
        ])
        plan = {"keyword_assignments": [
            {"keyword": item["phrase"], "disposition": "supporting"} for item in records
        ]}
        rejected = {
            item["keyword"] for item in _source_domain_brand_rejections(plan, records, primary)
        }
        self.assertEqual(rejected, {"call nature dental pro 7 reviews"})

    def test_provider_wrappers_and_json_strings_are_unwrapped(self):
        payload = {"master_target": "circuit diagram maker", "pages": []}
        self.assertEqual(_coerce_object({"result": json.dumps(payload)}), payload)
        self.assertEqual(_coerce_object([payload]), payload)
        self.assertIsNone(_coerce_object([{"fragment": 1}, {"fragment": 2}]))

    def test_context_competitor_names_reject_navigation_even_without_row_source(self):
        records = normalize_keyword_records([{'phrase': phrase} for phrase in (
            'spirit animal quiz', 'spirit animal quizzes buzzfeed', 'spirit animal quiz vs buzzfeed',
        )])
        plan = {'keyword_assignments': [{'keyword': item['phrase'], 'disposition': 'supporting'} for item in records]}
        context = json.dumps({'competitor_exclusions': ['www.buzzfeed.com', 'spiritanimalquiz.com']})
        rejected = _source_domain_brand_rejections(plan, records, 'spirit animal quiz', context)
        self.assertEqual([item['keyword'] for item in rejected], ['spirit animal quizzes buzzfeed'])

    def test_topic_substring_in_competitor_domain_is_not_a_brand_query(self):
        records = normalize_keyword_records([{'phrase': phrase} for phrase in (
            'spirit animal', 'spirit animal atlas quiz', 'owl symbolism',
        )])
        plan = {'keyword_assignments': [{'keyword': item['phrase'], 'disposition': 'supporting'} for item in records]}
        context = json.dumps({'competitor_exclusions': ['spiritanimalatlas.com', 'owlsymbolismguide.com']})
        rejected = _source_domain_brand_rejections(plan, records, 'spirit animal quiz', context)
        self.assertEqual([item['keyword'] for item in rejected], ['spirit animal atlas quiz'])

    def test_provider_prose_around_complete_json_is_parsed_as_one_object(self):
        payload = {"master_target": "circuit diagram maker", "pages": [{"target_keyword": "x"}]}
        content = "Here is the requested architecture:\n```json\n" + json.dumps(payload) + "\n```"
        self.assertEqual(_parse_json_payload(content), payload)

    def test_complete_ai_json_recovers_trailing_commas_without_changing_text(self):
        payload = {'pages': [{'target_keyword': 'dot plot maker',
                             'scope': 'Keep literal ,} and ,] and escaped "quotes" unchanged.'}],
                   'discarded': []}
        text = json.dumps(payload).replace('}],', '},],')
        text = text[:-1] + ',}'
        self.assertEqual(_parse_json_payload(text), payload)

    def test_json_recovery_never_invents_truncated_fields_or_closing_containers(self):
        for text in ('{"pages":[{"target_keyword":"dot plot maker",},],',
                     '{"pages":[{"target_keyword":', '{"pages": [1,,2]}',
                     '{"pages": [1], "scope": unquoted}'):
            with self.subTest(text=text), self.assertRaises(json.JSONDecodeError):
                _parse_json_payload(text)

    def test_truncated_outer_json_never_becomes_a_nested_page_or_keyword(self):
        for content in (
            '{"pages":[{"target_keyword":"spirit animal quiz"}], "keyword_decisions": [',
            'Here is the plan: {"pages":[{"target_keyword":"spirit animal quiz"}',
            '[{"phrase":"wolf spirit animal"}, {"phrase":',
        ):
            with self.subTest(content=content), self.assertRaises(json.JSONDecodeError):
                _parse_json_payload(content)

    def test_unavailable_semantic_review_cannot_publish_a_map(self):
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
                new=AsyncMock(side_effect=[specialist_payload(), [{"incomplete": "audit fragment"}]]),
            ),
        ):
            with self.assertRaisesRegex(ArchitectureAgentError, "previous saved map is unchanged"):
                asyncio.run(build_site_architecture(records, primary_keyword="circuit diagram maker"))

    def test_final_relevance_review_discards_a_competitor_keyword(self):
        competitor = "astro seek circuit diagram calculator"
        payload = specialist_payload()
        payload["keyword_assignments"].append({
            "keyword": competitor,
            "disposition": "supporting",
            "assigned_to": "circuit diagram maker",
            "placement": "variation",
            "reason": "Related calculator phrase.",
        })
        records = normalize_keyword_records([
            {"phrase": "circuit diagram maker"},
            {"phrase": "circuit diagram online"},
            {"phrase": "circuit diagram symbols"},
            {"phrase": "celebrity news"},
            {"phrase": competitor},
        ])
        review = {
            **approved_review(payload),
            "passed": True,
            "conflicts": [],
            "rejections": [{
                "keyword": competitor,
                "reason": "Navigational query for a competitor brand.",
            }],
        }
        with (
            patch("nlp.hub_spoke_agent.is_ai_configured", return_value=True),
            patch(
                "nlp.hub_spoke_agent._achat_json",
                new=AsyncMock(side_effect=[payload, review]),
            ),
        ):
            mapping = asyncio.run(build_site_architecture(
                records, primary_keyword="circuit diagram maker",
            ))
        decision = next(item for item in mapping["keyword_assignments"] if item["keyword"] == competitor)
        self.assertEqual(decision["disposition"], "discard")
        self.assertIn("competitor", decision["reason"])

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
        self.assertEqual(parsed["competitor_exclusions"], "broad astronomy sites")
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
                new=AsyncMock(side_effect=[specialist_payload(), approved_review(specialist_payload())]),
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
                **approved_review(specialist_payload()),
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
                new=AsyncMock(side_effect=[{"result": json.dumps(compact)}, approved_review(compact)]),
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
        conflict = {**approved_review(payload), "passed": False, "conflicts": [{
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

    def test_keyword_count_does_not_force_extra_pages(self):
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
        self.assertEqual(errors, [])

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

    def test_omitted_keywords_require_review_instead_of_implicit_rejection(self):
        primary = "dental pro 7 reviews"
        records = normalize_keyword_records([
            {"phrase": primary},
            {"phrase": "dental pro ingredients"},
            {"phrase": "dental pro 7 side effects"},
            {"phrase": "dental implants"},
            {"phrase": "amd dental clinic"},
        ])
        payload = {
            "master_target": primary,
            "pages": [{
                "target_keyword": primary, "search_intent": "review dental pro 7",
                "article_title": "Dental Pro 7 Reviews", "page_type": "article",
            }],
            "keyword_decisions": [
                [primary, "page_target", primary, "title", "EMD target."],
                ["dental pro ingredients", "discard", None, None, "Competitor-source phrase."],
            ],
        }
        plan = _repair_plan_consistency(_normalize_plan(payload, records, primary), records, primary)
        self.assertEqual(plan["master_hub"]["page_type"], "article")
        decisions = {item["keyword"]: item for item in plan["keyword_assignments"]}
        self.assertEqual(decisions["dental pro ingredients"]["disposition"], "supporting")
        for keyword in ("dental pro 7 side effects", "dental implants", "amd dental clinic"):
            self.assertEqual(decisions[keyword]["disposition"], "unassigned")
        self.assertTrue(any("invalid disposition" in error for error in validate_architecture(plan, records, primary)))

    def test_spoke_tool_requires_enough_search_volume_for_the_effort(self):
        records = normalize_keyword_records([
            {"phrase": "widget calculator", "search_volume": 5000, "difficulty": 30},
            {"phrase": "advanced widget calculator", "search_volume": 3000, "difficulty": 35},
            {"phrase": "tiny widget calculator", "search_volume": 20, "difficulty": 10},
            {"phrase": "tiny widget builder", "search_volume": 20, "difficulty": 10},
            {"phrase": "linear extrapolation calculator", "search_volume": 10, "difficulty": 40},
            {"phrase": "widget calculation guide", "search_volume": 2000, "difficulty": 20},
            {"phrase": "widget calculator terms and conditions", "search_volume": 5000, "difficulty": 15},
        ])
        metrics = {item["phrase"]: item for item in records}
        plan = {
            "master_hub": _generated_page("widget calculator", metrics),
            "spokes": [
                _generated_page("advanced widget calculator", metrics),
                _generated_page("tiny widget calculator", metrics),
                _generated_page("tiny widget builder", metrics),
                _generated_page("linear extrapolation calculator", metrics),
                _generated_page("widget calculation guide", metrics),
                _generated_page("widget calculator terms and conditions", metrics),
            ],
        }
        plan = _apply_tool_roi_rules(plan, records)
        page_types = {page["target_keyword"]: page["page_type"] for page in plan["spokes"]}
        self.assertEqual(page_types["advanced widget calculator"], "tool")
        self.assertEqual(page_types["tiny widget calculator"], "tool")
        self.assertEqual(page_types["linear extrapolation calculator"], "tool")
        self.assertEqual(page_types["tiny widget builder"], "article")
        self.assertEqual(page_types["widget calculation guide"], "article")
        self.assertEqual(page_types["widget calculator terms and conditions"], "article")

    def test_incomplete_keyword_fragments_are_detected(self):
        self.assertTrue(_looks_incomplete_keyword("what dental"))
        self.assertTrue(_looks_incomplete_keyword("teeth whitening side"))
        self.assertTrue(_looks_incomplete_keyword("dental dental"))
        self.assertFalse(_looks_incomplete_keyword("what causes gum recession"))
        self.assertFalse(_looks_incomplete_keyword("dental pro 7 side effects"))

    def test_cause_reason_and_why_variants_merge_into_one_spoke(self):
        records = normalize_keyword_records([
            {"phrase": "gum health guide", "search_volume": 1000},
            {"phrase": "what causes gum recession", "search_volume": 800},
            {"phrase": "why gum recession happens", "search_volume": 300},
        ])
        metrics = {item["phrase"]: item for item in records}
        primary = "gum health guide"
        plan = {
            "site_strategy": "Build complete gum-health coverage.",
            "master_hub": _generated_page(primary, metrics),
            "spokes": [
                _generated_page("what causes gum recession", metrics),
                _generated_page("why gum recession happens", metrics),
            ],
            "keyword_assignments": [
                {
                    "keyword": keyword,
                    "disposition": "page_target",
                    "assigned_to": keyword,
                    "placement": "title",
                    "reason": "Distinct proposed page.",
                }
                for keyword in metrics
            ],
        }

        conflicts = _mechanical_causal_conflicts(plan)
        self.assertEqual(len(conflicts), 1)
        merged, notes = _merge_intent_conflicts(plan, conflicts)

        self.assertEqual(
            [page["target_keyword"] for page in merged["spokes"]],
            ["what causes gum recession"],
        )
        decisions = {item["keyword"]: item for item in merged["keyword_assignments"]}
        self.assertEqual(decisions["why gum recession happens"]["disposition"], "supporting")
        self.assertEqual(
            decisions["why gum recession happens"]["assigned_to"],
            "what causes gum recession",
        )
        self.assertTrue(notes)

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
