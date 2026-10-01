from fastapi.testclient import TestClient
from backend.tests.test_accounts import admin
from backend.tests.support import sign_in, fake_writer
from backend.tests.test_storage import completed
from backend.tests.test_survey import fake_model


def test_dashboards_deny_members(admin):
    with TestClient(admin.app) as member:
        sign_in(member,employee_id='2222222')
        for route in ('operations','prompts','tokens','prompts/missing','prompts/missing/editor-history','prompts/missing/editor-chat'):
            assert member.get('/api/admin/'+route).status_code==403
        assert member.put('/api/admin/prompts/missing/sharing',json={'enabled':True}).status_code==403
        assert member.delete('/api/admin/prompts/missing').status_code==403


def test_usage_aggregates_filters_and_korean_dates(admin):
    uid=admin.get('/api/auth/me').json()['user_id']
    database=admin.app.state.database
    for key,stamp,total,status in [('before','2026-09-30T14:59:59Z',100,'success'),('inside','2026-09-30T15:00:00Z',30,'success'),('unknown','2026-10-01T14:59:59Z',None,'failed'),('after','2026-10-01T15:00:00Z',200,'success')]:
        database.record_llm(dict(request_id=key,user_id=uid,prompt_id=None,step='prompt_edit',provider='azure_openai',model='test-model',input_tokens=None if total is None else total-10,output_tokens=None if total is None else 10,total_tokens=total,cached_input_tokens=None if total is None else 5,attempt=1,status=status,started_at=stamp,duration_ms=1000))
    query='?start=2026-10-01&end=2026-10-01'
    result=admin.get('/api/admin/tokens'+query)
    assert result.status_code==200,result.text
    data=result.json();s=data['summary']
    assert (s['calls'],s['total_tokens'],s['unknown_usage'],s['failed'],s['cached_tokens'])==(2,30,1,1,5)
    assert data['groups']['daily'][0]['day']=='2026-10-01'
    assert data['groups']['models'][0]['total_tokens']==30
    assert len(admin.get('/api/admin/tokens'+query+'&status=failed').json()['items'])==1
    assert admin.get('/api/admin/tokens'+query+'&model=missing').json()['summary']['calls']==0
    assert admin.get('/api/admin/tokens?offset=-1').status_code==400
    assert admin.get('/api/admin/tokens?start=bad').status_code==400
    assert admin.get('/api/admin/operations?start=2026-10-02&end=2026-10-01').status_code==400
    ops=admin.get('/api/admin/operations'+query)
    assert ops.status_code==200,ops.text
    assert ops.json()['usage']['calls']==2 and len(ops.json()['errors'])==1


def test_admin_prompt_management_respects_private_copy_rules(admin,monkeypatch):
    fake_model(monkeypatch);fake_writer(monkeypatch)
    with TestClient(admin.app) as member:
        sign_in(member,employee_id='2222222')
        generated=completed(member)
        source=member.prompt_id
        member.post('/api/prompts/'+source+'/confirm',json={'revision':generated['revision']})
        private=member.post('/api/prompts/'+source+'/personal').json()['promptId']
    route='/api/admin/prompts/'
    assert admin.get('/api/admin/prompts?kind=personal').json()['items'][0]['prompt_id']==private
    assert admin.get('/api/admin/prompts?kind=confirmed').json()['items'][0]['prompt_id']==source
    assert admin.get('/api/admin/prompts?q=2222222').json()['total']==2
    assert admin.get('/api/admin/prompts?kind=bad').status_code==400
    detail=admin.get(route+source).json()
    assert detail['document']==detail['state']['documentText'] and detail['definition'] and detail['survey']
    assert admin.get(route+private+'/editor-history').json()=={'turns':[],'nextCursor':None}
    assert admin.get(route+private+'/editor-chat').json()=={'turns':[],'nextCursor':None}
    assert member.get('/api/shared/'+private+'/editor-chat').status_code in (401,404)
    assert admin.get(route+private+'/editor-history?before=0').status_code==400
    assert admin.put(route+private+'/sharing',json={'enabled':True}).status_code==400
    assert admin.put(route+source+'/sharing',json={'enabled':True}).status_code==200
    assert admin.get('/api/admin/prompts?kind=shared').json()['total']==1
    assert admin.put(route+source+'/sharing',json={'enabled':False}).status_code==200
    assert admin.delete(route+source).status_code==200
    assert admin.get(route+source).status_code==404
    assert admin.get(route+private).status_code==404
    assert admin.get('/api/admin/prompts?q=2222222').json()['total']==0
