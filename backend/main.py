"""FastAPI application. Run from the repository root with uvicorn backend.main:app."""
import asyncio
import hashlib
import logging
import os
import re
import json
from weakref import WeakValueDictionary
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from starlette.datastructures import Headers, MutableHeaders
from starlette.exceptions import HTTPException

from . import background_agent, prompt_writer, prompt_editor, survey
from .auth import Auth
from .accounts import account_router
from .admin import admin_router
from .llm_client import ConfigurationError, InvalidLLMResponse, usage_context
from openai import APIConnectionError, APIStatusError, APITimeoutError, RateLimitError
from .config import database_path
from .content import CONTEXT_STEPS, answer_text
from .database import Database, workspace
from .state import APIError, initial_state, validate_state, ready_for_prompt

DEFAULT_DB_PATH = Path(__file__).resolve().parent / 'app.db'
MAX_BODY = 512 * 1024


class EditMessagePayload(BaseModel):
    revision: int = Field(strict=True, ge=0)
    requestId: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,80}$')
    message: str = Field(min_length=1, max_length=3000)


class EditDecisionPayload(BaseModel):
    revision: int = Field(strict=True, ge=0)
    decision: Literal['accept', 'reject']


class SharingPayload(BaseModel):
    enabled: bool = Field(strict=True)


class RevisionPayload(BaseModel):
    revision: int = Field(strict=True, ge=0, le=9007199254740991)


class SavePayload(RevisionPayload):
    state: dict


class SurveyPayload(SavePayload):
    position: int = Field(strict=True, ge=0, lt=survey.MAX_QUESTIONS)


class PrefetchPayload(BaseModel):
    state: dict  # Position 0 may carry a not-yet-confirmed project so the first question is ready on confirm.
    position: int = Field(strict=True, ge=0, lt=survey.MAX_QUESTIONS)


class BackgroundPayload(RevisionPayload):
    message: str = Field(min_length=1, max_length=3000)
    requestId: str = Field(pattern=r'^[a-zA-Z0-9_-]{8,80}$')
    resetProject: bool = False


