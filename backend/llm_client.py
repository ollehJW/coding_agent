"""Azure OpenAI client based on WiaNews, without newsletter-specific tracking."""
import asyncio
import contextvars
import json
import logging
import math
import os
import re
import time
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
from jsonschema import Draft202012Validator, SchemaError, ValidationError
from openai import AsyncAzureOpenAI, APIConnectionError, APIStatusError, APITimeoutError, RateLimitError

from . import config  # Load root .env before reading LLM settings.

log = logging.getLogger(__name__)


# (record function, user_id, prompt_id) for the current request; copied into tasks it starts.
usage_context = contextvars.ContextVar('llm_usage_context', default=None)


def record_usage(request_id, operation, attempt, status, started_at, started, usage, reasoning_effort, error=None):
    """Store one call's token usage; bookkeeping must never break the model call itself."""
    context = usage_context.get()
    if context is None:
        return
    record, user_id, prompt_id = context
    usage = usage or {}
    details = lambda key: (usage.get(key) or {})
    try:
        record({'request_id': request_id, 'user_id': user_id, 'prompt_id': prompt_id, 'step': operation,
                'provider': 'azure_openai', 'model': os.getenv('OPENAI_MODEL', '').strip(), 'reasoning_effort': reasoning_effort,
                'input_tokens': usage.get('prompt_tokens'), 'output_tokens': usage.get('completion_tokens'),
                'total_tokens': usage.get('total_tokens'), 'cached_input_tokens': details('prompt_tokens_details').get('cached_tokens'),
                'reasoning_tokens': details('completion_tokens_details').get('reasoning_tokens'),
                'attempt': attempt, 'status': status, 'error_type': type(error).__name__ if error else None,
                'started_at': started_at, 'completed_at': datetime.now(timezone.utc).isoformat(),
                'duration_ms': round((time.monotonic() - started) * 1000)})
    except Exception as failure:
        log.warning('LLM usage not recorded request_id=%s type=%s', request_id, type(failure).__name__)


class CompletionText(str):
    def __new__(cls, content, request_id, usage=None):
        value = super().__new__(cls, content)
        value.request_id = request_id
        value.usage = usage
        return value


class ConfigurationError(Exception):
    pass


class InvalidLLMResponse(Exception):
    pass


def number_setting(name, default, *, integer=False, minimum=0, maximum=600):
    raw = os.getenv(name, str(default))
    try:
        value = int(raw) if integer else float(raw)
        if not math.isfinite(value) or not minimum <= value <= maximum:
            raise ValueError
    except (ValueError, OverflowError):
        raise ConfigurationError(f'{name} 설정값을 확인해주세요.') from None
    return value


def create_llm_client():
    values = {key: os.getenv(key, '').strip() for key in ('OPENAI_MODEL', 'OPENAI_API_KEY', 'OPENAI_BASE_URL')}
    missing = [key for key, value in values.items() if not value]
    if missing:
        raise ConfigurationError('LLM 설정이 필요합니다: ' + ', '.join(missing))
    try:
        endpoint = urlsplit(values['OPENAI_BASE_URL'])
        valid = endpoint.scheme == 'https' and bool(endpoint.hostname) and not (
            endpoint.username or endpoint.password or endpoint.query or endpoint.fragment)
    except ValueError:
        valid = False
    if not valid:
        raise ConfigurationError('OPENAI_BASE_URL에 Azure 리소스의 HTTPS 주소를 설정해주세요.')
    api_version = os.getenv('OPENAI_API_VERSION', '2025-04-01-preview').strip()
    if not api_version:
        raise ConfigurationError('OPENAI_API_VERSION 설정값을 확인해주세요.')
    return AsyncAzureOpenAI(
        azure_endpoint=values['OPENAI_BASE_URL'].rstrip('/'),
        api_key=values['OPENAI_API_KEY'],
        api_version=api_version,
        timeout=httpx.Timeout(
            number_setting('OPENAI_TIMEOUT_SECONDS', 60, minimum=0.1),
            connect=number_setting('OPENAI_CONNECT_TIMEOUT_SECONDS', 10, minimum=0.1)),
        max_retries=0,  # Retries are handled once here, not again inside the SDK.
    )


