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

COOKIE = 'wiacoding_auth'
SESSION_SECONDS = 8 * 3600
INITIAL_PASSWORD = 'wia1234!'
SCHEMA = '''
CREATE TABLE IF NOT EXISTS teams (
    team_id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS roles (
    role_id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY, employee_id TEXT NOT NULL UNIQUE COLLATE NOCASE,
    password_hash TEXT NOT NULL, full_name TEXT NOT NULL,
    team_id TEXT NOT NULL REFERENCES teams(team_id),
    role_id TEXT NOT NULL REFERENCES roles(role_id), email TEXT NOT NULL DEFAULT '',
    must_change_password INTEGER NOT NULL DEFAULT 1,
    is_active INTEGER NOT NULL DEFAULT 1,
    is_admin INTEGER NOT NULL DEFAULT 0 CHECK(is_admin IN (0,1)),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    last_login_at TEXT, password_changed_at TEXT);
CREATE TABLE IF NOT EXISTS sessions (
    token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TEXT NOT NULL, expires_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS sessions_user ON sessions(user_id);
CREATE TABLE IF NOT EXISTS login_attempts (
    attempt_key TEXT PRIMARY KEY, count INTEGER NOT NULL, expires_at REAL NOT NULL);
'''
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
        db.executescript(SCHEMA)

    def user(self, db, user_id):
        return public_user(db.execute(USER_QUERY + ' WHERE u.user_id=?', (user_id,)).fetchone())

    def set_session(self, db, response, user_id, old_token=None):
        if old_token:
            db.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash(old_token),))
        token = secrets.token_urlsafe(32)
        db.execute('DELETE FROM sessions WHERE expires_at<=?', (time.time(),))
        db.execute('INSERT INTO sessions VALUES (?,?,?,?)', (token_hash(token), user_id, now(), time.time() + SESSION_SECONDS))
        response.set_cookie(COOKIE, token, httponly=True, secure=self.secure, samesite='strict', max_age=SESSION_SECONDS, path='/api')

    def current_user(self, request: Request):
        token = request.cookies.get(COOKIE)
        if token:
            with self.database.connect() as db:
                row = db.execute(USER_QUERY + ''' JOIN sessions s ON s.user_id=u.user_id
                    WHERE s.token_hash=? AND s.expires_at>? AND u.is_active=1''', (token_hash(token), time.time())).fetchone()
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
        employee = body.employee_id.strip().lower()
        ip = request.client.host if request.client else 'unknown'
        keys = [('employee:' + employee, 10), ('ip:' + ip, 40)]
        timestamp = time.time()
        with self.database.connect() as db:
            db.execute('DELETE FROM login_attempts WHERE expires_at<=?', (timestamp,))
            for key, limit in keys:
                attempt = db.execute('SELECT count FROM login_attempts WHERE attempt_key=?', (key,)).fetchone()
                if attempt and attempt[0] >= limit:
                    raise APIError(429, '로그인 시도가 많습니다. 15분 후 다시 시도해 주세요.')
            row = db.execute(USER_QUERY + ' WHERE u.employee_id=?', (employee,)).fetchone()
            valid = verify_password(body.password, row['password_hash'] if row else DUMMY_HASH)
            if not valid or not row or not row['is_active']:
                for key, _ in keys:
                    db.execute('''INSERT INTO login_attempts VALUES (?,1,?)
                        ON CONFLICT(attempt_key) DO UPDATE SET count=count+1''', (key, timestamp + 900))
                db.commit()  # Preserve failed attempts before raising the response.
                raise APIError(401, '사번 또는 비밀번호를 확인해 주세요.')
            db.execute('DELETE FROM login_attempts WHERE attempt_key=?', (keys[0][0],))
            db.execute('UPDATE users SET last_login_at=? WHERE user_id=?', (now(), row['user_id']))
            self.set_session(db, response, row['user_id'], request.cookies.get(COOKIE))
            return self.user(db, row['user_id'])

    def me(self, request: Request):
        return self.current_user(request)

    def logout(self, request: Request, response: Response):
        with self.database.connect() as db:
            db.execute('DELETE FROM sessions WHERE token_hash=?', (token_hash(request.cookies.get(COOKIE, '')),))
        response.delete_cookie(COOKIE, path='/api', httponly=True, secure=self.secure, samesite='strict')
        return {'ok': True}

    def change_password(self, body: PasswordBody, request: Request, response: Response):
        user = self.current_user(request)
        problem = password_problem(body.new_password)
        if problem:
            raise APIError(400, problem)
        with self.database.connect() as db:
            row = db.execute('SELECT password_hash FROM users WHERE user_id=?', (user['user_id'],)).fetchone()
            if not verify_password(body.current_password, row[0]):
                raise APIError(400, '현재 비밀번호가 일치하지 않습니다.')
            if verify_password(body.new_password, row[0]):
                raise APIError(400, '현재 비밀번호와 다른 비밀번호를 입력해 주세요.')
            stamp = now()
            db.execute('''UPDATE users SET password_hash=?,must_change_password=0,password_changed_at=?,updated_at=?
                          WHERE user_id=?''', (hash_password(body.new_password), stamp, stamp, user['user_id']))
            db.execute('DELETE FROM sessions WHERE user_id=?', (user['user_id'],))
            self.set_session(db, response, user['user_id'])
            return self.user(db, user['user_id'])


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
