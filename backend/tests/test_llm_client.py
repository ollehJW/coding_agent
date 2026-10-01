import asyncio
import json
import logging
import os

import httpx
import pytest
from openai import AsyncAzureOpenAI, APIStatusError, RateLimitError

from backend import config, llm_client as llm

SCHEMA = {'type': 'object', 'properties': {'title': {'type': 'string'}},
          'required': ['title'], 'additionalProperties': False}
MESSAGES = [{'role': 'user', 'content': 'private test prompt'}]


@pytest.fixture(autouse=True)
def configuration(monkeypatch):
    values = {'OPENAI_MODEL': 'test-deployment', 'OPENAI_API_KEY': 'test-secret',
              'OPENAI_BASE_URL': 'https://test-resource.openai.azure.com',
              'OPENAI_API_VERSION': '2025-04-01-preview', 'OPENAI_MAX_RETRIES': '1',
              'OPENAI_TIMEOUT_SECONDS': '60', 'OPENAI_CONNECT_TIMEOUT_SECONDS': '10'}
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def completion(content='{"title":"테스트"}', finish='stop', refusal=None):
    return {'id': 'chat-test', 'object': 'chat.completion', 'created': 0, 'model': 'test-deployment',
            'choices': [{'index': 0, 'finish_reason': finish,
                         'message': {'role': 'assistant', 'content': content, 'refusal': refusal}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15}}


def transport(monkeypatch, handler):
    clients = []
    def factory(**kwargs):
        assert kwargs['max_retries'] == 0
        assert kwargs['timeout'].read == 60
        assert kwargs['timeout'].connect == 10
        client = AsyncAzureOpenAI(**kwargs, http_client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
        clients.append(client)
        return client
    monkeypatch.setattr(llm, 'AsyncAzureOpenAI', factory)
    return clients


def test_sdk_request_and_validated_response(monkeypatch):
    def handler(request):
        assert request.url.path == '/openai/deployments/test-deployment/chat/completions'
        assert request.url.params['api-version'] == '2025-04-01-preview'
        assert request.headers['api-key'] == 'test-secret'
        body = json.loads(request.content)
        assert body['messages'] == MESSAGES
        assert body['max_completion_tokens'] == 1000
        assert body['response_format']['json_schema'] == {'name': 'task_definition', 'strict': True, 'schema': SCHEMA}
        return httpx.Response(200, json=completion(), headers={'x-request-id': 'provider-request-1'})
    clients = transport(monkeypatch, handler)
    result = asyncio.run(llm.chat_completion(MESSAGES, SCHEMA, max_tokens=1000, schema_name='task_definition'))
    assert json.loads(result) == {'title': '테스트'}
    assert result.request_id == 'provider-request-1'
    assert result.usage['total_tokens'] == 15
    assert all(client.is_closed() for client in clients)


def test_plain_text(monkeypatch):
    def handler(request):
        assert 'response_format' not in json.loads(request.content)
        return httpx.Response(200, json=completion('개발 프롬프트'))
    transport(monkeypatch, handler)
    assert asyncio.run(llm.chat_completion(MESSAGES)) == '개발 프롬프트'


@pytest.mark.parametrize('status', [429, 500, 503])
def test_transient_error_retried_once(monkeypatch, status):
    calls = []
    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(status, json={'error': {'message': 'transient', 'type': 'error'}}, headers={'retry-after-ms': '0'})
        return httpx.Response(200, json=completion())
    clients = transport(monkeypatch, handler)
    assert asyncio.run(llm.chat_completion(MESSAGES, SCHEMA))
    assert len(calls) == 2
    assert all(client.is_closed() for client in clients)


def test_retry_limit(monkeypatch):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, json={'error': {'message': 'limit'}}, headers={'retry-after': '0'})
    transport(monkeypatch, handler)
    with pytest.raises(RateLimitError):
        asyncio.run(llm.chat_completion(MESSAGES, SCHEMA))
    assert len(calls) == 2


@pytest.mark.parametrize('status', [400, 401, 403])
def test_permanent_error_not_retried_or_logged_verbatim(monkeypatch, caplog, status):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, json={'error': {'message': 'test-secret private test prompt'}})
    transport(monkeypatch, handler)
    caplog.set_level(logging.WARNING, logger='backend.llm_client')
    with pytest.raises(APIStatusError):
        asyncio.run(llm.chat_completion(MESSAGES, SCHEMA))
    assert len(calls) == 1
    assert 'test-secret' not in caplog.text
    assert 'private test prompt' not in caplog.text


