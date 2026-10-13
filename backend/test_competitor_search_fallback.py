import base64
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import MagicMock, patch
from urllib.parse import quote

from workers.pipeline import (
    _competitor_gap_completion_message,
    _discover_competitor_domains,
    _extract_google_result_urls,
    _search_bing_result_urls,
    _search_duckduckgo_html_urls,
    _search_result_urls,
)


LIMIT_ERROR = 'Free tier limit reached (100 searches). An Apify paid plan is required to continue.'


class CompetitorSearchFallbackTests(TestCase):
    def project(self):
        return SimpleNamespace(own_domain='https://own.example', domain='https://own.example',
                               search_locale='us', audit_summary='Spirit animal quizzes and personality profiles')

    def test_google_preserves_per_page_evidence_and_prefers_the_heading_link(self):
        html = '''<div id="search"><div class="MjjYud">
          <div class="g"><a href="https://navigation.example">Menu</a>
            <a href="/url?q=https%3A%2F%2Fspecialist.example%2Ftools%2F42"><h3>Spirit Animal Quiz</h3></a>
            <div class="VwiC3b">Discover your animal personality.</div></div>
          <div class="g"><a href="https://unrelated.example/"><h3>Mortgage Rates</h3></a>
            <div class="VwiC3b">Compare home loans.</div></div>
        </div></div>'''
        details = {}
        urls = _extract_google_result_urls(html, result_details_out=details)
        self.assertEqual(urls[0], 'https://specialist.example/tools/42')
        self.assertEqual(details[urls[0]]['title'], 'Spirit Animal Quiz')
        self.assertEqual(details[urls[0]]['snippet'], 'Discover your animal personality.')
        self.assertEqual(details['https://unrelated.example/']['snippet'], 'Compare home loans.')
        self.assertNotIn('animal', details['https://unrelated.example/']['snippet'])

    def test_bing_preserves_evidence_through_redirect_links(self):
        url = 'https://specialist.example/tools/42'
        encoded = base64.urlsafe_b64encode(url.encode()).decode().rstrip('=')
        html = f'''<li class="b_algo"><h2><a href="https://www.bing.com/ck/a?u=a1{encoded}">
          Spirit Animal Quiz</a></h2><div class="b_caption"><p>Animal personality test.</p></div></li>'''
        details = {}
        with patch('requests.get', return_value=SimpleNamespace(status_code=200, text=html)):
            urls = _search_bing_result_urls('spirit animal quiz', result_details_out=details)
        self.assertEqual(urls, [url])
        self.assertEqual(details[url]['title'], 'Spirit Animal Quiz')
        self.assertEqual(details[url]['snippet'], 'Animal personality test.')

    def test_duckduckgo_preserves_evidence_for_relative_redirects(self):
        url = 'https://specialist.example/tools/42'
        html = f'''<div class="result"><a class="result__a" href="/l/?uddg={quote(url)}">
          Spirit Animal Quiz</a><a class="result__snippet">Find your animal traits.</a></div>'''
        details = {}
        with patch('requests.get', return_value=SimpleNamespace(status_code=200, text=html)):
            urls = _search_duckduckgo_html_urls('spirit animal quiz', result_details_out=details)
        self.assertEqual(urls, [url])
        self.assertEqual(details[url]['snippet'], 'Find your animal traits.')

    def test_fallback_merges_evidence_when_google_is_challenged(self):
        html = '''<li class="b_algo"><h2><a href="https://specialist.example/42">Spirit Animal Quiz</a></h2>
          <p>Personality and animal traits.</p></li>'''
        details = {}
        with patch('requests.get', side_effect=[
            SimpleNamespace(status_code=429, text=''), SimpleNamespace(status_code=200, text=html),
        ]):
            urls = _search_result_urls('spirit animal quiz', include_google=True, max_results=1,
                                       result_details_out=details)
        self.assertEqual(urls, ['https://specialist.example/42'])
        self.assertEqual(details[urls[0]]['source'], 'bing_html')

    def test_apify_quota_failure_still_finds_branded_competitors_from_fallback_evidence(self):
        html = '''<div id="search">
          <div class="g"><a href="https://specialist.example/tools/42"><h3>Spirit Animal Quiz</h3></a>
            <div class="VwiC3b">Find your spirit animal with this personality quiz.</div></div>
          <div class="g"><a href="https://own.example/"><h3>Spirit Animal Quiz</h3></a></div>
          <div class="g"><a href="https://reddit.com/quiz"><h3>Spirit Animal Quiz</h3></a></div>
          <div class="g"><a href="https://animal-news.example/"><h3>Animal news</h3></a>
            <div class="VwiC3b">Local wildlife and zoo news.</div></div>
        </div>'''
        def limited(query, **kwargs):
            kwargs['diagnostics'].append(LIMIT_ERROR)
            return []
        ranking = {}
        notes = []
        with (
            patch('scraping.apify_client_module.is_apify_configured', return_value=True),
            patch('scraping.apify_client_module.search_google_via_apify', side_effect=limited) as apify,
            patch('requests.get', return_value=SimpleNamespace(status_code=200, text=html)),
            patch('nlp.dataforseo.is_dataforseo_configured', return_value=False),
            patch('workers.pipeline._llm_filter_competitor_domains', return_value=[]) as judge,
        ):
            domains = _discover_competitor_domains(
                self.project(), ['spirit animal quiz', 'animal personality quiz'],
                ranking_urls_out=ranking, diagnostics_out=notes,
            )
        self.assertEqual(domains, ['https://specialist.example'])
        self.assertEqual(ranking[domains[0]], ['https://specialist.example/tools/42'])
        apify.assert_called_once()
        candidates = judge.call_args.args[2]
        specialist = next(item for item in candidates if item['domain'] == domains[0])
        self.assertIn('Spirit Animal Quiz', specialist['titles'])
        self.assertIn('Find your spirit animal', specialist['snippets'][0])

    def test_bare_candidate_urls_do_not_prevent_configured_backup_serp(self):
        with (
            patch('scraping.apify_client_module.is_apify_configured', return_value=False),
            patch('workers.pipeline._search_result_urls', return_value=['https://animal-news.example/']),
            patch('nlp.dataforseo.is_dataforseo_configured', return_value=True),
            patch('workers.pipeline.get_db', return_value=MagicMock()),
            patch('nlp.dataforseo.search_competitors', return_value=[{
                'url': 'https://specialist.example/42', 'title': 'Spirit Animal Quiz',
                'snippet': 'Discover your animal personality',
            }]) as backup,
            patch('workers.pipeline._llm_filter_competitor_domains', return_value=[]),
        ):
            domains = _discover_competitor_domains(self.project(), ['spirit animal quiz'])
        backup.assert_called_once()
        self.assertEqual(domains, ['https://specialist.example'])

    def test_matching_fallback_evidence_does_not_trigger_paid_backup(self):
        def fallback(query, **kwargs):
            url = 'https://specialist.example/42'
            kwargs['result_details_out'][url] = {'title': 'Spirit Animal Quiz', 'snippet': 'Find your animal'}
            return [url]
        with (
            patch('scraping.apify_client_module.is_apify_configured', return_value=False),
            patch('workers.pipeline._search_result_urls', side_effect=fallback),
            patch('nlp.dataforseo.is_dataforseo_configured', return_value=True),
            patch('nlp.dataforseo.search_competitors') as backup,
            patch('workers.pipeline._llm_filter_competitor_domains', return_value=[]),
        ):
            domains = _discover_competitor_domains(self.project(), ['spirit animal quiz'])
        backup.assert_not_called()
        self.assertEqual(domains, ['https://specialist.example'])

    def test_limit_message_does_not_blame_site_scope(self):
        message = _competitor_gap_completion_message(0, [], {}, [
            f'Apify competitor search failed: {LIMIT_ERROR}; fallback search found 13 candidate sites, '
            'but none had enough direct-page evidence',
        ])
        self.assertIn('allowance is exhausted', message)
        self.assertNotIn('seed keywords', message)
        self.assertNotIn('site scope', message)
