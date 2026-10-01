"""Administrator dashboards backed by stored prompts and LLM usage."""
import json
from .prompt_editor import EditStore
from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, StrictBool
from .state import APIError


class SharingBody(BaseModel):
    enabled: StrictBool


def period(start, end):
    try:
        finish = date.fromisoformat(end) if end else datetime.now(timezone(timedelta(hours=9))).date()
        begin = date.fromisoformat(start) if start else finish - timedelta(days=29)
        if not 0 <= (finish - begin).days <= 365:
            raise ValueError()
    except ValueError:
        raise APIError(400, '조회 기간은 시작일 이후 최대 366일로 선택해주세요.') from None
    return begin.isoformat(), finish.isoformat()


PROMPTS = '''FROM prompts p JOIN users u ON u.user_id=p.user_id JOIN teams t ON t.team_id=u.team_id
 LEFT JOIN personal_prompts pp ON pp.prompt_id=p.prompt_id'''
FIELDS = '''p.prompt_id,p.user_id,p.title,p.stage,p.created_at,p.updated_at,p.completed_at,p.shared_at,
 p.library_hidden_at,u.full_name,u.employee_id,t.name AS team_name,pp.prompt_id IS NOT NULL AS personal'''
USAGE = '''COUNT(*) AS calls, COALESCE(SUM(input_tokens),0) AS input_tokens,
 COALESCE(SUM(output_tokens),0) AS output_tokens, COALESCE(SUM(total_tokens),0) AS total_tokens,
 COALESCE(SUM(cached_input_tokens),0) AS cached_tokens,
 COALESCE(SUM(total_tokens IS NULL),0) AS unknown_usage,
 COALESCE(SUM(status='failed'),0) AS failed, COALESCE(SUM(status='cancelled'),0) AS cancelled,
 AVG(duration_ms) AS average_duration_ms'''


