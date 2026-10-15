"""Page ownership regressions with controlled planner and reviewer responses."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from architecture_test_fixtures import approved_review

from nlp.hub_spoke_agent import (
    ArchitectureAgentError, build_site_architecture,
)


APPROVED = {"passed": True, "conflicts": [], "rejections": []}
SAME_PAGE = dict.fromkeys(('same_user', 'same_task', 'same_answer', 'same_serp_intent', 'same_entity'), True)


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
        reviews = [approved_review(payload) if review is APPROVED else review for review in reviews]
        responses = ([{"proposals": []}] if authority else []) + [payload, *reviews]
        chat = AsyncMock(side_effect=responses)
        with patch('nlp.hub_spoke_agent.is_ai_configured', return_value=True), patch(
            'nlp.hub_spoke_agent._achat_json', chat,
        ):
            result = asyncio.run(build_site_architecture(
                [{"phrase": target} for target in targets], primary_keyword=targets[0],
                discover_topics=authority,
                context=context,
            ))
        return result, chat

    def test_bare_approval_cannot_publish_unjustified_spokes(self):
        targets = ['diagram maker', 'diagram maker with dark mode']
        bare = dict(APPROVED)  # Deliberately omit the new per-URL evidence.
        with self.assertRaisesRegex(ArchitectureAgentError, 'previous saved map is unchanged'):
            self.build(targets, payload_for(targets), [bare, bare])

    def test_minor_feature_classification_cannot_be_approved_as_a_page(self):
        targets = ['diagram maker', 'diagram maker with grid snapping']
        payload = payload_for(targets)
        for classification in ('small_feature', 'subsection', 'unsupported'):
            review = approved_review(payload)
            review['url_assessments'][1]['classification'] = classification
            with self.subTest(classification=classification), self.assertRaises(ArchitectureAgentError):
                self.build(targets, payload, [review, review])

    def test_independent_page_requires_capability_and_unique_value_evidence(self):
        targets = ['diagram maker', 'logic gate symbols']
        payload = payload_for(targets)
        for field in ('independent_task', 'unique_value', 'capability_basis'):
            review = approved_review(payload)
            review['url_assessments'][1][field] = ''
            with self.subTest(field=field), self.assertRaises(ArchitectureAgentError):
                self.build(targets, payload, [review, review])

    def test_editor_conveniences_are_consolidated_without_losing_useful_sections(self):
        primary = 'circuit diagram maker'
        features = ['grid snapping', 'keyboard shortcuts', 'Manhattan routing', '40 symbols',
                    'auto-save', 'LocalStorage', 'dark mode']
        targets = [primary, *(f'{primary} with {feature.lower()}' for feature in features)]
        payload = payload_for(targets)
        for page, feature in zip(payload['pages'][1:], features):
            page['content_requirements'] = [f'Explain {feature} in the editor documentation.']
        review = {'passed': False, 'conflicts': [
            {'page_a': primary, 'page_b': keyword, 'preferred_target': primary,
             'risk_type': 'doorway', 'one_page_test': SAME_PAGE,
             'reason': 'Small editor convenience; the homepage documentation satisfies this task.'}
            for keyword in targets[1:]
        ]}
        plan, _ = self.build(targets, payload, [review, APPROVED], authority=True)
        self.assertEqual(plan['spokes'], [])
        self.assertEqual(set(plan['master_hub']['targeted_keywords']), set(targets[1:]))
        self.assertEqual(len(plan['master_hub']['content_requirements']), len(features))

    def test_unsupported_core_feature_is_removed_without_merging_implementation(self):
        targets = ['circuit diagram maker', 'circuit diagram maker with real time collaboration']
        payload = payload_for(targets)
        payload['pages'][1]['tool_functions'] = ['Implement live multi-user editing']
        limitation = 'JSON files can be shared manually; real-time collaboration is not supported.'
        review = {'passed': True, 'conflicts': [], 'rejections': [{
            'keyword': targets[1], 'category': 'unsupported_capability',
            'reason': 'Real-time collaboration is outside the declared product capabilities.',
            'clarification_parent': targets[0], 'limitation': limitation,
        }]}
        plan, _ = self.build(targets, payload, [review], authority=True,
                             context='Supports JSON sharing and local storage. Real-time collaboration is not supported.')
        self.assertEqual(plan['spokes'], [])
        self.assertNotIn('Implement live multi-user editing', plan['master_hub']['tool_functions'])
        self.assertIn(limitation, plan['master_hub']['content_requirements'])
        decision = next(item for item in plan['keyword_assignments'] if item['keyword'] == targets[1])
        self.assertEqual(decision['disposition'], 'discard')

    def test_feature_phrasing_triggers_assessment_without_deciding_its_intent(self):
        from nlp.intent_policy import requires_feature_page_test
        for keyword in ('editor with layers', 'editor for architects', 'editing using masks',
                        'invoice maker', 'network diagram maker', 'logic circuit maker',
                        'resistor symbol', 'resistor symbols', 'Poster MAKER'):
            with self.subTest(keyword=keyword):
                self.assertTrue(requires_feature_page_test(keyword))
        for keyword in ('', 'maker', 'with', 'symbol', 'weather forecast', 'before sunrise'):
            with self.subTest(keyword=keyword):
                self.assertFalse(requires_feature_page_test(keyword))

    def test_small_features_keep_specific_parent_placements_while_workflow_gets_url(self):
        primary = 'visual editor'
        parent = 'design symbols'
        workflow = 'floor plan maker for architects'
        features = ['resistor symbol', 'editor with resistor symbols', 'drawing using connectors']
        targets = [primary, parent, workflow, *features]
        payload = payload_for(targets[:3])
        payload['pages'][2]['unique_page_value'] = 'Create dimensioned room layouts with architectural constraints.'
        payload['keyword_decisions'] += [
            [keyword, 'supporting', parent, 'h2:Components',
             'Small component: covered within the parent symbol resource.'] for keyword in features
        ]
        plan, chat = self.build(targets, payload, [APPROVED])
        self.assertEqual({page['target_keyword'] for page in plan['spokes']}, {parent, workflow})
        resource = next(page for page in plan['spokes'] if page['target_keyword'] == parent)
        self.assertEqual(set(resource['targeted_keywords']), set(features))
        self.assertEqual(set(resource['h2_sections'][0]['targeted_keywords_placed_here']), set(features))
        self.assertEqual(plan['master_hub']['targeted_keywords'], [])
        for call in chat.await_args_list:
            self.assertIn('FEATURE PAGE TEST', call.kwargs['user_prompt'])
            self.assertIn('drawing using connectors', call.kwargs['user_prompt'])

    def test_discovery_also_applies_the_feature_page_test(self):
        targets = ['visual editor', 'floor plan maker for architects']
        _, chat = self.build(targets, payload_for(targets), [APPROVED], authority=True)
        self.assertIn('FEATURE PAGE TEST', chat.await_args_list[0].kwargs['user_prompt'])
        self.assertIn('subsection/small feature/component', chat.await_args_list[0].kwargs['user_prompt'])

    def test_obvious_modifier_order_variants_share_one_url_in_any_niche(self):
        for topic in ('circuit diagram maker', 'video thumbnail maker'):
            targets = [f'free {topic}', f'free online {topic}', f'online {topic} free']
            with self.subTest(topic=topic):
                plan, _ = self.build(targets, payload_for(targets), [APPROVED])
                self.assertEqual(plan['spokes'], [])
                self.assertEqual(set(plan['master_hub']['targeted_keywords']), set(targets[1:]))
                self.assertEqual(len(plan['intent_consolidations']), 2)

    def test_feature_pages_consolidate_when_one_resource_satisfies_their_needs(self):
        # No circuit/symbol-specific rules: the reviewer compares the actual tasks.
        targets = ['diagram maker', 'diagram maker with electrical symbols',
                   'diagram maker with hydraulic symbols']
        payload = payload_for(targets)
        for index, page in enumerate(payload['pages'][1:]):
            page['content_requirements'] = [f'Include symbol library {index}.']
        conflicts = {'passed': False, 'conflicts': [
            {'page_a': targets[0], 'page_b': target, 'reason': 'Same drawing task; the symbol library is a feature.',
             'risk_type': 'doorway', 'one_page_test': SAME_PAGE}
            for target in targets[1:]
        ]}
        plan, _ = self.build(targets, payload, [conflicts, APPROVED])
        self.assertEqual(plan['spokes'], [])
        self.assertEqual(plan['master_hub']['content_requirements'], ['Include symbol library 0.', 'Include symbol library 1.'])
        self.assertTrue(all(item['risk_type'] == 'doorway' for item in plan['intent_consolidations']))
        self.assertTrue(all(item['to_keyword'] == targets[0] for item in plan['intent_consolidations']))
        self.assertIn('symbol library is a feature', plan['keyword_assignments'][1]['reason'])

    def test_majority_one_page_test_overrides_keyword_format_labels(self):
        targets = ['diagram maker', 'simple diagram maker tool']
        test = {**SAME_PAGE, 'same_serp_intent': False, 'same_entity': False}
        conflict = {'passed': False, 'conflicts': [{
            'page_a': targets[0], 'page_b': targets[1], 'reason': 'Same drawing task and answer.',
            'one_page_test': test,
        }]}
        plan, _ = self.build(targets, payload_for(targets), [conflict, APPROVED])
        self.assertEqual(plan['spokes'], [])

    def test_reviewer_can_choose_comprehensive_resource_over_feature_phrase(self):
        targets = ['diagram maker', 'diagram maker with power symbols', 'schematic symbols']
        conflict = {'passed': False, 'conflicts': [{
            'page_a': targets[1], 'page_b': targets[2], 'preferred_target': targets[2],
            'reason': 'Cover the component family in the comprehensive symbol resource.',
            'risk_type': 'doorway', 'one_page_test': SAME_PAGE,
        }]}
        plan, _ = self.build(targets, payload_for(targets), [conflict, APPROVED])
        self.assertEqual([page['target_keyword'] for page in plan['spokes']], [targets[2]])
        self.assertIn(targets[1], plan['spokes'][0]['targeted_keywords'])
        self.assertEqual(plan['intent_consolidations'][0]['to_keyword'], targets[2])

    def test_invalid_or_minority_one_page_test_cannot_authorize_a_merge(self):
        targets = ['diagram maker', 'best diagram software comparison']
        for test in ({**SAME_PAGE, 'same_user': 'yes'}, {'same_task': True},
                     {**SAME_PAGE, 'same_task': False, 'same_answer': False, 'same_serp_intent': False}):
            with self.subTest(test=test):
                conflict = {'passed': False, 'conflicts': [{
                    'page_a': targets[0], 'page_b': targets[1], 'reason': 'Shared words', 'one_page_test': test,
                }]}
                plan, _ = self.build(targets, payload_for(targets), [conflict, APPROVED])
                self.assertEqual(len(plan['spokes']), 1)

    def test_meaningful_modifier_and_feature_tasks_are_not_blindly_stripped(self):
        targets = ['diagram maker', 'best diagram software comparison', 'diagram software installation',
                   'electrical symbols reference', 'hydraulic symbols reference']
        plan, _ = self.build(targets, payload_for(targets), [APPROVED])
        self.assertEqual(len(plan['spokes']), 4)

    def test_inventory_does_not_merge_different_tasks_by_word_overlap(self):
        from nlp.keywords import check_intent_cannibalization
        self.assertTrue(check_intent_cannibalization(' Circuit Diagram Maker ', 'circuit diagram maker'))
        self.assertFalse(check_intent_cannibalization('circuit diagram maker', 'circuit diagram maker troubleshooting'))
        self.assertFalse(check_intent_cannibalization('usd to eur converter', 'eur to usd converter'))
        self.assertFalse(check_intent_cannibalization('', ''))

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

    def test_invalid_conflict_retry_identifies_bad_reference_and_current_targets(self):
        targets = ['lunar age calculator', 'lunar age meaning']
        invalid = {'passed': False, 'conflicts': [{
            'page_a': targets[0], 'page_b': 'lunar age formula', 'reason': 'Duplicate',
        }]}
        plan, chat = self.build(targets, payload_for(targets), [invalid, APPROVED])
        retry = chat.await_args_list[-1].kwargs['user_prompt']
        self.assertIn("invalid pair 'lunar age calculator' / 'lunar age formula'", retry)
        self.assertIn('supporting keywords are already assigned to pages', retry)
        self.assertIn('Allowed conflict targets', retry)
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
