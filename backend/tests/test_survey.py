import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from backend import survey
from backend.content import UNKNOWN, answer_text
from backend.llm_client import InvalidLLMResponse
from backend.main import create_app
from backend.tests.support import sign_in, url


PLAN = [{'id': f't{i}', 'label': f'주제 {i}', 'description': '설명', 'origin': 0} for i in range(1, 5)]


def fake_model(monkeypatch, fail=None):
    """Deterministic generator: plans 4 topics, one question per topic, then done. Records the answers it saw."""
    calls = []

    async def generate(project, topics, questions, answers):
        calls.append([answer_text(answers[q['id']]) for q in questions])
        if fail:
            raise fail
        count = len(questions)
        topics = topics or PLAN
        status = {t['id']: {'status': 'sufficient' if i < count else 'unasked', 'reason': ''} for i, t in enumerate(topics)}
        if count >= len(topics):
            return {'topics': topics, 'status': status, 'question': None}
        return {'topics': topics, 'status': status, 'question': {
            'topic': topics[count]['id'], 'label': f'주제{count + 1}', 'title': f'질문 {count + 1}', 'help': '도움말',
            'multi': count == 1, 'cards': [{'title': f'선택 {count + 1}-{x}', 'description': 'd', 'reason': 'r'} for x in 'AB']
            + [survey.UNKNOWN_CARD]}}
    monkeypatch.setattr(survey, 'generate', generate)
    return calls


def advance(client, data, position):
    return client.post(url(client, '/survey'), json={'revision': data['revision'], 'state': data['state'], 'position': position})


def answer_all(client, data, custom='팀장이 승인'):
    position = 0
    while True:
        data = advance(client, data, position).json()
        if data['state']['survey']['done']:
            return data
        question = data['state']['survey']['questions'][position]
        data['state']['answers'][question['id']] = {'selected': [question['cards'][0]['title']], 'custom': custom if position == 2 else ''}
        position += 1


def project_state(client, monkeypatch):
    from backend.tests.test_api import complete
    client.get(url(client))
    return client.put(url(client), json={'revision': 0, 'state': complete()}).json()


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'app.db')) as value:
        sign_in(value)
        yield value


def test_each_question_is_generated_from_previous_answers(client, monkeypatch):
    calls = fake_model(monkeypatch)
    data = advance(client, project_state(client, monkeypatch), 0).json()
    assert data['state']['survey']['questions'][0]['cards'][-1]['title'] == UNKNOWN
    data['state']['answers']['q1'] = {'selected': ['선택 1-B'], 'custom': '라인마다 양식이 달라요'}
    data = advance(client, data, 1).json()
    assert calls == [[], ['선택 1-B\n라인마다 양식이 달라요']]
    assert data['state']['questionIndex'] == 1
    assert [q['id'] for q in data['state']['survey']['questions']] == ['q1', 'q2']


def test_back_and_forward_reuses_questions_until_an_answer_changes(client, monkeypatch):
    calls = fake_model(monkeypatch)
    data = answer_all(client, project_state(client, monkeypatch))
    assert len(calls) == 5 and data['state']['survey']['done']
    assert advance(client, data, 1).json()['state']['questionIndex'] == 1
    data = client.get(url(client)).json()
    assert len(calls) == 5
    data['state']['answers']['q1'] = {'selected': ['선택 1-A'], 'custom': '바뀐 답변'}
    data = advance(client, data, 1).json()
    assert len(calls) == 6
    assert [q['id'] for q in data['state']['survey']['questions']] == ['q1', 'q2']
    assert list(data['state']['answers']) == ['q1']
    assert not data['state']['survey']['done']


def test_browser_cannot_forge_questions_or_skip_ahead(client, monkeypatch):
    fake_model(monkeypatch)
    data = advance(client, project_state(client, monkeypatch), 0).json()
    forged = data['state']
    forged['survey']['questions'][0]['cards'] = [{'title': '위조', 'description': '', 'reason': ''}]
    forged['answers']['q1'] = {'selected': ['위조'], 'custom': ''}
    assert client.put(url(client), json={'revision': data['revision'], 'state': forged}).status_code == 400
    assert advance(client, data, 1).status_code == 400  # q1 is unanswered.
    assert advance(client, data, 3).status_code == 400
    assert client.post(url(client, '/generate'), json={'revision': data['revision'], 'state': data['state']}).status_code == 400