def admin_router(database, auth):
    router = APIRouter(prefix='/api/admin', dependencies=[Depends(auth.admin_user)])

    @router.get('/operations')
    def operations(start: str = '', end: str = ''):
        begin, finish = period(start, end)
        with database.connect() as db:
            db.execute('BEGIN')
            snapshot = dict(db.execute('''SELECT COUNT(*) AS prompts,
              COALESCE(SUM(pp.prompt_id IS NOT NULL),0) AS personal,
              COALESCE(SUM(pp.prompt_id IS NULL AND p.completed_at IS NULL),0) AS in_progress,
              COALESCE(SUM(pp.prompt_id IS NULL AND p.completed_at IS NOT NULL),0) AS confirmed,
              COALESCE(SUM(p.shared_at IS NOT NULL),0) AS shared ''' + PROMPTS).fetchone())
            snapshot['users'] = db.execute('SELECT COUNT(*) FROM users WHERE is_active=1 AND is_admin=0').fetchone()[0]
            where = " WHERE date(started_at,'+9 hours') BETWEEN ? AND ?"
            usage = dict(db.execute('SELECT '+USAGE+' FROM llm_requests'+where, (begin, finish)).fetchone())
            activity = [dict(r) for r in db.execute('''SELECT u.full_name,u.employee_id,t.name AS team_name,
                (SELECT COUNT(*) FROM prompts p WHERE p.user_id=u.user_id AND date(p.created_at,'+9 hours') BETWEEN ? AND ?) AS prompts,
                (SELECT COUNT(*) FROM llm_requests l WHERE l.user_id=u.user_id AND date(l.started_at,'+9 hours') BETWEEN ? AND ?) AS calls,
                u.last_login_at FROM users u JOIN teams t ON t.team_id=u.team_id
                WHERE u.is_admin=0 ORDER BY calls DESC,prompts DESC,u.full_name LIMIT 100''',(begin,finish,begin,finish))]
            errors = [dict(r) for r in db.execute('''SELECT l.request_id,l.started_at,l.step,l.model,l.status,l.error_type,u.full_name
                FROM llm_requests l LEFT JOIN users u ON u.user_id=l.user_id
                WHERE date(l.started_at,'+9 hours') BETWEEN ? AND ? AND l.status!='success'
                ORDER BY l.started_at DESC LIMIT 50''',(begin,finish))]
        return dict(snapshot=snapshot,usage=usage,activity=activity,errors=errors)

    @router.get('/prompts')
    def prompts(q: str = '', kind: str = 'all', offset: int = Query(0, ge=0)):
        conditions = {'all':'1=1','active':'p.completed_at IS NULL AND pp.prompt_id IS NULL',
                      'confirmed':'p.completed_at IS NOT NULL AND pp.prompt_id IS NULL',
                      'shared':'p.shared_at IS NOT NULL','personal':'pp.prompt_id IS NOT NULL'}
        if kind not in conditions:
            raise APIError(400, '목록 구분을 확인해주세요.')
        where = ' WHERE '+conditions[kind]+" AND instr(lower(p.title||' '||u.full_name||' '||u.employee_id||' '||t.name),lower(?))>0"
        with database.connect() as db:
            db.execute('BEGIN')
            total = db.execute('SELECT COUNT(*) '+PROMPTS+where,(q.strip(),)).fetchone()[0]
            rows = [dict(r) for r in db.execute('SELECT '+FIELDS+' '+PROMPTS+where+' ORDER BY p.updated_at DESC,p.prompt_id LIMIT 20 OFFSET ?',(q.strip(),offset))]
        return dict(total=total,items=rows)

    def owner(prompt_id):
        with database.connect() as db:
            row = db.execute('SELECT user_id FROM prompts WHERE prompt_id=?',(prompt_id,)).fetchone()
            if row is None:
                raise APIError(404, '프롬프트를 찾을 수 없습니다.')
            return row['user_id']

    @router.get('/prompts/{prompt_id}')
    def detail(prompt_id: str):
        value=database.load(prompt_id,owner(prompt_id))
        if value is None:
            raise APIError(404, '프롬프트를 찾을 수 없습니다.')
        with database.connect() as db:
            row = db.execute('SELECT '+FIELDS+',d.spec '+PROMPTS+' LEFT JOIN prompt_documents d ON d.prompt_id=p.prompt_id WHERE p.prompt_id=?', (prompt_id,)).fetchone()
            if row is None:
                raise APIError(404, '프롬프트를 찾을 수 없습니다.')
            spec = json.loads(row['spec']) if row['spec'] else {}
        state = value['state']
        return {key:value[key] for key in ('promptId','state','confirmed','updatedAt')} | {
            'title':row['title'], 'team':row['team_name'], 'goal':spec.get('goal',''),
            'document':state['documentText'], 'definition':state['project'] or state['draft'],
            'survey':state['survey'], 'answers':state['answers']}

    @router.get('/prompts/{prompt_id}/editor-history')
    def editor_history(prompt_id: str, before: int | None = None):
        return EditStore(database).shared_history(prompt_id,before,require_shared=False)

    @router.get('/prompts/{prompt_id}/editor-chat')
    def editor_chat(prompt_id: str, before: int | None = None):
        return EditStore(database).shared_history(prompt_id,before,conversation=True,require_shared=False)

    @router.put('/prompts/{prompt_id}/sharing')
    def sharing(prompt_id: str, body: SharingBody):
        return database.set_sharing(prompt_id,owner(prompt_id),body.enabled)

    @router.delete('/prompts/{prompt_id}')
    def delete(prompt_id: str):
        if not database.delete_prompt(prompt_id,owner(prompt_id)):
            raise APIError(404, '프롬프트를 찾을 수 없습니다.')
        return {'ok':True}

    @router.get('/tokens')
    def tokens(start: str = '', end: str = '', user_id: str = '', model: str = '', status: str = '', offset: int = Query(0, ge=0)):
        begin,finish=period(start,end)
        if status not in ('','success','failed','cancelled'):
            raise APIError(400,'호출 상태를 확인해주세요.')
        where=" WHERE date(l.started_at,'+9 hours') BETWEEN ? AND ?"
        params=[begin,finish]
        for column,value in [('user_id',user_id),('model',model),('status',status)]:
            if value:
                where+=f' AND l.{column}=?';params.append(value)
        join=' FROM llm_requests l LEFT JOIN users u ON u.user_id=l.user_id'
        with database.connect() as db:
            db.execute('BEGIN')
            summary=dict(db.execute('SELECT '+USAGE+join+where,params).fetchone())
            groups={}
            for key,fields in [('models','l.provider,l.model'),('users',"COALESCE(u.full_name,'삭제된 계정') AS full_name,l.user_id"),('daily',"date(l.started_at,'+9 hours') AS day")]:
                grouping={'models':'l.provider,l.model','users':'l.user_id','daily':"date(l.started_at,'+9 hours')"}[key]
                groups[key]=[dict(r) for r in db.execute('SELECT '+fields+','+USAGE+join+where+' GROUP BY '+grouping+' ORDER BY '+('day' if key=='daily' else 'total_tokens DESC'),params)]
            rows=[dict(r) for r in db.execute('SELECT l.*,u.full_name'+join+where+' ORDER BY l.started_at DESC,l.request_id LIMIT 50 OFFSET ?',(*params,offset))]
            options={'users':[dict(r) for r in db.execute('SELECT user_id,full_name,employee_id FROM users ORDER BY full_name')],
                     'models':[r[0] for r in db.execute('SELECT DISTINCT model FROM llm_requests ORDER BY model')]}
        return dict(summary=summary,groups=groups,items=rows,options=options)
    return router
