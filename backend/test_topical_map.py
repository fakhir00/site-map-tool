"""Regression cases for the page graph, exact placements and bounded planner."""
from architecture_test_fixtures import approved_review
import asyncio
import copy
import json
import unittest
from unittest.mock import AsyncMock, patch

from nlp.hub_spoke_agent import (
    ArchitectureAgentError, _apply_assignments, _normalize_plan, build_site_architecture,
)
from nlp.topical_map import attach_topical_map
from test_authority_planning import PRIMARY, TOPICS, fixture_payload


class TopicalMapTests(unittest.TestCase):
    def plan(self):
        records = [{'phrase': PRIMARY}, *({'phrase': topic[0]} for topic in TOPICS[:3])]
        return _apply_assignments(_normalize_plan(fixture_payload(TOPICS[:3]), records, PRIMARY))

    def test_all_edges_resolve_and_existing_urls_are_preserved(self):
        plan = self.plan()
        parent, child = plan['spokes'][:2]
        parent['existing_url'] = 'https://example.com/established-method/?version=1'
        child['parent_target'] = parent['target_keyword']
        child['internal_links'] += ['unknown target', child['target_keyword']]
        result = attach_topical_map(plan)
        pages = [result['master_hub'], *result['spokes']]
        ids = {page['id'] for page in pages}
        self.assertTrue(all(edge['source'] in ids and edge['target'] in ids for edge in result['link_plan']))
        self.assertTrue(all(edge['source'] != edge['target'] for edge in result['link_plan']))
        edge = next(e for e in result['link_plan'] if e['source'] == child['id'] and e['target'] == parent['id'])
        self.assertEqual(edge['target_url'], parent['existing_url'])
        self.assertEqual(edge['relationship'], 'parent')
        self.assertEqual(sum(len(group['page_ids']) for group in result['topic_clusters']), 3)
        self.assertEqual({page['id'] for page in attach_topical_map(copy.deepcopy(plan))['spokes']}, ids - {pages[0]['id']})

    def test_homepage_links_to_entry_points_and_only_selected_deeper_pages(self):
        plan = self.plan()
        parent, child, featured = plan['spokes']
        parent['parent_target'] = PRIMARY
        child['parent_target'] = parent['target_keyword']
        featured['parent_target'] = parent['target_keyword']
        for page in [plan['master_hub'], *plan['spokes']]:
            page['internal_links'] = []
        plan['master_hub']['internal_links'] = [featured['target_keyword']]
        result = attach_topical_map(_apply_assignments(plan))
        links = {(edge['source_keyword'], edge['target_keyword']) for edge in result['link_plan']}
        self.assertEqual(set(result['master_hub']['internal_links']),
                         {parent['target_keyword'], featured['target_keyword']})
        self.assertNotIn((PRIMARY, child['target_keyword']), links)
        self.assertNotIn((child['target_keyword'], PRIMARY), links)
        self.assertIn((parent['target_keyword'], child['target_keyword']), links)
        self.assertIn((child['target_keyword'], parent['target_keyword']), links)
        self.assertIn((parent['target_keyword'], featured['target_keyword']), links)
        again = attach_topical_map(_apply_assignments(result))
        self.assertEqual({(edge['source_keyword'], edge['target_keyword']) for edge in again['link_plan']}, links)

    def test_invalid_and_circular_parents_still_reach_the_main_hub(self):
        plan = self.plan()
        first, second, third = plan['spokes']
        first['parent_target'] = second['target_keyword']
        second['parent_target'] = first['target_keyword']
        third['parent_target'] = 'a nonexistent target'
        result = attach_topical_map(plan)
        by_target = {page['target_keyword']: page for page in result['spokes']}
        for target in by_target:
            visited = set()
            while target != PRIMARY:
                self.assertNotIn(target, visited)
                visited.add(target)
                target = by_target[target]['parent_target']
        self.assertEqual(len(result['map_warnings']), 2)

    def test_keywords_keep_specific_sections_instead_of_all_falling_into_first_heading(self):
        plan = self.plan()
        page = plan['spokes'][0]
        page['h2_sections'] = [
            {'h2_heading': 'Choose the dates', 'targeted_keywords_placed_here': []},
            {'h2_heading': 'Apply the formula', 'targeted_keywords_placed_here': []},
        ]
        for keyword, placement in [('lunar age arithmetic', 'h2:apply the formula'),
                                   ('lunar age walkthrough', 'h2'), ('lunar age questions', 'faq:Which date counts?')]:
            plan['keyword_assignments'].append({'keyword': keyword, 'disposition': 'supporting',
                'assigned_to': page['target_keyword'], 'placement': placement, 'reason': 'Same reader task'})
        _apply_assignments(plan)
        self.assertEqual(page['h2_sections'][0]['targeted_keywords_placed_here'], [])
        self.assertEqual(page['h2_sections'][1]['targeted_keywords_placed_here'], ['lunar age arithmetic'])
        self.assertEqual(page['faq_schema_questions'][0]['targeted_keywords_placed_here'], ['lunar age questions'])
        self.assertIn('lunar age walkthrough', page['targeted_keywords'])

    def test_small_map_is_valid_without_a_second_full_generation(self):
        records = [{'phrase': PRIMARY}, *({'phrase': topic[0]} for topic in TOPICS)]
        payload = fixture_payload(TOPICS[:1])
        for topic in TOPICS[1:]:
            payload['keyword_decisions'].append([topic[0], 'supporting', PRIMARY, 'variation', 'Fixture consolidation'])
        chat = AsyncMock(side_effect=[{'proposals': []}, payload, approved_review(payload)])
        with patch('nlp.hub_spoke_agent.is_ai_configured', return_value=True), patch('nlp.hub_spoke_agent._achat_json', chat):
            result = asyncio.run(build_site_architecture(records, primary_keyword=PRIMARY, discover_topics=True))
        self.assertEqual(chat.await_count, 3)
        self.assertEqual(result['authority_coverage']['status'], 'validated')
        self.assertEqual(result['map_version'], 2)

    def test_authority_format_follows_reader_task_even_without_tool_keyword_or_volume(self):
        topic = ('days between two dates', 'Find a date interval', 'Date arithmetic', 'tool')
        payload = fixture_payload([topic])
        with patch('nlp.hub_spoke_agent.is_ai_configured', return_value=True), patch('nlp.hub_spoke_agent._achat_json', new=AsyncMock(side_effect=[
            {'proposals': []}, payload, approved_review(payload),
        ])):
            result = asyncio.run(build_site_architecture([{'phrase': PRIMARY}, {'phrase': topic[0]}], primary_keyword=PRIMARY, discover_topics=True))
        self.assertEqual(result['spokes'][0]['page_type'], 'tool')
        self.assertIsNone(result['spokes'][0]['search_volume'])

    def test_same_task_with_different_intent_labels_is_merged(self):
        payload = fixture_payload(TOPICS[:2])
        payload['pages'][2]['intent_class'] = 'definition'
        conflict = {'passed': False, 'conflicts': [{'page_a': TOPICS[0][0], 'page_b': TOPICS[1][0], 'reason': 'Fixture: same task'}]}
        with patch('nlp.hub_spoke_agent.is_ai_configured', return_value=True), patch('nlp.hub_spoke_agent._achat_json', new=AsyncMock(side_effect=[
            {'proposals': []}, payload, conflict, approved_review(payload),
        ])):
            result = asyncio.run(build_site_architecture([{'phrase': PRIMARY}, *({'phrase': t[0]} for t in TOPICS[:2])], primary_keyword=PRIMARY, discover_topics=True))
        self.assertEqual(len(result['spokes']), 1)
        self.assertEqual(result['_semantic_audit_status'], 'passed')

    def test_deadline_returns_actionable_failure(self):
        with patch('nlp.hub_spoke_agent._build_site_architecture', new=AsyncMock(side_effect=TimeoutError)):
            with self.assertRaisesRegex(ArchitectureAgentError, 'previous saved map is unchanged'):
                asyncio.run(build_site_architecture([{'phrase': PRIMARY}], discover_topics=True))

    def test_page_brief_reaches_the_actual_writing_prompt(self):
        from nlp.openrouter import write_prompt
        brief = {'outline': [], 'architecture_requirements': 'Preserve /manual-method/. Link to /calculator/. Exclude date conversion.'}
        with patch('nlp.openrouter._chat_text', return_value='Prompt') as chat:
            write_prompt(project_name='Test', primary_keyword='manual age method', brief=brief, competitor_pages=[])
        self.assertIn(brief['architecture_requirements'], chat.call_args.kwargs['user_prompt'])
        self.assertIn('takes precedence', chat.call_args.kwargs['user_prompt'])
        self.assertIn('Every page = enough content to completely satisfy its unique intent.', chat.call_args.kwargs['user_prompt'])

    def test_page_requirements_survive_normalization_without_a_word_quota(self):
        payload = fixture_payload(TOPICS[:1])
        raw = payload['pages'][1]
        raw.update({
            'word_count_suggestion': 1800,
            'user_problem': 'Determine which year boundary to use.',
            'entity_topic': 'Lunar age year boundaries',
            'content_requirements': ['Explain the boundary rule.', 'Show a worked date example.'],
            'url_decision_reason': 'The manual method needs a separate explanation from the tool.',
        })
        records = [{'phrase': PRIMARY}, {'phrase': TOPICS[0][0]}]
        plan = _normalize_plan(payload, records, PRIMARY)
        for page in [plan['master_hub'], *plan['spokes']]:
            self.assertNotIn('word_count_suggestion', page)
        for field in ('user_problem', 'entity_topic', 'content_requirements', 'url_decision_reason'):
            self.assertEqual(plan['spokes'][0][field], raw[field])

    def test_short_answer_reaches_semantic_audit_without_length_or_heading_quotas(self):
        from app.content.service import generate_final_article_package
        draft = '# Nominal age meaning\n\nNominal age counts a newborn as one and adds a year at the traditional new year.'
        brief = {'content_requirements': ['Define nominal age and when it increments.']}
        with patch('app.content.service.is_ai_configured', return_value=True), patch(
            'app.content.service.write_final_article', return_value=draft,
        ), patch('app.content.service.audit_article', return_value={
            'score': 95, 'keyword_intent_score': 95, 'gap_coverage_score': 95, 'passed': True,
        }) as audit:
            result = generate_final_article_package(
                primary_keyword='nominal age meaning', master_prompt='Define the term.', brief=brief,
            )
        self.assertEqual(result['status'], 'passed')
        audit.assert_called_once_with(primary_keyword='nominal age meaning', brief=brief, article_markdown=draft)

    def test_large_inventory_is_rejected_before_spending_provider_credits(self):
        with patch('nlp.hub_spoke_agent._achat_json', new=AsyncMock()) as chat:
            with self.assertRaisesRegex(ArchitectureAgentError, '300 distinct keywords'):
                asyncio.run(build_site_architecture([{'phrase': f'lunar age topic {index}'} for index in range(301)], discover_topics=True))
        chat.assert_not_awaited()

    def test_merging_preserves_existing_page_outline_and_redirects_incoming_links(self):
        from nlp.hub_spoke_agent import _merge_intent_conflicts
        plan = self.plan()
        first, second, referring = plan['spokes']
        second['existing_url'] = 'https://example.com/established-guide/'
        first['h2_sections'] = [{'h2_heading': 'Worked examples', 'targeted_keywords_placed_here': []}]
        first['content_requirements'] = ['Show a worked example.']
        second['content_requirements'] = ['Explain the method.']
        referring['internal_links'] = [first['target_keyword']]
        result, _ = _merge_intent_conflicts(plan, [{'page_a': first['target_keyword'], 'page_b': second['target_keyword'], 'reason': 'Same task'}])
        self.assertNotIn(first, result['spokes'])
        self.assertIn(second, result['spokes'])
        self.assertEqual(second['h2_sections'][0]['h2_heading'], 'Worked examples')
        self.assertIn(second['target_keyword'], referring['internal_links'])
        self.assertEqual(second['content_requirements'], ['Explain the method.', 'Show a worked example.'])
