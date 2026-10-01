"""Validate saved workspaces without trusting browser-supplied derived fields."""
import json
from .content import CONTEXT_STEPS
from .survey import MAX_QUESTIONS, complete, empty_survey

FIELDS = {'name': 80, 'background': 6000, 'users': 3000, 'scope': 3000}


class APIError(Exception):
    def __init__(self, status, message):
        self.status = status
        self.message = message
        super().__init__(message)


def fail(message):
    raise APIError(400, message)


def require_object(value, name):
    if not isinstance(value, dict):
        fail(f'{name}: 객체가 필요합니다.')
    return value


def text(value, maximum, name, required=False):
    # Match JavaScript's UTF-16 length limits, including emoji in existing workspaces.
    if not isinstance(value, str):
        fail(f'{name}: 입력값 또는 길이를 확인해주세요.')
    try:
        length = len(value.encode('utf-16-le')) // 2
    except UnicodeEncodeError:
        fail(f'{name}: 유효하지 않은 문자입니다.')
    if length > maximum or (required and not value.strip()):
        fail(f'{name}: 입력값 또는 길이를 확인해주세요.')
    return value


def definition(value, required=False):
    require_object(value, '과제')
    return {key: text(value.get(key), limit, key, required) for key, limit in FIELDS.items()}


def initial_state():
    return {'context': {}, 'draft': dict.fromkeys(FIELDS, ''), 'project': None, 'answers': {},
            'survey': empty_survey(), 'questionIndex': 0, 'stage': 1, 'documentText': '', 'manualEdited': False}


def validate_state(data, agent=None, survey=None, existing_project=None):
    """survey is the server-saved survey; generated questions are never taken from the browser."""
    require_object(data, '작업')
    state = initial_state()
    context = require_object(data.get('context'), '대화')
    gap = False
    for step in CONTEXT_STEPS:
        key = step['id']
        if key not in context:
            gap = True
            continue
        if gap:
            fail('대화 순서를 확인해주세요.')
        state['context'][key] = text(context[key], 3000, key, True)
    if agent is not None:
        from .background_agent import legacy_context
        state['context'] = legacy_context(agent)
    state['draft'] = definition(data.get('draft'))
    if type(data.get('stage')) is not int or data['stage'] not in (1, 2, 3):
        fail('유효하지 않은 단계입니다.')
    state['stage'] = data['stage']
    if data.get('project') is not None:
        project = definition(data['project'], True)
        # Imported documents carry only their public task definition, without the author's private conversation.
        imported = not state['context'] and existing_project is not None and project == definition(existing_project, True)
        if (agent is not None and not agent['ready']) or (len(state['context']) != len(CONTEXT_STEPS) and not imported):
            fail('업무 배경 대화를 먼저 완료해주세요.')
        # The type only matters for workspaces saved with the old fixed questions; new tasks are not categorised.
        state['project'] = {**project, 'type': existing_project['type'] if imported else agent.get('taskType', 'general') if agent else 'reservation',
                            'signature': json.dumps(project, ensure_ascii=False, separators=(',', ':')),
                            'messages': [m['content'] for m in agent['messages'] if m['role'] == 'user'] if agent else [state['context'][s['id']] for s in CONTEXT_STEPS if s['id'] in state['context']]}
    elif state['stage'] != 1:
        fail('과제를 먼저 확정해주세요.')
    answers = require_object(data.get('answers'), '답변')
    if state['project']:
        def answer(question):
            value = require_object(answers[question['id']], question['id'])
            selected = value.get('selected')
            maximum = len(question['cards']) if question.get('multi') else 1
            if not isinstance(selected, list) or len(selected) > maximum:
                fail('선택 개수를 확인해주세요.')
            allowed = [card['title'] for card in question['cards']]
            if any(not isinstance(item, str) or item not in allowed for item in selected):
                fail('유효하지 않은 답변 선택지입니다.')
            if len(set(selected)) != len(selected):
                fail('유효하지 않은 답변 선택지입니다.')
            return {'selected': selected, 'custom': text(value.get('custom'), 3000, '직접 답변')}
        current = survey is not None and survey['signature'] == state['project']['signature']
        state['survey'] = survey if current else empty_survey(state['project'])
        for question in state['survey']['questions']:
            if question['id'] in answers:
                state['answers'][question['id']] = answer(question)
    index = data.get('questionIndex')
    if type(index) is not int or not 0 <= index < MAX_QUESTIONS:
        fail('질문 순서를 확인해주세요.')
    state['questionIndex'] = min(index, max(0, len(state['survey']['questions']) - 1))
    state['documentText'] = text(data.get('documentText'), 100000, '프롬프트')
    if type(data.get('manualEdited')) is not bool:
        fail('수정 상태를 확인해주세요.')
    state['manualEdited'] = data['manualEdited']
    if not state['project'] and (answers or state['documentText']):
        fail('과제를 먼저 확정해주세요.')
    if state['stage'] == 3:
        require_complete(state)
    return state


def require_complete(state):
    if not state['project']:
        fail('과제를 먼저 확정해주세요.')
    if not complete(state['survey'], state['answers']):
        fail('모든 질문에 답해주세요.')


def ready_for_prompt(data, agent=None, survey=None):
    """The validated state, if the task and survey are complete enough to write the initial prompt."""
    state = validate_state(data, agent, survey)
    require_complete(state)
    return state
