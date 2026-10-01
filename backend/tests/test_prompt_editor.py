import json
import httpx
import pytest
from fastapi.testclient import TestClient

from backend import prompt_editor
from backend.main import create_app
from backend.tests.support import sign_in, url, fake_writer
from backend.tests.test_survey import fake_model
from backend.tests.test_storage import completed
from backend.tests.test_llm_client import transport, completion


@pytest.fixture
def app(tmp_path, monkeypatch):
    fake_model(monkeypatch); fake_writer(monkeypatch)
    with TestClient(create_app(tmp_path / 'editor.db')) as app:
        sign_in(app)
        app.generated = completed(app)
        yield app


@pytest.fixture
def model(monkeypatch):
    state = {'after': '# 수정 후 프롬프트\n\n팀즈 연동은 제외합니다.', 'message': '팀즈 연동을 제외하는 수정안입니다.', 'calls': []}
    async def reply(document, history, message):
        state['calls'].append((document, history, message))
        return state['message'], state['after']
    monkeypatch.setattr(prompt_editor, 'reply', reply)
    return state


def send(app, request_id='test-turn-0001', revision=None, message='팀즈 연동은 빼줘'):
    return app.post(url(app, '/editor'), json={'revision': app.generated['revision'] if revision is None else revision,
                                             'requestId': request_id, 'message': message})


def decide(app, decision='accept', request_id='test-turn-0001', revision=None):
    return app.post(url(app, f'/editor/{request_id}/decision'), json={
        'revision': app.generated['revision'] if revision is None else revision, 'decision': decision})


def test_proposal_does_not_modify_document_until_accepted(app, model):
    before = app.generated
    result = send(app)
    assert result.status_code == 200, result.text
    proposal = result.json()['turns'][0]
    assert proposal['status'] == 'proposed' and any(row['changed'] for row in proposal['diff'])
    assert app.get(url(app)).json() == before
    assert app.post(url(app, '/confirm'), json={'revision': before['revision']}).status_code == 400
    accepted = decide(app)
    assert accepted.status_code == 200, accepted.text
    data = accepted.json()
    assert data['state']['documentText'] == model['after'] and data['state']['manualEdited']
    assert not data['confirmed'] and data['revision'] == before['revision'] + 1
    assert data['turns'][0]['decisionMessage'] == '사용자의 요청대로 수정하였습니다.'
    assert data['turns'][0]['status'] == 'accepted'
    assert app.get('/api/shared').json()['prompts'] == []
    # A lost decision response can be retried without applying it twice.
    assert decide(app).json()['revision'] == data['revision']
    with app.app.state.database.connect() as db:
        row = db.execute('SELECT * FROM prompt_edit_turns').fetchone()
        assert row['before_text'] == before['state']['documentText'] and row['after_text'] == model['after']
        assert row['resolved_at'] and row['status'] == 'accepted'


def test_reject_preserves_original_and_conversation_continues(app, model):
    send(app)
    assert send(app, request_id='test-turn-0002').status_code == 400
    rejected = decide(app, 'reject').json()
    assert rejected['state'] == app.generated['state'] and rejected['revision'] == app.generated['revision']
    assert rejected['turns'][0]['status'] == 'rejected'
    assert decide(app, 'accept').status_code == 409
    model['after'] = None; model['message'] = '대신 어떤 공유 방법을 원하시나요?'
    result = send(app, request_id='test-turn-0002', message='다른 방법은?').json()
    assert result['turns'][-1]['status'] == 'answered'
    assert model['calls'][-1][1][0]['status'] == 'rejected'
    assert app.get(url(app)).json() == app.generated
    assert len(app.get(url(app, '/editor')).json()['turns']) == 2


def test_idempotent_request_and_stale_proposal(app, model):
    send(app); send(app)
    assert len(model['calls']) == 1
    assert send(app, message='다른 내용').status_code == 400
    before = app.generated
    saved = app.put(url(app), json={'revision': before['revision'], 'state': {**before['state'], 'documentText': '# 수동 수정'}}).json()
    assert app.get(url(app, '/editor')).json()['turns'][0]['status'] == 'stale'
    assert decide(app, revision=saved['revision']).status_code == 409
    assert app.get(url(app)).json()['state']['documentText'] == '# 수동 수정'


