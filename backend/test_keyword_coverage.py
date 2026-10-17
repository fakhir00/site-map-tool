"""Offline regressions for keyword loss and evidence-backed topical expansion."""
import asyncio
from copy import deepcopy
import json
import unittest
from unittest.mock import AsyncMock, patch

from architecture_test_fixtures import approved_review
from nlp.hub_spoke_agent import (
    _apply_assignments, _normalize_plan, _repair_plan_consistency,
    _review_keyword_coverage, build_site_architecture, normalize_keyword_records,
    validate_architecture,
)
from nlp.keywords import is_topic_relevant_keyword
from nlp.openrouter import generate_core_domain_terms
from nlp.providers import ProviderUnavailableError
from workers.pipeline import _semantic_terms


def animal_inventory():
    primary = "spirit animal quiz"
    pages = [{"target_keyword": primary, "article_title": "Spirit Animal Quiz",
              "search_intent": "Discover your animal personality", "page_type": "tool",
              "content_brief": "A personality quiz with supported animal result profiles."}]
    assignments = [[primary, "page_target", primary, "title", "Main discovery task."]]
    records = [{"phrase": primary}]
    destinations = {}
    for animal in ("wolf", "owl", "bear", "fox", "eagle", "deer"):
        target = f"{animal} spirit animal meaning"
        pages.append({"target_keyword": target, "article_title": f"{animal.title()} Personality and Meaning",
                      "search_intent": f"Understand your {animal} personality result", "page_type": "article",
                      "content_brief": f"Explain the {animal} personality result and its symbolism.",
                      "existing_url": f"https://animals.example/{animal}/",
                      "h2_sections": [{"h2_heading": "Personality traits"}]})
        assignments.append([target, "page_target", target, "title", "Distinct animal result profile."])
        phrases = [target, f"{animal} personality traits", f"{animal} animal symbolism",
                   f"what does the {animal} represent", f"{animal} personality strengths",
                   f"{animal} personality weaknesses", f"{animal} personality in relationships",
                   f"{animal} personality at work", f"{animal} spirit animal characteristics",
                   f"signs of a {animal} personality", f"{animal} personality compatibility",
                   f"understanding your {animal} quiz result"]
        records.extend({"phrase": phrase} for phrase in phrases)
        destinations.update({phrase: target for phrase in phrases[1:]})
    return primary, normalize_keyword_records(records), {"pages": pages, "keyword_decisions": assignments}, destinations


def coverage_reply(prompt, destinations):
    batch = json.loads(prompt.split("Keywords to review: ", 1)[1].split("\n", 1)[0])
    return {"keyword_decisions": [
        [item["phrase"], "supporting", destinations[item["phrase"]], "h2:Personality traits",
         "Animal quiz → supported animal profile → personality question; answer in the existing profile."]
        for item in batch
    ], "pages": []}