@pytest.mark.parametrize('body', [completion(finish='length'), completion(refusal='refused'), completion(''),
                                 completion('not json'), completion('{"title": 42}'), completion('{"title":"x","extra":true}'),
                                 {**completion(), 'choices': []}, completion('{"title":NaN}')])
def test_invalid_responses_not_retried(monkeypatch, body):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200, json=body)
    transport(monkeypatch, handler)
    with pytest.raises(llm.InvalidLLMResponse):
        asyncio.run(llm.chat_completion(MESSAGES, SCHEMA))
    assert len(calls) == 1


def test_cancellation_propagates_and_closes_client(monkeypatch):
    def handler(request):
        raise asyncio.CancelledError()
    clients = transport(monkeypatch, handler)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(llm.chat_completion(MESSAGES, SCHEMA))
    assert len(clients) == 1 and clients[0].is_closed()


@pytest.mark.parametrize('key,value', [('OPENAI_API_KEY', ''), ('OPENAI_BASE_URL', 'http://bad.example'),
                                     ('OPENAI_TIMEOUT_SECONDS', 'nan'), ('OPENAI_MAX_RETRIES', '-1')])
def test_configuration_errors(key, value, monkeypatch):
    monkeypatch.setenv(key, value)
    with pytest.raises(llm.ConfigurationError):
        asyncio.run(llm.chat_completion(MESSAGES, SCHEMA))


def test_env_precedence_and_relative_database(tmp_path, monkeypatch):
    env = tmp_path / '.env'
    env.write_text('OPENAI_MODEL=file-model\nWIACODING_TEST_SETTING=loaded\n')
    monkeypatch.delenv('WIACODING_TEST_SETTING', raising=False)
    config.load_environment(env)
    assert os.environ['OPENAI_MODEL'] == 'test-deployment'
    assert os.environ['WIACODING_TEST_SETTING'] == 'loaded'
    monkeypatch.setenv('DB_PATH', 'backend/app.db')
    monkeypatch.chdir(tmp_path)
    assert config.database_path() == config.PROJECT_ROOT / 'backend/app.db'
    monkeypatch.delenv('WIACODING_TEST_SETTING')


@pytest.mark.parametrize('header,expected', [('2500', 2.5), ('99999', 5), ('-100', 0), ('NaN', 1), ('bad', 1)])
def test_retry_delay(header, expected):
    response = httpx.Response(429, headers={'retry-after-ms': header}, request=httpx.Request('POST', 'https://test.example'))
    error = RateLimitError('rate limit', response=response, body=None)
    assert llm.retry_delay(error) == expected


def test_every_attempt_records_token_usage(monkeypatch):
    calls = iter([httpx.Response(200, json=completion('not json')), httpx.Response(200, json={
        **completion(), 'usage': {'prompt_tokens': 30, 'completion_tokens': 8, 'total_tokens': 38,
                                  'prompt_tokens_details': {'cached_tokens': 12}, 'completion_tokens_details': {'reasoning_tokens': 3}}},
        headers={'x-request-id': 'provider-request-2'})])
    transport(monkeypatch, lambda request: next(calls))
    recorded = []
    token = llm.usage_context.set((recorded.append, 'user-1', 'prompt-1'))
    try:
        with pytest.raises(llm.InvalidLLMResponse):  # Invalid JSON is not retried, but its tokens were still billed.
            asyncio.run(llm.chat_completion(MESSAGES, SCHEMA, operation='survey_question', reasoning_effort='low'))
        asyncio.run(llm.chat_completion(MESSAGES, SCHEMA, operation='survey_question'))
    finally:
        llm.usage_context.reset(token)
    assert [(r['status'], r['error_type'], r['total_tokens']) for r in recorded] == [('failed', 'InvalidLLMResponse', 15), ('success', None, 38)]
    assert recorded[0]['reasoning_effort'] == 'low' and recorded[0]['user_id'] == 'user-1' and recorded[0]['prompt_id'] == 'prompt-1'
    assert (recorded[1]['request_id'], recorded[1]['cached_input_tokens'], recorded[1]['reasoning_tokens']) == ('provider-request-2', 12, 3)
    assert recorded[1]['step'] == 'survey_question' and recorded[1]['model'] == 'test-deployment' and recorded[1]['duration_ms'] >= 0


def test_usage_recording_failure_does_not_break_the_call(monkeypatch):
    transport(monkeypatch, lambda request: httpx.Response(200, json=completion()))
    def broken(entry):
        raise RuntimeError('database locked')
    token = llm.usage_context.set((broken, 'user-1', None))
    try:
        assert json.loads(asyncio.run(llm.chat_completion(MESSAGES, SCHEMA))) == {'title': '테스트'}
    finally:
        llm.usage_context.reset(token)
