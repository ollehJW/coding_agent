"""WiaNews account management rules adapted to the WiaCoding database."""
import re
import psycopg
import unicodedata
import uuid
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, StrictBool, field_validator, model_validator
from .auth import USER_QUERY, INITIAL_PASSWORD, hash_password, now, public_user
from .state import APIError

class UserBody(BaseModel):
    employee_id: str = Field(pattern=r'^[A-Za-z0-9._-]{1,40}$')
    full_name: str = Field(min_length=1, max_length=80)
    team_id: str | None = None
    role_id: str | None = None
    team_name: str | None = Field(default=None, min_length=1, max_length=80)
    role_name: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator('team_name', 'role_name')
    @classmethod
    def clean_name(cls, value):
        if value is None:
            return value
        value = ' '.join(unicodedata.normalize('NFKC', value).split())
        if not value:
            raise ValueError('팀과 직급 이름을 입력해 주세요.')
        return value

    @model_validator(mode='after')
    def require_team_and_role(self):
        if not (self.team_id or self.team_name) or not (self.role_id or self.role_name):
            raise ValueError('소속 팀과 직급을 입력해 주세요.')
        if (self.team_id and self.team_name) or (self.role_id and self.role_name):
            raise ValueError('팀과 직급은 이름 또는 ID 중 하나로 지정해 주세요.')
        return self
    is_admin: StrictBool = False
    email: str = Field(default='', max_length=254)

    @field_validator('full_name', 'email')
    @classmethod
    def trimmed(cls, value, info):
        value = value.strip()
        if info.field_name == 'full_name' and not value:
            raise ValueError('이름을 입력해 주세요.')
        if info.field_name == 'email' and value and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('이메일 주소를 확인해 주세요.')
        return value