def test_prefetch_is_reused_on_submit(client, monkeypatch):
    calls = fake_model(monkeypatch)
    data = advance(client, project_state(client, monkeypatch), 0).json()
    data['state']['answers']['q1'] = {'selected': ['선택 1-A'], 'custom': ''}
    prefetch = client.post(url(client, '/survey/prefetch'), json={'state': data['state'], 'position': 1})
    assert prefetch.json() == {'status': 'started'}
    assert advance(client, data, 1).json()['state']['survey']['questions'][1]['title'] == '질문 2'
    assert len(calls) == 2
    data = client.get(url(client)).json()
    assert client.post(url(client, '/survey/prefetch'), json={'state': data['state'], 'position': 1}).json() == {'status': 'ready'}


def test_first_question_can_be_prefetched_before_confirming(client, monkeypatch):
    from backend.tests.test_api import complete
    calls = fake_model(monkeypatch)
    client.get(url(client))
    draft_only = {**complete(), 'project': None, 'stage': 1}
    saved = client.put(url(client), json={'revision': 0, 'state': draft_only}).json()
    assert client.post(url(client, '/survey/prefetch'), json={'state': complete(), 'position': 0}).json() == {'status': 'started'}
    assert saved['state']['project'] is None and client.get(url(client)).json()['revision'] == 1  # Nothing saved.
    confirmed = client.put(url(client), json={'revision': 1, 'state': complete()}).json()
    assert advance(client, confirmed, 0).json()['state']['survey']['questions'][0]['title'] == '질문 1'
    assert len(calls) == 1


def test_model_errors_are_reported_and_not_saved(client, monkeypatch):
    fake_model(monkeypatch, fail=InvalidLLMResponse('bad'))
    data = project_state(client, monkeypatch)
    response = advance(client, data, 0)
    assert response.status_code == 502 and 'error' in response.json()
    assert client.get(url(client)).json()['revision'] == data['revision']
    assert advance(client, {**data, 'revision': data['revision'] + 1}, 0).status_code == 409


def test_prefetcher_replaces_superseded_task():
    async def scenario():
        prefetcher = survey.Prefetcher()
        started = []

        async def slow(value):
            started.append(value)
            await asyncio.sleep(10)
        first = prefetcher.get('a', 'g', lambda: slow('a'))
        assert prefetcher.get('a', 'g', lambda: slow('again')) is first
        second = prefetcher.get('b', 'g', lambda: slow('b'))
        await asyncio.sleep(0)
        assert first.cancelled() and not second.done()
        second.cancel()
    asyncio.run(scenario())


TOPICS = [{'id': i, 'label': i, 'description': 'd'} for i in ('data_model', 'screen_flow', 'search_api', 'llm_provider')]
QUESTION = {'topic': 'data_model', 'label': '자료', 'title': '어떤 자료를 저장하나요?', 'help': '이유', 'decision': '저장할 자료', 'multi': False,
            'cards': [{'title': t, 'description': 'd', 'reason': 'r'} for t in ('엑셀', '시스템', UNKNOWN)]}


def status(**values):
    return [{'id': t['id'], 'status': values.get(t['id'], ('unasked', ''))[0], 'reason': values.get(t['id'], ('unasked', ''))[1]}
            for t in TOPICS]


def test_first_call_validates_plan_and_question():
    first = survey.clean_first({'topics': TOPICS, 'question': QUESTION})
    assert [c['title'] for c in first['question']['cards']] == ['엑셀', '시스템', UNKNOWN]
    assert all(t['origin'] == 0 for t in first['topics']) and {v['status'] for v in first['status'].values()} == {'unasked'}
    for broken in (TOPICS[:3], [*TOPICS[:3], TOPICS[0]], [*TOPICS[:3], {**TOPICS[3], 'id': 'Bad-Id'}]):
        with pytest.raises(InvalidLLMResponse):
            survey.clean_first({'topics': broken, 'question': QUESTION})
    with pytest.raises(InvalidLLMResponse):  # Question must use a planned topic.
        survey.clean_first({'topics': TOPICS, 'question': {**QUESTION, 'topic': 'success'}})
    for broken in ({'cards': QUESTION['cards'][:1]}, {'title': ' '}, {'cards': [QUESTION['cards'][0]] * 2}):
        with pytest.raises(InvalidLLMResponse):
            survey.clean_first({'topics': TOPICS, 'question': {**QUESTION, **broken}})