class KeywordCoverageTests(unittest.TestCase):
    def test_grouped_transport_preserves_supporting_placements_and_exclusions(self):
        primary, records, payload, destinations = animal_inventory()
        records = normalize_keyword_records([*records, {"phrase": "facebook login"}])
        refs = {item['phrase']: f'k{index}' for index, item in enumerate(records)}
        compact = {'master_target': refs[primary], 'pages': [],
                   'discarded': [[refs['facebook login'], 'Unrelated navigation to another service.']]}
        for page in payload['pages']:
            target = page['target_keyword']
            members = [refs[phrase] for phrase, owner in destinations.items() if owner == target]
            compact['pages'].append([
                refs[target], page['article_title'], page['search_intent'], 'Animal profiles',
                page['page_type'], page.get('existing_url'), None if target == primary else refs[primary],
                page['content_brief'], ['Explain the personality traits and strengths.'], ['Personality traits'], [],
                [['h2:Personality traits', members, 'Answers the animal result questions.']] if members else [],
            ])
        with patch('nlp.hub_spoke_agent.is_ai_configured', return_value=True), patch(
            'nlp.hub_spoke_agent._achat_json', new=AsyncMock(side_effect=[compact, approved_review(payload)]),
        ):
            plan = asyncio.run(build_site_architecture(records, primary_keyword=primary, context=json.dumps({
                'owned_pages': [{'url': page['existing_url']} for page in payload['pages'][1:]],
            })))
        self.assertEqual(plan['keyword_coverage'], {'total': 74, 'used': 73, 'page_targets': 7, 'supporting': 66, 'excluded': 1})
        self.assertEqual(plan['_semantic_audit_status'], 'passed')
        self.assertTrue(all(page['action'] == 'update' for page in plan['spokes']))
        self.assertTrue(all(len(page['h2_sections'][0]['targeted_keywords_placed_here']) == 11 for page in plan['spokes']))

    def test_coverage_resolves_only_unambiguous_planned_urls(self):
        for mode in ('known', 'unknown', 'ambiguous'):
            with self.subTest(mode=mode):
                primary, records, payload, destinations = animal_inventory()
                if mode == 'ambiguous':
                    payload['pages'][2]['existing_url'] = payload['pages'][1]['existing_url']
                plan = _repair_plan_consistency(_normalize_plan(payload, records, primary), records, primary)
                urls = {page['target_keyword']: page.get('existing_url') for page in payload['pages']}
                async def respond(**kwargs):
                    reply = coverage_reply(kwargs['user_prompt'], destinations)
                    for row in reply['keyword_decisions']:
                        row[2] = urls[row[2]] if mode != 'unknown' else 'https://other.example/unknown/'
                    return reply
                async def run():
                    return await _review_keyword_coverage(plan, records, 'Animal profiles', deadline=asyncio.get_running_loop().time() + 45)
                with patch('nlp.hub_spoke_agent._achat_json', side_effect=respond):
                    if mode == 'known':
                        result = _apply_assignments(asyncio.run(run()))
                        self.assertEqual(result['keyword_coverage']['used'], 73)
                        self.assertEqual(validate_architecture(result, records, primary), [])
                    else:
                        before = deepcopy(plan)
                        with self.assertRaisesRegex(ValueError, 'valid page'):
                            asyncio.run(run())
                        self.assertEqual(plan, before)

    def test_compact_large_plan_preserves_all_keywords_owned_urls_and_page_briefs(self):
        primary, records, payload, destinations = animal_inventory()
        refs = {item['phrase']: f'k{index}' for index, item in enumerate(records)}
        targets = {page['target_keyword'] for page in payload['pages']}
        compact = {'master_target': refs[primary], 'pages': [[
            refs[page['target_keyword']], page['article_title'], page['search_intent'], 'Animal profiles',
            page['page_type'], page.get('existing_url'), None if page['target_keyword'] == primary else refs[primary],
            page['content_brief'], ['Explain the personality traits and strengths.'], ['Personality traits'], [],
        ] for page in payload['pages']], 'keyword_decisions': [[
            refs[item['phrase']], 'page_target' if item['phrase'] in targets else 'supporting',
            refs[item['phrase'] if item['phrase'] in targets else destinations[item['phrase']]],
            'title' if item['phrase'] in targets else 'h2:Personality traits', 'Supported animal interpretation',
        ] for item in records]}
        chat = AsyncMock(side_effect=[compact, approved_review(payload)])
        with patch('nlp.hub_spoke_agent.is_ai_configured', return_value=True), patch('nlp.hub_spoke_agent._achat_json', chat):
            plan = asyncio.run(build_site_architecture(records, primary_keyword=primary, context=json.dumps({
                'owned_pages': [{'url': page['existing_url']} for page in payload['pages'][1:]],
            })))
        self.assertIn('COMPACT OUTPUT CONTRACT', chat.await_args_list[0].kwargs['user_prompt'])
        self.assertEqual(plan['keyword_coverage']['used'], 73)
        self.assertEqual(plan['keyword_coverage']['supporting'], 66)
        self.assertTrue(all(page['action'] == 'update' for page in plan['spokes']))
        self.assertTrue(all(page['content_requirements'] for page in plan['spokes']))
        self.assertEqual(plan['_semantic_audit_status'], 'passed')

    def test_full_build_uses_73_keywords_across_seven_pages_without_duplicate_urls(self):
        primary, records, payload, destinations = animal_inventory()
        coverage_batches = []

        async def respond(**kwargs):
            if "placement reviewer" in kwargs["system_prompt"]:
                result = coverage_reply(kwargs["user_prompt"], destinations)
                coverage_batches.append(result)
                return result
            if "information architect" in kwargs["system_prompt"]:
                return deepcopy(payload)
            return approved_review(payload)

        with patch("nlp.hub_spoke_agent.is_ai_configured", return_value=True), patch(
            "nlp.hub_spoke_agent._achat_json", side_effect=respond,
        ):
            plan = asyncio.run(build_site_architecture(
                records, primary_keyword=primary,
                context=json.dumps({
                    "capabilities": ["Animal personality quiz with wolf, owl, bear, fox, eagle and deer result profiles."],
                    "owned_pages": [{"url": page["existing_url"], "title": page["article_title"]} for page in payload["pages"][1:]],
                }),
            ))
        self.assertEqual(len(coverage_batches), 3)
        self.assertEqual(plan["keyword_coverage"], {"total": 73, "used": 73, "page_targets": 7, "supporting": 66, "excluded": 0})
        self.assertEqual(len(plan["spokes"]), 6)
        self.assertEqual(plan["_semantic_audit_status"], "passed")
        self.assertEqual(validate_architecture(plan, records, primary), [])
        for page in plan["spokes"]:
            self.assertTrue(page["existing_url"].startswith("https://animals.example/"))
            self.assertEqual(len(page["targeted_keywords"]), 11)
            self.assertEqual(len(page["h2_sections"][0]["targeted_keywords_placed_here"]), 11)
            self.assertIsNone(page["search_volume"])

    def test_duplicate_intent_is_reviewed_as_supporting_and_hard_reject_is_not_restored(self):
        primary, records, payload, destinations = animal_inventory()
        wanted = next(iter(destinations))
        records = normalize_keyword_records([{"phrase": primary}, {"phrase": wanted}, {"phrase": "facebook login"}])
        payload = {"pages": payload["pages"][:1], "keyword_decisions": [
            [primary, "page_target", primary, "title", "Primary task"],
            [wanted, "discard", None, None, "Duplicate intent, low volume"],
            ["facebook login", "discard", None, None, "Duplicate intent"],
        ]}
        plan = _repair_plan_consistency(_normalize_plan(payload, records, primary), records, primary)
        reply = {"keyword_decisions": [[wanted, "supporting", primary, "faq:What does your result mean?", "Answer the result subquestion on the quiz."]]}
        async def run():
            return await _review_keyword_coverage(plan, records, "Quiz with animal results", deadline=asyncio.get_running_loop().time() + 45)
        with patch("nlp.hub_spoke_agent._achat_json", new=AsyncMock(return_value=reply)) as model:
            result = asyncio.run(run())
        self.assertNotIn('"phrase": "facebook login"', model.call_args.kwargs["user_prompt"])
        result = _apply_assignments(result)
        self.assertEqual(result["keyword_coverage"]["used"], 2)
        self.assertEqual(result["keyword_coverage"]["excluded"], 1)

    def test_failed_batch_does_not_commit_partial_coverage_or_invented_targets(self):
        for failure in ("missing", "invented_destination"):
            with self.subTest(failure=failure):
                primary, records, payload, destinations = animal_inventory()
                plan = _repair_plan_consistency(_normalize_plan(payload, records, primary), records, primary)
                before = deepcopy(plan)
                async def respond(**kwargs):
                    reply = coverage_reply(kwargs["user_prompt"], destinations)
                    if failure == "missing":
                        reply["keyword_decisions"].pop()
                    else:
                        reply["keyword_decisions"][0][2] = "invented animal page"
                    return reply
                async def run():
                    return await _review_keyword_coverage(plan, records, "Animal profiles", deadline=asyncio.get_running_loop().time() + 45)
                with patch("nlp.hub_spoke_agent._achat_json", side_effect=respond), self.assertRaises(ValueError):
                    asyncio.run(run())
                self.assertEqual(plan, before)

    def test_malformed_placement_is_repaired_without_rebuilding_valid_pages(self):
        primary, records, payload, destinations = animal_inventory()
        wanted = next(iter(destinations))
        records = normalize_keyword_records([{'phrase': primary}, {'phrase': wanted}])
        plan = _repair_plan_consistency(_normalize_plan({'pages': payload['pages'][:1]}, records, primary), records, primary)
        before = deepcopy(plan['master_hub'])
        bad = {'keyword_decisions': [[wanted, 'supporting', 'https://unknown.example/', 'h2:Result', 'Explain the result']]}
        good = {'keyword_decisions': [[wanted, 'supporting', primary, 'h2:Result', 'Explain the supported animal result']]}
        async def run():
            return await _review_keyword_coverage(plan, records, 'Quiz with animal results', deadline=asyncio.get_running_loop().time() + 45)
        with patch('nlp.hub_spoke_agent._achat_json', new=AsyncMock(side_effect=[bad, good])) as chat:
            result = asyncio.run(run())
        self.assertEqual(chat.await_count, 2)
        self.assertIn('https://unknown.example/', chat.await_args_list[1].kwargs['user_prompt'])
        self.assertEqual(result['master_hub'], before)
        self.assertEqual(_apply_assignments(result)['keyword_coverage']['used'], 2)

    def test_provider_failure_keeps_coverage_unassigned_and_is_not_hidden_by_batching(self):
        primary, records, payload, _ = animal_inventory()
        plan = _repair_plan_consistency(_normalize_plan(payload, records, primary), records, primary)
        before = deepcopy(plan)
        async def run():
            return await _review_keyword_coverage(plan, records, "Animal profiles", deadline=asyncio.get_running_loop().time() + 45)
        with patch("nlp.hub_spoke_agent._achat_json", new=AsyncMock(side_effect=ProviderUnavailableError("Offline provider"))):
            with self.assertRaises(ProviderUnavailableError):
                asyncio.run(run())
        self.assertEqual(plan, before)
        self.assertEqual(sum(item["disposition"] == "unassigned" for item in plan["keyword_assignments"]), 66)

    def test_two_hop_topics_require_explicit_entity_subject_relationship(self):
        terms = {"wolf", "owl", "__scope__personality", "__related__wolf|personality", "__related__wolf|traits"}
        for phrase in ("wolf personality traits", "understanding wolf personality"):
            self.assertTrue(is_topic_relevant_keyword(phrase, ["spirit animal quiz"], terms, set()))
        for phrase in ("wolf food guide", "owl personality traits", "celebrity personality quiz"):
            self.assertFalse(is_topic_relevant_keyword(phrase, ["spirit animal quiz"], terms, set()), phrase)
        self.assertFalse(is_topic_relevant_keyword("wolf personality hunting", ["spirit animal quiz"], terms, {"hunting"}))
        product_terms = {"dental", "gum", "__related__gum|health"}
        self.assertTrue(is_topic_relevant_keyword("gum health guide", ["dental pro 7 reviews"], product_terms, set()))
        self.assertFalse(is_topic_relevant_keyword("gum surgery cost", ["dental pro 7 reviews"], product_terms, set()))
        self.assertFalse(is_topic_relevant_keyword("gum health reddit", ["dental pro 7 reviews"], product_terms, set()))

    def test_recovered_distinct_task_requires_a_complete_page_brief(self):
        primary = "spirit animal quiz"
        target = "wolf personality traits"
        records = normalize_keyword_records([{"phrase": primary}, {"phrase": target}])
        payload = {"pages": [{"target_keyword": primary, "article_title": "Animal Quiz", "search_intent": "Discover your animal result"}]}
        page = {"target_keyword": target, "article_title": "Wolf Personality Traits", "page_type": "article",
                "search_intent": "Understand the wolf result", "content_brief": "Explain strengths and weaknesses of the wolf result.",
                "user_problem": "What does my wolf result mean?", "unique_page_value": "A supported result profile with its own personality explanation."}
        for incomplete in (False, True):
            with self.subTest(incomplete=incomplete):
                plan = _repair_plan_consistency(_normalize_plan(payload, records, primary), records, primary)
                reply = {"pages": [{key: value for key, value in page.items() if not incomplete or key != "unique_page_value"}],
                         "keyword_decisions": [[target, "page_target", target, "title", "Independent personality result explanation."]]}
                async def run():
                    return await _review_keyword_coverage(plan, records, "Animal quiz with wolf results", deadline=asyncio.get_running_loop().time() + 45)
                with patch("nlp.hub_spoke_agent._achat_json", new=AsyncMock(return_value=reply)):
                    if incomplete:
                        with self.assertRaisesRegex(ValueError, "distinct task"):
                            asyncio.run(run())
                        self.assertEqual(plan["spokes"], [])
                    else:
                        result = asyncio.run(run())
                        self.assertEqual(result["spokes"][0]["target_keyword"], target)
                        self.assertEqual(validate_architecture(result, records, primary), [])

    def test_taxonomy_only_uses_supported_relationships_and_propagates_research_queries(self):
        audit = json.dumps({"primary_keyword": "spirit animal quiz", "capabilities": ["animal personality result profiles"]})
        payload = {"core_terms": ["wolf", "owl"], "scope_terms": ["personality"], "related_topics": [
            {"entity": "wolf", "qualifiers": ["personality", "traits"], "research_query": "wolf personality traits", "evidence": "animal personality result profiles"},
            {"entity": "owl", "qualifiers": ["food"], "research_query": "owl food guide", "evidence": "invented wildlife service"},
        ]}
        with patch("nlp.openrouter.is_ai_configured", return_value=True), patch.dict("nlp.openrouter._semantic_cache", {}, clear=True), patch(
            "nlp.openrouter._achat_json", new=AsyncMock(return_value=payload),
        ):
            taxonomy = asyncio.run(generate_core_domain_terms(["spirit animal quiz"], audit))
        self.assertEqual(taxonomy["research_seeds"], ["wolf personality traits"])
        self.assertEqual(taxonomy["related_pairs"], ["wolf|personality", "wolf|traits"])
        with patch("nlp.openrouter.generate_core_domain_terms", new=AsyncMock(return_value=taxonomy)):
            terms, negatives = _semantic_terms(["spirit animal quiz"], audit)
        self.assertIn("__research_seed__wolf personality traits", terms)
        self.assertTrue(is_topic_relevant_keyword("wolf personality strengths", ["spirit animal quiz"], terms, negatives))

    def test_multiword_exclusions_cannot_blacklist_the_sites_positive_subject(self):
        audit = json.dumps({'primary_keyword': 'spirit animal quiz', 'capabilities': ['wolf spirit animal profiles']})
        payload = {'anchor_terms': ['spirit animal'], 'scope_terms': ['meaning', 'traits'],
                   'negative_terms': ['animal husbandry', 'pet care', 'spirit possession', 'quiz'],
                   'related_topics': [{'entity': 'wolf', 'qualifiers': ['spirit', 'animal', 'meaning'],
                       'research_query': 'wolf spirit animal', 'evidence': 'wolf spirit animal profiles'}]}
        with patch('nlp.openrouter.is_ai_configured', return_value=True), patch.dict('nlp.openrouter._semantic_cache', {}, clear=True), patch(
            'nlp.openrouter._achat_json', new=AsyncMock(return_value=payload),
        ):
            taxonomy = asyncio.run(generate_core_domain_terms(['spirit animal quiz'], audit))
        self.assertTrue({'husbandry', 'pet', 'care', 'possession'} <= set(taxonomy['negative_terms']))
        self.assertFalse({'spirit', 'animal', 'quiz'} & set(taxonomy['negative_terms']))
        self.assertIn('wolf spirit animal', taxonomy['research_seeds'])
        # The pipeline also protects seed/evidence words if a cached or legacy
        # taxonomy still contains a conflicting negative token.
        taxonomy['negative_terms'].append('animal')
        with patch('nlp.openrouter.generate_core_domain_terms', new=AsyncMock(return_value=taxonomy)):
            terms, negatives = _semantic_terms(['spirit animal quiz'], audit)
        self.assertTrue(is_topic_relevant_keyword('bear spirit animal meaning', ['spirit animal quiz'], terms, negatives))
        self.assertFalse(is_topic_relevant_keyword('animal husbandry', ['spirit animal quiz'], terms, negatives))
