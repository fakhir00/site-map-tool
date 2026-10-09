import asyncio
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, patch
from nlp import providers


class ProviderReliabilityTests(TestCase):
    def setUp(self):
        providers._status.clear()
        self.addCleanup(providers._status.clear)
        self.configs = [('DeepSeek', 'https://one.example', 'secret-one', 'one'),
                        ('OpenRouter', 'https://two.example', 'secret-two', 'two')]
        self.config_patch = patch('nlp.providers.configured_providers', return_value=self.configs)
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)

    def test_sync_falls_back_on_balance_failure_and_does_not_expose_keys(self):
        error = RuntimeError('secret-one raw provider error')
        error.status_code = 402
        first, second = MagicMock(), MagicMock()
        first.__enter__.return_value.chat.completions.create.side_effect = error
        second.__enter__.return_value.chat.completions.create.return_value = 'working response'
        with patch('nlp.providers.OpenAI', side_effect=[first, second]) as factory:
            self.assertEqual(providers.complete({'messages': []}), 'working response')
        self.assertEqual(factory.call_count, 2)
        status = providers.provider_status()
        self.assertFalse(status['providers'][0]['available'])
        self.assertTrue(status['providers'][1]['available'])
        self.assertIn('Insufficient balance', status['providers'][0]['message'])
        self.assertNotIn('secret-', str(status))
        self.assertEqual(second.__enter__.return_value.chat.completions.create.call_args.kwargs['model'], 'two')

    def test_async_falls_back_and_closes_clients(self):
        first, second = MagicMock(), MagicMock()
        first.__aenter__ = AsyncMock(return_value=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=TimeoutError())))))
        second.__aenter__ = AsyncMock(return_value=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value='ok')))))
        first.__aexit__ = AsyncMock()
        second.__aexit__ = AsyncMock()
        with patch('nlp.providers.AsyncOpenAI', side_effect=[first, second]):
            self.assertEqual(asyncio.run(providers.acomplete({'messages': []})), 'ok')
        first.__aexit__.assert_awaited_once()
        second.__aexit__.assert_awaited_once()

    def test_bounded_discovery_can_reach_fallback_when_first_provider_stalls(self):
        async def stalled(**kwargs):
            await asyncio.sleep(1)
        first, second = MagicMock(), MagicMock()
        first.__aenter__ = AsyncMock(return_value=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=stalled))))
        second.__aenter__ = AsyncMock(return_value=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value='recovered')))))
        first.__aexit__ = AsyncMock()
        second.__aexit__ = AsyncMock()
        with patch('nlp.providers.AsyncOpenAI', side_effect=[first, second]) as client:
            result = asyncio.run(providers.acomplete({'messages': []}, request_timeout=0.1))
        self.assertEqual(result, 'recovered')
        self.assertEqual(client.call_count, 2)
        self.assertLessEqual(client.call_args_list[0].kwargs['timeout'], 0.05)
        first.__aexit__.assert_awaited_once()

    def test_failed_accounts_are_not_retried_for_every_scan_batch(self):
        for config in self.configs:
            providers._record(config, False, 'Insufficient balance.')
        with patch('nlp.providers.OpenAI') as client:
            with self.assertRaisesRegex(providers.ProviderUnavailableError, 'Insufficient balance'):
                providers.complete({'messages': []})
        client.assert_not_called()

    def test_status_does_not_make_billed_calls_or_claim_untested_provider_works(self):
        with patch('nlp.providers.OpenAI') as client:
            status = providers.provider_status()
        client.assert_not_called()
        self.assertIsNone(status['providers'][0]['available'])

    def test_editorial_enrichment_does_not_create_fake_metrics(self):
        from nlp.deepseek_seo import enrich_keywords_with_seo_data
        with patch('nlp.deepseek_seo._get_deepseek_client'), patch('nlp.deepseek_seo._enrich_batch', return_value=[
            {'keyword': 'lunar age', 'search_volume': 9000, 'difficulty': 12, 'recommendation': 'Explain counting rules'},
            {'keyword': 'invented topic', 'recommendation': 'Ignore'},
        ]):
            result = enrich_keywords_with_seo_data(['lunar age'], ['lunar age'])
        self.assertIsNone(result['lunar age']['search_volume'])
        self.assertIsNone(result['lunar age']['difficulty'])
        self.assertNotIn('invented topic', result)

    def test_website_prompt_errors_preserve_provider_failure(self):
        from nlp.website_prompts import analyze_website_intent, generate_website_prompt
        with patch('nlp.website_prompts._chat_json', side_effect=providers.ProviderUnavailableError('AI unavailable')):
            with self.assertRaises(providers.ProviderUnavailableError):
                analyze_website_intent('lunar age')
        with patch('nlp.website_prompts._chat_text', side_effect=providers.ProviderUnavailableError('AI unavailable')):
            with self.assertRaises(providers.ProviderUnavailableError):
                generate_website_prompt('lunar age', 'tool', 'theme')

    def test_backend_only_deploy_has_packaged_theme(self):
        from app.website_prompts.service import get_master_theme_text
        with patch('app.website_prompts.service.THEME_FILE_PATH', '/nonexistent/repo-theme.txt'):
            self.assertGreater(len(get_master_theme_text()), 1000)

    def test_empty_prompt_is_not_returned_as_success(self):
        from app.website_prompts.service import generate_prompt_flow, generate_gap_page_flow
        with patch('app.website_prompts.service.generate_website_prompt', return_value=''), patch(
            'app.website_prompts.service.audit_website_prompt', return_value={'passed': False, 'score': 0}
        ):
            with self.assertRaisesRegex(ValueError, 'no usable'):
                generate_prompt_flow('lunar age', 'tool', [])
        self.assertIsNone(generate_gap_page_flow('lunar age', 'tool', [])['audit_score'])
