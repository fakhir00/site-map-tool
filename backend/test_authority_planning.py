"""Behavioral authority-planning tests; model outputs are controlled, not live SEO evidence."""
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from nlp.authority import expand_inventory
from nlp.hub_spoke_agent import ArchitectureAgentError, build_site_architecture


PRIMARY = 'lunar age calculator'
# Different user tasks, not modifier permutations. Fixture input is editorial,
# not claimed search demand or confirmed gaps for the actual website.
TOPICS = [
    ('how to calculate lunar age', 'Manual calculation', 'Method', 'article'),
    ('lunar age vs western age', 'Compare age counting systems', 'Comparisons', 'article'),
    ('nominal age meaning', 'Explain nominal age terminology', 'Foundations', 'article'),
    ('lunar age at birth', 'Explain newborn age counting', 'Foundations', 'article'),
    ('lunar age leap month rules', 'Handle an intercalary birth month', 'Edge cases', 'article'),
    ('lunar age before chinese new year', 'Resolve the birth year boundary', 'Edge cases', 'article'),
    ('lunar age calculation mistakes', 'Diagnose common incorrect inputs', 'Troubleshooting', 'article'),
    ('lunar age formula examples', 'Work through age formula examples', 'Method', 'article'),
    ('chinese lunar calendar explained', 'Understand calendar structure', 'Foundations', 'article'),
    ('lunar age vs gestational age', 'Distinguish calendar age from gestation', 'Comparisons', 'article'),
    ('chinese age vs korean age', 'Compare the two traditional counting rules', 'Comparisons', 'article'),
    ('lunar age calculator accuracy', 'Evaluate implementation accuracy', 'Troubleshooting', 'article'),
    ('gregorian lunar date converter', 'Convert calendar dates interactively', 'Tools', 'tool'),
    ('korean age calculator', 'Calculate traditional Korean age', 'Tools', 'tool'),
    ('islamic lunar age calculator', 'Calculate age in the Hijri calendar', 'Tools', 'tool'),
    ('lunar birthday calculator', 'Find a birthday on the lunar calendar', 'Tools', 'tool'),
    ('lunar age at conception calculator', 'Calculate age for a historical conception date', 'Tools', 'tool'),
    ('chinese gender predictor accuracy', 'Evaluate predictive claims', 'Gender chart', 'article'),
    ('chinese gender chart history', 'Trace the claimed chart origins', 'Gender chart', 'article'),
    ('chinese gender predictor twins', 'Explain the chart limitations for twins', 'Gender chart', 'article'),
    ('chinese conception month conversion', 'Explain conception input conversion', 'Gender chart', 'article'),
    ('chinese gender chart vs mayan chart', 'Compare chart inputs and assumptions', 'Comparisons', 'article'),
    ('vietnamese lunar age traditions', 'Explain the Vietnamese age convention', 'Foundations', 'article'),
    ('lunar age birth time zone', 'Resolve date changes across time zones', 'Edge cases', 'article'),
    ('chinese new year birthday examples', 'Explain age increments at the annual boundary', 'Edge cases', 'article'),
]


def fixture_payload(topics):
    pages = [{'target_keyword': PRIMARY, 'search_intent': 'Calculate lunar age interactively',
              'article_title': 'Lunar Age Calculator', 'page_type': 'tool', 'spoke_category': 'Tools'}]
    pages.extend({'target_keyword': phrase, 'search_intent': intent, 'article_title': phrase.title(),
                  'page_type': kind, 'spoke_category': category, 'content_brief': intent,
                  'intent_class': 'transactional_tool' if kind == 'tool' else 'informational_guide'}
                 for phrase, intent, category, kind in topics)
    return {'master_target': PRIMARY, 'pages': pages, 'keyword_decisions': [
        [p['target_keyword'], 'page_target', p['target_keyword'], 'title', p['search_intent']]
        for p in pages]}


