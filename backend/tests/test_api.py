import copy
import hashlib
import json
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.content import CONTEXT_STEPS
from backend.database import Database
from backend.main import create_app, DEFAULT_DB_PATH
from backend.migrate_db import migrate
from backend.state import initial_state
from backend.tests.test_survey import fake_model, answer_all
from backend.tests.support import fake_writer, sign_in, url


@pytest.fixture
def client(tmp_path, monkeypatch):
    fake_model(monkeypatch)
    fake_writer(monkeypatch)
    with TestClient(create_app(tmp_path / 'app.db')) as value:
        sign_in(value)
        yield value


def complete():
    state = initial_state()
    state['context'] = {s['id']: '\n'.join(s['options'][0]) for s in CONTEXT_STEPS}
    state['draft'] = {'name': '장비 예약 🚀', 'background': '메신저로 예약', 'users': '팀원 20명', 'scope': '예약 관리'}
    state['project'] = {**state['draft'], 'type': 'reservation'}
    state['stage'] = 2
    return state


def answered(client, revision=0, custom='팀장이 승인'):
    """Save complete() and answer every generated question; returns the last API response."""
    saved = client.put(url(client), json={'revision': revision, 'state': complete()}).json()
    return answer_all(client, saved, custom)


def test_full_workflow_and_restart(tmp_path, monkeypatch):
    fake_model(monkeypatch)
    fake_writer(monkeypatch)
    path = tmp_path / 'app.db'
    with TestClient(create_app(path)) as client:
        sign_in(client)
        first = client.get(url(client))
        assert first.json()['revision'] == 0
        state = complete()
        response = client.put(url(client), json={'revision': 0, 'state': state})
        assert response.status_code == 200
        assert response.json()['state']['project']['signature'] == json.dumps(state['draft'], ensure_ascii=False, separators=(',', ':'))
        assert client.put(url(client), json={'revision': 0, 'state': state}).status_code == 409
        done = answer_all(client, response.json())
        assert len(client.get(url(client, '/questions')).json()['questions']) == 4
        revision = done['revision']
        generated = client.post(url(client, '/generate'), json={'revision': revision, 'state': done['state']})
        assert generated.status_code == 200
        edited = generated.json()['state']
        assert edited['stage'] == 3 and '팀장이 승인' in edited['documentText']
        edited.update(manualEdited=True, documentText='# 사용자 수정\n<기록>')
        assert client.put(url(client), json={'revision': revision + 1, 'state': edited}).status_code == 200
    with TestClient(create_app(path)) as restarted:
        sign_in(restarted)  # Same account on a new browser and a restarted server.
        restored = restarted.get(url(restarted)).json()
        assert restored['state'] == edited
        assert restored['revision'] == revision + 2
        assert restarted.delete(url(restarted)).json() == {'ok': True}
        assert restarted.get('/api/prompts').json()['prompts'] == []
        assert restarted.get(url(restarted)).status_code == 404


def test_login_required_and_workspaces_are_per_account(client):
    state = complete()
    client.put(url(client), json={'revision': 0, 'state': state})
    with TestClient(client.app) as anonymous:
        anonymous.prompt_id = client.prompt_id
        assert anonymous.get(url(anonymous)).status_code == 401
        assert anonymous.get('/api/prompts').status_code == 401
        assert anonymous.get('/api/background').status_code == 401
        assert anonymous.get('/api/health').status_code == 200
    with TestClient(client.app) as other:
        sign_in(other, employee_id='7654321')
        assert other.get(url(other)).json()['state']['project'] is None
        assert other.get(url(client)).status_code == 404  # Another account's prompt is invisible.
    assert client.get(url(client)).json()['state']['project']['name'] == state['project']['name']
    assert client.post('/api/auth/logout', json={}).status_code == 200
    assert client.get(url(client)).status_code == 401


def test_login_rules_match_wianews(client):
    with TestClient(client.app) as browser:
        assert browser.post('/api/auth/login', json={'employee_id': '1234567', 'password': 'wrong'}).status_code == 401
        user = sign_in(browser, employee_id='1111111', must_change=True)
        assert user['must_change_password'] == 1 and 'password_hash' not in user
        assert browser.get('/api/prompts').status_code == 403  # Initial password must be changed first.
        weak = browser.post('/api/auth/password', json={'current_password': 'Passw0rd!', 'new_password': 'abcdefgh'})
        assert weak.status_code == 400 and '특수문자' in weak.json()['error']
        changed = browser.post('/api/auth/password', json={'current_password': 'Passw0rd!', 'new_password': 'N3w-secret!'})
        assert changed.status_code == 200 and changed.json()['must_change_password'] == 0
        assert browser.post('/api/prompts', json={}).status_code == 201
        for _ in range(10):
            browser.post('/api/auth/login', json={'employee_id': '2222222', 'password': 'x'})
        assert browser.post('/api/auth/login', json={'employee_id': '2222222', 'password': 'x'}).status_code == 429
    with client.app.state.database.connect() as db:
        db.execute('UPDATE sessions SET expires_at = 0')
    assert client.get(url(client)).status_code == 401


def test_incomplete_generation(client):
    client.get(url(client))
    assert client.post(url(client, '/generate'), json={'revision': 0, 'state': initial_state()}).status_code == 400
    assert client.post(url(client, '/generate'), json={'revision': 0, 'state': complete()}).status_code == 400
    done = answered(client)
    state = done['state']
    state['answers']['q2'] = {'selected': [], 'custom': ''}
    assert client.post(url(client, '/generate'), json={'revision': done['revision'], 'state': state}).status_code == 400
    assert client.get(url(client)).json()['revision'] == done['revision']


