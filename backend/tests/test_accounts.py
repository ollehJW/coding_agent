from fastapi.testclient import TestClient
import pytest
from backend.main import create_app
from backend.auth import INITIAL_PASSWORD
from backend.tests.support import sign_in, PASSWORD


@pytest.fixture
def admin(tmp_path):
    with TestClient(create_app(tmp_path / 'accounts.db')) as client:
        user = sign_in(client)
        with client.app.state.database.connect() as db:
            db.execute('UPDATE users SET is_admin=1 WHERE user_id=?', (user['user_id'],))
        yield client


def body(**values):
    return dict(employee_id='7654321',full_name='신규 사용자',email='new@example.com',team_name='DX추진랩',role_name='매니저',is_admin=False) | values


def test_account_crud_validation_and_self_protection(admin):
    original=admin.get('/api/auth/me').json()
    created=admin.post('/api/admin/users',json=body())
    assert created.status_code==201, created.text
    user=created.json();target='/api/admin/users/'+user['user_id']
    assert user['must_change_password'] and not user['is_admin'] and 'password_hash' not in user
    assert admin.get('/api/admin/users').headers['cache-control']=='no-store'
    assert admin.post('/api/admin/users',json=body(team_name='롤백 팀')).status_code==409
    assert not any(t['name']=='롤백 팀' for t in admin.get('/api/admin/options').json()['teams'])
    assert admin.post('/api/admin/users',json=body(employee_id='bad')).status_code==400
    assert admin.post('/api/admin/users',json=body(employee_id='7654322',is_admin='false')).status_code==400
    assert admin.post('/api/admin/users',json=body(employee_id='7654322',email='bad')).status_code==400
    edited=admin.put(target,json=body(full_name='변경 사용자',team_name='DX 추진랩',role_name='팀장'))
    assert edited.status_code==200 and edited.json()['team_id']==user['team_id']
    own='/api/admin/users/'+original['user_id']
    assert admin.delete(own).status_code==400
    assert admin.put(own,json=body(employee_id=original['employee_id'])).status_code==400
    assert admin.delete(target).status_code==200
    assert admin.delete(target).status_code==404


def test_account_endpoints_require_admin_and_changed_password(admin):
    paths=[('get','/api/admin/users',None),('get','/api/admin/options',None),('post','/api/admin/users',body()),('put','/api/admin/users/missing',body()),('delete','/api/admin/users/missing',None),('post','/api/admin/users/missing/reset-password',None)]
    with TestClient(admin.app) as viewer:
        for method,path,payload in paths:
            assert viewer.request(method,path,**({'json':payload} if payload else {})).status_code==401
        sign_in(viewer,employee_id='1111111')
        for method,path,payload in paths:
            assert viewer.request(method,path,**({'json':payload} if payload else {})).status_code==403
        user=viewer.get('/api/auth/me').json()
        with viewer.app.state.database.connect() as db:
            db.execute('UPDATE users SET is_admin=1,must_change_password=1 WHERE user_id=?',(user['user_id'],))
        assert viewer.get('/api/admin/users').status_code==403


def test_password_reset_and_role_change_revoke_sessions(admin):
    user=admin.post('/api/admin/users',json=body()).json()
    target='/api/admin/users/'+user['user_id']
    with TestClient(admin.app) as viewer:
        assert viewer.post('/api/auth/login',json={'employee_id':user['employee_id'],'password':INITIAL_PASSWORD}).status_code==200
        assert viewer.get('/api/prompts').status_code==403
        assert viewer.post('/api/auth/password',json={'current_password':INITIAL_PASSWORD,'new_password':PASSWORD}).status_code==200
        assert admin.put(target,json=body(is_admin=True)).status_code==200
        assert viewer.get('/api/auth/me').status_code==401
        assert viewer.post('/api/auth/login',json={'employee_id':user['employee_id'],'password':PASSWORD}).status_code==200
        assert viewer.get('/api/admin/users').status_code==200
        reset=admin.post(target+'/reset-password')
        assert reset.status_code==200 and reset.json()['must_change_password']
        assert viewer.get('/api/auth/me').status_code==401
        assert viewer.post('/api/auth/login',json={'employee_id':user['employee_id'],'password':PASSWORD}).status_code==401
        assert viewer.post('/api/auth/login',json={'employee_id':user['employee_id'],'password':INITIAL_PASSWORD}).status_code==200
        assert viewer.get('/api/admin/users').status_code==403
