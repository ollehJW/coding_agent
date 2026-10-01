from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.tests.support import fake_writer, sign_in, url
from backend.tests.test_survey import fake_model
from backend.tests.test_storage import completed


@pytest.fixture
def owner(tmp_path, monkeypatch):
    fake_model(monkeypatch); fake_writer(monkeypatch)
    with TestClient(create_app(tmp_path / 'imports.db')) as owner:
        sign_in(owner)
        generated=completed(owner)
        owner.post(url(owner,'/confirm'),json={'revision':generated['revision']})
        owner.put(url(owner,'/sharing'),json={'enabled':True})
        yield owner


def test_import_creates_private_confirmed_independent_copy_without_private_history(owner):
    source=owner.get(url(owner)).json()
    with TestClient(owner.app) as viewer:
        user=sign_in(viewer,employee_id='7654321')
        result=viewer.post(f'/api/shared/{owner.prompt_id}/import')
        assert result.status_code==200, result.text
        imported=result.json();assert imported['created'] and imported['promptId']!=owner.prompt_id
        target='/api/prompts/'+imported['promptId']
        copy=viewer.get(target).json()
        assert copy['confirmed'] and copy['state']['documentText']==source['state']['documentText']
        assert copy['state']['project']['name']==source['state']['project']['name']
        assert copy['state']['answers']==source['state']['answers']
        assert not copy['state']['context'] and not copy['backgroundAgent'] and not copy['state']['project']['messages']
        assert viewer.get(target+'/editor').json()['turns']==[]
        assert not any(p['promptId']==imported['promptId'] for p in viewer.get('/api/sharing').json()['prompts'])
        assert len(viewer.get('/api/shared').json()['prompts'])==1
        assert viewer.get(f'/api/shared/{owner.prompt_id}').json()['imported']
        assert owner.get(target).status_code==404
        saved=viewer.put(target,json={'revision':copy['revision'],'state':{**copy['state'],'documentText':'# 개인 수정','manualEdited':True}})
        assert saved.status_code==200,saved.text
        assert not saved.json()['confirmed']
        assert owner.get(url(owner)).json()==source
        # Revocation or deletion of the original does not delete an already imported private copy.
        owner.put(url(owner,'/sharing'),json={'enabled':False})
        assert viewer.post(f'/api/shared/{owner.prompt_id}/import').status_code==404
        owner.delete(url(owner))
        assert viewer.get(target).json()['state']['documentText']=='# 개인 수정'
        assert viewer.post(target+'/confirm',json={'revision':saved.json()['revision']}).json()['confirmed']


def test_import_is_idempotent_including_concurrent_requests(owner):
    with TestClient(owner.app) as viewer:
        user=sign_in(viewer,employee_id='7654321')
        db=owner.app.state.database
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _: db.import_shared(owner.prompt_id,user['user_id']),range(2)))
        assert results[0]['promptId']==results[1]['promptId']
        assert sum(r['created'] for r in results)==1
        repeated=viewer.post(f'/api/shared/{owner.prompt_id}/import').json()
        assert repeated=={'promptId':results[0]['promptId'],'created':False}
        viewer.delete('/api/prompts/'+repeated['promptId'])
        assert viewer.post(f'/api/shared/{owner.prompt_id}/import').json()['created']


def test_import_requires_shared_source_and_authentication(owner):
    route=f'/api/shared/{owner.prompt_id}/import'
    own=owner.post(route).json()
    assert own['created'] and own['promptId'] != owner.prompt_id
    with TestClient(owner.app) as anonymous:
        assert anonymous.post(route).status_code==401
    owner.put(url(owner,'/sharing'),json={'enabled':False})
    with TestClient(owner.app) as viewer:
        sign_in(viewer,employee_id='7654321')
        assert viewer.post(route).status_code==404
        assert viewer.post('/api/shared/missing/import').status_code==404


def test_personal_removal_preserves_shared_original_and_all_related_data(owner):
    original=owner.get(url(owner)).json()
    with owner.app.state.database.connect() as db:
        tables=['prompts','prompt_documents','task_definitions','survey_questions','survey_answers','prompt_edit_turns','llm_requests']
        counts={table:db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in tables}
    assert owner.delete(url(owner,'/library-entry')).status_code==200
    assert owner.delete(url(owner,'/library-entry')).status_code==200
    assert not any(row['promptId']==owner.prompt_id for row in owner.get('/api/prompts').json()['prompts'])
    assert owner.get(url(owner)).json()==original
    assert owner.get(f'/api/shared/{owner.prompt_id}').status_code==200
    assert not owner.get(f'/api/shared/{owner.prompt_id}').json()['imported']
    assert owner.get('/api/sharing').json()['prompts'][0]['enabled']
    with owner.app.state.database.connect() as db:
        assert {table:db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in tables}==counts
    restored=owner.post(f'/api/shared/{owner.prompt_id}/import').json()
    assert restored['created'] and restored['promptId'] != owner.prompt_id
    assert owner.get('/api/prompts').json()['prompts'][0]['promptId']==restored['promptId']