def test_topic_status_drives_follow_ups_and_completion():
    planned = survey.clean_first({'topics': TOPICS, 'question': QUESTION})['topics']
    asked = [{'id': 'q1', 'topic': 'data_model', 'title': '어떤 자료를 저장하나요?', 'decision': '저장할 자료'}]
    follow_up = {**QUESTION, 'title': '실적은 라인별로 나눠 보관할까요?', 'decision': '실적 보관 단위'}
    # The model cannot mark an unanswered topic settled; the server resets it to unasked.
    result = survey.clean_next({'topic_status': status(data_model=('needs_detail', '날짜 기준 미정'), screen_flow=('sufficient', '')),
                                'done': False, 'add_topic': None, 'question': follow_up}, planned, asked, {'data_model'})
    assert result['status']['data_model'] == {'status': 'needs_detail', 'reason': '날짜 기준 미정'}
    assert result['status']['screen_flow']['status'] == 'unasked'
    with pytest.raises(InvalidLLMResponse, match='reason'):
        survey.clean_next({'topic_status': status(data_model=('needs_detail', '')), 'done': False, 'add_topic': None,
                           'question': follow_up}, planned, asked, {'data_model'})
    with pytest.raises(InvalidLLMResponse, match='sufficient'):  # A settled topic is not asked again.
        survey.clean_next({'topic_status': status(data_model=('sufficient', '')), 'done': False, 'add_topic': None,
                           'question': follow_up}, planned, asked, {'data_model'})
    for duplicate in ({**QUESTION, 'title': '어떤 자료를 저장 하나요?', 'decision': '새 결정'},  # Same wording.
                      {**QUESTION, 'title': '어떤 자료들을 저장해야 할까요?', 'decision': '새 결정'},  # Looser within a topic.
                      {**QUESTION, 'topic': 'screen_flow', 'title': '화면에는 무엇을 보여줄까요?', 'decision': '저장할 자료 범위'}):
        with pytest.raises(InvalidLLMResponse, match='이미 정한 결정'):
            survey.clean_next({'topic_status': status(data_model=('needs_detail', '항목')), 'done': False, 'add_topic': None,
                               'question': duplicate}, planned, asked, {'data_model'})
    with pytest.raises(InvalidLLMResponse, match='모든 주제'):
        survey.clean_next({'topic_status': status()[:3], 'done': False, 'add_topic': None, 'question': follow_up},
                          planned, asked, {'data_model'})
    everything = {t['id'] for t in TOPICS}
    with pytest.raises(InvalidLLMResponse, match='sufficient가 아닌'):  # Done needs every topic settled.
        survey.clean_next({'topic_status': status(**{**{t: ('sufficient', '') for t in everything}, 'llm_provider': ('needs_detail', '모델 미정')}),
                           'done': True, 'add_topic': None, 'question': None}, planned, asked * 4, everything)
    done = survey.clean_next({'topic_status': status(**{t: ('sufficient', '') for t in everything}), 'done': True,
                              'add_topic': None, 'question': None}, planned, asked * 4, everything)
    assert done['question'] is None
    added = survey.clean_next({'topic_status': [*status(data_model=('sufficient', '')), {'id': 'map_api', 'status': 'unasked', 'reason': ''}],
                               'done': False, 'add_topic': {'id': 'map_api', 'label': '지도', 'description': 'd'},
                               'question': {**follow_up, 'topic': 'map_api'}}, planned, asked, {'data_model'})
    assert added['topics'][-1] == {'id': 'map_api', 'label': '지도', 'description': 'd', 'origin': 1}


def test_budget_rules_spread_questions_across_topics():
    planned = survey.clean_first({'topics': TOPICS, 'question': QUESTION})['topics']
    follow_up = {**QUESTION, 'title': '실적 항목의 저장 단위는 무엇인가요?', 'decision': '저장 단위'}
    drilled = [{'id': 'q0', 'topic': 'data_model', 'title': '엑셀 원본을 그대로 쓰나요?'}, {'id': 'q1', 'topic': 'data_model', 'title': '보관 기간은 얼마나 되나요?'}]
    with pytest.raises(InvalidLLMResponse, match='이미 2번'):
        survey.clean_next({'topic_status': status(data_model=('needs_detail', '세부')), 'done': False, 'add_topic': None,
                           'question': follow_up}, planned, drilled, {'data_model'})
    # 7 of 8 questions used and two topics never asked: the last one must go to an unasked topic.
    many = [{'id': f'q{i}', 'topic': 'data_model' if i < 1 else 'screen_flow', 'title': f'질문 번호 {i} 입니다'} for i in range(7)]
    with pytest.raises(InvalidLLMResponse, match='아직 묻지 않은'):
        survey.clean_next({'topic_status': status(data_model=('needs_detail', '세부'), screen_flow=('sufficient', '')), 'done': False,
                           'add_topic': None, 'question': follow_up}, planned, many, {'data_model', 'screen_flow'})
    # At the limit the final evaluation is kept even though topics remain open.
    final = survey.clean_next({'topic_status': status(data_model=('needs_detail', '메일과 Teams 답변이 모순')), 'done': False,
                               'add_topic': None, 'question': follow_up}, planned, many + many[:1], {'data_model'})
    assert final['question'] is None and final['status']['data_model']['reason'] == '메일과 Teams 답변이 모순'


