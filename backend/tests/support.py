import json

from backend import prompt_writer
from backend.auth import create_user

PASSWORD = 'Passw0rd!'


def sign_in(client, employee_id='1234567', name='테스터', must_change=False):
    """Create an account in the app's database and log the test client in."""
    with client.app.state.database.connect() as db:
        if not db.execute('SELECT 1 FROM users WHERE employee_id=?', (employee_id,)).fetchone():
            create_user(db, employee_id, name, PASSWORD, must_change=must_change)
    response = client.post('/api/auth/login', json={'employee_id': employee_id, 'password': PASSWORD})
    assert response.status_code == 200, response.text
    if not must_change:  # Work in the account's first prompt, as a returning user would.
        prompts = client.get('/api/prompts').json()['prompts']
        client.prompt_id = prompts[0]['promptId'] if prompts else client.post('/api/prompts', json={}).json()['promptId']
    return response.json()


def url(client, suffix=''):
    return f'/api/prompts/{client.prompt_id}{suffix}'



def fake_writer(monkeypatch):
    """Deterministic stand-in for the prompt-writing model; returns the requests it received."""
    calls = []

    async def completion(messages, schema, **options):
        data = json.loads(messages[-1]['content'])
        calls.append(data)
        return json.dumps({'goal': data['project']['name'] + ' 도구', 'context': data['project']['background'] or '배경',
                           'first_milestone': '핵심 흐름을 끝까지 동작', 'constraints': [], 'tech_stack': [], 'out_of_scope': [],
                           'requirements': [{'area': a['area'], 'items': [f"{a['decision']}: {', '.join(a['selected'] + ([a['custom']] if a['custom'] else []))}"]}
                                            for a in data['answered']],
                           'open_questions': data['unresolved_topics'], 'acceptance': ['정상 흐름 확인', '빈 입력 확인', '잘못된 값 확인']},
                          ensure_ascii=False)
    monkeypatch.setattr(prompt_writer, 'chat_completion', completion)
    return calls
