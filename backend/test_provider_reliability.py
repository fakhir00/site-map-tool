import asyncio
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import AsyncMock, MagicMock, patch
from nlp import providers


class ProviderReliabilityTests(TestCase):
    def test_architecture_requests_json_mode_without_changing_list_research(self):
        from nlp.hub_spoke_agent import _achat_json as architecture_chat
        from nlp.openrouter import _achat_json as research_chat
        responses = [SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=body))])
                     for body in ['{"pages": []}', '[{"phrase": "owl symbolism"}]']]
        with patch('nlp.providers.acomplete', new=AsyncMock(side_effect=responses)) as complete:
            kwargs = {'system_prompt': 'Return JSON.', 'user_prompt': 'Review the supplied evidence.'}
            self.assertEqual(asyncio.run(architecture_chat(**kwargs)), {'pages': []})
            self.assertEqual(asyncio.run(research_chat(**kwargs)), [{'phrase': 'owl symbolism'}])
        self.assertEqual(complete.await_args_list[0].args[0]['response_format'], {'type': 'json_object'})
        self.assertNotIn('response_format', complete.await_args_list[1].args[0])

    def setUp(self):
        providers._status.clear()
        self.addCleanup(providers._status.clear)
        self.configs = [('DeepSeek', 'https://one.example', 'secret-one', 'one'),
                        ('OpenRouter', 'https://two.example', 'secret-two', 'two')]
        self.config_patch = patch('nlp.providers.configured_providers', return_value=self.configs)
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)

    def test_output_limit_cannot_be_mistaken_for_a_complete_architecture(self):
        from nlp.hub_spoke_agent import _achat_json
        response = SimpleNamespace(choices=[SimpleNamespace(
            finish_reason='length', message=SimpleNamespace(content='{"pages": []}'),
        )])
        with patch('nlp.providers.acomplete', new=AsyncMock(return_value=response)):
            with self.assertRaisesRegex(ValueError, 'output limit.*preserve all keyword decisions'):
                asyncio.run(_achat_json(system_prompt='Return JSON.', user_prompt='Build the plan.'))

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
        first.__aexit__ = AsyncMock(return_value=False)
        second.__aexit__ = AsyncMock(return_value=False)
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
        first.__aexit__ = AsyncMock(return_value=False)
        second.__aexit__ = AsyncMock(return_value=False)
        # Control the stage clock so host scheduling delays do not consume the
        # fallback budget. asyncio still cancels the genuinely stalled request.
        clock = SimpleNamespace(time=providers.time.time, monotonic=MagicMock(side_effect=[10.0, 10.0, 10.05]))
        with patch('nlp.providers.AsyncOpenAI', side_effect=[first, second]) as client, patch('nlp.providers.time', clock):
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

    def test_large_plan_gets_completion_time_and_preserves_fallback_reserve(self):
        first, second = MagicMock(), MagicMock()
        first.__aenter__ = AsyncMock(return_value=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(side_effect=TimeoutError())))))
        second.__aenter__ = AsyncMock(return_value=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value='complete plan')))))
        first.__aexit__ = AsyncMock(return_value=False)
        second.__aexit__ = AsyncMock(return_value=False)
        clock = SimpleNamespace(time=providers.time.time, monotonic=MagicMock(side_effect=[10.0, 10.0, 106.0]))
        with patch('nlp.providers.AsyncOpenAI', side_effect=[first, second]) as factory, patch('nlp.providers.time', clock):
            result = asyncio.run(providers.acomplete({'messages': [], 'max_tokens': 16000}, request_timeout=120))
        self.assertEqual(result, 'complete plan')
        self.assertEqual(factory.call_args_list[0].kwargs['timeout'], 96)
        self.assertEqual(factory.call_args_list[1].kwargs['timeout'], 24)
        first.__aexit__.assert_awaited_once()

    def test_sync_single_provider_retries_temporary_server_error_once(self):
        self.configs[:] = self.configs[:1]
        error = RuntimeError('secret-one provider response')
        error.status_code = 503
        client = MagicMock()
        create = client.__enter__.return_value.chat.completions.create
        create.side_effect = [error, 'recovered']
        with patch('nlp.providers.OpenAI', return_value=client), patch('nlp.providers.time.sleep'):
            self.assertEqual(providers.complete({'messages': []}), 'recovered')
        self.assertEqual(create.call_count, 2)
        self.assertTrue(providers.provider_status()['providers'][0]['available'])

    def test_transient_exhaustion_does_not_disable_next_planning_stage(self):
        self.configs[:] = self.configs[:1]
        create = AsyncMock(side_effect=[TimeoutError(), TimeoutError(), 'next stage recovered'])
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
        client.__aexit__ = AsyncMock(return_value=False)

        async def run():
            with self.assertRaisesRegex(providers.ProviderUnavailableError, 'timed out'):
                await providers.acomplete({'messages': []})
            self.assertEqual(create.await_count, 2)
            self.assertEqual(await providers.acomplete({'messages': []}), 'next stage recovered')

        with patch('nlp.providers.AsyncOpenAI', return_value=client), patch('nlp.providers.asyncio.sleep', new=AsyncMock()):
            asyncio.run(run())
        self.assertEqual(create.await_count, 3)
        self.assertEqual(client.__aexit__.await_count, 3)

    def test_invalid_request_is_not_retried_or_allowed_to_disable_other_requests(self):
        self.configs[:] = self.configs[:1]
        error = RuntimeError('secret-one rejected payload')
        error.status_code = 400
        client = MagicMock()
        create = client.__enter__.return_value.chat.completions.create
        create.side_effect = [error, 'valid request succeeded']
        with patch('nlp.providers.OpenAI', return_value=client):
            with self.assertRaisesRegex(providers.ProviderUnavailableError, 'rejected the request'):
                providers.complete({'messages': []})
            self.assertEqual(create.call_count, 1)
            self.assertEqual(providers.complete({'messages': []}), 'valid request succeeded')
        self.assertEqual(create.call_count, 2)

    def test_actual_balance_failure_is_not_retried_and_keeps_account_cooldown(self):
        self.configs[:] = self.configs[:1]
        error = RuntimeError('secret-one rejected account')
        error.status_code = 402
        client = MagicMock()
        create = client.__enter__.return_value.chat.completions.create
        create.side_effect = error
        with patch('nlp.providers.OpenAI', return_value=client):
            for _ in range(2):
                with self.assertRaisesRegex(providers.ProviderUnavailableError, 'Insufficient balance'):
                    providers.complete({'messages': []})
        self.assertEqual(create.call_count, 1)

    def test_exhausted_async_deadline_does_not_start_another_request(self):
        self.configs[:] = self.configs[:1]
        async def stalled(**kwargs):
            await asyncio.sleep(1)
        create = AsyncMock(side_effect=stalled)
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
        client.__aexit__ = AsyncMock(return_value=False)
        with patch('nlp.providers.AsyncOpenAI', return_value=client):
            with self.assertRaisesRegex(providers.ProviderUnavailableError, 'timed out'):
                asyncio.run(providers.acomplete({'messages': []}, request_timeout=0.01))
        create.assert_awaited_once()
        client.__aexit__.assert_awaited_once()

    def test_explicit_planning_budget_can_exceed_default_short_request_timeout(self):
        self.configs[:] = self.configs[:1]
        async def slow_plan(**kwargs):
            await asyncio.sleep(0.03)
            return 'complete plan'
        create = AsyncMock(side_effect=slow_plan)
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
        client.__aexit__ = AsyncMock(return_value=False)
        with patch('nlp.providers.AsyncOpenAI', return_value=client), patch(
            'nlp.providers.settings.AI_REQUEST_TIMEOUT', 0.01,
        ):
            self.assertEqual(asyncio.run(providers.acomplete({'messages': []}, request_timeout=0.2)), 'complete plan')
        create.assert_awaited_once()

    def test_cancellation_is_not_retried_or_recorded_as_provider_failure(self):
        async def cancelled(**kwargs):
            raise asyncio.CancelledError()
        create = AsyncMock(side_effect=cancelled)
        client = MagicMock()
        client.__aenter__ = AsyncMock(return_value=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
        client.__aexit__ = AsyncMock(return_value=False)
        with patch('nlp.providers.AsyncOpenAI', return_value=client):
            with self.assertRaises(asyncio.CancelledError):
                asyncio.run(providers.acomplete({'messages': []}))
        create.assert_awaited_once()
        self.assertIsNone(providers.provider_status()['providers'][0]['available'])

    def test_failure_diagnostics_are_specific_and_sanitized(self):
        error = RuntimeError('secret-one raw body with user content')
        error.status_code = 503
        self.assertIn('HTTP 503', providers._failure(error))
        self.assertIn('timed out', providers._failure(TimeoutError('secret-one')))
        self.assertIn('connect', providers._failure(ConnectionError('secret-one')))
        self.assertNotIn('secret-one', providers._failure(error))

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
