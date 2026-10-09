"""Behavioral authority-planning tests; model outputs are controlled, not live SEO evidence."""
from architecture_test_fixtures import approved_review
import asyncio
import json
import unittest
from unittest.mock import AsyncMock, patch

from nlp.authority import expand_inventory, reconcile_owned_pages
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
    def test_discovery_recovers_wrapped_and_list_responses(self):
        proposal = {'phrase': TOPICS[0][0], 'support_phrase': PRIMARY, 'rationale': TOPICS[0][1]}
        for payload in ({'result': json.dumps({'proposals': [proposal]})}, [proposal], [{'proposals': [proposal]}]):
            with self.subTest(payload=payload):
                expanded, status = asyncio.run(expand_inventory(
                    [{'phrase': PRIMARY}], '', PRIMARY, AsyncMock(return_value=payload)))
                self.assertEqual(status, 'completed')
                self.assertEqual(expanded[-1]['phrase'], TOPICS[0][0])

    def test_discovery_retries_transient_failure_and_retains_evidence(self):
        chat = AsyncMock(side_effect=[TimeoutError(), {'proposals': [
            {'phrase': TOPICS[0][0], 'support_phrase': PRIMARY, 'rationale': TOPICS[0][1]}]}])
        diagnostics = []
        expanded, status = asyncio.run(expand_inventory(
            [{'phrase': PRIMARY}], '', PRIMARY, chat, diagnostics=diagnostics))
        self.assertEqual(chat.await_count, 2)
        self.assertEqual(status, 'completed')
        self.assertEqual(len(expanded), 2)
        self.assertEqual(diagnostics, [])
        self.assertEqual(chat.await_args.kwargs['request_timeout'], 60)

    def test_invalid_proposals_are_not_reported_as_successful_research(self):
        chat = AsyncMock(return_value={'proposals': [
            {'phrase': 'invented unrelated topic', 'support_phrase': 'not in inventory', 'rationale': 'Guess'}]})
        diagnostics = []
        records, status = asyncio.run(expand_inventory(
            [{'phrase': PRIMARY}], '', PRIMARY, chat, diagnostics=diagnostics))
        self.assertEqual(status, 'unavailable')
        self.assertEqual(len(records), 1)
        self.assertEqual(chat.await_count, 2)
        self.assertIn('evidence', diagnostics[0])

    def test_failed_discovery_cannot_publish_a_successful_zero_spoke_map(self):
        payload = fixture_payload([])
        with patch('nlp.hub_spoke_agent.is_ai_configured', return_value=True), patch(
            'nlp.hub_spoke_agent._achat_json', new=AsyncMock(side_effect=[
                TimeoutError(), TimeoutError(), payload, approved_review(payload),
            ]),
        ):
            with self.assertRaisesRegex(ArchitectureAgentError, 'previous saved map is unchanged'):
                asyncio.run(build_site_architecture([{'phrase': PRIMARY}], primary_keyword=PRIMARY, discover_topics=True))

    def test_failed_discovery_marks_an_inventory_based_map_partial(self):
        payload = fixture_payload(TOPICS[:1])
        with patch('nlp.hub_spoke_agent.is_ai_configured', return_value=True), patch(
            'nlp.hub_spoke_agent._achat_json', new=AsyncMock(side_effect=[
                TimeoutError(), TimeoutError(), payload, approved_review(payload),
            ]),
        ):
            plan = asyncio.run(build_site_architecture(
                [{'phrase': PRIMARY}, {'phrase': TOPICS[0][0]}], primary_keyword=PRIMARY, discover_topics=True))
        self.assertEqual(plan['authority_coverage']['status'], 'partial')
        self.assertIn('timed out', plan['authority_coverage']['discovery_message'])

    def test_homepage_only_is_validated_without_any_count_shortfall(self):
        chat = AsyncMock(side_effect=[{'proposals': []}, fixture_payload([]),
                                     approved_review(fixture_payload([]))])
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
                proposals, payload, approved_review(payload),
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
                {'proposals': []}, payload, approved_review(payload),
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
                RuntimeError('discovery unavailable'), RuntimeError('discovery unavailable'), payload, RuntimeError('review unavailable'),
            ]),
        ):
            with self.assertRaisesRegex(ArchitectureAgentError, 'previous saved map is unchanged'):
                asyncio.run(build_site_architecture(
                    [{'phrase': PRIMARY}, {'phrase': TOPICS[0][0]}], primary_keyword=PRIMARY, discover_topics=True))


class OwnedPageMatchingTests(unittest.TestCase):
    def plan(self):
        return {'master_hub': {'target_keyword': PRIMARY, 'slug': '/', 'action': 'create'},
                'spokes': [{'target_keyword': 'manual lunar age', 'article_title': 'Calculate Lunar Age by Hand',
                            'slug': '/new-manual-guide/', 'action': 'create'}],
                'link_plan': [{'source_keyword': PRIMARY, 'target_keyword': 'manual lunar age',
                               'source_url': '/', 'target_url': '/new-manual-guide/'}]}

    def test_same_title_reuses_owned_page_despite_different_keyword_and_slug(self):
        context = json.dumps({'owned_pages': [{'url': 'https://example.com/established-guide/',
                                              'title': 'Calculate Lunar Age by Hand!'}]})
        plan = reconcile_owned_pages(self.plan(), context)
        self.assertEqual(plan['spokes'][0]['action'], 'update')
        self.assertEqual(plan['spokes'][0]['slug'], '/established-guide/')
        self.assertEqual(plan['link_plan'][0]['target_url'], 'https://example.com/established-guide/')
        self.assertEqual(plan['master_hub']['action'], 'create')

    def test_url_equivalents_keep_the_original_owned_url(self):
        plan = self.plan()
        plan['spokes'][0]['existing_url'] = 'http://www.example.com/guide#examples'
        context = json.dumps({'owned_pages': [{'url': 'https://example.com/guide/'}]})
        reconcile_owned_pages(plan, context)
        self.assertEqual(plan['spokes'][0]['existing_url'], 'https://example.com/guide/')

    def test_nested_url_matches_keyword_without_crawl_text(self):
        plan = reconcile_owned_pages(self.plan(), json.dumps({'owned_pages': [
            {'url': 'https://example.com/blog/manual-lunar-age/'}]}))
        self.assertEqual(plan['spokes'][0]['action'], 'update')

    def test_distinct_tasks_and_query_pages_are_not_matched_by_shared_words(self):
        plan = reconcile_owned_pages(self.plan(), json.dumps({'owned_pages': [
            {'url': 'https://example.com/?topic=other'},
            {'url': 'https://example.com/age/', 'title': 'Lunar age calculator accuracy'}]}))
        self.assertTrue(all(page['action'] == 'create' for page in [plan['master_hub'], *plan['spokes']]))

    def test_unowned_urls_and_two_intents_for_one_url_are_rejected(self):
        plan = self.plan()
        plan['spokes'][0]['existing_url'] = 'https://competitor.example/guide/'
        with self.assertRaisesRegex(ValueError, 'outside the owned-page inventory'):
            reconcile_owned_pages(plan, '{}')
        plan = self.plan()
        plan['spokes'].append(dict(plan['spokes'][0], target_keyword='other task'))
        with self.assertRaisesRegex(ValueError, 'same existing URL'):
            reconcile_owned_pages(plan, json.dumps({'owned_pages': [
                {'url': 'https://example.com/new-manual-guide/'}]}))
