"""AI availability and bounded failover shared by scan and writing requests."""
import hashlib
import asyncio
import threading
import time
from typing import Any

from openai import AsyncOpenAI, OpenAI
from app.config import settings

_lock = threading.Lock()
_status: dict[str, dict[str, Any]] = {}


class ProviderUnavailableError(RuntimeError):
    pass


def configured_providers(writing: bool = False) -> list[tuple[str, str, str, str]]:
    choices = [
        ('TokenRouter', 'https://api.tokenrouter.com/v1', settings.TOKENROUTER_API_KEY,
         settings.TOKENROUTER_WRITING_MODEL if writing else settings.TOKENROUTER_MODEL),
        ('DeepSeek', 'https://api.deepseek.com', settings.DEEPSEEK_API_KEY, settings.DEEPSEEK_MODEL),
        ('Groq', 'https://api.groq.com/openai/v1', settings.GROQ_API_KEY, settings.GROQ_MODEL),
        ('OpenRouter', 'https://openrouter.ai/api/v1', settings.OPENROUTER_API_KEY, settings.OPENROUTER_MODEL),
    ]
    return [(name, url, key.strip(), model) for name, url, key, model in choices if key.strip()]


def _key(config):
    return hashlib.sha256(f'{config[0]}:{config[2]}:{config[3]}'.encode()).hexdigest()


def _record(config, available, message):
    with _lock:
        _status[_key(config)] = {'available': available, 'message': message, 'checked_at': time.time()}


def _failure(exc):
    code = getattr(exc, 'status_code', None)
    if code == 402:
        return 'Insufficient balance. Add credit or use another configured AI provider.'
    if code in (401, 403):
        return 'Credentials rejected or model access denied.'
    if code == 429:
        return 'Rate limit or quota reached.'
    if code in (400, 404, 422):
        return 'The provider rejected the request or configured model.'
    return 'The AI provider could not complete the request. Check connectivity and service availability.'


def provider_status():
    providers = []
    with _lock:
        for config in configured_providers():
            observed = _status.get(_key(config), {})
            fresh = time.time() - observed.get('checked_at', 0) < 300
            providers.append({'name': config[0], 'model': config[3],
                              'available': observed.get('available') if fresh else None,
                              'message': observed.get('message') if fresh else 'Not checked yet.',
                              'checked_at': observed.get('checked_at')})
    return {'configured': bool(providers), 'providers': providers,
            'message': 'Configured providers are tried in order when one is unavailable.' if providers else 'No AI provider is configured.'}


def _eligible(config):
    with _lock:
        previous = _status.get(_key(config), {})
    return previous.get('available') is not False or time.time() - previous.get('checked_at', 0) >= 60


def _request(config, request):
    return {**request, 'model': config[3]}


def _unavailable():
    status = provider_status()
    details = '; '.join(f"{p['name']}: {p['message']}" for p in status['providers'])
    return ProviderUnavailableError('AI unavailable. ' + (details or status['message']))


def complete(request: dict, writing=False):
    for config in configured_providers(writing):
        if not _eligible(config):
            continue
        try:
            with OpenAI(base_url=config[1], api_key=config[2], timeout=settings.AI_REQUEST_TIMEOUT, max_retries=0) as client:
                response = client.chat.completions.create(**_request(config, request))
            _record(config, True, 'AI requests are working.')
            return response
        except Exception as exc:
            _record(config, False, _failure(exc))
    raise _unavailable()


async def acomplete(request: dict, writing=False, request_timeout: float | None = None):
    configs = [config for config in configured_providers(writing) if _eligible(config)]
    deadline = time.monotonic() + request_timeout if request_timeout is not None else None
    for index, config in enumerate(configs):
        # A bounded caller must leave time for fallback providers. Previously
        # the discovery deadline cancelled the first provider before failover.
        timeout = settings.AI_REQUEST_TIMEOUT
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            timeout = min(timeout, remaining / (len(configs) - index))
        try:
            async with asyncio.timeout(timeout):
                async with AsyncOpenAI(base_url=config[1], api_key=config[2], timeout=timeout, max_retries=0) as client:
                    response = await client.chat.completions.create(**_request(config, request))
            _record(config, True, 'AI requests are working.')
            return response
        except Exception as exc:
            _record(config, False, _failure(exc))
    raise _unavailable()


def check_providers():
    # Explicit user-initiated probe; ordinary status reads make no billed calls.
    for config in configured_providers():
        try:
            with OpenAI(base_url=config[1], api_key=config[2], timeout=10, max_retries=0) as client:
                client.chat.completions.create(model=config[3], messages=[{'role': 'user', 'content': 'Reply OK.'}], max_tokens=8)
            _record(config, True, 'A test AI request succeeded.')
        except Exception as exc:
            _record(config, False, _failure(exc))
    return provider_status()
