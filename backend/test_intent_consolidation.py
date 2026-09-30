"""Page ownership regressions with controlled planner and reviewer responses."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from nlp.hub_spoke_agent import (
    ArchitectureAgentError, build_site_architecture,
)


APPROVED = {"passed": True, "conflicts": [], "rejections": []}


def payload_for(targets):
    return {
        "master_target": targets[0],
        "pages": [{
            "target_keyword": target, "article_title": target.title(),
            "search_intent": f"Answer the query {target}", "page_type": "article",
            "spoke_category": f"Group {index}",
        } for index, target in enumerate(targets)],
        "keyword_decisions": [
            [target, "page_target", target, "title", "Proposed task"] for target in targets
        ],
    }


class IntentConsolidationTests(unittest.TestCase):
    def build(self, targets, payload, reviews, *, authority=False, context=''):
        responses = ([{"proposals": []}] if authority else []) + [payload, *reviews]
        chat = AsyncMock(side_effect=responses)
        with patch('nlp.hub_spoke_agent.is_ai_configured', return_value=True), patch(
            'nlp.hub_spoke_agent._achat_json', chat,
        ):
            result = asyncio.run(build_site_architecture(
                [{"phrase": target} for target in targets], primary_keyword=targets[0],
                target_spokes=25 if authority else None,
                context=context,
            ))
        return result, chat

    def test_common_variants_merge_across_groups_and_formats(self):
        targets = ['lunar age calculator', 'free lunar age calculator online',
                   'lunar age meaning', 'what is lunar age',
                   'how to calculate lunar age', 'lunar age calculation guide']
        for authority in (False, True):
            with self.subTest(authority=authority):
                payload = payload_for(targets)
                payload['pages'][0]['page_type'] = 'tool'
                plan, _ = self.build(targets, payload, [APPROVED], authority=authority)
                self.assertEqual(len(plan['spokes']), 2)
                self.assertEqual(plan['_deduplication_check']['duplicates_removed'], 3)
                self.assertIn(targets[1], plan['master_hub']['targeted_keywords'])
                decisions = {item['keyword']: item for item in plan['keyword_assignments']}
                self.assertEqual(decisions[targets[3]]['assigned_to'], targets[2])
                self.assertEqual(decisions[targets[5]]['assigned_to'], targets[4])
                self.assertEqual(plan['_semantic_audit_status'], 'passed')

    def test_distinct_entities_qualifiers_and_tasks_survive(self):
        targets = ['lunar age calculator', 'how to calculate lunar age',
                   'lunar age meaning', 'lunar age calculator accuracy',
                   'korean age calculator', 'lunar age at conception calculator',
                   'north node meaning', 'south node meaning',
                   'causes of gum recession', 'causes of gum inflammation',
                   'lunar age without birth time calculator',
                   'lunar age calculator errors', 'usd to eur converter', 'eur to usd converter']
        plan, _ = self.build(targets, payload_for(targets), [APPROVED])
        self.assertEqual(len(plan['spokes']), len(targets) - 1)

    def test_large_variant_inventory_never_promotes_supporting_keywords(self):
        primary = 'lunar age calculator'
        variants = [f'lunar age calculator example {index}' for index in range(35)]
        payload = payload_for([primary])
        payload['keyword_decisions'] += [
            [variant, 'supporting', primary, 'h2:Examples', 'Same task'] for variant in variants
        ]
        plan, _ = self.build([primary, *variants], payload, [APPROVED])
        self.assertEqual(plan['spokes'], [])
        self.assertEqual(set(plan['master_hub']['targeted_keywords']), set(variants))

    def test_semantic_paraphrases_merge_despite_different_page_formats(self):
        targets = ['lunar age calculator', 'find your chinese age', 'traditional age lookup']
        payload = payload_for(targets)
        payload['pages'][1]['page_type'] = 'tool'
        payload['pages'][1]['tool_functions'] = ['Compute traditional age from birth date']
        payload['pages'][2]['existing_url'] = 'https://example.com/traditional-age/'
        conflict = {'passed': False, 'conflicts': [{
            'page_a': targets[1], 'page_b': targets[2], 'reason': 'Same traditional age lookup task',
        }]}
        context = json.dumps({'owned_pages': [{'url': 'https://example.com/traditional-age/'}]})
        plan, chat = self.build(targets, payload, [conflict, APPROVED], authority=True, context=context)
        self.assertEqual(len(plan['spokes']), 1)
        self.assertEqual(plan['spokes'][0]['target_keyword'], targets[2])
        self.assertIn('Compute traditional age from birth date', plan['spokes'][0]['tool_functions'])
        self.assertEqual(plan['spokes'][0]['page_type'], 'tool')
        self.assertIn('h2_sections', chat.await_args_list[2].kwargs['user_prompt'])
        self.assertEqual(plan['_semantic_audit_status'], 'passed')

    def test_merged_plan_requires_a_successful_followup_review(self):
        targets = ['lunar age calculator', 'find your chinese age']
        conflict = {'passed': False, 'conflicts': [{
            'page_a': targets[0], 'page_b': targets[1], 'reason': 'Same calculation task',
        }]}
        with self.assertRaisesRegex(ArchitectureAgentError, 'previous saved map is unchanged'):
            self.build(targets, payload_for(targets), [conflict, RuntimeError('unavailable')])

    def test_invalid_review_references_cannot_approve_a_map(self):
        targets = ['lunar age calculator', 'lunar age meaning']
        invalid = {'passed': False, 'conflicts': [{
            'page_a': targets[0], 'page_b': 'invented target', 'reason': 'Duplicate',
        }]}
        with self.assertRaisesRegex(ArchitectureAgentError, 'previous saved map is unchanged'):
            self.build(targets, payload_for(targets), [invalid, invalid])

    def test_transient_review_failure_retries_review_without_regenerating(self):
        targets = ['lunar age calculator', 'lunar age meaning']
        plan, chat = self.build(targets, payload_for(targets), [RuntimeError('temporary'), APPROVED])
        self.assertEqual(chat.await_count, 3)
        self.assertEqual(plan['_semantic_audit_status'], 'passed')

    def test_specific_duplicate_intent_is_not_hidden_by_relabeling(self):
        from nlp.hub_spoke_agent import _normalize_plan, _repair_plan_consistency, validate_architecture
        targets = ['lunar age calculator', 'find your chinese age']
        payload = payload_for(targets)
        for page in payload['pages']:
            page['search_intent'] = 'Calculate traditional age from birth date'
        records = [{'phrase': target} for target in targets]
        plan = _repair_plan_consistency(_normalize_plan(payload, records, targets[0]), records, targets[0])
        self.assertIn('two pages have the same declared search intent', validate_architecture(plan, records))
