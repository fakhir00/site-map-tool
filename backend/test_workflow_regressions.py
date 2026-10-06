"""Offline regression tests using isolated databases and mocked providers."""
from architecture_test_fixtures import approved_review
import asyncio
import json
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch
import uuid
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker
from app.auth.jwt import create_access_token
from app.database import get_db
from app.main import app, _ensure_runtime_schema
from app.models import ArticleDraft, HubSpokeCluster, Keyword, KeywordBank, KeywordUrl, Project, ScanJob, Url, User
from workers.pipeline import _clear_previous_results, _ensure_minimum_keyword_count, _scan_is_active

PACKAGE = dict(status='passed', title='Test prompt', content_markdown='# CONTENT WRITING ASSIGNMENT\nTest prompt',
    audit={'score': 95, 'passed': True}, attempts=1, brief={}, competitor_pages=[], own_pages=[])

class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        directory = self.stack.enter_context(tempfile.TemporaryDirectory())
        path = Path(directory) / 'test.db'
        self.sync_engine = create_engine(f'sqlite:///{path}', connect_args={'check_same_thread': False, 'timeout': 15})
        self.stack.callback(self.sync_engine.dispose)
        self.async_engine = create_async_engine(f'sqlite+aiosqlite:///{path}')
        for engine in [self.sync_engine, self.async_engine.sync_engine]:
            @event.listens_for(engine, 'connect')
            def foreign_keys(connection, _):
                connection.execute('PRAGMA foreign_keys=ON')
        self.sessions = sessionmaker(self.sync_engine, expire_on_commit=False)
        async_sessions = async_sessionmaker(self.async_engine, expire_on_commit=False)
        async def test_db():
            async with async_sessions() as db:
                try:
                    yield db
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise
        app.dependency_overrides[get_db] = test_db
        self.stack.callback(app.dependency_overrides.clear)
        self.stack.enter_context(patch('app.main.engine', self.async_engine))
        self.stack.enter_context(patch('workers.pipeline.SyncSession', self.sessions))
        self.stack.enter_context(patch('app.scan.router.settings.USE_CELERY', False))
        self.stack.enter_context(patch('app.scan.router.settings.DATABASE_URL', f'sqlite+aiosqlite:///{path}'))
        self.client = self.stack.enter_context(TestClient(app))
        with self.sessions() as db:
            user = User(email='test@example.com')
            db.add(user)
            db.commit()
            self.user_id = user.id
        self.client.headers['Authorization'] = f'Bearer {create_access_token(self.user_id)}'

    def project(self):
        response = self.client.post('/api/projects', json=dict(name='Test', domain='https://own.example',
            target_keywords=['circuit diagram'], audit_summary='Electronics tool'))
        self.assertEqual(response.status_code, 201, response.text)
        return response.json()['id']

    def seed_job(self, pid, status='running', age=0):
        with self.sessions() as db:
            project = db.get(Project, uuid.UUID(pid))
            project.status = status
            job = ScanJob(project_id=project.id, status=status,
                started_at=datetime.now(timezone.utc) - timedelta(seconds=age))
            db.add(job)
            db.commit()
            return job.id

    def test_provider_diagnostics_require_auth_and_status_does_not_probe(self):
        with patch('nlp.providers.check_providers', return_value={'configured': False, 'providers': []}) as probe:
            response = self.client.get('/api/providers/ai/status')
            self.assertEqual(response.status_code, 200)
            probe.assert_not_called()
            self.assertEqual(self.client.post('/api/providers/ai/check').status_code, 200)
            probe.assert_called_once()
            self.client.headers.pop('Authorization')
            self.assertEqual(self.client.get('/api/providers/ai/status').status_code, 401)
            self.assertEqual(self.client.post('/api/providers/ai/check').status_code, 401)

    def test_real_page_stats_and_invalid_pagination(self):
        pid = self.project()
        with self.sessions() as db:
            for source in ['own', 'competitor', 'ai', 'provider']:
                db.add(Url(project_id=uuid.UUID(pid), url=f'https://example.com/{source}',
                           source_type=source, status='scraped'))
            db.commit()
        response = self.client.get(f'/api/projects/{pid}/stats')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total_urls'], 2)
        self.assertEqual(response.json()['scraped_urls'], 2)
        for endpoint in ['urls', 'keywords']:
            self.assertEqual(self.client.get(f'/api/projects/{pid}/{endpoint}?page_size=0').status_code, 422)

    def test_unavailable_ai_returns_actionable_service_error(self):
        from nlp.providers import ProviderUnavailableError
        pid = self.project()
        with patch('app.keywords.router.generate_ai_keywords', new=AsyncMock(
            side_effect=ProviderUnavailableError('AI unavailable. DeepSeek: Insufficient balance.')
        )), patch('nlp.openrouter.generate_core_domain_terms', new=AsyncMock(
            return_value={'core_terms': ['circuit'], 'negative_terms': []}
        )):
            response = self.client.post(f'/api/projects/{pid}/keywords/generate')
        self.assertEqual(response.status_code, 503, response.text)
        self.assertIn('Insufficient balance', response.json()['detail'])

    def test_registration_login_and_project_context(self):
        body = dict(email='new@example.com', password='long-password')
        self.assertEqual(self.client.post('/api/auth/register', json=body).status_code, 201)
        self.assertEqual(self.client.post('/api/auth/login', json=body).status_code, 200)
        pid = self.project()
        self.assertEqual(self.client.get(f'/api/projects/{pid}').json()['audit_summary'], 'Electronics tool')

    def test_gold_hunter_always_returns_three_to_five_distinct_seeds(self):
        result = {
            'audit_summary': {
                'primary_keyword': 'circuit diagram maker',
                'content_opportunities': ['circuit symbols guide', 'electrical schematic tutorial'],
            },
            'seeds': [
                {'keyword': 'circuit diagram software', 'justification': 'Relevant tool intent'},
                {'keyword': 'circuit diagram software', 'justification': 'Duplicate'},
                {'keyword': 'dog age calculator', 'justification': 'Unrelated generic age overlap'},
            ],
        }
        with (
            patch('app.goldhunter.router.fetch_url_content', new=AsyncMock(return_value='Circuit tool page')),
            patch('app.goldhunter.router.generate_gold_hunter_seeds', new=AsyncMock(return_value=result)),
        ):
            response = self.client.post('/api/goldhunter/scan', json={'url': 'https://own.example'})
        self.assertEqual(response.status_code, 200, response.text)
        seeds = response.json()['seeds']
        self.assertGreaterEqual(len(seeds), 3)
        self.assertLessEqual(len(seeds), 5)
        self.assertEqual(len({seed['keyword'] for seed in seeds}), len(seeds))
        self.assertNotIn('dog age calculator', {seed['keyword'] for seed in seeds})

        many_result = {
            **result,
            'seeds': [
                {'keyword': f'circuit diagram topic {index}', 'justification': 'Relevant'}
                for index in range(7)
            ],
        }
        with (
            patch('app.goldhunter.router.fetch_url_content', new=AsyncMock(return_value='Circuit tool page')),
            patch('app.goldhunter.router.generate_gold_hunter_seeds', new=AsyncMock(return_value=many_result)),
        ):
            response = self.client.post('/api/goldhunter/scan', json={'url': 'https://own.example'})
        self.assertEqual(len(response.json()['seeds']), 5)

    def test_legacy_schema_migration_is_idempotent(self):
        with self.sync_engine.begin() as conn:
            conn.execute(text('ALTER TABLE projects DROP COLUMN audit_summary'))
        async def migrate():
            async with self.async_engine.begin() as conn:
                await _ensure_runtime_schema(conn)
                await _ensure_runtime_schema(conn)
        asyncio.run(migrate())
        self.project()
        self.assertEqual(self.client.get('/api/projects').status_code, 200)

    def test_dispatch_failure_is_recorded_and_retryable(self):
        pid = self.project()
        with patch('app.scan.router._dispatch_scan', side_effect=RuntimeError('broker offline')):
            response = self.client.post(f'/api/projects/{pid}/scan/start')
        self.assertEqual(response.status_code, 503, response.text)
        self.assertEqual(self.client.get(f'/api/projects/{pid}').json()['status'], 'error')
        self.assertEqual(self.client.get(f'/api/projects/{pid}/scan/jobs').json()[0]['status'], 'error')
        with patch('app.scan.router._dispatch_scan', return_value='test-task'):
            self.assertEqual(self.client.post(f'/api/projects/{pid}/scan/start').status_code, 200)
            self.assertEqual(self.client.post(f'/api/projects/{pid}/scan/start').status_code, 409)

    def test_stale_scan_and_pause_fence_old_worker(self):
        pid = self.project()
        old_job = self.seed_job(pid, age=3600)
        self.assertEqual(self.client.get(f'/api/projects/{pid}/scan/status').json()['status'], 'error')
        with self.sessions() as db:
            self.assertFalse(_scan_is_active(db, uuid.UUID(pid), old_job))
        job = self.seed_job(pid)
        self.assertEqual(self.client.post(f'/api/projects/{pid}/scan/pause').status_code, 200)
        with patch('app.scan.router._dispatch_scan', return_value='new-task'):
            self.assertEqual(self.client.post(f'/api/projects/{pid}/scan/resume').status_code, 200)
        with self.sessions() as db:
            self.assertFalse(_scan_is_active(db, uuid.UUID(pid), job))

    def test_manual_article_uuid_and_ownership(self):
        pid = self.project()
        with patch('app.content.router.generate_article_package', return_value=PACKAGE):
            response = self.client.post('/api/projects/manual-generate', json=dict(main_keyword='circuit design', project_id=pid))
            self.assertEqual(response.status_code, 200, response.text)
            self.assertEqual(response.json()['project_id'], pid)
            for project_id, expected in [(str(uuid.uuid4()), 404), ('invalid', 422)]:
                response = self.client.post('/api/projects/manual-generate', json=dict(main_keyword='circuit design', project_id=project_id))
                self.assertEqual(response.status_code, expected)
            self.assertEqual(self.client.post('/api/projects/manual-generate', json=dict(main_keyword='   ', project_id=pid)).status_code, 422)

    def test_article_failure_and_rewrite_reuses_original_prompt(self):
        pid = self.project()
        with patch('app.content.router.generate_article_package', return_value=PACKAGE):
            draft = self.client.post('/api/projects/manual-generate', json=dict(main_keyword='circuit design', project_id=pid)).json()
        endpoint = f"/api/projects/{pid}/articles/{draft['id']}/write-final"
        with patch('app.content.router.generate_final_article_package', side_effect=RuntimeError('provider offline')):
            self.assertEqual(self.client.post(endpoint).status_code, 502)
        self.assertEqual(self.client.get(f'/api/projects/{pid}/articles').json()['items'][0]['status'], 'error')
        with patch('app.content.router.generate_final_article_package', return_value={**PACKAGE, 'content_markdown': '# Finished article'}) as writer:
            self.assertEqual(self.client.post(endpoint).status_code, 200)
            self.assertEqual(self.client.post(endpoint).status_code, 200)
            self.assertEqual(writer.call_args.kwargs['master_prompt'], PACKAGE['content_markdown'])

    def test_rescan_preserves_saved_work_and_invalidates_map(self):
        pid = uuid.UUID(self.project())
        with self.sessions() as db:
            keyword = Keyword(project_id=pid, phrase='circuit design')
            url = Url(project_id=pid, url='https://competitor.example/blog/circuit')
            db.add_all([keyword, url])
            db.flush()
            draft = ArticleDraft(project_id=pid, keyword_id=keyword.id, status='passed')
            bank = KeywordBank(user_id=self.user_id, keyword_id=keyword.id)
            db.add_all([draft, bank, KeywordUrl(keyword_id=keyword.id, url_id=url.id), HubSpokeCluster(project_id=pid, mapping_data={})])
            db.commit()
            _clear_previous_results(db, pid)
            self.assertIsNotNone(db.get(ArticleDraft, draft.id))
            self.assertIsNotNone(db.get(KeywordBank, bank.id))
            self.assertEqual(db.execute(select(Url)).scalars().all(), [])
            self.assertEqual(db.execute(select(HubSpokeCluster)).scalars().all(), [])

    def test_full_scan_keeps_evidence_without_quota_padding_and_resumes(self):
        from scraping.crawler import ScrapedPage
        pid = self.project()
        def extract(seeds, urls, **kwargs):
            first_url = next(iter(urls))
            return [dict(phrase='circuit board layout', type='lsi', url_ids=[str(first_url.id)])]
        with ExitStack() as mocks:
            mocks.enter_context(patch('workers.pipeline._semantic_terms', return_value=({'circuit'}, set())))
            mocks.enter_context(patch('workers.pipeline._discover_competitor_domains', return_value=['https://competitor.example']))
            mocks.enter_context(patch('workers.pipeline._discover_content_urls', side_effect=lambda domain, *args, **kwargs: [domain + '/blog/circuit-guide']))
            scraper = mocks.enter_context(patch('scraping.crawler.scrape_page', side_effect=lambda url, **kwargs: ScrapedPage(url=url, text='Circuit design content', word_count=3)))
            extractor = mocks.enter_context(patch('nlp.openrouter.extract_keywords_from_urls_ai', side_effect=extract))
            mocks.enter_context(patch('nlp.openrouter.filter_keyword_gap_recommendations', side_effect=lambda seeds, candidates, **kwargs: candidates))
            mocks.enter_context(patch('nlp.openrouter.generate_ai_keywords_sync', return_value=[]))
            mocks.enter_context(patch('workers.pipeline._own_content_keyword_phrases', return_value=set()))
            response = self.client.post(f'/api/projects/{pid}/scan/start')
            self.assertEqual(response.status_code, 200, response.text)
            project = self.client.get(f'/api/projects/{pid}').json()
            self.assertEqual(project['status'], 'complete', self.client.get(f'/api/projects/{pid}/scan/jobs').text)
            self.assertEqual(project['total_keywords'], 1)
            self.assertEqual(project['urls_processed'], 2)
            self.seed_job(pid, status='paused')
            scraper.reset_mock()
            extractor.reset_mock()
            self.assertEqual(self.client.post(f'/api/projects/{pid}/scan/resume').status_code, 200)
            extractor.assert_called_once()
            scraper.assert_not_called()
            self.assertEqual(self.client.get(f'/api/projects/{pid}').json()['status'], 'complete')

    def test_empty_enrichment_retains_verified_seed_and_completes(self):
        pid = self.project()
        with ExitStack() as mocks:
            mocks.enter_context(patch('workers.pipeline._semantic_terms', return_value=(set(), set())))
            mocks.enter_context(patch('workers.pipeline._discover_competitor_domains', return_value=[]))
            mocks.enter_context(patch('workers.pipeline._discover_content_urls', return_value=[]))
            mocks.enter_context(patch('nlp.openrouter.generate_ai_keywords_sync', return_value=[]))
            self.client.post(f'/api/projects/{pid}/scan/start')
        project = self.client.get(f'/api/projects/{pid}').json()
        self.assertEqual(project['status'], 'complete')
        self.assertGreaterEqual(project['total_keywords'], 1)

    def test_generate_does_not_pad_empty_ai_results_and_project_uses_specialist_architect(self):
        pid = self.project()
        with (
            patch('app.keywords.router.generate_ai_keywords', new=AsyncMock(return_value=[])),
            patch('nlp.openrouter.generate_core_domain_terms', new=AsyncMock(return_value={
                'core_terms': ['circuit'], 'negative_terms': [],
            })),
        ):
            response = self.client.post(f'/api/projects/{pid}/keywords/generate')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(self.client.get(f'/api/projects/{pid}').json()['total_keywords'], 0)

        # Architecture generation receives the project's real candidate inventory.
        with self.sessions() as db:
            db.add_all([
                Keyword(
                    project_id=uuid.UUID(pid),
                    phrase=f'circuit diagram topic {index}',
                    keyword_type='long-tail',
                )
                for index in range(21)
            ])
            db.commit()

        specialist_map = {
            'hubs': [{'hub_title': 'Circuit Diagram', 'target_keyword': 'circuit diagram',
                      'h2_keywords': [], 'layers': {'Topics': []}, 'sub_silos': []}],
            'master_hub': {'article_title': 'Circuit Diagram', 'target_keyword': 'circuit diagram'},
            'spokes': [], 'keyword_assignments': [],
        }
        with patch('nlp.hub_spoke_agent.build_site_architecture', new=AsyncMock(return_value=specialist_map)) as architect:
            response = self.client.post(f'/api/projects/{pid}/keywords/hub-spoke')
        self.assertEqual(response.status_code, 200, response.text)
        mapping = response.json()['clusters']
        self.assertEqual(len(mapping['hubs']), 1)
        self.assertEqual(len(architect.await_args.args[0]), 21)
        self.assertTrue(architect.await_args.kwargs['discover_topics'])
        self.assertNotIn('target_spokes', architect.await_args.kwargs)

    def test_topical_map_api_preserves_explicit_main_topic_and_declared_owned_urls(self):
        from test_authority_planning import PRIMARY, TOPICS, fixture_payload
        payload = fixture_payload(TOPICS[:1])
        payload['pages'][1]['existing_url'] = 'https://own.example/existing-method/'
        pid = self.project()
        with patch('nlp.hub_spoke_agent.is_ai_configured', return_value=True), patch(
            'nlp.hub_spoke_agent._achat_json', new=AsyncMock(side_effect=[
                {'proposals': []}, payload, approved_review(payload),
            ]),
        ):
            response = self.client.post('/api/hub-spoke/build', json={
                'keywords': [TOPICS[0][0], PRIMARY], 'primary_keyword': PRIMARY,
                'project_id': pid, 'context': 'Age calculation for families.',
                'existing_urls': ['https://own.example/existing-method/'],
            })
        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()
        self.assertEqual(result['clusters']['master_hub']['target_keyword'], PRIMARY)
        self.assertEqual(result['clusters']['spokes'][0]['action'], 'update')
        self.assertEqual(result['clusters']['map_version'], 2)
        saved = self.client.get('/api/hub-spoke/history/' + result['history_id']).json()
        self.assertEqual(saved['clusters']['link_plan'], result['clusters']['link_plan'])
        self.assertEqual(json.loads(saved['context'])['primary_keyword'], PRIMARY)
        with patch('nlp.hub_spoke_agent.is_ai_configured', return_value=True), patch(
            'nlp.hub_spoke_agent._achat_json', new=AsyncMock(side_effect=[
                {'proposals': []}, fixture_payload(TOPICS[:1]),
                RuntimeError('review unavailable'), RuntimeError('review unavailable'),
            ]),
        ):
            failed = self.client.post('/api/hub-spoke/build', json={
                'keywords': [TOPICS[0][0], PRIMARY], 'primary_keyword': PRIMARY,
            })
        self.assertEqual(failed.status_code, 502, failed.text)
        self.assertIn('previous saved map is unchanged', failed.json()['detail'])
        self.assertEqual(len(self.client.get('/api/hub-spoke/history').json()), 1)
        self.assertEqual(
            self.client.get('/api/hub-spoke/history/' + result['history_id']).json()['clusters'],
            saved['clusters'],
        )
        self.assertEqual(self.client.post('/api/hub-spoke/build', json={
            'keywords': [PRIMARY], 'existing_urls': ['javascript:alert(1)'],
        }).status_code, 422)

    def test_authority_build_receives_owned_pages_and_ignores_legacy_target(self):
        pid = self.project()
        with self.sessions() as db:
            db.add(Url(project_id=uuid.UUID(pid), url='https://own.example/existing-tool/',
                       source_type='own', status='scraped', h1='Existing Tool',
                       scraped_text='A working circuit tool already exists.'))
            db.commit()
        mapping = {
            'master_hub': {'article_title': 'Circuit Diagram', 'target_keyword': 'circuit diagram'},
            'spokes': [], 'keyword_assignments': [],
            '_keyword_metrics': [{'phrase': 'circuit diagram'},
                                 {'phrase': 'circuit troubleshooting', 'evidence_type': 'editorial_proposal'}],
        }
        with patch('app.hub_spoke.router.build_site_architecture', new=AsyncMock(return_value=mapping)) as architect:
            response = self.client.post('/api/hub-spoke/build', json={
                'keywords': ['circuit diagram'], 'project_id': pid, 'target_spokes': 500,
            })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(architect.await_args.kwargs['discover_topics'])
        self.assertNotIn('target_spokes', architect.await_args.kwargs)
        context = json.loads(architect.await_args.kwargs['context'])
        self.assertEqual(context['owned_pages'][0]['url'], 'https://own.example/existing-tool/')
        self.assertIn('already exists', context['owned_pages'][0]['text_excerpt'])
        self.assertEqual(len(response.json()['keyword_data']), 2)

    def test_saved_maps_recheck_all_owned_urls_including_unscraped_pages(self):
        pid = self.project()
        mapping = {'hubs': [], 'master_hub': {'article_title': 'Circuit Diagram',
                   'target_keyword': 'circuit diagram', 'slug': '/', 'action': 'create'},
                   'spokes': [{'target_keyword': 'circuit symbols', 'article_title': 'Circuit Symbols',
                               'slug': '/new-symbols/', 'action': 'create'}],
                   'keyword_assignments': [], 'link_plan': []}
        with patch('app.hub_spoke.router.build_site_architecture', new=AsyncMock(return_value=mapping)):
            response = self.client.post('/api/hub-spoke/build', json={
                'keywords': ['circuit diagram'], 'project_id': pid})
        self.assertEqual(response.status_code, 200, response.text)
        history_id = response.json()['history_id']
        with self.sessions() as db:
            for index in range(35):
                db.add(Url(project_id=uuid.UUID(pid), url=f'https://own.example/a-{index}/',
                           source_type='own', status='scraped', h1=f'Other topic {index}'))
            db.add(Url(project_id=uuid.UUID(pid), url='https://own.example/z/circuit-symbols/',
                       source_type='own', status='pending'))
            db.add(Url(project_id=uuid.UUID(pid), url='https://competitor.example/',
                       source_type='competitor', status='scraped', h1='Circuit Diagram'))
            db.commit()
        saved = self.client.get('/api/hub-spoke/history/' + history_id)
        self.assertEqual(saved.status_code, 200, saved.text)
        clusters = saved.json()['clusters']
        self.assertEqual(clusters['spokes'][0]['action'], 'update')
        self.assertEqual(clusters['spokes'][0]['existing_url'], 'https://own.example/z/circuit-symbols/')
        self.assertEqual(clusters['master_hub']['action'], 'create')
        with patch('app.hub_spoke.router.build_site_architecture', new=AsyncMock(return_value=mapping)) as architect:
            response = self.client.post('/api/hub-spoke/build', json={
                'keywords': ['circuit diagram'], 'project_id': pid})
        context = json.loads(architect.await_args.kwargs['context'])
        self.assertEqual(len(context['owned_pages']), 36)
        self.assertFalse(any('competitor.example' in page['url'] for page in context['owned_pages']))

    def test_standalone_hub_workspace_builds_and_saves_specialist_plan(self):
        keywords = ['circuit diagram maker', 'circuit diagram symbols', 'celebrity news']
        specialist_map = {
            'hubs': [{'hub_title': 'Circuit Diagram Maker', 'target_keyword': 'circuit diagram maker',
                      'h2_keywords': [], 'layers': {'Reference': ['Circuit Diagram Symbols (Target Keyword: circuit diagram symbols)']}, 'sub_silos': []}],
            'master_hub': {'article_title': 'Circuit Diagram Maker', 'target_keyword': 'circuit diagram maker'},
            'spokes': [{'article_title': 'Circuit Diagram Symbols', 'target_keyword': 'circuit diagram symbols'}],
            'keyword_assignments': [
                {'keyword': 'circuit diagram maker', 'disposition': 'page_target'},
                {'keyword': 'circuit diagram symbols', 'disposition': 'page_target'},
                {'keyword': 'celebrity news', 'disposition': 'discard'},
            ],
            'discarded_keywords': [{'keyword': 'celebrity news', 'reason': 'Off topic'}],
        }
        with patch('app.hub_spoke.router.build_site_architecture', new=AsyncMock(return_value=specialist_map)):
            built = self.client.post('/api/hub-spoke/build', json={
                'keywords': keywords,
                'context': 'Circuit design education for electronics students.',
            })
        self.assertEqual(built.status_code, 200, built.text)
        self.assertEqual(len(built.json()['clusters']['hubs']), 1)
        history_id = built.json()['history_id']
        history = self.client.get('/api/hub-spoke/history')
        self.assertEqual(history.status_code, 200, history.text)
        self.assertEqual(history.json()[0]['id'], history_id)
        self.assertEqual(history.json()[0]['keyword_count'], 2)
        restored = self.client.get(f'/api/hub-spoke/history/{history_id}')
        self.assertEqual(restored.status_code, 200, restored.text)
        self.assertEqual(restored.json()['context'], 'Circuit design education for electronics students.')
        self.assertEqual(restored.json()['clusters'], built.json()['clusters'])
        with self.sessions() as db:
            other_user = User(email='other@example.com')
            db.add(other_user)
            db.commit()
            other_user_id = other_user.id
        self.client.headers['Authorization'] = f'Bearer {create_access_token(other_user_id)}'
        self.assertEqual(self.client.get('/api/hub-spoke/history').json(), [])
        self.assertEqual(self.client.get(f'/api/hub-spoke/history/{history_id}').status_code, 404)
        self.assertEqual(self.client.delete(f'/api/hub-spoke/history/{history_id}').status_code, 404)
        self.client.headers['Authorization'] = f'Bearer {create_access_token(self.user_id)}'
        self.assertEqual(self.client.delete(f'/api/hub-spoke/history/{history_id}').status_code, 204)
        self.assertEqual(self.client.get('/api/hub-spoke/history').json(), [])
        self.assertEqual(self.client.get(f'/api/hub-spoke/history/{history_id}').status_code, 404)

    def test_hub_workspace_imports_gap_keywords_with_selected_keyword_first(self):
        pid = self.project()
        with self.sessions() as db:
            project_id = uuid.UUID(pid)
            db.add_all([
                Keyword(project_id=project_id, phrase='circuit symbols', frequency=8, search_volume=3200, difficulty=61),
                Keyword(project_id=project_id, phrase='circuit diagram examples', frequency=4, search_volume=900, difficulty=22),
            ])
            db.commit()

        imported = self.client.get(
            f'/api/hub-spoke/project-import/{pid}',
            params={'primary_keyword': 'circuit diagram examples'},
        )

        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertEqual(imported.json()['keywords'][0], 'circuit diagram examples')
        self.assertEqual(imported.json()['keyword_data'][0]['phrase'], 'circuit diagram examples')
        self.assertEqual(imported.json()['keyword_data'][0]['search_volume'], 900)
        self.assertEqual(imported.json()['keyword_data'][0]['difficulty'], 22)
        imported_context = json.loads(imported.json()['context'])
        self.assertEqual(imported_context['audit_summary'], 'Electronics tool')
        self.assertEqual(imported_context['primary_keyword'], 'circuit diagram')
        self.assertEqual(imported_context['seed_keywords'], ['circuit diagram'])
        self.assertEqual(imported.json()['project_id'], pid)

    def test_scan_does_not_pad_with_ai_when_evidence_sources_reach_target(self):
        pid = uuid.UUID(self.project())
        generated = [
            {"phrase": f"circuit diagram easy win {index}", "type": "long-tail"}
            for index in range(60)
        ]
        generator = Mock(return_value=generated)
        with self.sessions() as db:
            db.add_all([
                Keyword(
                    project_id=pid,
                    phrase=f"circuit diagram existing {index}",
                    keyword_type="long-tail",
                    frequency=1,
                )
                for index in range(100)
            ])
            db.flush()
            total = _ensure_minimum_keyword_count(
                db=db,
                project_id=pid,
                seed_keywords=["circuit diagram"],
                topic_terms={"circuit"},
                negative_terms=set(),
                audit_summary=json.dumps({"primary_keyword": "circuit diagram"}),
                generate_keywords=generator,
                ai_generated_source=lambda: ("https://ai.generated", "AI Recommendations"),
            )
            db.commit()

        self.assertEqual(total, 100)
        generator.assert_not_called()

    def test_bulk_keyword_delete_cannot_touch_another_project(self):
        first_project_id = uuid.UUID(self.project())
        second_project_id = uuid.UUID(self.project())
        with self.sessions() as db:
            first_keyword = Keyword(project_id=first_project_id, phrase='first project keyword', frequency=2)
            second_keyword = Keyword(project_id=second_project_id, phrase='second project keyword', frequency=3)
            db.add_all([first_keyword, second_keyword])
            db.flush()
            first_keyword_id = first_keyword.id
            second_keyword_id = second_keyword.id
            db.add_all([
                KeywordBank(user_id=self.user_id, keyword_id=first_keyword_id),
                KeywordBank(user_id=self.user_id, keyword_id=second_keyword_id),
            ])
            db.commit()

        response = self.client.post(f'/api/projects/{first_project_id}/keywords/bulk-delete', json={
            'keyword_ids': [str(first_keyword_id), str(second_keyword_id)],
        })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn('1 keyword', response.json()['message'])
        with self.sessions() as db:
            self.assertIsNone(db.get(Keyword, first_keyword_id))
            self.assertIsNotNone(db.get(Keyword, second_keyword_id))
            second_bank = db.scalar(select(KeywordBank).where(KeywordBank.keyword_id == second_keyword_id))
            self.assertIsNotNone(second_bank)

    def test_keyword_list_and_csv_export_batch_source_data(self):
        pid = self.project()
        with self.sessions() as db:
            project_id = uuid.UUID(pid)
            keyword = Keyword(
                project_id=project_id,
                phrase='circuit design software',
                frequency=3,
                search_volume=500,
                difficulty=0,
            )
            low_volume_keyword = Keyword(
                project_id=project_id,
                phrase='circuit layout tutorial',
                frequency=1,
                search_volume=20,
            )
            source = Url(
                project_id=project_id,
                url='https://competitor.example/circuit-design',
                source_type='competitor',
                source_domain='https://competitor.example',
            )
            db.add_all([keyword, low_volume_keyword, source])
            db.flush()
            db.add(KeywordUrl(keyword_id=keyword.id, url_id=source.id))
            db.commit()

        listed = self.client.get(f'/api/projects/{pid}/keywords')
        volume_ascending = self.client.get(f'/api/projects/{pid}/keywords?sort_by=search_volume_asc')
        volume_descending = self.client.get(f'/api/projects/{pid}/keywords?sort_by=search_volume_desc')
        exported = self.client.get(f'/api/projects/{pid}/keywords/export')

        self.assertEqual(listed.status_code, 200, listed.text)
        self.assertEqual(listed.json()['items'][0]['source_urls'], ['https://competitor.example/circuit-design'])
        self.assertEqual(volume_ascending.status_code, 200, volume_ascending.text)
        self.assertEqual(
            [item['phrase'] for item in volume_ascending.json()['items']],
            ['circuit layout tutorial', 'circuit design software'],
        )
        self.assertEqual(volume_descending.status_code, 200, volume_descending.text)
        self.assertEqual(
            [item['phrase'] for item in volume_descending.json()['items']],
            ['circuit design software', 'circuit layout tutorial'],
        )
        self.assertEqual(exported.status_code, 200, exported.text)
        self.assertTrue(exported.headers['content-type'].startswith('text/csv'))
        self.assertIn('circuit design software', exported.text)
        self.assertIn('https://competitor.example/circuit-design', exported.text)
        import csv
        import io
        rows = list(csv.DictReader(io.StringIO(exported.text.lstrip('\ufeff'))))
        self.assertEqual(rows[0]['Competitor Pages'], '1')
        self.assertEqual(float(rows[0]['Difficulty']), 0)
        self.assertEqual(rows[1]['Competitor Pages'], '0')


if __name__ == '__main__':
    unittest.main()
