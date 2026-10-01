import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.tests.support import fake_writer, sign_in, url
from backend.tests.test_survey import fake_model
from backend.tests.test_storage import completed


@pytest.fixture
def app(tmp_path, monkeypatch):
    fake_model(monkeypatch)
    fake_writer(monkeypatch)
    with TestClient(create_app(tmp_path / 'app.db')) as owner:
        sign_in(owner, name='홍길동')
        yield owner


def other(owner, employee_id='7654321'):
    client = TestClient(owner.app)
    sign_in(client, employee_id=employee_id, name='김동료')
    return client


def publish(app, generated):
    confirmed = app.post(url(app, '/confirm'), json={'revision': generated['revision']})
    assert confirmed.status_code == 200
    assert app.put(url(app, '/sharing'), json={'enabled': True}).status_code == 200
    return confirmed.json()


def test_only_completed_prompts_are_shared_and_author_shows_as_team(app):
    assert app.get('/api/shared').json() == {'prompts': []}  # Still in progress.
    generated = completed(app)
    publish(app, generated)
    with other(app) as viewer:
        cards = viewer.get('/api/shared').json()['prompts']
        assert len(cards) == 1
        card = cards[0]
        assert card['title'] == '장비 예약 🚀' and card['team'] == '미지정' and not card['mine'] and card['goal'] == '장비 예약 🚀 도구'
        assert '홍길동' not in str(card) and 'user_id' not in card
        detail = viewer.get(f"/api/shared/{card['promptId']}").json()
        assert detail['document'].startswith('# 장비 예약 🚀') and detail['definition']['name'] == '장비 예약 🚀'
        assert len(detail['survey']['questions']) == 4 and set(detail['answers']) == {'q1', 'q2', 'q3', 'q4'}
        assert not {'messages', 'backgroundAgent', 'evidence'} & set(detail) and '홍길동' not in str(detail)
    assert app.get('/api/shared').json()['prompts'][0]['mine']


def test_search_and_recommendation_sort(app):
    generated = completed(app)
    publish(app, generated)
    first = app.prompt_id
    with other(app) as viewer:
        assert len(viewer.get('/api/shared', params={'q': '장비 예약'}).json()['prompts']) == 1
        assert viewer.get('/api/shared', params={'q': '없는과제'}).json()['prompts'] == []
        assert viewer.put(f'/api/shared/{first}/recommendation').json() == {'recommendations': 1, 'recommended': True}
        assert viewer.put(f'/api/shared/{first}/recommendation').json()['recommendations'] == 1  # Once per user.
        assert viewer.get('/api/shared').json()['prompts'][0]['recommended']
    assert app.get('/api/shared').json()['prompts'][0] | {} == app.get('/api/shared', params={'sort': 'recommended'}).json()['prompts'][0]
    assert not app.get('/api/shared').json()['prompts'][0]['recommended']  # Recommended by the colleague, not by the owner.
    assert app.put(f'/api/shared/{first}/recommendation').json() == {'recommendations': 2, 'recommended': True}
    assert app.put(f'/api/shared/{first}/recommendation').json()['recommendations'] == 2
    assert app.get(f'/api/shared/{first}').json()['recommended']
    assert app.delete(f'/api/shared/{first}/recommendation').json() == {'recommendations': 1, 'recommended': False}
    with other(app) as viewer:
        assert viewer.delete(f'/api/shared/{first}/recommendation').json() == {'recommendations': 0, 'recommended': False}


def test_reopened_or_deleted_prompts_leave_the_shared_list(app):
    generated = completed(app)
    generated = publish(app, generated)
    with other(app) as viewer:
        viewer.put(f'/api/shared/{app.prompt_id}/recommendation')
    reopened = {**generated['state'], 'stage': 2}
    app.put(url(app), json={'revision': generated['revision'], 'state': reopened})
    assert app.get('/api/shared').json()['prompts'] == []
    with other(app) as viewer:
        assert viewer.get(f'/api/shared/{app.prompt_id}').status_code == 404
        assert viewer.put(f'/api/shared/{app.prompt_id}/recommendation').status_code == 404
    app.delete(url(app))
    with app.app.state.database.connect() as db:
        assert db.execute('SELECT COUNT(*) FROM prompt_recommendations').fetchone()[0] == 0