def test_newer_document_during_model_call_is_not_overwritten(app, monkeypatch):
    user_id = app.get('/api/auth/me').json()['user_id']
    async def concurrent_edit(document, history, message):
        db = app.app.state.database
        current = db.load(app.prompt_id, user_id)
        db.save(current, current['revision'], {**current['state'], 'documentText': '# 외부 변경'})
        return '수정안', '# 덮어쓰면 안 됨'
    monkeypatch.setattr(prompt_editor, 'reply', concurrent_edit)
    assert send(app).status_code == 409
    assert app.get(url(app)).json()['state']['documentText'] == '# 외부 변경'
    assert app.get(url(app, '/editor')).json()['turns'][0]['status'] == 'stale'


def test_owner_only_and_confirmed_prompt_rejected(app, model):
    with TestClient(app.app) as other:
        sign_in(other, employee_id='7654321')
        assert other.get(url(app, '/editor')).status_code == 404
        assert other.post(url(app, '/editor'), json={'revision': 0, 'message': '수정', 'requestId': 'other-1234'}).status_code == 404
        assert other.post(url(app, '/editor/test-turn-0001/decision'), json={'revision': 0, 'decision': 'accept'}).status_code == 404
    with TestClient(app.app) as anonymous:
        assert anonymous.get(url(app, '/editor')).status_code == 401
    confirmed = app.post(url(app, '/confirm'), json={'revision': app.generated['revision']}).json()
    assert send(app, revision=confirmed['revision']).status_code == 400
    assert not model['calls']


def test_llm_usage_and_turn_link_are_recorded(app, monkeypatch):
    for key, value in {'OPENAI_MODEL': 'test-deployment', 'OPENAI_API_KEY': 'test-secret',
                       'OPENAI_BASE_URL': 'https://test-resource.openai.azure.com', 'OPENAI_TIMEOUT_SECONDS': '60',
                       'OPENAI_CONNECT_TIMEOUT_SECONDS': '10', 'OPENAI_MAX_RETRIES': '0'}.items():
        monkeypatch.setenv(key, value)
    def handler(request):
        body = json.loads(request.content)
        assert body['response_format']['json_schema']['name'] == 'prompt_edit_response'
        assert json.loads(body['messages'][-1]['content'])['current_prompt'] == app.generated['state']['documentText']
        return httpx.Response(200, json=completion(json.dumps({'message': '공유 연동만 제외합니다.', 'revised_prompt': '# 수정안'})), headers={'x-request-id': 'edit-provider-1'})
    transport(monkeypatch, handler)
    assert send(app).status_code == 200
    with app.app.state.database.connect() as db:
        row = db.execute('SELECT * FROM llm_requests WHERE step=?', ('prompt_edit',)).fetchone()
        turn = db.execute('SELECT * FROM prompt_edit_turns').fetchone()
        assert row['prompt_id'] == app.prompt_id and row['request_id'] == turn['llm_request_id']
        assert row['status'] == 'success' and row['total_tokens'] == 15 and row['duration_ms'] >= 0


def test_failed_call_is_logged_and_retry_is_possible(app, monkeypatch):
    for key, value in {'OPENAI_MODEL': 'test-deployment', 'OPENAI_API_KEY': 'test-secret',
                       'OPENAI_BASE_URL': 'https://test-resource.openai.azure.com', 'OPENAI_TIMEOUT_SECONDS': '60',
                       'OPENAI_CONNECT_TIMEOUT_SECONDS': '10', 'OPENAI_MAX_RETRIES': '0'}.items():
        monkeypatch.setenv(key, value)
    transport(monkeypatch, lambda request: httpx.Response(500, json={'error': {'message': 'failure'}}))
    assert send(app).status_code == 502
    with app.app.state.database.connect() as db:
        assert db.execute("SELECT status FROM llm_requests WHERE step='prompt_edit'").fetchone()[0] == 'failed'
        assert db.execute('SELECT status FROM prompt_edit_turns').fetchone()[0] == 'failed'
    assert app.get(url(app)).json() == app.generated


def test_deleted_prompt_removes_editor_history(app, model):
    send(app)
    assert app.delete(url(app)).status_code == 200
    with app.app.state.database.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM prompt_edit_turns').fetchone()[0] == 0


