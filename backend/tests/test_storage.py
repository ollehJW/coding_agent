import json

from fastapi.testclient import TestClient
import pytest

from backend.main import create_app
from backend.tests.support import fake_writer, sign_in, url
from backend.tests.test_survey import answer_all, fake_model

TABLES = ['chat_messages', 'background_items', 'task_definitions', 'survey_topics', 'survey_questions', 'survey_answers', 'prompt_documents']


@pytest.fixture
def client(tmp_path, monkeypatch):
    fake_model(monkeypatch)
    fake_writer(monkeypatch)
    with TestClient(create_app(tmp_path / 'app.db')) as value:
        sign_in(value)
        yield value


def counts(client, prompt_id):
    with client.app.state.database.connect() as db:
        return {table: db.execute(f'SELECT COUNT(*) FROM {table} WHERE prompt_id = ?', (prompt_id,)).fetchone()[0] for table in TABLES}


def completed(client):
    from backend.tests.test_api import complete
    saved = client.put(url(client), json={'revision': 0, 'state': complete()}).json()
    done = answer_all(client, saved)
    return client.post(url(client, '/generate'), json={'revision': done['revision'], 'state': done['state']}).json()


def test_prompt_is_stored_in_normalized_tables_and_restored_exactly(client):
    generated = completed(client)
    assert counts(client, client.prompt_id) == {'chat_messages': 0, 'background_items': 5, 'task_definitions': 2, 'survey_topics': 4,
                                                'survey_questions': 4, 'survey_answers': 4, 'prompt_documents': 1}
    assert client.get(url(client)).json() == generated
    with client.app.state.database.connect() as db:
        row = db.execute('SELECT title, stage, completed_at FROM prompts WHERE prompt_id = ?', (client.prompt_id,)).fetchone()
        assert (row['title'], row['stage']) == ('장비 예약 🚀', 3) and row['completed_at'] is None
    edited = {**generated['state'], 'manualEdited': True, 'documentText': '# 직접 수정'}
    saved = client.put(url(client), json={'revision': generated['revision'], 'state': edited}).json()
    with client.app.state.database.connect() as db:  # Only the latest document is kept, with the spec it was written from.
        row = db.execute('SELECT content, source, spec FROM prompt_documents').fetchone()
        assert (row['content'], row['source']) == ('# 직접 수정', 'edited') and json.loads(row['spec'])['goal'] == '장비 예약 🚀 도구'
    assert client.get(url(client)).json()['state'] == saved['state']


def test_prompts_are_listed_per_user_newest_first_and_deleted_completely(client):
    first = client.prompt_id
    completed(client)
    second = client.post('/api/prompts', json={}).json()
    assert [p['promptId'] for p in client.get('/api/prompts').json()['prompts']] == [second['promptId'], first]
    assert client.get('/api/prompts').json()['prompts'][1] | {'updatedAt': None} == {
        'promptId': first, 'title': '장비 예약 🚀', 'stage': 3, 'updatedAt': None, 'confirmed': False}
    database = client.app.state.database
    database.record_llm({'request_id': 'r1', 'user_id': None, 'prompt_id': first, 'step': 'survey_question', 'provider': 'azure_openai',
                         'model': 'm', 'total_tokens': 38, 'attempt': 1, 'status': 'success', 'started_at': '2026-09-30T00:00:00'})
    assert client.delete(url(client)).json() == {'ok': True}
    assert counts(client, first) == dict.fromkeys(TABLES, 0)
    with database.connect() as db:  # Usage stays for totals, detached from the deleted prompt.
        assert [tuple(r) for r in db.execute('SELECT prompt_id, total_tokens FROM llm_requests')] == [(None, 38)]
    assert client.delete(url(client)).status_code == 404
    assert [p['promptId'] for p in client.get('/api/prompts').json()['prompts']] == [second['promptId']]


def test_owned_former_workspace_is_moved_on_startup(tmp_path, monkeypatch):
    import json, time
    from backend.state import initial_state
    path = tmp_path / 'app.db'
    with TestClient(create_app(path)) as client:
        sign_in(client)
        user_id = client.get('/api/auth/me').json()['user_id']
        state = {**initial_state(), 'draft': {'name': '예전 초안', 'background': '', 'users': '', 'scope': ''}}
        with client.app.state.database.connect() as db:
            db.execute('INSERT INTO workspaces (token_hash, state, revision, updated_at, expires_at, user_id) VALUES (?, ?, 7, ?, ?, ?)',
                       ('b' * 64, json.dumps(state), '2026-09-01T00:00:00Z', int(time.time()) + 60, user_id))
    with TestClient(create_app(path)) as restarted:
        sign_in(restarted)
        titles = {p['title']: p for p in restarted.get('/api/prompts').json()['prompts']}
        assert '예전 초안' in titles
        moved = restarted.get(f"/api/prompts/{titles['예전 초안']['promptId']}").json()
        assert moved['revision'] == 7 and moved['state']['draft']['name'] == '예전 초안'