def test_shared_api_requires_login(app):
    with TestClient(app.app) as anonymous:
        assert anonymous.get('/api/shared').status_code == 401


def test_confirmation_and_private_defaults(app):
    assert app.post(url(app, '/confirm'), json={'revision': 0}).status_code == 400
    generated = completed(app)
    assert generated['confirmed'] is False
    assert app.get('/api/shared').json()['prompts'] == []
    assert app.put(url(app, '/sharing'), json={'enabled': True}).status_code == 400
    assert app.post(url(app, '/confirm'), json={'revision': generated['revision'] - 1}).status_code == 409
    confirmed = app.post(url(app, '/confirm'), json={'revision': generated['revision']}).json()
    assert confirmed['confirmed'] is True
    assert app.get('/api/shared').json()['prompts'] == []
    row = app.get('/api/sharing').json()['prompts'][0]
    assert row['canShare'] and not row['enabled']
    assert app.get('/api/prompts').json()['prompts'][0]['confirmed']


def test_sharing_is_owner_only_and_private_data_is_inaccessible(app):
    generated = publish(app, completed(app))
    with other(app) as viewer:
        assert viewer.get('/api/sharing').json()['prompts'][0]['promptId'] != app.prompt_id
        assert viewer.put(url(app, '/sharing'), json={'enabled': False}).status_code == 404
        assert viewer.post(url(app, '/confirm'), json={'revision': generated['revision']}).status_code == 404
        assert app.put(url(app, '/sharing'), json={'enabled': False}).status_code == 200
        assert viewer.get('/api/shared').json()['prompts'] == []
        assert viewer.get(f'/api/shared/{app.prompt_id}').status_code == 404
        assert viewer.put(f'/api/shared/{app.prompt_id}/recommendation').status_code == 404
        assert viewer.delete(f'/api/shared/{app.prompt_id}/recommendation').status_code == 404
    edited = app.put(url(app), json={'revision': generated['revision'], 'state': {**generated['state'], 'documentText': '# private edited', 'manualEdited': True}}).json()
    assert not edited['confirmed']
    assert app.get('/api/shared').json()['prompts'] == []
    confirmed = app.post(url(app, '/confirm'), json={'revision': edited['revision']}).json()
    assert confirmed['confirmed']
    assert app.get('/api/shared').json()['prompts'] == []
    assert not app.get('/api/sharing').json()['prompts'][0]['enabled']


def test_shared_edits_require_reconfirmation(app):
    generated = publish(app, completed(app))
    edited = app.put(url(app), json={'revision': generated['revision'], 'state': {**generated['state'], 'documentText': '# revised', 'manualEdited': True}}).json()
    assert not edited['confirmed']
    assert app.get('/api/shared').json()['prompts'] == []
    row = app.get('/api/sharing').json()['prompts'][0]
    assert row['enabled'] and not row['canShare']
    confirmed = app.post(url(app, '/confirm'), json={'revision': edited['revision']}).json()
    assert confirmed['confirmed']
    assert app.get(f'/api/shared/{app.prompt_id}').json()['document'] == '# revised'
    assert app.put(url(app), json={'revision': confirmed['revision'], 'state': confirmed['state']}).json()['confirmed']


def test_sharing_endpoints_require_authentication_and_boolean(app):
    with TestClient(app.app) as anonymous:
        assert anonymous.get('/api/sharing').status_code == 401
        assert anonymous.put(url(app, '/sharing'), json={'enabled': True}).status_code == 401
        assert anonymous.post(url(app, '/confirm'), json={'revision': 0}).status_code == 401
    assert app.put(url(app, '/sharing'), json={'enabled': 'false'}).status_code == 400


def test_migration_keeps_existing_sharing_and_defaults_to_private(app):
    publish(app, completed(app))
    db = app.app.state.database
    with db.connect() as conn:
        conn.execute('ALTER TABLE prompts DROP COLUMN sharing_enabled')
    db.create_tables()
    assert app.get('/api/sharing').json()['prompts'][0]['enabled']
    assert len(app.get('/api/shared').json()['prompts']) == 1
    new = app.post('/api/prompts', json={}).json()
    rows = app.get('/api/sharing').json()['prompts']
    assert not next(row for row in rows if row['promptId'] == new['promptId'])['enabled']