def test_diff_preserves_text_and_marks_insertions_deletions():
    before = '# 업무\n팀즈로 공유\n삭제할 줄'
    after = '# 업무\n워드로 저장\n새 줄\n추가 줄'
    rows = prompt_editor.diff_rows(before, after)
    for side, expected in [('before', before), ('after', after)]:
        reconstructed = '\n'.join(''.join(part['text'] for part in row[side]['parts']) for row in rows if row[side] is not None)
        assert reconstructed == expected
    assert not rows[0]['changed'] and all(row['changed'] for row in rows[1:])


def test_shared_history_shows_only_accepted_changes_and_respects_visibility(app, model):
    send(app); accepted = decide(app).json()
    send(app, request_id='reject-turn-002', revision=accepted['revision'], message='반려할 비공개 요청')
    decide(app, 'reject', request_id='reject-turn-002', revision=accepted['revision'])
    model['after']=None
    send(app, request_id='answer-turn-003', revision=accepted['revision'], message='적용하지 않은 질문')
    confirmed=app.post(url(app,'/confirm'),json={'revision':accepted['revision']})
    assert confirmed.status_code==200
    path=f'/api/shared/{app.prompt_id}/editor-history'
    with TestClient(app.app) as other:
        sign_in(other,employee_id='7654321')
        assert other.get(path).status_code==404
        app.put(url(app,'/sharing'),json={'enabled':True})
        response=other.get(path)
        assert response.status_code==200
        rows=response.json()['turns']
        assert len(rows)==1 and rows[0]['status']=='accepted' and rows[0]['diff']
        assert rows[0]['decisionMessage']=='사용자의 요청대로 수정하였습니다.'
        assert '반려할 비공개 요청' not in response.text and '적용하지 않은 질문' not in response.text
        chat=other.get(path.replace('editor-history','editor-chat')).json()['turns']
        assert [turn['status'] for turn in chat]==['accepted','rejected','answered']
        assert chat[1]['message']=='반려할 비공개 요청' and chat[2]['message']=='적용하지 않은 질문'
        assert all(not turn['diff'] for turn in chat)
        assert not {'before_text','after_text','user_id','llm_request_id'} & set(rows[0])
        assert other.get(path,params={'before':-1}).status_code==400
        app.put(url(app,'/sharing'),json={'enabled':False})
        assert other.get(path).status_code==404
        assert other.get(path.replace('editor-history','editor-chat')).status_code==404
    with TestClient(app.app) as anonymous:
        assert anonymous.get(path).status_code==401
        assert anonymous.get(path.replace('editor-history','editor-chat')).status_code==401


def test_shared_history_empty_without_accepted_edits(app):
    app.post(url(app,'/confirm'),json={'revision':app.generated['revision']})
    app.put(url(app,'/sharing'),json={'enabled':True})
    assert app.get(f'/api/shared/{app.prompt_id}/editor-history').json()=={'turns':[],'nextCursor':None}


def test_personal_agent_history_and_accepted_edits_are_isolated(app, model):
    send(app)
    accepted=decide(app).json()
    confirmed=app.post(url(app,'/confirm'),json={'revision':accepted['revision']}).json()
    app.put(url(app,'/sharing'),json={'enabled':True})
    source_id=app.prompt_id
    public=app.get(f'/api/shared/{source_id}').json()
    history=app.get(f'/api/shared/{source_id}/editor-chat').json()
    copy=app.post(url(app,'/personal')).json()
    app.prompt_id=copy['promptId']
    assert len(app.get(url(app,'/editor')).json()['turns'])==1
    saved=app.put(url(app),json={'revision':copy['revision'],'state':{**copy['state'],'documentText':'# 개인 초안','manualEdited':True}}).json()
    model['after']='# 개인 Agent 수정'
    assert send(app,request_id='personal-turn-0002',revision=saved['revision']).status_code==200
    revised=decide(app,request_id='personal-turn-0002',revision=saved['revision']).json()
    assert revised['state']['documentText']==model['after']
    assert app.post(url(app,'/confirm'),json={'revision':revised['revision']}).status_code==200
    assert app.get(f'/api/shared/{source_id}').json()==public
    assert app.get(f'/api/shared/{source_id}/editor-chat').json()==history
    assert len(app.get(url(app,'/editor')).json()['turns'])==2
