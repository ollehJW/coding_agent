import asyncio
import copy
import json

import pytest
from fastapi.testclient import TestClient

from backend import background_agent as agent
from backend.llm_client import InvalidLLMResponse, ConfigurationError
from backend.main import create_app
from backend.tests.support import sign_in, url
from backend.state import initial_state


FACT = '주간보고를 혼자 정리합니다. 매주 엑셀 자료를 모아 표로 만들고 누락이 없는지 확인합니다.'


def output(message_id='turn_0001', message=FACT, ready=False):
    categories = copy.deepcopy(agent.initial_agent()['categories'])
    for category in agent.CATEGORIES:
        if ready or category['id'] == 'problem':
            categories[category['id']] = {'status': 'complete', 'summary': f'{category["label"]}: {message}',
                                          'reason': '', 'evidence': [{'message_id': message_id, 'quote': message[:30]}]}
    return {'title': '개인 주간보고 정리', 'message': '누가 사용하고 어떤 순서로 처리하나요?' if not ready else '과제 초안을 검토해주세요.',
            'next_categories': ['users', 'current'] if not ready else [], 'categories': categories}


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'app.db')) as client:
        sign_in(client)
        client.get(url(client))
        yield client


def model(monkeypatch, ready=False):
    calls = []
    async def completion(messages, schema, **kwargs):
        data = json.loads(messages[-1]['content'])
        calls.append(data)
        last = data['conversation'][-1]
        return json.dumps(output(last['id'], last['content'], ready=ready), ensure_ascii=False)
    monkeypatch.setattr(agent, 'chat_completion', completion)
    return calls


def post(client, revision=0, request_id='turn_0001', message=FACT, **kwargs):
    return client.post(url(client, '/background'), json={'revision': revision, 'requestId': request_id, 'message': message, **kwargs})


def test_partial_interview_is_persisted_and_cannot_confirm(client, monkeypatch):
    calls = model(monkeypatch)
    result = post(client)
    assert result.status_code == 200
    data = result.json()
    assert not data['backgroundAgent']['ready']
    assert len(data['backgroundAgent']['remaining']) == 4
    assert data['backgroundAgent']['messages'][-2]['content'] == FACT
    assert client.get(url(client)).json() == data
    forged = data['state']
    forged['context'] = dict.fromkeys(['problem', 'current', 'impact', 'users', 'goal'], FACT)
    forged['draft'] = dict.fromkeys(['name', 'background', 'users', 'scope'], FACT)
    forged['project'] = {**forged['draft'], 'type': 'reservation'}
    forged['stage'] = 2
    forged['backgroundAgent'] = {'ready': True}
    assert client.put(url(client), json={'revision': 1, 'state': forged}).status_code == 400
    assert len(calls) == 1


def test_history_completion_type_handoff_idempotency_and_reset(client, monkeypatch):
    model(monkeypatch)
    first = post(client).json()
    calls = model(monkeypatch, ready=True)
    second = post(client, revision=1, request_id='turn_0002', message=FACT + ' 첫 버전은 표 작성까지만 합니다.').json()
    assert len(calls[0]['conversation']) == 4
    assert second['backgroundAgent']['ready']
    assert 'objective' not in second['state']['draft']
    assert second['state']['draft']['scope'].startswith('원하는 변화·범위:')
    assert post(client, revision=1, request_id='turn_0002', message=FACT + ' 첫 버전은 표 작성까지만 합니다.').json() == second
    assert len(calls) == 1
    assert post(client, revision=2, request_id='turn_0002', message='다른 내용').status_code == 400
    assert post(client, revision=0, request_id='turn_0003').status_code == 409
    assert len(calls) == 1
    state = second['state']
    state['project'] = {**state['draft'], 'type': 'reservation'}  # Server uses agent classification.
    state['stage'] = 2
    saved = client.put(url(client), json={'revision': 2, 'state': state}).json()
    assert saved['state']['project']['type'] == 'general'  # Not categorised; the browser's value is ignored.
    assert len(saved['state']['project']['messages']) == 2
    assert saved['state']['survey']['signature'] == saved['state']['project']['signature']
    assert client.get(url(client, '/questions')).json()['questions'] == []
    assert post(client, revision=3, request_id='turn_0003').status_code == 400
    model(monkeypatch, ready=False)
    revised = post(client, revision=3, request_id='turn_0003', resetProject=True).json()
    assert not revised['backgroundAgent']['ready']
    assert revised['state']['project'] is None
    assert client.delete(url(client)).json() == {'ok': True}  # Starting over is a new prompt; the old one is removed.
    with client.app.state.database.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM chat_messages').fetchone()[0] == 0


