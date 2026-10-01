"""Shared, language-independent question and prompt content."""
import json
from pathlib import Path

CONTENT = json.loads((Path(__file__).resolve().parent.parent / 'shared/content.json').read_text())
UNKNOWN = CONTENT['unknown']
CONTEXT_STEPS = CONTENT['contextSteps']
LEGACY_TOPICS = CONTENT['legacySurveyTopics']  # Fixed topics of surveys saved before per-project topic plans.


def legacy_questions(project, answers=None):
    """Fixed per-type questions used before the adaptive survey; kept to migrate saved workspaces."""
    if not project:
        return []
    profile = CONTENT['profiles'][project['type']]
    selected = (answers or {}).get('rules', {}).get('selected', [])
    return [q for q in profile['questions'] if q['id'] != 'followup' or profile['followValue'] in selected]


def answer_text(answer):
    if not answer:
        return ''
    return '\n'.join(filter(None, [*answer['selected'], answer['custom'].strip()]))
