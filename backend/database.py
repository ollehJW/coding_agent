"""SQLite persistence: each prompt is stored in normalized tables and assembled into the workspace state the API validates.

Only the latest version of everything is kept. Deleting a prompt removes all of its rows; LLM usage rows stay
(with prompt_id cleared) so token totals by day and user remain correct.
"""
import json
import sqlite3
import time
import uuid
from contextlib import contextmanager, nullcontext
from datetime import datetime, timezone
from pathlib import Path

from .content import CONTEXT_STEPS
from .state import APIError, initial_state

KEEP_AGENT = object()
LIFETIME = 30 * 24 * 60 * 60  # Anonymous pre-login workspaces only.
AGENT_META = ('title', 'ready', 'nextCategories', 'remaining', 'deferred', 'lastTurn')

SCHEMA = '''
CREATE TABLE IF NOT EXISTS prompts (
    prompt_id TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    title TEXT NOT NULL DEFAULT '', stage INTEGER NOT NULL DEFAULT 1, task_type TEXT, question_index INTEGER NOT NULL DEFAULT 0,
    agent_meta TEXT, survey_signature TEXT NOT NULL DEFAULT '', survey_done INTEGER NOT NULL DEFAULT 0,
    survey_done_basis TEXT NOT NULL DEFAULT '', revision INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL, completed_at TEXT);
CREATE INDEX IF NOT EXISTS prompts_user ON prompts(user_id, updated_at);
CREATE TABLE IF NOT EXISTS chat_messages (
    prompt_id TEXT NOT NULL REFERENCES prompts(prompt_id) ON DELETE CASCADE, message_id TEXT NOT NULL,
    seq INTEGER NOT NULL, role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL,
    llm_request_id TEXT, created_at TEXT NOT NULL, PRIMARY KEY (prompt_id, message_id));
CREATE TABLE IF NOT EXISTS background_items (
    prompt_id TEXT NOT NULL REFERENCES prompts(prompt_id) ON DELETE CASCADE, category TEXT NOT NULL,
    status TEXT NOT NULL, summary TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '', evidence TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL, PRIMARY KEY (prompt_id, category));
CREATE TABLE IF NOT EXISTS task_definitions (
    prompt_id TEXT NOT NULL REFERENCES prompts(prompt_id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK(kind IN ('draft','confirmed')),
    name TEXT NOT NULL, background TEXT NOT NULL, users TEXT NOT NULL, scope TEXT NOT NULL,
    signature TEXT, updated_at TEXT NOT NULL, PRIMARY KEY (prompt_id, kind));
CREATE TABLE IF NOT EXISTS survey_topics (
    prompt_id TEXT NOT NULL REFERENCES prompts(prompt_id) ON DELETE CASCADE, topic_id TEXT NOT NULL,
    seq INTEGER NOT NULL, label TEXT NOT NULL, description TEXT NOT NULL, origin INTEGER NOT NULL DEFAULT 0,
    empty_text TEXT, status TEXT, reason TEXT NOT NULL DEFAULT '', PRIMARY KEY (prompt_id, topic_id));
CREATE TABLE IF NOT EXISTS survey_questions (
    prompt_id TEXT NOT NULL REFERENCES prompts(prompt_id) ON DELETE CASCADE, question_id TEXT NOT NULL,
    position INTEGER NOT NULL, topic_id TEXT NOT NULL, label TEXT NOT NULL, title TEXT NOT NULL, help TEXT NOT NULL, decision TEXT,
    multi INTEGER NOT NULL, cards TEXT NOT NULL, basis TEXT NOT NULL, topic_status TEXT,
    llm_request_id TEXT, created_at TEXT NOT NULL, PRIMARY KEY (prompt_id, question_id));
CREATE TABLE IF NOT EXISTS survey_answers (
    prompt_id TEXT NOT NULL, question_id TEXT NOT NULL, selected TEXT NOT NULL, custom TEXT NOT NULL,
    updated_at TEXT NOT NULL, PRIMARY KEY (prompt_id, question_id),
    FOREIGN KEY (prompt_id, question_id) REFERENCES survey_questions(prompt_id, question_id) ON DELETE CASCADE);
CREATE TABLE IF NOT EXISTS prompt_documents (
    prompt_id TEXT PRIMARY KEY REFERENCES prompts(prompt_id) ON DELETE CASCADE, content TEXT NOT NULL,
    source TEXT NOT NULL CHECK(source IN ('generated','edited')), updated_at TEXT NOT NULL,
    llm_request_id TEXT, spec TEXT);
CREATE TABLE IF NOT EXISTS prompt_edit_turns (
    turn_id TEXT NOT NULL, prompt_id TEXT NOT NULL REFERENCES prompts(prompt_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE, base_revision INTEGER NOT NULL,
    user_message TEXT NOT NULL, assistant_message TEXT NOT NULL DEFAULT '', before_text TEXT NOT NULL, after_text TEXT,
    status TEXT NOT NULL CHECK(status IN ('generating','answered','proposed','accepted','rejected','failed','stale')),
    decision_message TEXT NOT NULL DEFAULT '', llm_request_id TEXT REFERENCES llm_requests(request_id) ON DELETE SET NULL,
    created_at TEXT NOT NULL, resolved_at TEXT, PRIMARY KEY (prompt_id,turn_id));
CREATE INDEX IF NOT EXISTS prompt_edit_pending ON prompt_edit_turns(prompt_id,status);
CREATE TABLE IF NOT EXISTS prompt_recommendations (
    prompt_id TEXT NOT NULL REFERENCES prompts(prompt_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    created_at TEXT NOT NULL, PRIMARY KEY (prompt_id, user_id));
CREATE TABLE IF NOT EXISTS llm_requests (
    request_id TEXT PRIMARY KEY, user_id TEXT REFERENCES users(user_id) ON DELETE SET NULL,
    prompt_id TEXT REFERENCES prompts(prompt_id) ON DELETE SET NULL,
    step TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL, reasoning_effort TEXT,
    input_tokens INTEGER, output_tokens INTEGER, total_tokens INTEGER, cached_input_tokens INTEGER, reasoning_tokens INTEGER,
    attempt INTEGER NOT NULL, status TEXT NOT NULL CHECK(status IN ('success','failed','cancelled')), error_type TEXT,
    started_at TEXT NOT NULL, completed_at TEXT, duration_ms INTEGER);
CREATE INDEX IF NOT EXISTS llm_requests_started ON llm_requests(started_at);
CREATE INDEX IF NOT EXISTS llm_requests_user ON llm_requests(user_id, started_at);
'''


def timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00', 'Z')


def dumps(value):
    return json.dumps(value, ensure_ascii=False)


def prompt_title(state, agent):
    """List title: the task name once confirmed, otherwise what the user first said."""
    first = next((m['content'] for m in (agent or {}).get('messages', []) if m['role'] == 'user'), '')
    title = state['project']['name'] if state['project'] else first or state['draft']['name']
    title = ' '.join(title.split())
    return title[:79] + '…' if len(title) > 80 else title


class Database:
    def __init__(self, path):
        self.path = Path(path).resolve()

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute('PRAGMA foreign_keys=ON')
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        """Create tables. Accounts must exist first (Auth.initialize) for the foreign keys."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            # Former one-per-browser store; kept only until its rows are moved into prompts.
            db.execute('''CREATE TABLE IF NOT EXISTS workspaces (
                token_hash TEXT PRIMARY KEY, state TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL, expires_at INTEGER NOT NULL)''')
            columns = {row[1] for row in db.execute('PRAGMA table_info(workspaces)')}
            if 'background_agent' not in columns:
                db.execute('ALTER TABLE workspaces ADD COLUMN background_agent TEXT')
            if 'user_id' not in columns:
                db.execute('ALTER TABLE workspaces ADD COLUMN user_id TEXT')

    def create_tables(self):
        with self.connect() as db:
            db.executescript(SCHEMA)
            # Columns added after the first release.
            if 'decision' not in {row[1] for row in db.execute('PRAGMA table_info(survey_questions)')}:
                db.execute('ALTER TABLE survey_questions ADD COLUMN decision TEXT')
            if 'shared_at' not in {row[1] for row in db.execute('PRAGMA table_info(prompts)')}:
                # Completed prompts are shared with everyone; earlier ones were made without that notice, so no backfill.
                db.execute('ALTER TABLE prompts ADD COLUMN shared_at TEXT')
            if 'sharing_enabled' not in {row[1] for row in db.execute('PRAGMA table_info(prompts)')}:
                db.execute('ALTER TABLE prompts ADD COLUMN sharing_enabled INTEGER NOT NULL DEFAULT 0')
                db.execute('UPDATE prompts SET sharing_enabled = 1 WHERE shared_at IS NOT NULL')
            if 'library_hidden_at' not in {row[1] for row in db.execute('PRAGMA table_info(prompts)')}:
                db.execute('ALTER TABLE prompts ADD COLUMN library_hidden_at TEXT')
            if 'source_prompt_id' not in {row[1] for row in db.execute('PRAGMA table_info(prompts)')}:
                db.execute('ALTER TABLE prompts ADD COLUMN source_prompt_id TEXT REFERENCES prompts(prompt_id) ON DELETE SET NULL')
            db.execute('DROP INDEX IF EXISTS prompts_import_source')
            db.execute("""CREATE TABLE IF NOT EXISTS personal_prompts (
                prompt_id TEXT PRIMARY KEY REFERENCES prompts(prompt_id) ON DELETE CASCADE,
                user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
                source_prompt_id TEXT REFERENCES prompts(prompt_id) ON DELETE SET NULL,
                UNIQUE(user_id, source_prompt_id))""")
            db.execute('INSERT OR IGNORE INTO personal_prompts SELECT prompt_id,user_id,source_prompt_id FROM prompts '
                       'WHERE source_prompt_id IS NOT NULL AND sharing_enabled=0')
            db.execute('CREATE INDEX IF NOT EXISTS prompts_shared ON prompts(shared_at) WHERE shared_at IS NOT NULL')
            document_columns = {row[1] for row in db.execute('PRAGMA table_info(prompt_documents)')}
            for column in ('llm_request_id', 'spec'):
                if column not in document_columns:
                    db.execute(f'ALTER TABLE prompt_documents ADD COLUMN {column} TEXT')
            owned = db.execute('SELECT token_hash FROM workspaces WHERE user_id IS NOT NULL').fetchall()
        for row in owned:
            self._move_workspace(row['token_hash'])

    # Former workspaces ---------------------------------------------------------------------------

    def _move_workspace(self, token_hash, user_id=None):
        """Turn a former workspace into a prompt of its owner (or `user_id` when claiming) and delete it."""
        from .survey import normalize
        with self.connect() as db:
            row = db.execute('SELECT * FROM workspaces WHERE token_hash = ?', (token_hash,)).fetchone()
            owner = user_id or (row and row['user_id'])
            if row is None or owner is None:
                return None
            state = normalize(json.loads(row['state']))
            agent = json.loads(row['background_agent']) if row['background_agent'] else None
            prompt_id = str(uuid.uuid4())
            db.execute('''INSERT INTO prompts (prompt_id, user_id, revision, created_at, updated_at)
                          VALUES (?, ?, ?, ?, ?)''', (prompt_id, owner, row['revision'], row['updated_at'], row['updated_at']))
            self._write(db, prompt_id, state, agent, row['updated_at'])
            db.execute('DELETE FROM workspaces WHERE token_hash = ?', (token_hash,))
        return prompt_id

    def claim(self, token_hash, user_id):
        """Move a pre-login anonymous workspace from this browser into the user's prompts."""
        with self.connect() as db:
            db.execute('DELETE FROM workspaces WHERE expires_at <= ? AND user_id IS NULL', (int(time.time()),))
            if not db.execute('SELECT 1 FROM workspaces WHERE token_hash = ? AND user_id IS NULL', (token_hash,)).fetchone():
                return None
        return self._move_workspace(token_hash, user_id)

    # Prompts ------------------------------------------------------------------------------------

    def list_prompts(self, user_id):
        with self.connect() as db:
            items = []
            rows = db.execute('SELECT p.prompt_id,p.title,p.stage,p.updated_at,p.completed_at,t.name AS team,d.spec, ' 
                              'EXISTS(SELECT 1 FROM personal_prompts pp WHERE pp.prompt_id=p.prompt_id) AS personal '
                              'FROM prompts p JOIN users u ON u.user_id=p.user_id JOIN teams t ON t.team_id=u.team_id '
                              'LEFT JOIN prompt_documents d ON d.prompt_id=p.prompt_id WHERE p.user_id=? '
                              'AND NOT EXISTS(SELECT 1 FROM personal_prompts pp WHERE pp.source_prompt_id=p.prompt_id AND pp.user_id=p.user_id) '
                              'AND (p.library_hidden_at IS NULL OR (p.completed_at IS NULL AND NOT EXISTS(SELECT 1 FROM personal_prompts pp WHERE pp.prompt_id=p.prompt_id))) ORDER BY p.updated_at DESC', (user_id,))
            for row in rows:
                item = {'promptId': row['prompt_id'], 'title': row['title'], 'stage': row['stage'],
                        'updatedAt': row['updated_at'], 'confirmed': bool(row['completed_at'])}
                if row['personal']:
                    item['personal'] = True
                if row['completed_at'] or row['personal']:
                    spec = json.loads(row['spec']) if row['spec'] else {}
                    item.update(team=row['team'], goal=spec.get('goal', ''),
                                tags=[entry['choice'] for entry in spec.get('tech_stack', [])][:6])
                items.append(item)
            return items

    def create_prompt(self, user_id):
        prompt_id, now = str(uuid.uuid4()), timestamp()
        with self.connect() as db:
            db.execute('INSERT INTO prompts (prompt_id, user_id, created_at, updated_at) VALUES (?, ?, ?, ?)',
                       (prompt_id, user_id, now, now))
        return self.load(prompt_id, user_id)

    def remove_from_library(self, prompt_id, user_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT completed_at FROM prompts WHERE prompt_id=? AND user_id=?', (prompt_id,user_id)).fetchone()
            if row is None:
                raise APIError(404, '프롬프트를 찾을 수 없습니다.')
            if not row['completed_at'] and not db.execute('SELECT 1 FROM personal_prompts WHERE prompt_id=?', (prompt_id,)).fetchone():
                raise APIError(400, '확정된 프롬프트만 개인 목록에서 제거할 수 있어요.')
            db.execute('UPDATE prompts SET library_hidden_at=COALESCE(library_hidden_at,?) WHERE prompt_id=?', (timestamp(),prompt_id))
        return {'ok': True}

    def delete_prompt(self, prompt_id, user_id):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if not db.execute('SELECT 1 FROM prompts WHERE prompt_id=? AND user_id=?', (prompt_id,user_id)).fetchone():
                return False
            db.execute('DELETE FROM prompts WHERE prompt_id IN (SELECT prompt_id FROM personal_prompts WHERE source_prompt_id=? AND user_id=?)',
                       (prompt_id,user_id))
            return db.execute('DELETE FROM prompts WHERE prompt_id = ? AND user_id = ?', (prompt_id, user_id)).rowcount == 1

    def load(self, prompt_id, user_id, connection=None):
        """The prompt as {promptId, state, backgroundAgent, revision, updatedAt}, or None if not the user's."""
        with nullcontext(connection) if connection is not None else self.connect() as db:
            prompt = db.execute('SELECT * FROM prompts WHERE prompt_id = ? AND user_id = ?', (prompt_id, user_id)).fetchone()
            if prompt is None:
                return None
            personal = bool(db.execute('SELECT 1 FROM personal_prompts WHERE prompt_id=?', (prompt_id,)).fetchone())
            rows = lambda sql: db.execute(sql, (prompt_id,)).fetchall()
            items = {row['category']: row for row in rows('SELECT * FROM background_items WHERE prompt_id = ?')}
            definitions = {row['kind']: row for row in rows('SELECT * FROM task_definitions WHERE prompt_id = ?')}
            topics = rows('SELECT * FROM survey_topics WHERE prompt_id = ? ORDER BY seq')
            questions = rows('SELECT * FROM survey_questions WHERE prompt_id = ? ORDER BY position')
            answers = rows('SELECT * FROM survey_answers WHERE prompt_id = ?')
            document = db.execute('SELECT * FROM prompt_documents WHERE prompt_id = ?', (prompt_id,)).fetchone()
            messages = rows('SELECT * FROM chat_messages WHERE prompt_id = ? ORDER BY seq')

        agent = None
        if prompt['agent_meta']:
            agent = {'messages': [{'id': m['message_id'], 'role': m['role'], 'content': m['content'],
                                   **({'llmRequestId': m['llm_request_id']} if m['llm_request_id'] else {})} for m in messages],
                     'categories': {key: {'status': item['status'], 'summary': item['summary'], 'reason': item['reason'],
                                          'evidence': json.loads(item['evidence'])} for key, item in items.items()},
                     **json.loads(prompt['agent_meta'])}
        state = initial_state()
        if agent:
            from .background_agent import legacy_context
            state['context'] = legacy_context(agent)
        else:  # Workspaces from before the chat agent kept plain answers per background step.
            state['context'] = {step['id']: items[step['id']]['summary'] for step in CONTEXT_STEPS if step['id'] in items}
        definition = lambda row: {key: row[key] for key in ('name', 'background', 'users', 'scope')}
        if 'draft' in definitions:
            state['draft'] = definition(definitions['draft'])
        if 'confirmed' in definitions:
            state['project'] = {**definition(definitions['confirmed']), 'type': prompt['task_type'],
                                'signature': definitions['confirmed']['signature'],
                                'messages': [m['content'] for m in agent['messages'] if m['role'] == 'user'] if agent
                                else [state['context'][step['id']] for step in CONTEXT_STEPS if step['id'] in state['context']]}
        state['answers'] = {a['question_id']: {'selected': json.loads(a['selected']), 'custom': a['custom']} for a in answers}
        state['survey'] = {
            'signature': prompt['survey_signature'],
            'topics': [{'id': t['topic_id'], 'label': t['label'], 'description': t['description'],
                        **({'empty': t['empty_text']} if t['empty_text'] is not None else {}), 'origin': t['origin']} for t in topics],
            'questions': [{'id': q['question_id'], 'topic': q['topic_id'], 'label': q['label'], 'title': q['title'],
                           'help': q['help'], **({'decision': q['decision']} if q['decision'] else {}), 'multi': bool(q['multi']), 'cards': json.loads(q['cards']), 'basis': q['basis'],
                           **({'status': json.loads(q['topic_status'])} if q['topic_status'] else {}),
                           **({'llmRequestId': q['llm_request_id']} if q['llm_request_id'] else {})} for q in questions],
            'done': bool(prompt['survey_done']), 'doneBasis': prompt['survey_done_basis'],
            'topicStatus': {t['topic_id']: {'status': t['status'], 'reason': t['reason']} for t in topics if t['status']}}
        state.update(questionIndex=prompt['question_index'], stage=prompt['stage'],
                     documentText=document['content'] if document else '',
                     manualEdited=bool(document) and document['source'] == 'edited')
        return {'promptId': prompt_id, 'state': state, 'backgroundAgent': agent,
                'revision': prompt['revision'], 'updatedAt': prompt['updated_at'], 'confirmed': bool(prompt['completed_at']), **({'personal': True} if personal else {})}

    def save(self, current, revision, state, agent=KEEP_AGENT, document=None):
        """Replace the prompt's stored content with a validated state, if nobody saved in between.

        `document` ({llmRequestId, spec}) is given when the initial prompt was just written by the LLM."""
        agent = current['backgroundAgent'] if agent is KEEP_AGENT else agent
        updated_at = timestamp()
        with self.connect() as db:
            changed = db.execute('UPDATE prompts SET revision = revision + 1, updated_at = ? WHERE prompt_id = ? AND revision = ?',
                                 (updated_at, current['promptId'], revision))
            if changed.rowcount != 1:
                raise APIError(409, '다른 탭에서 작업이 변경되었습니다. 현재 내용을 복사해 보관한 뒤 새로고침해주세요.')
            if any(current['state'][key] != state[key] for key in ('project', 'survey', 'answers', 'documentText')):
                db.execute('UPDATE prompts SET completed_at=NULL, shared_at=NULL WHERE prompt_id=?', (current['promptId'],))
            db.execute("UPDATE prompt_edit_turns SET status='stale',decision_message=?,resolved_at=? WHERE prompt_id=? AND status IN ('proposed','generating')",
                       ('프롬프트가 변경되어 수정안을 다시 요청해주세요.', updated_at, current['promptId']))
            self._write(db, current['promptId'], state, agent, updated_at, document)
            confirmed = bool(db.execute('SELECT completed_at FROM prompts WHERE prompt_id=?', (current['promptId'],)).fetchone()[0])
        return {'promptId': current['promptId'], 'state': state, 'revision': revision + 1, 'updatedAt': updated_at,
                'backgroundAgent': agent, 'confirmed': confirmed}

    def _write(self, db, prompt_id, state, agent, now, document=None):
        project, survey = state['project'], state['survey']
        previous = db.execute('SELECT content FROM prompt_documents WHERE prompt_id=?', (prompt_id,)).fetchone()
        if state['stage'] != 3 or document is not None or not previous or previous['content'] != state['documentText']:
            db.execute('UPDATE prompts SET completed_at=NULL, shared_at=NULL WHERE prompt_id=?', (prompt_id,))
            db.execute("UPDATE prompt_edit_turns SET status='stale',decision_message=?,resolved_at=? WHERE prompt_id=? AND status IN ('proposed','generating')",
                       ('프롬프트가 변경되어 수정안을 다시 요청해주세요.', now, prompt_id))

        db.execute('''UPDATE prompts SET title = ?, stage = ?, task_type = ?, question_index = ?, agent_meta = ?,
                      survey_signature = ?, survey_done = ?, survey_done_basis = ? WHERE prompt_id = ?''',
                   (prompt_title(state, agent), state['stage'], project['type'] if project else None,
                    state['questionIndex'], dumps({key: agent.get(key) for key in AGENT_META}) if agent else None,
                    survey['signature'], int(survey['done']), survey['doneBasis'], prompt_id))

        # Rows are upserted by key and removed when gone, so creation times of kept rows survive.
        def sync(table, key, rows, columns, keep=()):
            keys = [row[0] for row in rows]
            db.execute(f'DELETE FROM {table} WHERE prompt_id = ? AND {key} NOT IN ({",".join("?" * len(keys))})', (prompt_id, *keys))
            updates = ', '.join(f'{column} = excluded.{column}' for column in columns[1:] if column not in keep)
            db.executemany(f'INSERT INTO {table} (prompt_id, {", ".join(columns)}) VALUES (?, {", ".join("?" * len(columns))}) '
                           f'ON CONFLICT (prompt_id, {key}) DO UPDATE SET {updates}', [(prompt_id, *row) for row in rows])

        messages = agent['messages'] if agent else []
        sync('chat_messages', 'message_id', [(m['id'], seq, m['role'], m['content'], m.get('llmRequestId'), now)
                                             for seq, m in enumerate(messages)],
             ['message_id', 'seq', 'role', 'content', 'llm_request_id', 'created_at'], keep=('created_at',))
        items = agent['categories'] if agent else {key: {'status': 'complete', 'summary': value, 'reason': '', 'evidence': []}
                                                   for key, value in state['context'].items()}
        sync('background_items', 'category', [(key, item['status'], item['summary'], item['reason'], dumps(item['evidence']), now)
                                               for key, item in items.items()],
             ['category', 'status', 'summary', 'reason', 'evidence', 'updated_at'])
        fields = ('name', 'background', 'users', 'scope')
        definitions = [('draft', *(state['draft'][f] for f in fields), None, now)]
        if project:
            definitions.append(('confirmed', *(project[f] for f in fields), project['signature'], now))
        sync('task_definitions', 'kind', definitions, ['kind', *fields, 'signature', 'updated_at'])
        status = survey['topicStatus']
        sync('survey_topics', 'topic_id', [(t['id'], seq, t['label'], t['description'], t['origin'], t.get('empty'),
                                            status.get(t['id'], {}).get('status'), status.get(t['id'], {}).get('reason', ''))
                                           for seq, t in enumerate(survey['topics'])],
             ['topic_id', 'seq', 'label', 'description', 'origin', 'empty_text', 'status', 'reason'])
        sync('survey_questions', 'question_id',
             [(q['id'], position, q['topic'], q['label'], q['title'], q['help'], q.get('decision'), int(q['multi']), dumps(q['cards']), q['basis'],
               dumps(q['status']) if 'status' in q else None, q.get('llmRequestId'), now)
              for position, q in enumerate(survey['questions'])],
             ['question_id', 'position', 'topic_id', 'label', 'title', 'help', 'decision', 'multi', 'cards', 'basis', 'topic_status',
              'llm_request_id', 'created_at'], keep=('created_at',))
        asked = {q['id'] for q in survey['questions']}
        sync('survey_answers', 'question_id', [(key, dumps(a['selected']), a['custom'], now) for key, a in state['answers'].items()
                                               if key in asked],
             ['question_id', 'selected', 'custom', 'updated_at'])
        if not state['documentText']:
            db.execute('DELETE FROM prompt_documents WHERE prompt_id = ?', (prompt_id,))
        elif document:
            db.execute('''INSERT OR REPLACE INTO prompt_documents (prompt_id, content, source, updated_at, llm_request_id, spec)
                          VALUES (?, ?, 'generated', ?, ?, ?)''', (prompt_id, state['documentText'], now, document['llmRequestId'], dumps(document['spec'])))
        else:  # Ordinary saves and manual edits keep the record of how the document was generated.
            db.execute('''INSERT INTO prompt_documents (prompt_id, content, source, updated_at) VALUES (?, ?, ?, ?)
                          ON CONFLICT (prompt_id) DO UPDATE SET content = excluded.content, source = excluded.source,
                          updated_at = excluded.updated_at WHERE content != excluded.content OR source != excluded.source''',
                       (prompt_id, state['documentText'], 'edited' if state['manualEdited'] else 'generated', now))
        # Saving content never opts a private prompt into sharing. Reopening ends sharing.
        db.execute('UPDATE prompts SET shared_at = CASE WHEN ? AND sharing_enabled THEN shared_at END, '
                   'sharing_enabled = CASE WHEN ? THEN sharing_enabled ELSE 0 END WHERE prompt_id = ?',
                   (state['stage'] == 3 and bool(state['documentText']),
                    state['stage'] == 3 and bool(state['documentText']), prompt_id))

    def confirm(self, prompt_id, user_id, revision):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT p.*, d.content FROM prompts p LEFT JOIN prompt_documents d '
                             'ON d.prompt_id=p.prompt_id WHERE p.prompt_id=? AND p.user_id=?', (prompt_id, user_id)).fetchone()
            if row is None:
                raise APIError(404, '프롬프트를 찾을 수 없습니다.')
            if row['revision'] != revision:
                raise APIError(409, '다른 탭에서 내용이 변경되었습니다. 새로고침 후 다시 확정해주세요.')
            if row['stage'] != 3 or not row['content']:
                raise APIError(400, '개발 프롬프트를 생성한 뒤 확정해주세요.')
            if db.execute("SELECT 1 FROM prompt_edit_turns WHERE prompt_id=? AND status IN ('proposed','generating')", (prompt_id,)).fetchone():
                raise APIError(400, 'Agent의 수정안을 수정 또는 반려한 뒤 확정해주세요.')
            now = timestamp()
            db.execute('UPDATE prompts SET completed_at=COALESCE(completed_at, ?), updated_at=?, revision=revision+1, library_hidden_at=NULL, '
                       'shared_at=CASE WHEN sharing_enabled THEN COALESCE(shared_at, ?) END WHERE prompt_id=?',
                       (now, now, now, prompt_id))
        return self.load(prompt_id, user_id)

    def sharing_list(self, user_id):
        with self.connect() as db:
            return [{'promptId': r['prompt_id'], 'title': r['title'], 'stage': r['stage'],
                     'updatedAt': r['updated_at'], 'enabled': bool(r['sharing_enabled']),
                     'canShare': bool(r['completed_at']) and r['stage'] == 3 and bool(r['content'])}
                    for r in db.execute('SELECT p.*, d.content FROM prompts p LEFT JOIN prompt_documents d '
                                        'ON d.prompt_id=p.prompt_id WHERE p.user_id=? AND NOT EXISTS(SELECT 1 FROM personal_prompts pp WHERE pp.prompt_id=p.prompt_id) ORDER BY p.updated_at DESC', (user_id,))]

    def set_sharing(self, prompt_id, user_id, enabled):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT p.stage, p.completed_at, d.content FROM prompts p LEFT JOIN prompt_documents d '
                             'ON d.prompt_id=p.prompt_id WHERE p.prompt_id=? AND p.user_id=?', (prompt_id, user_id)).fetchone()
            if row is None:
                raise APIError(404, '프롬프트를 찾을 수 없습니다.')
            if enabled and db.execute('SELECT 1 FROM personal_prompts WHERE prompt_id=?', (prompt_id,)).fetchone():
                raise APIError(400, '나만의 프롬프트 수정 내용은 개인 보관용으로만 저장됩니다.')
            if enabled and (not row['completed_at'] or row['stage'] != 3 or not row['content']):
                raise APIError(400, '확정된 프롬프트만 공유할 수 있어요.')
            db.execute('UPDATE prompts SET sharing_enabled=?, shared_at=CASE WHEN ? THEN COALESCE(shared_at, ?) END '
                       'WHERE prompt_id=? AND user_id=?', (int(enabled), enabled, timestamp(), prompt_id, user_id))
        return {'promptId': prompt_id, 'enabled': enabled}

    # Shared prompts -----------------------------------------------------------------------------

    SHARED = '''SELECT p.prompt_id, p.user_id, p.title, p.shared_at, p.library_hidden_at, EXISTS(SELECT 1 FROM personal_prompts pp WHERE pp.source_prompt_id=p.prompt_id AND pp.user_id=p.user_id) AS has_personal, t.name AS team, d.spec,
        (SELECT COUNT(*) FROM survey_questions q WHERE q.prompt_id = p.prompt_id) AS questions,
        (SELECT COUNT(*) FROM prompt_recommendations r WHERE r.prompt_id = p.prompt_id) AS recommendations,
        EXISTS (SELECT 1 FROM prompt_recommendations r WHERE r.prompt_id = p.prompt_id AND r.user_id = ?) AS recommended,
        EXISTS (SELECT 1 FROM personal_prompts pp JOIN prompts imported ON imported.prompt_id=pp.prompt_id WHERE pp.source_prompt_id=p.prompt_id AND pp.user_id=? AND imported.library_hidden_at IS NULL) AS imported
        FROM prompts p JOIN users u ON u.user_id = p.user_id JOIN teams t ON t.team_id = u.team_id
        JOIN prompt_documents d ON d.prompt_id = p.prompt_id WHERE p.shared_at IS NOT NULL'''

    @staticmethod
    def shared_card(row, viewer_id):
        """What everyone may see: the author is shown only by team."""
        spec = json.loads(row['spec']) if row['spec'] else {}
        return {'promptId': row['prompt_id'], 'title': row['title'], 'team': row['team'],
                'sharedAt': row['shared_at'], 'goal': spec.get('goal', ''),
                'tags': [item['choice'] for item in spec.get('tech_stack', [])][:6],
                'questions': row['questions'], 'recommendations': row['recommendations'],
                'recommended': bool(row['recommended']), 'mine': row['user_id'] == viewer_id, 'imported': bool(row['imported']) or (row['user_id'] == viewer_id and row['library_hidden_at'] is None and not row['has_personal'])}

    def shared_list(self, viewer_id):
        with self.connect() as db:
            return [self.shared_card(row, viewer_id) for row in db.execute(self.SHARED + ' ORDER BY p.shared_at DESC', (viewer_id, viewer_id))]

    def shared_detail(self, prompt_id, viewer_id):
        """A shared prompt for reading: the document, task definition and survey, but no chat or quoted evidence."""
        with self.connect() as db:
            db.execute('BEGIN')
            row = db.execute(self.SHARED + ' AND p.prompt_id = ?', (viewer_id, viewer_id, prompt_id)).fetchone()
            if row is None:
                return None
            state = self.load(prompt_id, row['user_id'], connection=db)['state']
        return {**self.shared_card(row, viewer_id), 'document': state['documentText'], 'definition': state['project'] and {
                    key: state['project'][key] for key in ('name', 'background', 'users', 'scope')},
                'survey': {key: state['survey'][key] for key in ('topics', 'questions')}, 'answers': state['answers']}

    def import_shared(self, source_id, user_id):
        """Create one private, independent copy of the public document. Never copy private conversations."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            source = db.execute('SELECT p.user_id,p.library_hidden_at,d.spec FROM prompts p JOIN prompt_documents d ON d.prompt_id=p.prompt_id '
                                'WHERE p.prompt_id=? AND p.shared_at IS NOT NULL AND p.completed_at IS NOT NULL', (source_id,)).fetchone()
            if source is None:
                raise APIError(404, '공유된 프롬프트를 찾을 수 없습니다.')
            existing = db.execute('SELECT p.prompt_id,p.library_hidden_at FROM personal_prompts pp JOIN prompts p ON p.prompt_id=pp.prompt_id WHERE pp.user_id=? AND pp.source_prompt_id=?', (user_id,source_id)).fetchone()
            if existing:
                db.execute('UPDATE prompts SET library_hidden_at=NULL WHERE prompt_id=?', (existing['prompt_id'],))
                return {'promptId': existing['prompt_id'], 'created': False, **({'restored': True} if existing['library_hidden_at'] else {})}
            original = self.load(source_id,source['user_id'],connection=db)['state']
            state = initial_state()
            # The public definition and survey are the only context copied into this workspace.
            state['draft'] = {key: original['project'][key] for key in ('name','background','users','scope')}
            state['project'] = {**state['draft'], 'type': original['project']['type'],
                                'signature': original['project']['signature'], 'messages': []}
            state['survey'] = original['survey']
            for question in state['survey']['questions']:
                question.pop('llmRequestId',None)
            state.update(answers=original['answers'], questionIndex=original['questionIndex'], stage=3,
                         documentText=original['documentText'], manualEdited=original['manualEdited'])
            prompt_id, now = str(uuid.uuid4()), timestamp()
            db.execute('INSERT INTO prompts(prompt_id,user_id,source_prompt_id,created_at,updated_at) VALUES(?,?,?,?,?)',
                       (prompt_id,user_id,source_id,now,now))
            db.execute('INSERT INTO personal_prompts VALUES(?,?,?)', (prompt_id,user_id,source_id))
            self._write(db,prompt_id,state,None,now)
            db.execute('UPDATE prompts SET completed_at=? WHERE prompt_id=?', (now,prompt_id))
            db.execute('UPDATE prompt_documents SET spec=? WHERE prompt_id=?', (source['spec'],prompt_id))
            return {'promptId': prompt_id, 'created': True}

    def open_personal(self, source_id, user_id):
        """Detach personal edits from the confirmed original, once per owner/source."""
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            original = self.load(source_id, user_id, connection=db)
            if original is None:
                raise APIError(404, '프롬프트를 찾을 수 없습니다.')
            if original.get('personal'):
                return original
            existing = db.execute('SELECT prompt_id FROM personal_prompts WHERE user_id=? AND source_prompt_id=?',
                                  (user_id,source_id)).fetchone()
            if existing:
                return self.load(existing['prompt_id'],user_id,connection=db)
            if not original['confirmed']:
                raise APIError(400, '확정된 프롬프트만 개인 사본으로 열 수 있어요.')
            prompt_id, now = str(uuid.uuid4()), timestamp()
            db.execute('INSERT INTO prompts(prompt_id,user_id,source_prompt_id,created_at,updated_at) VALUES(?,?,?,?,?)',
                       (prompt_id,user_id,source_id,now,now))
            db.execute('INSERT INTO personal_prompts VALUES(?,?,?)', (prompt_id,user_id,source_id))
            self._write(db,prompt_id,original['state'],original['backgroundAgent'],now)
            db.execute('UPDATE prompts SET completed_at=? WHERE prompt_id=?', (now,prompt_id))
            db.execute('UPDATE prompt_documents SET spec=(SELECT spec FROM prompt_documents WHERE prompt_id=?) WHERE prompt_id=?',
                       (source_id,prompt_id))
            columns = [row[1] for row in db.execute('PRAGMA table_info(prompt_edit_turns)') if row[1] != 'prompt_id']
            fields = ','.join(columns)
            db.execute(f'INSERT INTO prompt_edit_turns(prompt_id,{fields}) SELECT ?,{fields} FROM prompt_edit_turns WHERE prompt_id=?',
                       (prompt_id,source_id))
            return self.load(prompt_id,user_id,connection=db)

    def recommend(self, prompt_id, viewer_id, on):
        """Add or remove the viewer's recommendation; returns the new count, or None if the prompt is not shared."""
        with self.connect() as db:
            owner = db.execute('SELECT user_id FROM prompts WHERE prompt_id = ? AND shared_at IS NOT NULL', (prompt_id,)).fetchone()
            if owner is None:
                return None
            if on:
                db.execute('INSERT OR IGNORE INTO prompt_recommendations VALUES (?, ?, ?)', (prompt_id, viewer_id, timestamp()))
            else:
                db.execute('DELETE FROM prompt_recommendations WHERE prompt_id = ? AND user_id = ?', (prompt_id, viewer_id))
            return db.execute('SELECT COUNT(*) FROM prompt_recommendations WHERE prompt_id = ?', (prompt_id,)).fetchone()[0]

    # LLM usage ----------------------------------------------------------------------------------

    def record_llm(self, entry):
        with self.connect() as db:
            db.execute(f'INSERT INTO llm_requests ({", ".join(entry)}) VALUES ({", ".join("?" * len(entry))})', tuple(entry.values()))

    def health(self):
        with self.connect() as db:
            db.execute('SELECT 1').fetchone()


def workspace(current):
    return {key: current[key] for key in ('promptId', 'state', 'backgroundAgent', 'revision', 'updatedAt', 'confirmed')} | ({'personal': True} if current.get('personal') else {})