class APIMiddleware:
    """Bound request bodies before parsing; preserve the original API error format."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)

        async def send_headers(message):
            if message['type'] == 'http.response.start':
                headers = MutableHeaders(scope=message)
                headers['Cache-Control'] = 'no-store'
                headers['X-Content-Type-Options'] = 'nosniff'
            await send(message)

        if scope['path'].startswith('/api') and scope['method'] in ('POST', 'PUT', 'DELETE'):
            headers = Headers(scope=scope)
            try:
                if 'origin' in headers:
                    try:
                        origin = urlsplit(headers['origin'])
                        valid = origin.scheme in ('http', 'https') and origin.netloc == headers.get('host')
                    except ValueError:
                        valid = False
                    if not valid:
                        raise APIError(403, '허용되지 않은 요청 출처입니다.')
                json_body = headers.get('content-type', '').split(';', 1)[0].strip().lower() == 'application/json'
                data = bytearray()
                while True:
                    message = await asyncio.wait_for(receive(), timeout=15)
                    if message['type'] == 'http.disconnect':
                        return
                    data.extend(message.get('body', b''))
                    if len(data) > MAX_BODY:
                        raise APIError(413, '요청이 너무 큽니다.')
                    if not message.get('more_body'):
                        break
                if data and not json_body:  # Body-less requests such as DELETE need no content type.
                    raise APIError(415, 'JSON 형식으로 요청해주세요.')
                delivered = False

                async def replay():
                    nonlocal delivered
                    if not delivered:
                        delivered = True
                        return {'type': 'http.request', 'body': bytes(data), 'more_body': False}
                    return await receive()

                return await self.app(scope, replay, send_headers)
            except APIError as error:
                return await JSONResponse({'error': error.message}, status_code=error.status)(scope, receive, send_headers)
            except TimeoutError:
                return await JSONResponse({'error': '요청 시간이 초과되었습니다.'}, status_code=408)(scope, receive, send_headers)
        await self.app(scope, receive, send_headers)


def create_app(db_path=None, secure_cookie=None):
    database = Database(db_path or database_path())
    secure = os.environ.get('COOKIE_SECURE', '').lower() == 'true' if secure_cookie is None else secure_cookie
    auth = Auth(database, secure)
    signed_in = Depends(auth.ready_user)

    @asynccontextmanager
    async def lifespan(app):
        database.initialize()
        with database.connect() as db:
            auth.initialize(db)
        database.create_tables()  # After accounts, which prompts reference; moves former workspaces.
        yield

    app = FastAPI(title='WiaCoding API', version='1.0.0', lifespan=lifespan)
    locks = WeakValueDictionary()
    capacity = asyncio.Semaphore(4)
    prefetcher = survey.Prefetcher()
    editor_store = prompt_editor.EditStore(database)
    app.state.database = database
    app.add_middleware(APIMiddleware)
    app.include_router(auth.router)
    app.include_router(account_router(database, auth))
    app.include_router(admin_router(database, auth))

    @app.exception_handler(APIError)
    async def api_error(request, error):
        return JSONResponse({'error': error.message}, status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, error):
        if request.url.path.startswith('/api/admin/'):
            issues = error.errors()
            message = issues[0]['msg'].removeprefix('Value error, ') if issues and issues[0]['type'] == 'value_error' else '입력 형식을 확인해주세요. 사번·필수 항목·조회 조건을 확인해 주세요.'
            return JSONResponse({'error': message}, status_code=400)
        return JSONResponse({'error': '요청 형식을 확인해주세요. 유효한 revision과 작업 내용이 필요합니다.'}, status_code=400)

    @app.exception_handler(HTTPException)
    async def http_error(request, error):
        return JSONResponse({'error': '요청한 API 또는 요청 방식을 확인해주세요.'}, status_code=error.status_code)

    @app.exception_handler(Exception)
    async def unexpected_error(request, error):
        logging.getLogger(__name__).error('API request failed', exc_info=error)
        return JSONResponse({'error': '서버 처리 중 오류가 발생했습니다.'}, status_code=500)

    def claim_former_workspace(user, request, response):
        """Work saved anonymously in this browser before login becomes one of the user's prompts."""
        token = request.cookies.get('wiacoding_session', '')
        if re.fullmatch('[a-f0-9]{64}', token):
            database.claim(hashlib.sha256(token.encode()).hexdigest(), user['user_id'])
            response.delete_cookie('wiacoding_session', path='/api', httponly=True, secure=secure, samesite='strict')

    def owned(user, prompt_id):
        current = database.load(prompt_id, user['user_id'])
        if current is None:
            raise APIError(404, '프롬프트를 찾을 수 없습니다. 목록에서 다시 선택해주세요.')
        # LLM calls made for this request (and prefetch tasks it starts) are recorded against this prompt.
        usage_context.set((database.record_llm, user['user_id'], prompt_id))
        return current

    @app.get('/api/health')
    def health():
        database.health()
        return {'status': 'ok', 'storage': 'sqlite', 'generation': 'template', 'framework': 'fastapi', 'background': 'llm'}

    @app.get('/api/prompts')
    def list_prompts(request: Request, response: Response, user: dict = signed_in):
        claim_former_workspace(user, request, response)
        return {'prompts': database.list_prompts(user['user_id'])}

    @app.post('/api/prompts', status_code=201)
    def create_prompt(user: dict = signed_in):
        return workspace(database.create_prompt(user['user_id']))

    @app.get('/api/prompts/{prompt_id}')
    def get_prompt(prompt_id: str, user: dict = signed_in):
        return workspace(owned(user, prompt_id))

    @app.post('/api/prompts/{prompt_id}/personal')
    def open_personal_prompt(prompt_id: str, user: dict = signed_in):
        return workspace(database.open_personal(prompt_id, user['user_id']))

    @app.put('/api/prompts/{prompt_id}')
    def save_prompt(prompt_id: str, payload: SavePayload, user: dict = signed_in):
        current = owned(user, prompt_id)
        return database.save(current, payload.revision, validate_state(payload.state, current['backgroundAgent'], current['state']['survey'], existing_project=current['state']['project']))

    @app.post('/api/prompts/{prompt_id}/confirm')
    def confirm_prompt(prompt_id: str, payload: RevisionPayload, user: dict = signed_in):
        return workspace(database.confirm(prompt_id, user['user_id'], payload.revision))

    @app.delete('/api/prompts/{prompt_id}/library-entry')
    def remove_library_entry(prompt_id: str, user: dict = signed_in):
        return database.remove_from_library(prompt_id, user['user_id'])

    @app.delete('/api/prompts/{prompt_id}')
    def delete_prompt(prompt_id: str, user: dict = signed_in):
        if not database.delete_prompt(prompt_id, user['user_id']):
            raise APIError(404, '프롬프트를 찾을 수 없습니다. 목록에서 다시 선택해주세요.')
        return {'ok': True}

    @app.post('/api/prompts/{prompt_id}/generate')
    async def generate_document(prompt_id: str, payload: SavePayload, user: dict = signed_in):
        """Consolidate the task and survey into the initial prompt with one LLM call."""
        lock = locks.setdefault(prompt_id, asyncio.Lock())
        async with lock:
            current = owned(user, prompt_id)
            if current['revision'] != payload.revision:
                raise APIError(409, '다른 탭에서 작업이 변경되었습니다. 새로고침해주세요.')
            state = ready_for_prompt(payload.state, current['backgroundAgent'], current['state']['survey'])
            try:
                async with asyncio.timeout(150):
                    async with capacity:
                        text, spec, request_id = await prompt_writer.write(state['project'], current['backgroundAgent'],
                                                                           state['survey'], state['answers'])
            except ConfigurationError:
                raise APIError(503, '프롬프트 생성의 LLM 연결 설정을 확인해주세요.') from None
            except InvalidLLMResponse:
                raise APIError(502, '프롬프트를 정리하는 중 형식을 확인하지 못했습니다. 다시 시도해주세요.') from None
            except (TimeoutError, APITimeoutError):
                raise APIError(504, '프롬프트 생성 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.') from None
            except RateLimitError:
                raise APIError(429, '요청이 많습니다. 잠시 후 다시 시도해주세요.') from None
            except (APIConnectionError, APIStatusError):
                raise APIError(502, '프롬프트 생성 서비스 연결이 원활하지 않습니다. 잠시 후 다시 시도해주세요.') from None
            state.update(documentText=text, manualEdited=False, stage=3)
            return database.save(current, payload.revision, state, document={'llmRequestId': request_id, 'spec': spec})

    @app.get('/api/prompts/{prompt_id}/editor')
    def edit_history(prompt_id: str, user: dict = signed_in):
        owned(user, prompt_id)
        return {'turns': editor_store.history(prompt_id)}

    @app.post('/api/prompts/{prompt_id}/editor')
    async def edit_prompt(prompt_id: str, payload: EditMessagePayload, user: dict = signed_in):
        message = payload.message.strip()
        if not message:
            raise APIError(400, '수정할 내용을 입력해주세요.')
        lock = locks.setdefault(prompt_id, asyncio.Lock())
        async with lock:
            owned(user, prompt_id)
            history = editor_store.rows(prompt_id)
            current, previous = editor_store.start(prompt_id, user['user_id'], payload.revision, payload.requestId, message)
            if previous:
                return {'revision': current['revision'], 'turns': editor_store.history(prompt_id)}
            token = usage_context.set((lambda entry: editor_store.record(prompt_id, payload.requestId, entry), user['user_id'], prompt_id))
            try:
                async with asyncio.timeout(150):
                    async with capacity:
                        response, after = await prompt_editor.reply(current['state']['documentText'], history, message)
                return editor_store.finish(prompt_id, user['user_id'], payload.requestId, response, after)
            except (ConfigurationError, InvalidLLMResponse, TimeoutError, APIConnectionError, APIStatusError) as error:
                if isinstance(error, ConfigurationError): status, text = 503, 'Agent 연결 설정을 확인해주세요.'
                elif isinstance(error, (TimeoutError, APITimeoutError)): status, text = 504, 'Agent 응답 시간이 초과되었습니다. 다시 요청해주세요.'
                elif isinstance(error, RateLimitError): status, text = 429, '요청이 많습니다. 잠시 후 다시 시도해주세요.'
                else: status, text = 502, '수정안을 만들지 못했어요. 다시 요청해주세요.'
                editor_store.fail(prompt_id, payload.requestId, text)
                raise APIError(status, text) from None
            except BaseException:
                editor_store.fail(prompt_id, payload.requestId, '응답이 중단되었습니다. 다시 요청해주세요.')
                raise
            finally:
                usage_context.reset(token)

    @app.post('/api/prompts/{prompt_id}/editor/{turn_id}/decision')
    def decide_edit(prompt_id: str, turn_id: str, payload: EditDecisionPayload, user: dict = signed_in):
        owned(user, prompt_id)
        return editor_store.decide(prompt_id, user['user_id'], turn_id, payload.revision, payload.decision)

    @app.get('/api/background', dependencies=[signed_in])
    def background_metadata():
        return {'categories': background_agent.CATEGORIES, 'introduction': background_agent.INTRODUCTION}

    @app.post('/api/prompts/{prompt_id}/background')
    async def background_turn(prompt_id: str, payload: BackgroundPayload, user: dict = signed_in):
        message = payload.message.strip()
        if not message:
            raise APIError(400, '업무 상황이나 답변을 입력해주세요.')
        lock = locks.setdefault(prompt_id, asyncio.Lock())
        async with lock:
            row = owned(user, prompt_id)
            saved = workspace(row)
            state = saved['state']
            agent = saved['backgroundAgent'] or background_agent.initial_agent(state)
            if agent['lastTurn'] and agent['lastTurn']['id'] == payload.requestId:
                if agent['lastTurn']['message'] != message:
                    raise APIError(400, '이미 사용한 요청 ID입니다.')
                return saved
            if any(m['id'] == payload.requestId for m in agent['messages']):
                raise APIError(400, '이미 사용한 요청 ID입니다.')
            if saved['revision'] != payload.revision:
                raise APIError(409, '다른 탭에서 작업이 변경되었습니다. 새로고침해주세요.')
            if state['project'] and not payload.resetProject:
                raise APIError(400, '배경을 수정하려면 기존 설문·프롬프트 초기화를 확인해주세요.')
            if sum(len(m['content']) for m in agent['messages']) + len(message) > 60000:
                raise APIError(400, '대화가 길어졌습니다. 정리한 내용을 보관하고 새 과제로 이어주세요.')
            try:
                async with asyncio.timeout(150):
                    async with capacity:
                        updated = await background_agent.run_turn(agent, message, payload.requestId)
            except ConfigurationError:
                raise APIError(503, '대화 Agent의 LLM 연결 설정을 확인해주세요.') from None
            except InvalidLLMResponse:
                raise APIError(502, '답변을 정리하는 중 형식을 확인하지 못했습니다. 같은 내용을 다시 전송해주세요.') from None
            except (TimeoutError, APITimeoutError):
                raise APIError(504, '답변 생성 시간이 초과되었습니다. 잠시 후 다시 전송해주세요.') from None
            except RateLimitError:
                raise APIError(429, '대화 요청이 많습니다. 잠시 후 다시 전송해주세요.') from None
            except (APIConnectionError, APIStatusError):
                raise APIError(502, '대화 서비스 연결이 원활하지 않습니다. 잠시 후 다시 전송해주세요.') from None
            state = initial_state()
            state['context'] = background_agent.legacy_context(updated)
            state['draft'] = background_agent.draft_from_agent(updated)
            # Save the new conversation and draft in the same optimistic transaction.
            return database.save(row, payload.revision, validate_state(state, updated), agent=updated)

    def survey_request(row, data, position):
        """Validate the browser state against the saved survey and identify the next question slot."""
        saved = row
        state = validate_state(data, saved['backgroundAgent'], saved['state']['survey'])
        questions = state['survey']['questions']
        if not state['project'] or state['stage'] != 2 or position > len(questions):
            raise APIError(400, '질문 순서를 확인해주세요.')
        if any(not answer_text(state['answers'].get(q['id'])) for q in questions[:position]):
            raise APIError(400, '카드를 선택하거나 Custom Answer에 답변을 적어주세요.')
        answered = survey.basis(questions, state['answers'], position)
        key = (row['promptId'], state['project']['signature'], answered)
        project, prefix, answers = state['project'], questions[:position], state['answers']
        # Topics added while generating a replaced question are dropped with it; position 0 plans anew.
        topics = [topic for topic in state['survey']['topics'] if topic['origin'] < position] if position else []

        async def generate():
            async with capacity:
                return await survey.generate(project, topics, prefix, answers)
        return state, answered, key, (row['promptId'], position), generate

    @app.post('/api/prompts/{prompt_id}/survey')
    async def survey_next(prompt_id: str, payload: SurveyPayload, user: dict = signed_in):
        """Move to the question after `position` answered ones, generating it only when needed."""
        lock = locks.setdefault(prompt_id, asyncio.Lock())
        async with lock:
            row = owned(user, prompt_id)
            if row['revision'] != payload.revision:
                raise APIError(409, '다른 탭에서 작업이 변경되었습니다. 새로고침해주세요.')
            position = payload.position
            state, answered, key, group, generate = survey_request(row, payload.state, position)
            current = state['survey']
            if position < len(current['questions']) and current['questions'][position]['basis'] == answered:
                return database.save(row, payload.revision, {**state, 'questionIndex': position})
            if position == len(current['questions']) and current['done'] and current['doneBasis'] == answered:
                return database.save(row, payload.revision, state)
            try:
                async with asyncio.timeout(150):
                    # Shield so an abandoned request still leaves the result for the retry.
                    result = await asyncio.shield(prefetcher.get(key, group, generate))
            except ConfigurationError:
                raise APIError(503, '설문 생성의 LLM 연결 설정을 확인해주세요.') from None
            except InvalidLLMResponse:
                raise APIError(502, '다음 질문을 만드는 중 형식을 확인하지 못했습니다. 다시 시도해주세요.') from None
            except (TimeoutError, APITimeoutError):
                raise APIError(504, '다음 질문 생성 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.') from None
            except RateLimitError:
                raise APIError(429, '요청이 많습니다. 잠시 후 다시 시도해주세요.') from None
            except (APIConnectionError, APIStatusError):
                raise APIError(502, '설문 생성 서비스 연결이 원활하지 않습니다. 잠시 후 다시 시도해주세요.') from None
            prefetcher.finish(key, group)
            question = result['question']
            prefix = current['questions'][:position]
            state['answers'] = {q['id']: state['answers'][q['id']] for q in prefix}  # Later answers belong to replaced questions.
            if question:
                # Each question keeps the topic evaluation it was asked under, for the progress chips.
                prefix = [*prefix, {**question, 'id': f'q{position + 1}', 'basis': answered, 'status': result['status'],
                                    **({'llmRequestId': result['requestId']} if result.get('requestId') else {})}]
            state['survey'] = {**current, 'topics': result['topics'], 'topicStatus': result['status'],
                               'questions': prefix, 'done': question is None,
                               'doneBasis': '' if question else answered}
            state['questionIndex'] = position if question else max(0, position - 1)
            return database.save(row, payload.revision, state)

    @app.post('/api/prompts/{prompt_id}/survey/prefetch')
    async def survey_prefetch(prompt_id: str, payload: PrefetchPayload, user: dict = signed_in):
        """Best-effort: begin generating the next question from answers that are not submitted yet."""
        row = owned(user, prompt_id)
        state, answered, key, group, generate = survey_request(row, payload.state, payload.position)
        current = state['survey']
        questions = current['questions']
        ready = (payload.position < len(questions) and questions[payload.position]['basis'] == answered) or (
            payload.position == len(questions) and current['done'] and current['doneBasis'] == answered)
        if not ready:
            prefetcher.get(key, group, generate)
        return {'status': 'ready' if ready else 'started'}

    @app.get('/api/sharing')
    def sharing_list(user: dict = signed_in):
        return {'prompts': database.sharing_list(user['user_id'])}

    @app.put('/api/prompts/{prompt_id}/sharing')
    def set_sharing(prompt_id: str, payload: SharingPayload, user: dict = signed_in):
        return database.set_sharing(prompt_id, user['user_id'], payload.enabled)

    @app.get('/api/shared')
    def shared_prompts(q: str = '', sort: str = 'latest', user: dict = signed_in):
        """Completed prompts of all users; search covers title, goal, tools and team."""
        query = ''.join(q.lower().split())
        cards = [card for card in database.shared_list(user['user_id'])
                 if query in ''.join(' '.join([card['title'], card['goal'], card['team'], *card['tags']]).lower().split())]
        if sort == 'recommended':
            cards.sort(key=lambda card: card['recommendations'], reverse=True)  # Stable: ties stay newest first.
        return {'prompts': cards}

    @app.get('/api/shared/{prompt_id}')
    def shared_prompt(prompt_id: str, user: dict = signed_in):
        detail = database.shared_detail(prompt_id, user['user_id'])
        if detail is None:
            raise APIError(404, '공유된 프롬프트를 찾을 수 없습니다.')
        return detail

    @app.get('/api/shared/{prompt_id}/editor-history')
    def shared_editor_history(prompt_id: str, before: int | None = None, user: dict = signed_in):
        return editor_store.shared_history(prompt_id, before)

    @app.get('/api/shared/{prompt_id}/editor-chat')
    def shared_editor_chat(prompt_id: str, before: int | None = None, user: dict = signed_in):
        return editor_store.shared_history(prompt_id, before, conversation=True)

    @app.post('/api/shared/{prompt_id}/import')
    def import_prompt(prompt_id: str, user: dict = signed_in):
        return database.import_shared(prompt_id, user['user_id'])

    @app.put('/api/shared/{prompt_id}/recommendation')
    def recommend(prompt_id: str, user: dict = signed_in):
        return recommendation(prompt_id, user, True)

    @app.delete('/api/shared/{prompt_id}/recommendation')
    def unrecommend(prompt_id: str, user: dict = signed_in):
        return recommendation(prompt_id, user, False)

    def recommendation(prompt_id, user, on):
        count = database.recommend(prompt_id, user['user_id'], on)
        if count is None:
            raise APIError(404, '공유된 프롬프트를 찾을 수 없습니다.')
        return {'recommendations': count, 'recommended': on}

    @app.get('/api/templates/task-definition', dependencies=[signed_in])
    def task_definition_template():
        # Read on each request so template edits apply without a restart.
        return {'html': (Path(__file__).resolve().parent / 'templates/task_definition.html').read_text()}

    @app.get('/api/context', dependencies=[signed_in])
    def context():
        return {'steps': CONTEXT_STEPS}

    @app.get('/api/prompts/{prompt_id}/questions')
    def survey_questions(prompt_id: str, user: dict = signed_in):
        return {'questions': owned(user, prompt_id)['state']['survey']['questions']}

    return app


app = create_app()
