import content from './content.json' with { type: 'json' };
const UNKNOWN = content.unknown;
const contextSteps = content.contextSteps;
function answerText(answer) { return answer ? [...answer.selected, answer.custom.trim()].filter(Boolean).join('\n') : ''; }
// Must match survey.basis in the backend: the answers a generated question was based on.
function answerBasis(questions, answers, position) {
  return JSON.stringify(questions.slice(0, position).map(q => [answers[q.id]?.selected ?? [], answers[q.id]?.custom ?? '']));
}
export { UNKNOWN, contextSteps, answerText, answerBasis };
