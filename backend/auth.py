"""Accounts and revocable login sessions, ported from WiaNews (same schema, hashing and rules)."""
import hashlib
import hmac
import re
import secrets
import time
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field

from .state import APIError

COOKIE = 'ax_platform_session'
SESSION_SECONDS = 8 * 3600
INITIAL_PASSWORD = 'wia1234!'
USER_QUERY = '''SELECT u.*, t.name AS team_name, r.name AS role_name
                FROM users u JOIN teams t ON t.team_id=u.team_id JOIN roles r ON r.role_id=u.role_id'''
PUBLIC = ('user_id', 'employee_id', 'full_name', 'team_id', 'team_name', 'role_id', 'role_name', 'is_admin', 'email',
          'must_change_password', 'is_active', 'created_at', 'updated_at', 'last_login_at', 'password_changed_at')


def now():
    return datetime.now(timezone.utc).isoformat()


def hash_password(password):
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'


def verify_password(password, encoded):
    try:
        algorithm, iterations, salt, expected = encoded.split('$')
        if algorithm != 'pbkdf2_sha256':
            return False
        actual = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), int(iterations)).hex()
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


DUMMY_HASH = hash_password(secrets.token_urlsafe(32))


def token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def public_user(row):
    return {key: row[key] for key in PUBLIC}


def password_problem(value):
    if len(value) < 8 or not (re.search('[A-Za-z]', value) and re.search('[0-9]', value) and re.search(r'[^\w\s]', value)):
        return '영문, 숫자, 특수문자를 포함해 8자 이상 입력해 주세요.'
    if value in (INITIAL_PASSWORD, 'admin123'):
        return '초기 비밀번호는 새 비밀번호로 사용할 수 없습니다.'
    return None


class LoginBody(BaseModel):
    employee_id: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)


class PasswordBody(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=1, max_length=128)


class Auth:
    """Login endpoints and user dependencies bound to one application database."""
    def __init__(self, database, secure):
        self.database, self.secure = database, secure
        self.router = APIRouter(prefix='/api/auth')
        self.router.post('/login')(self.login)
        self.router.get('/me')(self.me)
        self.router.post('/logout')(self.logout)
        self.router.post('/password')(self.change_password)

    def initialize(self, db):
        db.execute("SELECT 1 FROM platform.users LIMIT 1")

    def user(self, db, user_id):
        return public_user(db.execute(USER_QUERY + ' WHERE u.user_id=?', (user_id,)).fetchone())

    def set_session(self, *args, **kwargs):
        raise RuntimeError("Only the platform may issue sessions")

    def current_user(self, request: Request):
        token = request.cookies.get(COOKIE)
        if token:
            with self.database.connect() as db:
                row = db.execute(USER_QUERY + ''' JOIN sessions s ON s.user_id=u.user_id
                    WHERE s.token_hash=? AND s.expires_at>? AND u.is_active=TRUE''', (token_hash(token), time.time())).fetchone()
                if row:
                    return public_user(row)
        raise APIError(401, '로그인이 필요합니다.')

    def ready_user(self, request: Request):
        user = self.current_user(request)
        if user['must_change_password']:
            raise APIError(403, '초기 비밀번호를 먼저 변경해 주세요.')
        return user

    def admin_user(self, request: Request):
        user = self.ready_user(request)
        if not user['is_admin']:
            raise APIError(403, '관리자만 사용할 수 있습니다.')
        return user

    def login(self, body: LoginBody, request: Request, response: Response):
        raise APIError(409, 'AX for Works 통합 로그인 페이지를 이용해 주세요.')

    def me(self, request: Request):
        return self.current_user(request)

    def logout(self, request: Request, response: Response):
        with self.database.connect() as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash(request.cookies.get(COOKIE, '')),))
        response.delete_cookie(COOKIE, path='/', httponly=True, secure=self.secure, samesite='strict')
        return {'ok': True}

    def change_password(self, body: PasswordBody, request: Request, response: Response):
        raise APIError(409, 'AX for Works에서 비밀번호를 변경해 주세요.')


def create_user(db, employee_id, full_name, password=INITIAL_PASSWORD, team='미지정', role='미지정', is_admin=False, must_change=True):
    """Create an account (used by tests and manual setup); teams and roles are reused by name."""
    stamp = now()
    ids = []
    for table, column, name in (('teams', 'team_id', team), ('roles', 'role_id', role)):
        row = db.execute(f'SELECT {column} FROM {table} WHERE name=?', (name,)).fetchone()
        if row is None:
            row = (str(uuid.uuid4()),)
            db.execute(f'INSERT INTO {table} VALUES (?,?,?)', (row[0], name, stamp))
        ids.append(row[0])
    user_id = str(uuid.uuid4())
    db.execute('''INSERT INTO users (user_id,employee_id,password_hash,full_name,team_id,role_id,is_admin,must_change_password,created_at,updated_at)
                  VALUES (?,?,?,?,?,?,?,?,?,?)''', (user_id, employee_id.lower(), hash_password(password), full_name, *ids,
                                                     int(is_admin), int(must_change), stamp, stamp))
    return user_id