def test_question_limit_scales_with_topics_and_unresolved_topics_reach_prompt():
    assert [survey.question_limit((TOPICS * 2)[:n]) for n in (2, 4, 7)] == [6, 8, 11] and survey.question_limit(TOPICS * 3) == 12


def test_first_call_plans_topics_and_later_calls_send_history(monkeypatch):
    seen = []
    question = {**QUESTION, 'topic': 'search_api', 'title': '어떤 검색 API를 쓸까요?', 'cards': QUESTION['cards'][:2]}

    async def completion(messages, schema, **options):
        seen.append((messages, schema, options))
        if schema is survey.FIRST_SCHEMA:
            return json.dumps({'topics': TOPICS, 'question': question})
        return json.dumps({'topic_status': status(search_api=('needs_detail', '한국어 품질 확인')), 'done': False, 'add_topic': None,
                           'question': {**question, 'title': '국내 기사는 어떤 비중으로 모을까요?', 'decision': '국내 기사 비중'}})
    monkeypatch.setattr(survey, 'chat_completion', completion)
    monkeypatch.delenv('OPENAI_SURVEY_REASONING_EFFORT', raising=False)
    project = {'type': 'general', 'name': '동향 브리핑', 'background': 'b', 'users': 'u', 'scope': 's', 'messages': ['긴 대화'] * 50}
    first = asyncio.run(survey.generate(project, [], [], {}))
    assert [t['id'] for t in first['topics']] == [t['id'] for t in TOPICS]
    assert survey.PLAN_PROMPT in seen[0][0][0]['content'] and seen[0][2]['reasoning_effort'] == 'low'
    asked = [{**first['question'], 'id': 'q1', 'status': first['status']}]
    second = asyncio.run(survey.generate(project, first['topics'], asked, {'q1': {'selected': ['엑셀'], 'custom': '한국어 기사 위주'}}))
    assert second['status']['search_api'] == {'status': 'needs_detail', 'reason': '한국어 품질 확인'}
    payload = json.loads(seen[1][0][1]['content'])
    # Card choice and custom text are sent separately so the model can spot a conflict between them.
    assert payload['answered'] == [{'topic': 'search_api', 'decision': '저장할 자료', 'question': '어떤 검색 API를 쓸까요?',
                                    'selected': ['엑셀'], 'custom': '한국어 기사 위주', 'other_options': ['시스템']}]
    # Stable parts first so consecutive calls share a cacheable prefix.
    assert list(payload) == ['project', 'answered', 'topics', 'can_add_topic', 'question_number', 'question_limit', 'final_evaluation']
    # search_api was answered after the stored evaluation, so it is not reported as unasked.
    assert [t['previous_status'] for t in payload['topics']] == ['unasked', 'unasked', 'answered_not_evaluated', 'unasked']
    assert payload['question_limit'] == 8
    assert second['question']['decision'] == '국내 기사 비중'
    assert survey.PLAN_PROMPT not in seen[1][0][0]['content'] and '긴 대화' not in seen[1][0][1]['content']


def test_legacy_fixed_survey_is_migrated(tmp_path):
    from backend.content import legacy_questions
    from backend.tests.test_api import complete
    state = complete()
    state['project']['signature'] = 'legacy'
    for q in legacy_questions(state['project']):
        state['answers'][q['id']] = {'selected': [q['cards'][0]['title']], 'custom': ''}
    del state['survey']
    migrated = survey.legacy_survey(state)
    from backend.state import validate_state
    assert validate_state({**state, 'stage': 3}, None, migrated)['survey'] == migrated  # Kept, not reset as another project's.
    assert migrated['done'] and [q['id'] for q in migrated['questions']] == [q['id'] for q in legacy_questions(state['project'])]
    assert {q['topic'] for q in migrated['questions']} <= {t['id'] for t in migrated['topics']}
    assert survey.complete(migrated, state['answers'])