def test_removed_import_is_restored_without_overwriting_or_duplicating(owner):
    with TestClient(owner.app) as viewer:
        sign_in(viewer,employee_id='7654321')
        route=f'/api/shared/{owner.prompt_id}/import'
        imported=viewer.post(route).json()['promptId']
        target='/api/prompts/'+imported
        before=viewer.get(target).json()
        assert viewer.delete(target+'/library-entry').status_code==200
        assert not any(row['promptId']==imported for row in viewer.get('/api/prompts').json()['prompts'])
        assert viewer.get(target).json()==before
        assert viewer.get(f'/api/shared/{owner.prompt_id}').json()['imported'] is False
        restored=viewer.post(route).json()
        assert restored=={'promptId':imported,'created':False,'restored':True}
        assert viewer.get(target).json()==before
        assert viewer.get(f'/api/shared/{owner.prompt_id}').json()['imported'] is True


def test_library_removal_is_owner_only_and_does_not_hide_active_work(owner):
    with TestClient(owner.app) as other:
        sign_in(other,employee_id='7654321')
        assert other.delete(url(owner,'/library-entry')).status_code==404
        assert other.delete(url(other,'/library-entry')).status_code==400
    with TestClient(owner.app) as anonymous:
        assert anonymous.delete(url(owner,'/library-entry')).status_code==401
    assert owner.get('/api/prompts').json()['prompts'][0]['promptId']==owner.prompt_id


def test_owner_personal_edits_and_reconfirmation_never_change_shared_original(owner):
    before=owner.get(f'/api/shared/{owner.prompt_id}').json()
    original=owner.get(url(owner)).json()
    copy=owner.post(url(owner,'/personal')).json()
    assert copy['personal'] and copy['promptId'] != owner.prompt_id
    assert copy['state']==original['state']
    target='/api/prompts/'+copy['promptId']
    assert owner.post(url(owner,'/personal')).json()['promptId']==copy['promptId']
    assert owner.post(target+'/personal').json()['promptId']==copy['promptId']
    edited=owner.put(target,json={'revision':copy['revision'],'state':{**copy['state'],'documentText':'# 나만의 비공개 수정','manualEdited':True}})
    assert edited.status_code==200,edited.text
    listed=owner.get('/api/prompts').json()['prompts']
    assert len(listed)==1 and listed[0]['personal'] and listed[0]['promptId']==copy['promptId']
    assert owner.get(f'/api/shared/{owner.prompt_id}').json()==before
    assert owner.post(target+'/confirm',json={'revision':edited.json()['revision']}).status_code==200
    assert owner.get(f'/api/shared/{owner.prompt_id}').json()==before
    assert owner.get(url(owner)).json()==original
    assert owner.put(target+'/sharing',json={'enabled':True}).status_code==400
    assert [p['promptId'] for p in owner.get('/api/sharing').json()['prompts']]==[owner.prompt_id]
    assert owner.delete(target+'/library-entry').status_code==200
    assert owner.get('/api/prompts').json()['prompts']==[]
    assert owner.get(f'/api/shared/{owner.prompt_id}').json()['imported'] is False
    assert owner.post(f'/api/shared/{owner.prompt_id}/import').json()=={'promptId':copy['promptId'],'created':False,'restored':True}
    assert owner.get(target).json()['state']['documentText']=='# 나만의 비공개 수정'


def test_personal_copy_creation_is_owner_only_and_concurrent_idempotent(owner):
    with TestClient(owner.app) as viewer:
        sign_in(viewer,employee_id='7654321')
        assert viewer.post(url(owner,'/personal')).status_code==404
    database=owner.app.state.database
    user_id=owner.get('/api/auth/me').json()['user_id']
    with ThreadPoolExecutor(max_workers=2) as pool:
        copies=list(pool.map(lambda _:database.open_personal(owner.prompt_id,user_id),range(2)))
    assert copies[0]['promptId']==copies[1]['promptId']
    database.create_tables()
    assert database.open_personal(owner.prompt_id,user_id)['promptId']==copies[0]['promptId']


def test_whole_deletion_removes_owners_personal_copy_but_keeps_others(owner):
    own=owner.post(url(owner,'/personal')).json()['promptId']
    with TestClient(owner.app) as viewer:
        sign_in(viewer,employee_id='7654321')
        other=viewer.post(f'/api/shared/{owner.prompt_id}/import').json()['promptId']
        assert owner.delete(url(owner)).status_code==200
        assert owner.get('/api/prompts/'+own).status_code==404
        assert viewer.get('/api/prompts/'+other).status_code==200