class AuthorityPlanningTests(unittest.TestCase):
    def test_homepage_only_is_validated_without_any_count_shortfall(self):
        chat = AsyncMock(side_effect=[{'proposals': []}, fixture_payload([]),
                                     {'passed': True, 'conflicts': [], 'rejections': []}])
        with patch('nlp.hub_spoke_agent.is_ai_configured', return_value=True), patch(
            'nlp.hub_spoke_agent._achat_json', chat,
        ):
            plan = asyncio.run(build_site_architecture(
                [{'phrase': PRIMARY}], primary_keyword=PRIMARY, discover_topics=True,
            ))
        coverage = plan['authority_coverage']
        self.assertEqual(plan['spokes'], [])
        self.assertEqual(coverage['actual_spokes'], 0)
        self.assertEqual(coverage['status'], 'validated')
        for key in ('target_spokes', 'minimum_spokes', 'maximum_spokes', 'shortfall'):
            self.assertNotIn(key, coverage)
        for call in chat.await_args_list:
            prompt = call.kwargs['user_prompt']
            self.assertIn('There is no minimum or target URL count.', prompt)
            self.assertIn('product capability', prompt)

    def test_discovery_respects_inventory_capacity_without_imposing_a_page_target(self):
        chat = AsyncMock(return_value={'proposals': [
            {'phrase': phrase, 'support_phrase': PRIMARY, 'rationale': intent}
            for phrase, intent, _, _ in TOPICS[:3]
        ]})
        expanded, status = asyncio.run(expand_inventory(
            [{'phrase': PRIMARY}], '', PRIMARY, chat, max_keywords=2,
        ))
        self.assertEqual(len(expanded), 2)
        self.assertEqual(status, 'completed')
        chat.reset_mock()
        unchanged, status = asyncio.run(expand_inventory(expanded, '', PRIMARY, chat, max_keywords=2))
        self.assertEqual(unchanged, expanded)
        self.assertEqual(status, 'inventory_limit')
        chat.assert_not_awaited()

    def test_expansion_requires_exact_evidence_and_never_inherits_fake_metrics(self):
        records = [{'phrase': PRIMARY}]
        chat = AsyncMock(return_value={'proposals': [
            {'phrase': 'lunar age leap month rules', 'support_phrase': PRIMARY,
             'rationale': 'Birth month edge case', 'search_volume': 90000, 'difficulty': 1},
            {'phrase': 'chinese zodiac calculator', 'support_phrase': 'absent evidence', 'rationale': 'Nearby'},
            {'phrase': 'lunar age leap month rules', 'support_phrase': PRIMARY, 'rationale': 'Duplicate'},
        ]})
        expanded, status = asyncio.run(expand_inventory(records, '', PRIMARY, chat))
        self.assertEqual(status, 'completed')
        self.assertEqual(len(expanded), 2)
        self.assertIsNone(expanded[1]['search_volume'])
        self.assertIsNone(expanded[1]['difficulty'])
        self.assertEqual(expanded[1]['frequency'], 0)
        self.assertEqual(expanded[1]['evidence_type'], 'editorial_proposal')

    def test_full_pipeline_builds_25_distinct_spokes_and_reuses_owned_url(self):
        payload = fixture_payload(TOPICS)
        payload['pages'][13]['existing_url'] = 'https://example.com/calendar-conversion/'
        context = json.dumps({'owned_pages': [{'url': 'https://example.com/calendar-conversion/',
                                              'title': 'Gregorian Lunar Date Converter'}]})
        proposals = {'proposals': [{'phrase': phrase, 'support_phrase': PRIMARY,
                                   'rationale': intent} for phrase, intent, _, _ in TOPICS]}
        with patch('nlp.hub_spoke_agent.is_ai_configured', return_value=True), patch(
            'nlp.hub_spoke_agent._achat_json', new=AsyncMock(side_effect=[
                proposals, payload, {'passed': True, 'conflicts': [], 'rejections': []},
            ]),
        ) as chat:
            plan = asyncio.run(build_site_architecture([{'phrase': PRIMARY}], context=context,
                                                       primary_keyword=PRIMARY, discover_topics=True))
        self.assertEqual(len(plan['spokes']), 25)
        accuracy = next(p for p in plan['spokes'] if p['target_keyword'] == 'lunar age calculator accuracy')
        self.assertEqual(accuracy['page_type'], 'article')
        self.assertEqual(plan['authority_coverage']['status'], 'validated')
        self.assertEqual(plan['authority_coverage']['existing_spokes'], 1)
        self.assertEqual(plan['authority_coverage']['new_spokes'], 24)
        self.assertEqual(len({p['slug'] for p in plan['spokes']}), 25)
        self.assertEqual(len(plan['master_hub']['internal_links']), 25)
        self.assertTrue(all(PRIMARY in p['internal_links'] for p in plan['spokes']))
        self.assertTrue(all(p['search_volume'] is None for p in plan['spokes']))
        self.assertIn('There is no minimum or target URL count.', chat.await_args_list[1].kwargs['user_prompt'])
        updated = next(p for p in plan['spokes'] if p['action'] == 'update')
        self.assertEqual(updated['slug'], '/calendar-conversion/')

    def test_small_plan_is_validated_without_promoting_same_intent_variants(self):
        payload = fixture_payload(TOPICS[:1])
        variant = 'free lunar age calculator'
        payload['keyword_decisions'].append([variant, 'supporting', PRIMARY, 'feature', 'Same tool'])
        records = [{'phrase': PRIMARY}, {'phrase': TOPICS[0][0]}, {'phrase': variant}]
        with patch('nlp.hub_spoke_agent.is_ai_configured', return_value=True), patch(
            'nlp.hub_spoke_agent._achat_json', new=AsyncMock(side_effect=[
                {'proposals': []}, payload, {'passed': True, 'conflicts': [], 'rejections': []},
            ]),
        ):
            plan = asyncio.run(build_site_architecture(records, primary_keyword=PRIMARY, discover_topics=True))
        self.assertEqual(len(plan['spokes']), 1)
        self.assertEqual(plan['authority_coverage']['status'], 'validated')
        self.assertNotIn('shortfall', plan['authority_coverage'])
        self.assertIn(variant, plan['master_hub']['targeted_keywords'])

    def test_unavailable_discovery_and_review_are_not_reported_as_success(self):
        payload = fixture_payload(TOPICS[:1])
        with patch('nlp.hub_spoke_agent.is_ai_configured', return_value=True), patch(
            'nlp.hub_spoke_agent._achat_json', new=AsyncMock(side_effect=[
                RuntimeError('discovery unavailable'), payload, RuntimeError('review unavailable'),
            ]),
        ):
            with self.assertRaisesRegex(ArchitectureAgentError, 'previous saved map is unchanged'):
                asyncio.run(build_site_architecture(
                    [{'phrase': PRIMARY}, {'phrase': TOPICS[0][0]}], primary_keyword=PRIMARY, discover_topics=True))