def test_deferred_item_blocks_completion_and_stays_in_draft():
    response = output(ready=True)
    response['categories']['impact'].update(status='deferred', reason='사용자가 다음 주에 건수를 확인하기로 함')
    response['next_categories'] = ['impact']
    result = agent.clean_response(response, [{'id': 'turn_0001', 'role': 'user', 'content': FACT}])
    assert not result['ready'] and result['deferred'] == ['impact']
    draft = agent.draft_from_agent(result)
    assert '확인 필요' in draft['background']


def test_saved_workspace_with_removed_categories_is_normalized(monkeypatch):
    calls = []
    async def completion(messages, schema, **kwargs):
        calls.append(json.loads(messages[-1]['content']))
        return json.dumps(output(), ensure_ascii=False)
    monkeypatch.setattr(agent, 'chat_completion', completion)
    saved = agent.initial_agent()
    saved['categories'] = {'purpose': {'status': 'complete', 'summary': '예전', 'reason': '', 'evidence': []}}
    asyncio.run(agent.run_turn(saved, FACT, 'turn_0001'))
    assert list(calls[0]['previous_categories']) == agent.IDS


@pytest.mark.parametrize('change', [
    lambda r: r['categories']['problem'].update(status='not_applicable', reason='생략'),
    lambda r: r['categories']['problem'].update(evidence=[]),
    lambda r: r['categories']['problem'].update(evidence=[{'message_id': 'assistant_0', 'quote': FACT[:30]}]),
    lambda r: r['categories']['problem'].update(evidence=[{'message_id': 'turn_0001', 'quote': '사용자가 말하지 않은 수치 100명'}]),
    lambda r: r['categories']['impact'].update(status='deferred', reason=''),
    lambda r: r['categories'].pop('current'),
    lambda r: r.update(next_categories=['problem']),
])
def test_invalid_skip_evidence_and_question_targets_rejected(change):
    response = output(ready=True)
    change(response)
    with pytest.raises(InvalidLLMResponse):
        agent.clean_response(response, [{'id': 'turn_0001', 'role': 'user', 'content': FACT}])


def test_core_unknown_is_not_completion():
    response = output(ready=True)
    response['categories']['goal'].update(status='deferred', reason='아직 범위를 모름')
    response['next_categories'] = ['goal']
    result = agent.clean_response(response, [{'id': 'turn_0001', 'role': 'user', 'content': FACT}])
    assert not result['ready'] and result['remaining'] == ['goal']


@pytest.mark.parametrize('error,status', [(InvalidLLMResponse('invalid'), 502), (ConfigurationError('secret-key'), 503)])
def test_failure_does_not_write_or_leak_provider_details(client, monkeypatch, error, status):
    async def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(agent, 'chat_completion', fail)
    response = post(client)
    assert response.status_code == status and 'secret-key' not in response.text
    current = client.get(url(client)).json()
    assert current['revision'] == 0 and current['backgroundAgent'] is None


def test_multi_tab_change_during_model_call_cannot_overwrite(client, monkeypatch):
    async def completion(messages, schema, **kwargs):
        db = client.app.state.database
        with db.connect() as connection:
            connection.execute('UPDATE prompts SET revision=revision+1')
        return json.dumps(output())
    monkeypatch.setattr(agent, 'chat_completion', completion)
    assert post(client).status_code == 409
    assert client.get(url(client)).json()['backgroundAgent'] is None


def test_empty_message_and_session_validation(client):
    assert post(client, message='   ').status_code == 400
    assert post(client, message='x' * 3001).status_code == 400
    assert post(client, request_id='short').status_code == 400
    client.cookies.clear()
    assert post(client).status_code == 401
