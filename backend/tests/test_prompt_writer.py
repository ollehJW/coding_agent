import asyncio
import json

import pytest

from backend import prompt_writer
from backend.content import UNKNOWN
from backend.llm_client import InvalidLLMResponse

PROJECT = {'name': '회의록 작성 지원', 'background': '녹음을 다시 들으며 작성', 'users': '작성자 1명', 'scope': '요약이 있는 워드 회의록'}
AGENT = {'categories': {'problem': {'status': 'complete', 'summary': '재청취 시간이 길다', 'reason': '', 'evidence': []},
                        'goal': {'status': 'deferred', 'summary': '양식 미정', 'reason': '팀장 확인 필요', 'evidence': []}}}
SURVEY = {'topics': [{'id': 'policy', 'label': '데이터 정책'}, {'id': 'llm', 'label': '회의록 AI'}],
          'questions': [{'id': 'q1', 'topic': 'policy', 'title': '외부로 보내도 되나요?', 'decision': '외부 전송 범위'},
                        {'id': 'q2', 'topic': 'llm', 'title': '어떤 AI?', 'decision': '회의록 LLM'},
                        {'id': 'q3', 'topic': 'llm', 'title': '미답변 질문', 'decision': '미답변'}],
          'topicStatus': {'llm': {'status': 'needs_detail', 'reason': '모델 버전 미정'}, 'policy': {'status': 'sufficient', 'reason': ''}}}
ANSWERS = {'q1': {'selected': ['사내에서만 처리'], 'custom': ''}, 'q2': {'selected': [UNKNOWN], 'custom': 'Azure OpenAI 토큰 있음'},
           'q3': {'selected': [], 'custom': ''}}
SPEC = {'goal': '회의 녹음으로 보고용 회의록 초안을 만든다', 'context': '작성자가 녹음을 다시 듣느라 시간이 오래 걸린다.',
        'first_milestone': '녹음 1개 업로드 → 전사 → 요약 → 워드 다운로드',
        'requirements': [{'area': '회의록 AI', 'items': ['Azure OpenAI로 요약한다', ' ']}, {'area': '빈 영역', 'items': []}],
        'constraints': [{'type': 'must_not', 'text': 'Azure OpenAI 외 외부 서비스로 전송하지 않는다'}, {'type': 'must', 'text': '사내 서버에 저장한다'}],
        'tech_stack': [{'area': '요약', 'choice': 'Azure OpenAI', 'note': '사내 승인'}], 'out_of_scope': [],
        'open_questions': ['모델 버전', '모델 버전'], 'acceptance': ['녹음 업로드 후 워드가 생성된다', '빈 파일은 거부된다', '긴 회의도 처리된다']}


def test_request_contains_task_background_and_every_answered_decision_in_order():
    content = json.loads(prompt_writer.request_content(PROJECT, AGENT, SURVEY, ANSWERS))
    assert content['project'] == PROJECT
    assert content['background_items'][1] == {'item': '원하는 변화·범위', 'status': 'deferred', 'summary': '양식 미정', 'needs_confirmation': '팀장 확인 필요'}
    assert [a['decision'] for a in content['answered']] == ['외부 전송 범위', '회의록 LLM']  # Unanswered q3 is left out.
    assert content['answered'][1] == {'area': '회의록 AI', 'decision': '회의록 LLM', 'question': '어떤 AI?',
                                      'selected': [UNKNOWN], 'custom': 'Azure OpenAI 토큰 있음'}
    assert content['unresolved_topics'] == ['회의록 AI: 모델 버전 미정']


def test_spec_is_cleaned_and_rendered_for_a_coding_agent(monkeypatch):
    seen = {}

    async def completion(messages, schema, **options):
        seen.update(messages=messages, options=options)
        return json.dumps(SPEC, ensure_ascii=False)
    monkeypatch.setattr(prompt_writer, 'chat_completion', completion)
    monkeypatch.delenv('OPENAI_PROMPT_REASONING_EFFORT', raising=False)
    text, spec, _ = asyncio.run(prompt_writer.write(PROJECT, AGENT, SURVEY, ANSWERS))
    assert seen['options']['operation'] == 'prompt_generation' and seen['options']['reasoning_effort'] == 'low'
    assert spec['requirements'] == [{'area': '회의록 AI', 'items': ['Azure OpenAI로 요약한다']}] and spec['open_questions'] == ['모델 버전']
    for part in ['# 회의록 작성 지원', '> 회의 녹음으로 보고용 회의록 초안을 만든다', '## 2. 첫 번째 목표\n\n녹음 1개 업로드',
                 '- [금지] Azure OpenAI 외 외부 서비스로 전송하지 않는다', '- [필수] 사내 서버에 저장한다', '- 요약: Azure OpenAI (사내 승인)',
                 '## 6. 이번 버전에서 하지 않을 것\n\n- 따로 정하지 않았습니다', '2. 빈 파일은 거부된다', 'AGENTS.md', 'CLAUDE.md']:
        assert part in text, part


def test_invalid_spec_is_repaired_once_then_reported(monkeypatch):
    replies = [json.dumps({**SPEC, 'goal': ' '}), json.dumps(SPEC)]

    async def completion(messages, schema, **options):
        return replies.pop(0)
    monkeypatch.setattr(prompt_writer, 'chat_completion', completion)
    assert asyncio.run(prompt_writer.write(PROJECT, AGENT, SURVEY, ANSWERS))[1]['goal']
    replies[:] = [json.dumps({**SPEC, 'acceptance': []})] * 2
    with pytest.raises(InvalidLLMResponse):
        asyncio.run(prompt_writer.write(PROJECT, AGENT, SURVEY, ANSWERS))