@pytest.mark.parametrize('mutate', [
    lambda s: s['answers']['q1'].update(selected=['없는 선택지']),
    lambda s: s['answers']['q1'].update(selected=[{}]),
    lambda s: s['answers']['q1'].update(selected=['선택 1-A'] * 2),
    lambda s: s['answers']['q1'].update(selected=['선택 1-A', '선택 1-B']),
    lambda s: s['answers'].update(q1='선택 1-A'),
    lambda s: s['context'].update(problem='x' * 3001),
    lambda s: s['draft'].update(name='🚀' * 41),
    lambda s: s.update(stage=True),
    lambda s: s.update(questionIndex=-1),
    lambda s: s.update(questionIndex=True),
    lambda s: s.update(questionIndex=16),
    lambda s: s.update(manualEdited='yes'),
    lambda s: s['context'].pop('current'),
    lambda s: s.update(documentText='x' * 100001),
    lambda s: s['project'].update(name='  '),
])
def test_invalid_state_rejected_without_writes(client, mutate):
    client.get(url(client))
    done = answered(client)
    state = done['state']
    mutate(state)
    response = client.put(url(client), json={'revision': done['revision'], 'state': state})
    assert response.status_code == 400
    assert 'error' in response.json()
    assert client.get(url(client)).json()['revision'] == done['revision']


def test_http_validation(client):
    client.get(url(client))
    for revision in (True, '0', -1, 1.5):
        assert client.put(url(client), json={'revision': revision, 'state': initial_state()}).status_code == 400
    assert client.put(url(client), content='{', headers={'Content-Type': 'application/json'}).status_code == 400
    assert client.put(url(client), content='{}', headers={'Content-Type': 'text/plain'}).status_code == 415
    assert client.put(url(client), json={'revision': 0, 'state': initial_state()}, headers={'Origin': 'https://other.example'}).status_code == 403
    assert client.put(url(client), content='x' * 524289, headers={'Content-Type': 'application/json'}).status_code == 413
    assert len(client.get('/api/context').json()['steps']) == 5
    assert client.get('/api/missing').status_code == 404
    assert client.patch(url(client), json={}).status_code == 405
    assert client.get('/api/health').json()['framework'] == 'fastapi'
    assert client.get('/api/health').headers['Cache-Control'] == 'no-store'
    assert '/api/prompts/{prompt_id}' in client.get('/openapi.json').json()['paths']


def test_concurrent_writes_only_one_wins(client):
    client.get(url(client))
    token = client.cookies.get('wiacoding_auth')
    def save(index):
        with TestClient(client.app) as tab:
            tab.cookies.set('wiacoding_auth', token, path='/api')
            tab.prompt_id = client.prompt_id
            state = initial_state()
            state['draft']['name'] = str(index)
            return tab.put(url(tab), json={'revision': 0, 'state': state}).status_code
    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(save, range(2)))
    assert sorted(statuses) == [200, 409]
    assert client.get(url(client)).json()['revision'] == 1


def test_migration_preserves_session_revision_state_and_original(tmp_path):
    source, target = tmp_path / 'old.sqlite', tmp_path / 'app.db'
    old = Database(source)
    old.initialize()
    token = 'a' * 64
    with old.connect() as db:  # An anonymous workspace as saved before login existed.
        db.execute('INSERT INTO workspaces (token_hash, state, revision, updated_at, expires_at) VALUES (?, ?, 1, ?, ?)',
                   (hashlib.sha256(token.encode()).hexdigest(), json.dumps(initial_state()), 'x', int(time.time()) + 3600))
    assert migrate(source, target) == 1
    assert source.exists()
    with TestClient(create_app(target)) as client:
        client.cookies.set('wiacoding_session', token, path='/api')
        sign_in(client)  # Listing prompts moves this browser's former workspace into the account.
        state = client.get(url(client)).json()
        assert state['revision'] == 1
        assert state['state'] == initial_state()
        with client.app.state.database.connect() as db:
            assert db.execute('SELECT COUNT(*) FROM workspaces').fetchone()[0] == 0
    with TestClient(create_app(target)) as other:
        other.cookies.set('wiacoding_session', token, path='/api')
        sign_in(other, employee_id='7654321')
        assert other.get(url(other)).json()['revision'] == 0  # Already moved; not shared.
    with pytest.raises(FileExistsError):
        migrate(source, target)
    assert DEFAULT_DB_PATH.name == 'app.db'


def test_secure_cookie(tmp_path):
    with TestClient(create_app(tmp_path / 'app.db', secure_cookie=True), base_url='https://testserver') as client:
        with client.app.state.database.connect() as db:
            from backend.auth import create_user
            create_user(db, '1234567', '테스터', 'Passw0rd!', must_change=False)
        cookie = client.post('/api/auth/login', json={'employee_id': '1234567', 'password': 'Passw0rd!'}).headers['set-cookie']
        assert 'Secure' in cookie and 'HttpOnly' in cookie and 'SameSite=strict' in cookie


def test_task_definition_template_has_editable_fields_and_evidence(client):
    html = client.get('/api/templates/task-definition').json()['html']
    for field in ('name', 'background', 'users', 'scope'):
        assert f'data-field="{field}"' in html and f'data-count="{field}"' in html
    assert 'data-evidence="problem,current,impact"' in html and 'data-evidence="goal"' in html
    with TestClient(client.app) as anonymous:
        assert anonymous.get('/api/templates/task-definition').status_code == 401
