"""Offline regression tests using isolated databases and mocked providers."""
from architecture_test_fixtures import approved_review
import asyncio
import json
from contextlib import ExitStack
from datetime import datetime, timedelta, timezone
from pathlib import Path
import tempfile
import time
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
from app.models import ArticleDraft, HubSpokeCluster, Keyword, KeywordBank, KeywordUrl, Project, ResearchKeyword, ScanJob, Url, User
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
        self.stack.enter_context(patch('scraping.apify_client_module.research_keywords_via_apify', return_value=[]))
        self.stack.enter_context(patch('scraping.apify_client_module.search_google_via_apify', return_value=[]))
        self.stack.enter_context(patch('nlp.deepseek_seo.enrich_keywords_with_seo_data', return_value={}))
        self.stack.enter_context(patch('nlp.dataforseo.is_dataforseo_configured', return_value=False))
        self.stack.enter_context(patch('scraping.autocomplete.research_autocomplete', return_value=[]))
        self.stack.enter_context(patch('app.scan.router.settings.DATABASE_URL', f'sqlite+aiosqlite:///{path}'))
        self.client = self.stack.enter_context(TestClient(app))
        with self.sessions() as db:
            user = User(email='test@example.com', is_active=True)
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

    def test_hub_import_keeps_competitor_provenance_and_known_unscraped_pages(self):
        from app.hub_spoke.context import context_with_owned_pages
        from sqlalchemy.ext.asyncio import async_sessionmaker
        pid = self.project()
        with self.sessions() as db:
            keyword = Keyword(project_id=uuid.UUID(pid), phrase='circuit diagram symbols', search_volume=0,
                              seo_recommendation='Explain unfamiliar symbols in the existing symbol reference.')
            competitor = Url(project_id=uuid.UUID(pid), url='https://competitor.example/symbols', source_type='competitor', status='scraped')
            own = Url(project_id=uuid.UUID(pid), url='https://own.example/symbol-reference', source_type='own', status='discovered')
            db.add_all([keyword, competitor, own])
            db.flush()
            db.add(KeywordUrl(keyword_id=keyword.id, url_id=competitor.id))
            db.commit()
        imported = self.client.get(f'/api/hub-spoke/project-import/{pid}')
        self.assertEqual(imported.status_code, 200, imported.text)
        row = next(row for row in imported.json()['keyword_data'] if row['phrase'] == 'circuit diagram symbols')
        self.assertEqual(row['source_domains'], ['competitor.example'])
        self.assertEqual(row['search_volume'], 0)
        self.assertEqual(row['seo_recommendation'], 'Explain unfamiliar symbols in the existing symbol reference.')
        async def load_context():
            async with async_sessionmaker(self.async_engine)() as db:
                return json.loads(await context_with_owned_pages(db, uuid.UUID(pid), '{}'))
        context = asyncio.run(load_context())
        self.assertEqual(context['owned_pages'][0]['url'], 'https://own.example/symbol-reference')
        self.assertEqual(context['owned_pages'][0]['evidence'], 'owned_sitemap')

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
            db.add_all([keyword, url, ResearchKeyword(project_id=pid, phrase='circuit troubleshooting', payload={})])
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
            self.assertEqual(db.execute(select(ResearchKeyword)).scalars().all(), [])

    def test_full_scan_keeps_evidence_without_quota_padding_and_resumes(self):
        from scraping.crawler import ScrapedPage
        pid = self.project()
        def extract(seeds, urls, **kwargs):
            first_url = next(iter(urls))
            return [dict(phrase='circuit board layout', type='lsi', url_ids=[str(first_url.id)])]
        with ExitStack() as mocks:
            mocks.enter_context(patch('workers.pipeline._semantic_terms', return_value=({'circuit', '__scope__board'}, set())))
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
            self.assertEqual(self.client.get(f'/api/projects/{pid}/keywords').json()['items'][0]['phrase'], 'circuit board layout')
            self.assertEqual(project['urls_processed'], 2)
            self.seed_job(pid, status='paused')
            scraper.reset_mock()
            extractor.reset_mock()
            self.assertEqual(self.client.post(f'/api/projects/{pid}/scan/resume').status_code, 200)
            extractor.assert_called_once()
            scraper.assert_not_called()
            self.assertEqual(self.client.get(f'/api/projects/{pid}').json()['status'], 'complete')

    def test_scan_persists_and_displays_competitor_ai_and_both_research_sources(self):
        from scraping.crawler import ScrapedPage
        from nlp.dataforseo import KeywordResearchResult
        pid = self.project()
        def extract(seeds, urls, **kwargs):
            page = next(iter(urls))
            return [dict(phrase='circuit diagram troubleshooting', type='lsi', url_ids=[str(page.id)])]
        generated = [dict(phrase=phrase, type='long-tail', support_source='seed', support_phrase='circuit diagram')
                     for phrase in ['circuit diagram for beginners', 'circuit diagram common mistakes']]
        with ExitStack() as mocks:
            mocks.enter_context(patch('workers.pipeline._semantic_terms', return_value=({'circuit'}, set())))
            mocks.enter_context(patch('workers.pipeline._discover_competitor_domains', return_value=['https://competitor.example']))
            mocks.enter_context(patch('workers.pipeline._discover_content_urls', side_effect=lambda domain, *a, **kw: [domain + '/circuit']))
            mocks.enter_context(patch('scraping.crawler.scrape_page', side_effect=lambda url, **kw:
                ScrapedPage(url=url, text='Circuit diagram troubleshooting guide', word_count=4)))
            mocks.enter_context(patch('scraping.apify_client_module.is_apify_configured', return_value=True))
            mocks.enter_context(patch('scraping.apify_client_module.research_keywords_via_apify', return_value=[
                dict(phrase='circuit diagram symbols', search_volume=0, difficulty=0)]))
            mocks.enter_context(patch('nlp.dataforseo.is_dataforseo_configured', return_value=True))
            mocks.enter_context(patch('nlp.dataforseo.collect_keyword_research', return_value=KeywordResearchResult([
                dict(phrase='circuit diagram tutorial', search_volume=20, difficulty=5)], 0, 0, 1)))
            mocks.enter_context(patch('nlp.openrouter.extract_keywords_from_urls_ai', side_effect=extract))
            mocks.enter_context(patch('nlp.openrouter.filter_keyword_gap_recommendations', side_effect=lambda seeds, rows, **kw: rows))
            mocks.enter_context(patch('nlp.openrouter.is_ai_configured', return_value=True))
            mocks.enter_context(patch('nlp.openrouter._chat_json', return_value=generated))
            mocks.enter_context(patch('workers.pipeline._own_content_keyword_phrases', return_value=set()))
            self.assertEqual(self.client.post(f'/api/projects/{pid}/scan/start').status_code, 200)
        project = self.client.get(f'/api/projects/{pid}').json()
        self.assertEqual(project['status'], 'complete', self.client.get(f'/api/projects/{pid}/scan/jobs').text)
        self.assertEqual(project['total_keywords'], 5)
        keywords = self.client.get(f'/api/projects/{pid}/keywords').json()
        self.assertEqual(keywords['total'], 5)
        rows = {row['phrase']: row for row in keywords['items']}
        self.assertEqual(rows['circuit diagram symbols']['search_volume'], 0)
        self.assertEqual(rows['circuit diagram symbols']['sources'][0]['source_type'], 'provider')
        self.assertEqual(rows['circuit diagram tutorial']['sources'][0]['source_domain'], 'DataForSEO')
        self.assertEqual(rows['circuit diagram for beginners']['competitor_pages'], 1)
        self.assertEqual(rows['circuit diagram symbols']['competitor_pages'], 1)
        self.assertEqual(rows['circuit diagram troubleshooting']['competitor_pages'], 1)
        self.assertEqual(rows['circuit diagram troubleshooting']['sources'][0]['source_type'], 'competitor')

    def test_empty_enrichment_does_not_disguise_seeds_as_ai_research(self):
        pid = self.project()
        with ExitStack() as mocks:
            mocks.enter_context(patch('workers.pipeline._semantic_terms', return_value=(set(), set())))
            mocks.enter_context(patch('workers.pipeline._discover_competitor_domains', return_value=[]))
            mocks.enter_context(patch('workers.pipeline._discover_content_urls', return_value=[]))
            mocks.enter_context(patch('nlp.openrouter.generate_ai_keywords_sync', return_value=[]))
            self.client.post(f'/api/projects/{pid}/scan/start')
        project = self.client.get(f'/api/projects/{pid}').json()
        self.assertEqual(project['status'], 'complete')
        self.assertEqual(project['total_keywords'], 0)
        with self.sessions() as db:
            self.assertEqual(db.execute(select(Url).where(Url.project_id == uuid.UUID(pid), Url.source_type == 'ai')).scalars().all(), [])
        # Site context can still seed the architecture without becoming a fake gap.
        imported = self.client.get(f'/api/hub-spoke/project-import/{pid}')
        self.assertEqual(imported.status_code, 200, imported.text)
        self.assertIn('circuit diagram', imported.json()['keywords'])

    def test_gap_recovery_scrapes_new_matching_pages_with_a_hard_cap(self):
        from workers.pipeline import _research_additional_gap_pages
        from scraping.crawler import ScrapedPage
        pid = uuid.UUID(self.project())
        job_id = self.seed_job(str(pid))
        known_url = 'https://competitor.example/circuit'
        with self.sessions() as db:
            db.add(Url(project_id=pid, url=known_url, source_type='competitor', status='scraped'))
            db.commit()
        results = [
            {'url': url, 'title': title} for url, title in [
                (known_url, 'Circuit diagram guide'),
                ('https://own.example/circuit', 'Circuit diagram guide'),
                ('https://unrelated.example/', 'Dog age calculator'),
                ('https://new.example/circuit', 'Circuit diagram guide'),
                ('https://extra.example/circuit', 'Circuit diagram guide'),
            ]
        ]
        stats = {}
        with patch('scraping.apify_client_module.is_apify_configured', return_value=True), patch(
            'scraping.apify_client_module.search_google_via_apify', return_value=results,
        ) as search, patch('scraping.crawler.scrape_page', side_effect=lambda url, **kw:
                          ScrapedPage(url=url, text='Circuit diagram guide and instructions', word_count=6)) as scrape, patch(
            'workers.pipeline.settings.GAP_RECOVERY_PAGE_LIMIT', 1,
        ):
            domains = _research_additional_gap_pages(pid, job_id, ['circuit diagram'], 'https://own.example',
                                                     'gb', set(), stats, deadline=time.monotonic() + 60)
        self.assertEqual(domains, ['https://new.example'])
        self.assertEqual(stats['recovery_pages'], 1)
        self.assertEqual(scrape.call_args.args[0], 'https://new.example/circuit')
        scrape.assert_called_once()
        self.assertEqual(search.call_args.kwargs['start_page'], 4)
        self.assertEqual(search.call_args.kwargs['country_code'], 'gb')
        with self.sessions() as db:
            pages = db.execute(select(Url).where(Url.project_id == pid)).scalars().all()
            self.assertEqual(len(pages), 2)
            self.assertTrue(all(page.status == 'scraped' for page in pages))

    def test_full_scan_recovers_after_the_first_review_rejects_every_candidate(self):
        self._check_sparse_scan_recovery(empty_first=True)

    def test_full_scan_researches_more_pages_when_only_one_keyword_passes(self):
        self._check_sparse_scan_recovery(empty_first=False)

    def _check_sparse_scan_recovery(self, empty_first):
        from scraping.crawler import ScrapedPage
        pid = self.project()
        def extract(seeds, urls, **kwargs):
            return [dict(phrase='circuit diagram troubleshooting', type='lsi', url_ids=[str(page.id)])
                    for page in urls]
        verdicts = []
        def review(seeds, candidates, **kwargs):
            verdicts.append(candidates)
            return [] if empty_first and len(verdicts) == 1 else candidates
        with ExitStack() as mocks:
            mocks.enter_context(patch('workers.pipeline._semantic_terms', return_value=({'circuit'}, set())))
            mocks.enter_context(patch('workers.pipeline._discover_competitor_domains', return_value=['https://competitor.example']))
            mocks.enter_context(patch('workers.pipeline._discover_content_urls', side_effect=lambda domain, *a, **kw: [domain + '/circuit']))
            mocks.enter_context(patch('scraping.crawler.scrape_page', side_effect=lambda url, **kw:
                                     ScrapedPage(url=url, text='Circuit diagram troubleshooting guide', word_count=4)))
            mocks.enter_context(patch('scraping.apify_client_module.is_apify_configured', return_value=True))
            search = mocks.enter_context(patch('scraping.apify_client_module.search_google_via_apify', return_value=[
                {'url': 'https://new.example/circuit', 'title': 'Circuit diagram troubleshooting'}]))
            mocks.enter_context(patch('nlp.openrouter.extract_keywords_from_urls_ai', side_effect=extract))
            mocks.enter_context(patch('nlp.openrouter.filter_keyword_gap_recommendations', side_effect=review))
            mocks.enter_context(patch('nlp.openrouter.generate_ai_keywords_sync', return_value=[]))
            mocks.enter_context(patch('workers.pipeline._own_content_keyword_phrases', return_value=set()))
            response = self.client.post(f'/api/projects/{pid}/scan/start')
        self.assertEqual(response.status_code, 200, response.text)
        project = self.client.get(f'/api/projects/{pid}').json()
        jobs = self.client.get(f'/api/projects/{pid}/scan/jobs').json()
        self.assertEqual(project['status'], 'complete', jobs)
        self.assertEqual(project['total_keywords'], 1)
        self.assertEqual(project['urls_processed'], 3)
        self.assertEqual(len(verdicts), 2)
        self.assertGreater(len(verdicts[1]), len(verdicts[0]))
        self.assertFalse(jobs[0]['error_message'])
        self.assertEqual(search.call_args.kwargs['start_page'], 4)

    def test_gap_recovery_stops_for_pause_deadline_and_full_url_budget(self):
        from workers.pipeline import _research_additional_gap_pages
        pid = uuid.UUID(self.project())
        job_id = self.seed_job(str(pid))
        with patch('scraping.apify_client_module.is_apify_configured', return_value=True), patch(
            'scraping.apify_client_module.search_google_via_apify', return_value=[],
        ) as search:
            for deadline, limit in [(0, 200), (time.monotonic() + 60, 0)]:
                with patch('workers.pipeline.settings.MAX_URLS_PER_SCAN', limit):
                    self.assertEqual(_research_additional_gap_pages(
                        pid, job_id, ['circuit diagram'], 'https://own.example', 'us', set(), {},
                        deadline=deadline), [])
            paused_job_id = self.seed_job(str(pid), status='paused')
            self.assertEqual(_research_additional_gap_pages(
                pid, paused_job_id, ['circuit diagram'], 'https://own.example', 'us', set(), {},
                deadline=time.monotonic() + 60), [])
            search.assert_not_called()

    def test_gap_recovery_deduplicates_seeds_and_bounds_extra_searches(self):
        from workers.pipeline import _research_additional_gap_pages
        pid = uuid.UUID(self.project())
        job_id = self.seed_job(str(pid))
        stats = {}
        with patch('scraping.apify_client_module.is_apify_configured', return_value=True), patch(
            'scraping.apify_client_module.search_google_via_apify', return_value=[],
        ) as search, patch('workers.pipeline.settings.GAP_RECOVERY_SEARCH_LIMIT', 2):
            self.assertEqual(_research_additional_gap_pages(
                pid, job_id, ['circuit diagram', 'circuit diagram', 'circuit drawing', 'circuit maker'],
                'https://own.example', 'us', set(), stats, deadline=time.monotonic() + 60), [])
        self.assertEqual([call.args[0] for call in search.call_args_list], ['circuit diagram', 'circuit drawing'])
        self.assertEqual(stats['recovery_searches'], 2)
        self.assertEqual(stats['recovery_pages'], 0)

    def test_gap_recovery_stops_on_provider_failure(self):
        from workers.pipeline import _research_additional_gap_pages
        pid = uuid.UUID(self.project())
        job_id = self.seed_job(str(pid))
        def unavailable(*args, **kwargs):
            kwargs['diagnostics'].append('Actor quota reached')
            return []
        stats = {}
        with patch('scraping.apify_client_module.is_apify_configured', return_value=True), patch(
            'scraping.apify_client_module.search_google_via_apify', side_effect=unavailable,
        ) as search:
            self.assertEqual(_research_additional_gap_pages(
                pid, job_id, ['circuit diagram', 'circuit drawing'], 'https://own.example', 'us', set(), stats,
                deadline=time.monotonic() + 60), [])
            search.assert_called_once()
        self.assertEqual(stats['recovery_provider_notes'], ['Actor quota reached'])

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
        self.assertEqual(len(architect.await_args.args[0]), 22)
        self.assertIn('circuit diagram', {row['phrase'] for row in architect.await_args.args[0]})
        self.assertTrue(architect.await_args.kwargs['discover_topics'])
        self.assertNotIn('target_spokes', architect.await_args.kwargs)

    def test_two_gaps_keep_full_research_and_build_seven_existing_pages(self):
        from copy import deepcopy
        from test_keyword_coverage import animal_inventory, coverage_reply
        from test_research_quality import decision, pending_from_prompt
        from workers.pipeline import _process_apify_keywords
        primary, records, payload, destinations = animal_inventory()
        pid = self.project()
        own_urls = {page['target_keyword']: page.get('existing_url', 'https://animals.example/') for page in payload['pages']}
        gaps = {'wolf personality weaknesses', 'owl personality weaknesses'}
        def review(**kwargs):
            decisions = []
            for item in pending_from_prompt(kwargs):
                verdict = decision(item)
                if item['phrase'] not in gaps:
                    target = destinations.get(item['phrase'], item['phrase'])
                    verdict.update(decision='covered', placement='existing_page', target_url=own_urls[target],
                                   target_topic=target, coverage_gap='', reason='Already answered by the existing profile.')
                decisions.append(verdict)
            return {'decisions': decisions}
        with self.sessions() as db:
            project = db.get(Project, uuid.UUID(pid))
            project.domain = 'https://animals.example'
            project.target_keywords = [primary]
            project.audit_summary = json.dumps({'capabilities': ['Animal personality quiz with wolf, owl, bear, fox, eagle and deer profiles.']})
            for target, url in own_urls.items():
                db.add(Url(project_id=project.id, url=url, source_type='own', status='scraped',
                           h1=target, scraped_text='Animal personality traits, meanings, strengths and relationships.'))
            db.commit()
            bridges = {f'__related__{animal}|{qualifier}' for animal in ('wolf', 'owl', 'bear', 'fox', 'eagle', 'deer')
                       for qualifier in ('personality', 'animal', 'represent', 'quiz')}
            raw = [{**item, 'search_volume': 0} for item in records]
            raw.append({'phrase': 'wolf minecraft food', 'search_volume': 10000})
            with patch('scraping.apify_client_module.is_apify_configured', return_value=True), patch(
                'scraping.apify_client_module.research_keywords_via_apify', return_value=raw,
            ), patch('nlp.openrouter.is_ai_configured', return_value=True), patch('nlp.openrouter._chat_json', side_effect=review):
                count = _process_apify_keywords(db, project.id, [primary], bridges, {'minecraft'}, audit_summary=project.audit_summary)
            self.assertEqual(count, 2)
            self.assertEqual(len(db.execute(select(ResearchKeyword).where(ResearchKeyword.project_id == project.id)).scalars().all()), 73)
        imported = self.client.get(f'/api/hub-spoke/project-import/{pid}').json()
        self.assertEqual(imported['research_summary']['new_gaps'], 2)
        self.assertEqual(imported['research_summary']['planning_keywords'], 73)
        self.assertEqual(imported['research_summary']['pending_review'], 0)
        self.assertEqual(len(self.client.get(f'/api/projects/{pid}/keywords').json()['items']), 2)
        async def architect(**kwargs):
            if 'Discover missing page intents' in kwargs['user_prompt']:
                return {'proposals': []}
            if 'placement reviewer' in kwargs['system_prompt']:
                return coverage_reply(kwargs['user_prompt'], destinations)
            if 'information architect' in kwargs['system_prompt']:
                self.assertIn('reviewed_research', kwargs['user_prompt'])
                return deepcopy(payload)
            return approved_review(payload)
        with patch('nlp.hub_spoke_agent.is_ai_configured', return_value=True), patch('nlp.hub_spoke_agent._achat_json', side_effect=architect):
            response = self.client.post(f'/api/projects/{pid}/keywords/hub-spoke')
        self.assertEqual(response.status_code, 200, response.text)
        plan = response.json()['clusters']
        self.assertEqual(plan['keyword_coverage'], {'total': 73, 'used': 73, 'page_targets': 7, 'supporting': 66, 'excluded': 0})
        self.assertTrue(all(page['action'] == 'update' for page in plan['spokes']))
        self.assertEqual({page['existing_url'] for page in plan['spokes']}, set(own_urls.values()) - {'https://animals.example/'})

    def test_large_planning_inventory_is_balanced_bounded_and_reports_unselected_research(self):
        from workers.research_inventory import remember_candidates
        pid = self.project()
        with self.sessions() as db:
            db.add(Keyword(project_id=uuid.UUID(pid), phrase='circuit troubleshooting'))
            db.add(Url(project_id=uuid.UUID(pid), url='https://own.example/existing-reference',
                       source_type='own', h1='Circuit symbol reference'))
            db.commit()
            remember_candidates(db, uuid.UUID(pid), [
                {'phrase': f'circuit diagram model {index}'} for index in range(400)
            ], 'Apify')
        imported = self.client.get(f'/api/hub-spoke/project-import/{pid}').json()
        self.assertEqual(len(imported['keywords']), 300)
        self.assertEqual(imported['research_summary']['available_keywords'], 403)
        self.assertEqual(imported['research_summary']['not_included'], 103)
        self.assertIn('circuit diagram', imported['keywords'])
        self.assertIn('circuit troubleshooting', imported['keywords'])
        self.assertIn('circuit symbol reference', imported['keywords'])
        self.assertTrue(any(row['phrase'].startswith('circuit diagram model ') for row in imported['keyword_data']))

    def test_no_new_gaps_still_imports_primary_and_can_start_both_planners(self):
        pid = self.project()
        imported = self.client.get(f'/api/hub-spoke/project-import/{pid}').json()
        self.assertEqual(imported['keywords'], ['circuit diagram'])
        self.assertEqual(imported['research_summary']['new_gaps'], 0)
        mapping = {'hubs': [], 'master_hub': {'target_keyword': 'circuit diagram'}, 'spokes': [], 'keyword_assignments': []}
        with patch('nlp.hub_spoke_agent.build_site_architecture', new=AsyncMock(return_value=mapping)) as build:
            response = self.client.post(f'/api/projects/{pid}/keywords/hub-spoke')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(build.await_args.args[0][0]['phrase'], 'circuit diagram')
        with patch('app.hub_spoke.router.build_site_architecture', new=AsyncMock(return_value=mapping)) as build:
            response = self.client.post('/api/hub-spoke/build', json={
                'keywords': imported['keywords'], 'keyword_data': imported['keyword_data'],
                'context': imported['context'], 'project_id': pid, 'primary_keyword': 'circuit diagram',
            })
        self.assertEqual(response.status_code, 200, response.text)
        self.assertTrue(build.await_args.kwargs['discover_topics'])

    def test_pending_research_survives_review_outage_but_is_not_a_gap_or_shared_between_users(self):
        from workers.pipeline import _review_provider_keywords
        from workers.research_inventory import remember_candidates, record_review
        pid = self.project()
        with self.sessions() as db:
            with patch('nlp.openrouter.is_ai_configured', return_value=True), patch('nlp.openrouter.filter_keyword_gap_recommendations', return_value=None):
                kept = _review_provider_keywords(db, uuid.UUID(pid), ['circuit diagram'],
                    [{'phrase': 'circuit diagram grounding', 'search_volume': 0, 'difficulty': 0}], {'circuit'}, set(), '', 'Apify')
            self.assertEqual(kept, [])
            remember_candidates(db, uuid.UUID(pid), [{'phrase': 'circuit diagram celebrity gossip'}], 'Apify')
            record_review(db, uuid.UUID(pid), [{'source_phrase': 'circuit diagram celebrity gossip', 'decision': 'reject', 'reason': 'Unrelated reader task'}])
        imported = self.client.get(f'/api/hub-spoke/project-import/{pid}').json()
        self.assertEqual(imported['research_summary']['new_gaps'], 0)
        self.assertEqual(imported['research_summary']['pending_review'], 1)
        self.assertIn('circuit diagram grounding', imported['keywords'])
        self.assertNotIn('circuit diagram celebrity gossip', imported['keywords'])
        row = next(row for row in imported['keyword_data'] if row['phrase'] == 'circuit diagram grounding')
        self.assertEqual(row['research_status'], 'pending')
        self.assertEqual(row['search_volume'], 0)
        with self.sessions() as db:
            remember_candidates(db, uuid.UUID(pid), [{
                'phrase': 'circuit diagram safety checklist',
                'evidence': {'kind': 'editorial_inference', 'excerpt': 'circuit diagram'},
            }], 'AI editorial research')
        imported = self.client.get(f'/api/hub-spoke/project-import/{pid}').json()
        idea = next(row for row in imported['keyword_data'] if row['phrase'] == 'circuit diagram safety checklist')
        self.assertEqual(idea['evidence_type'], 'editorial_proposal')
        self.assertIn('not an observed search query', idea['seo_recommendation'])
        self.assertIsNone(idea['search_volume'])
        other = self.project()
        self.assertNotIn('circuit diagram grounding', self.client.get(f'/api/hub-spoke/project-import/{other}').json()['keywords'])
        self.client.headers['Authorization'] = f'Bearer {create_access_token(uuid.uuid4())}'
        self.assertIn(self.client.get(f'/api/hub-spoke/project-import/{pid}').status_code, (401, 404))

    def test_manual_keyword_generation_reviews_owned_coverage_and_persists_findings(self):
        pid = self.project()
        owned_url = 'https://own.example/circuit-guide'
        note = 'Explain troubleshooting as a section in the existing circuit guide.'
        with self.sessions() as db:
            db.add(Url(project_id=uuid.UUID(pid), url=owned_url, source_type='own', status='scraped',
                       h1='Circuit Guide', scraped_text='How to draw a circuit diagram.'))
            db.commit()
        with (
            patch('app.keywords.router.generate_ai_keywords', new=AsyncMock(side_effect=[
                [{'phrase': 'circuit diagram troubleshooting', 'type': 'long-tail', 'review_reason': note}], [], [], [], [],
            ])) as generate,
            patch('nlp.openrouter.generate_core_domain_terms', new=AsyncMock(return_value={
                'core_terms': ['circuit'], 'negative_terms': [],
            })),
        ):
            response = self.client.post(f'/api/projects/{pid}/keywords/generate')
        self.assertEqual(response.status_code, 200, response.text)
        for call in generate.await_args_list:
            self.assertTrue(call.kwargs['apply_gap_filter'])
            self.assertIn(owned_url, call.kwargs['audit_summary'])
        rows = self.client.get(f'/api/projects/{pid}/keywords').json()['items']
        self.assertEqual(rows[0]['seo_recommendation'], note)

    def test_editorial_enrichment_preserves_measured_metrics_and_reviewed_guidance(self):
        pid = self.project()
        with self.sessions() as db:
            db.add_all([
                Keyword(project_id=uuid.UUID(pid), phrase='circuit diagram examples', search_volume=100, difficulty=0),
                Keyword(project_id=uuid.UUID(pid), phrase='circuit diagram mistakes', seo_recommendation='Reviewed missing examples.'),
            ])
            db.commit()
        with patch('nlp.deepseek_seo.is_deepseek_configured', return_value=True), patch(
            'nlp.deepseek_seo.enrich_keywords_with_seo_data', return_value={
                'circuit diagram examples': {'search_volume': None, 'difficulty': None, 'recommendation': 'Show a worked example.'},
            },
        ) as enrich:
            response = self.client.post(f'/api/projects/{pid}/keywords/seo-enrich')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(enrich.call_args.args[0], ['circuit diagram examples'])
        rows = {row['phrase']: row for row in self.client.get(f'/api/projects/{pid}/keywords').json()['items']}
        self.assertEqual(rows['circuit diagram examples']['search_volume'], 100)
        self.assertEqual(rows['circuit diagram examples']['difficulty'], 0)
        self.assertEqual(rows['circuit diagram mistakes']['seo_recommendation'], 'Reviewed missing examples.')

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

    def test_research_batches_use_owned_content_and_distinct_topic_focuses(self):
        pid = uuid.UUID(self.project())
        generator = Mock(return_value=[])
        with self.sessions() as db:
            db.add_all([
                Url(project_id=pid, url='https://animalsoulquiz.com/', source_type='own', status='scraped',
                    h1='Discover Your Spirit Animal', scraped_text='55 spirit animal profiles with meanings and traits.'),
                Url(project_id=pid, url='https://animalsoulquiz.com/wolf-trivia-quiz', source_type='own', status='scraped',
                    h1='Wolf Trivia Quiz', scraped_text='Test your wolf knowledge.'),
            ])
            db.commit()
            total = _ensure_minimum_keyword_count(db, pid, ['spirit animal quiz'], {'spirit', 'animal'}, set(),
                json.dumps({'primary_keyword': 'spirit animal quiz'}), generator,
                lambda: ('https://ai.generated', 'AI Recommendations'))
            self.assertEqual(total, 0)
            self.assertFalse(db.execute(select(Keyword).where(Keyword.project_id == pid)).scalars().all())
        calls = generator.call_args_list
        self.assertGreater(len(calls), 1)
        self.assertEqual(len({call.kwargs['research_focus'] for call in calls}), len(calls))
        self.assertTrue(all(call.kwargs['apply_gap_filter'] for call in calls))
        context = json.loads(calls[0].kwargs['audit_summary'])
        self.assertEqual(context['primary_keyword'], 'spirit animal quiz')
        self.assertIn('Wolf Trivia Quiz', {page['heading'] for page in context['OWN SITE COVERAGE']})

    def test_hub_import_anchors_sparse_legacy_results_to_the_sites_main_topic(self):
        pid = uuid.UUID(self.project())
        with self.sessions() as db:
            project = db.get(Project, pid)
            project.domain = 'https://animalsoulquiz.com'
            project.audit_summary = json.dumps({'primary_keyword': 'spirit animal quiz'})
            project.target_keywords = ['wolf trivia quiz', 'owl trivia quiz']
            db.add(Keyword(project_id=pid, phrase='wolf trivia quiz'))
            db.add(Url(project_id=pid, url='https://animalsoulquiz.com/wolf-spirit-animal', source_type='own',
                       status='scraped', h1='Wolf Spirit Animal Meaning', scraped_text='Wolf symbolism and traits.'))
            db.commit()
        response = self.client.get(f'/api/hub-spoke/project-import/{pid}')
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['keywords'][0], 'spirit animal quiz')
        self.assertIn('wolf spirit animal meaning', response.json()['keywords'])
        self.assertEqual(json.loads(response.json()['context'])['primary_keyword'], 'spirit animal quiz')
        with self.sessions() as db:
            self.assertEqual(db.execute(select(Keyword.phrase).where(Keyword.project_id == pid)).scalars().all(), ['wolf trivia quiz'])

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
