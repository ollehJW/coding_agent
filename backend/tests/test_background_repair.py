import asyncio
import copy
import json

import pytest

from backend import background_agent as agent
from backend.llm_client import InvalidLLMResponse


@pytest.mark.parametrize('recover', [True, False])
def test_invalid_evidence_repair_is_bounded_and_never_added_to_history(monkeypatch, recover):
    fact = '개인 보고서를 작성합니다.'
    categories = copy.deepcopy(agent.initial_agent()['categories'])
    categories['problem'].update(status='complete', summary=fact,
        evidence=[{'message_id': 'turn_0001', 'quote': fact}])
    valid = {'title': '개인 보고서', 'message': '어떤 점이 불편한가요?',
             'next_categories': ['current'], 'categories': categories}
    invalid = copy.deepcopy(valid)
    invalid['categories']['problem']['evidence'][0]['quote'] = '없는 내용'
    calls = []

    async def completion(messages, *args, **kwargs):
        calls.append(copy.deepcopy(messages))
        return json.dumps(valid if recover and len(calls) == 2 else invalid)

    monkeypatch.setattr(agent, 'chat_completion', completion)
    if recover:
        result = asyncio.run(agent.run_turn(agent.initial_agent(), fact, 'turn_0001'))
        assert len(result['messages']) == 3
        assert result['categories']['problem']['evidence'][0]['quote'] == fact
    else:
        with pytest.raises(InvalidLLMResponse):
            asyncio.run(agent.run_turn(agent.initial_agent(), fact, 'turn_0001'))
    assert len(calls) == 2
    assert 'evidence' in calls[1][-1]['content']