def retryable(error):
    return isinstance(error, (RateLimitError, APIConnectionError, APITimeoutError)) or (
        isinstance(error, APIStatusError) and error.status_code >= 500)


def retry_delay(error):
    headers = getattr(getattr(error, 'response', None), 'headers', {})
    try:
        delay = float(headers['retry-after-ms']) / 1000 if headers.get('retry-after-ms') else float(headers.get('retry-after', '1'))
        return min(5, max(0, delay)) if math.isfinite(delay) else 1
    except (ValueError, TypeError):
        return 1


def invalid_constant(value):
    raise ValueError('Non-finite JSON number')


async def chat_completion(messages, schema=None, max_tokens=16000,
                          operation='prompt_generation', schema_name='wiacoding_response', reasoning_effort=None):
    """Return text (with request_id/usage); optionally require a validated JSON schema."""
    if type(max_tokens) is not int or max_tokens <= 0:
        raise ValueError('max_tokens must be a positive integer')
    validator = None
    if schema is not None:
        if not isinstance(schema, dict) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', schema_name):
            raise ValueError('유효한 schema와 schema_name이 필요합니다.')
        try:
            Draft202012Validator.check_schema(schema)
            validator = Draft202012Validator(schema)
        except SchemaError:
            raise ValueError('유효한 JSON Schema가 필요합니다.') from None
    retries = number_setting('OPENAI_MAX_RETRIES', 1, integer=True, maximum=5)
    for attempt in range(retries + 1):
        started = time.monotonic()
        started_at = datetime.now(timezone.utc).isoformat()
        request_id = str(uuid.uuid4())
        usage = None
        try:
            async with create_llm_client() as client:
                parameters = {'model': os.environ['OPENAI_MODEL'].strip(), 'messages': messages,
                              'max_completion_tokens': max_tokens}
                if reasoning_effort:
                    parameters['reasoning_effort'] = reasoning_effort
                if schema is not None:
                    parameters['response_format'] = {'type': 'json_schema', 'json_schema': {
                        'name': schema_name, 'strict': True, 'schema': schema}}
                response = await client.chat.completions.create(**parameters)
            # Tokens are billed even when the answer is rejected below, so capture usage first.
            request_id = getattr(response, '_request_id', None) or request_id
            usage = response.usage.model_dump() if response.usage else None
            if not response.choices:
                raise InvalidLLMResponse('LLM 응답에 결과가 없습니다.')
            choice = response.choices[0]
            content = choice.message.content
            if choice.finish_reason != 'stop' or choice.message.refusal or not content or not content.strip():
                raise InvalidLLMResponse('LLM 응답이 거절되었거나 완성되지 않았습니다.')
            if validator is not None:
                try:
                    value = json.loads(content, parse_constant=invalid_constant)
                    validator.validate(value)
                except (ValueError, ValidationError):
                    raise InvalidLLMResponse('LLM 응답이 요청한 JSON 형식과 일치하지 않습니다.') from None
            record_usage(request_id, operation, attempt + 1, 'success', started_at, started, usage, reasoning_effort)
            log.info('LLM success operation=%s attempt=%s request_id=%s duration_ms=%s',
                     operation, attempt + 1, request_id, round((time.monotonic() - started) * 1000))
            return CompletionText(content, request_id, usage)
        except asyncio.CancelledError:
            record_usage(request_id, operation, attempt + 1, 'cancelled', started_at, started, usage, reasoning_effort)
            log.info('LLM cancelled operation=%s attempt=%s request_id=%s', operation, attempt + 1, request_id)
            raise
        except Exception as error:
            record_usage(request_id, operation, attempt + 1, 'failed', started_at, started, usage, reasoning_effort, error)
            # Never log prompts, responses, API keys, or full provider exception messages.
            log.warning('LLM failed operation=%s attempt=%s type=%s status=%s duration_ms=%s',
                        operation, attempt + 1, type(error).__name__, getattr(error, 'status_code', None),
                        round((time.monotonic() - started) * 1000))
            if attempt == retries or not retryable(error):
                raise
            await asyncio.sleep(retry_delay(error))