def account_router(store, auth):
    router = APIRouter(prefix='/api')
    database = store.connect

    admin_user = auth.admin_user

    @router.get('/admin/users')
    def users(response: Response, user=Depends(admin_user)):
        response.headers['Cache-Control'] = 'no-store'
        with database() as db:
            return [public_user(row) for row in db.execute(USER_QUERY+' ORDER BY u.created_at DESC')]


    @router.get('/admin/options')
    def options(user=Depends(admin_user)):
        with database() as db:
            return {'teams': [dict(row) for row in db.execute('SELECT * FROM teams ORDER BY name')],
                    'roles': [dict(row) for row in db.execute('SELECT * FROM roles ORDER BY name')]}


    def name_key(value):
        return ''.join(unicodedata.normalize('NFKC', value).split()).casefold()


    def resolve_team_or_role(db, kind, item_id, name):
        # kind is an internal constant, never request input.
        table, column = ('teams', 'team_id') if kind == 'team' else ('roles', 'role_id')
        if item_id:
            if not db.execute(f'SELECT 1 FROM {table} WHERE {column}=?', (item_id,)).fetchone():
                raise APIError(400, '팀 또는 직급을 확인해 주세요.')
            return item_id
        for row in db.execute(f'SELECT {column},name FROM {table}'):
            if name_key(row['name']) == name_key(name):
                return row[column]
        item_id = str(uuid.uuid4())
        if kind == 'team':
            db.execute('INSERT INTO teams VALUES (?,?,?)', (item_id, name, now()))
        else:
            db.execute('INSERT INTO roles VALUES (?,?,?)', (item_id, name, now()))
        return item_id


    class CreateUserBody(UserBody):
        employee_id: str = Field(pattern=r'^[0-9]{1,7}$')


    @router.post('/admin/users', status_code=201)
    def create_user(body: CreateUserBody, user=Depends(admin_user)):
        try:
            with database() as db:
                # Serialize lookup + insertion so concurrent requests reuse the same names.
                # Any account creation failure also rolls back new teams and job titles.
                db.execute("SELECT pg_advisory_xact_lock(741902630)")
                team_id = resolve_team_or_role(db, 'team', body.team_id, body.team_name)
                role_id = resolve_team_or_role(db, 'role', body.role_id, body.role_name)
                uid, stamp = str(uuid.uuid4()), now()
                db.execute('''INSERT INTO users (user_id,employee_id,password_hash,full_name,team_id,role_id,is_admin,email,created_at,updated_at)
                              VALUES (?,?,?,?,?,?,?,?,?,?)''',
                           (uid, body.employee_id.lower(), hash_password(INITIAL_PASSWORD), body.full_name,
                            team_id, role_id, bool(body.is_admin), body.email, stamp, stamp))
                return public_user(db.execute(USER_QUERY+' WHERE u.user_id=?', (uid,)).fetchone())
        except psycopg.IntegrityError:
            raise APIError(409, '이미 등록된 사번입니다.') from None


    class TeamBody(BaseModel):
        name: str = Field(min_length=1, max_length=80)

        @field_validator('name')
        @classmethod
        def name_not_blank(cls, value):
            if not value.strip():
                raise ValueError('팀 이름을 입력해 주세요.')
            return value.strip()


    @router.post('/admin/teams', status_code=201)
    def create_team(body: TeamBody, user=Depends(admin_user)):
        try:
            with database() as db:
                tid = str(uuid.uuid4())
                db.execute('INSERT INTO teams VALUES (?,?,?)', (tid, body.name, now()))
                return {'team_id': tid, 'name': body.name}
        except psycopg.IntegrityError:
            raise APIError(409, '이미 등록된 팀입니다.') from None


    @router.put('/admin/users/{user_id}')
    def edit_user(user_id: str, body: UserBody, user=Depends(admin_user)):
        if user_id == user['user_id'] and not body.is_admin:
            raise APIError(400, '로그인 중인 본인의 관리자 권한은 해제할 수 없습니다.')
        try:
            with database() as db:
                db.execute("SELECT pg_advisory_xact_lock(741902630)")
                existing = db.execute('SELECT * FROM users WHERE user_id=?', (user_id,)).fetchone()
                if not existing:
                    raise APIError(404, '계정을 찾을 수 없습니다.')
                team_id = resolve_team_or_role(db, 'team', body.team_id, body.team_name)
                role_id = resolve_team_or_role(db, 'role', body.role_id, body.role_name)
                db.execute('''UPDATE users SET employee_id=?,full_name=?,team_id=?,role_id=?,is_admin=?,email=?,updated_at=?
                              WHERE user_id=?''', (body.employee_id.lower(), body.full_name, team_id, role_id,
                              bool(body.is_admin), body.email, now(), user_id))
                if existing['is_admin'] != bool(body.is_admin):
                    db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
                return public_user(db.execute(USER_QUERY+' WHERE u.user_id=?', (user_id,)).fetchone())
        except psycopg.IntegrityError:
            raise APIError(409, '이미 등록된 사번입니다.') from None


    @router.delete('/admin/users/{user_id}')
    def delete_user(user_id: str, user=Depends(admin_user)):
        if user_id == user['user_id']:
            raise APIError(400, '로그인 중인 본인 계정은 삭제할 수 없습니다.')
        try:
            with database() as db:
                if db.execute('DELETE FROM users WHERE user_id=?', (user_id,)).rowcount != 1:
                    raise APIError(404, '계정을 찾을 수 없습니다.')
        except psycopg.IntegrityError:
            raise APIError(409, '연결된 데이터로 인해 계정을 삭제할 수 없습니다.') from None
        return {'ok': True}


    @router.post('/admin/users/{user_id}/reset-password')
    def reset_password(user_id: str, user=Depends(admin_user)):
        with database() as db:
            db.execute("SELECT pg_advisory_xact_lock(741902630)")
            if not db.execute('SELECT 1 FROM users WHERE user_id=?', (user_id,)).fetchone():
                raise APIError(404, '계정을 찾을 수 없습니다.')
            db.execute('''UPDATE users SET password_hash=?,must_change_password=TRUE,
                          password_changed_at=NULL,updated_at=? WHERE user_id=?''',
                       (hash_password(INITIAL_PASSWORD), now(), user_id))
            db.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
            return public_user(db.execute(USER_QUERY+' WHERE u.user_id=?', (user_id,)).fetchone())

    return router
