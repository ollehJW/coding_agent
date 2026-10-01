import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, ArrowRight, Check, RotateCcw, Sparkles } from 'lucide-react';
import { answerText } from './content.js';

const generationSteps = {
  first: ['과제 정의 읽기', '이 과제에서 확인할 항목 정하기', '첫 질문과 선택지 만들기'],
  next: ['방금 답변 반영하기', '다음으로 확인할 내용 고르기', '질문과 선택지 만들기'],
  prompt: ['답변과 과제 정의 모으기', '중복·모순 정리하기', '개발 요청 프롬프트 쓰기'],
};
const headlines = { first: '과제에 맞는 첫 질문을 만들고 있어요', next: '답변에 맞춰 다음 질문을 만들고 있어요', prompt: '답변을 정리해 개발 프롬프트를 쓰고 있어요' };
const expectedSeconds = { first: 9, next: 5, prompt: 25 };  // The first call also plans the topics; the prompt is the longest answer.

// Model latency is unknown up front, so the bar eases toward 95% and only completes when the question arrives.
function GenerationProgress({ mode }) {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const started = performance.now();
    const timer = setInterval(() => setElapsed((performance.now() - started) / 1000), 200);
    return () => clearInterval(timer);
  }, [mode]);
  const steps = generationSteps[mode];
  const expected = expectedSeconds[mode];
  const percent = Math.round(95 * (1 - Math.exp(-elapsed / (expected * 0.7))));
  const active = elapsed < expected * 0.25 ? 0 : elapsed < expected * 0.6 ? 1 : 2;
  if (elapsed < 0.25) return <div className="survey-generating pending" aria-busy="true" />;  // Avoid flashing when the question was prefetched.
  return <div className="survey-generating" role="status" aria-live="polite">
    <div className="generating-head"><Sparkles size={18} /><div><strong>{headlines[mode]}</strong><small>보통 {expected}초 안팎 걸려요 · {Math.floor(elapsed)}초</small></div></div>
    <div className="generating-bar" role="progressbar" aria-label="다음 질문 생성 진행률" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}><span style={{ width: `${percent}%` }} /></div>
    <ol className="generating-steps">{steps.map((step, i) => <li key={step} className={i < active ? 'done' : i === active ? 'active' : ''}>{i < active ? <Check size={13} /> : <i />}{step}</li>)}</ol>
  </div>;
}

export default function Survey({ project, survey, answers, index, setIndex, onChange, onBack, onNext, onFinish, onRetry, generating, error: generationError, complete, canFinish }) {
  const [error, setError] = useState(false);
  const heading = useRef(null);
  const custom = useRef(null);
  const list = survey.questions;
  const question = generating ? null : list[index];
  const answer = (question && answers[question.id]) || { selected: [], custom: '' };
  const topics = survey.topics;
  const covered = new Set(list.filter(item => answerText(answers[item.id])).map(item => item.topic));
  // Each question carries the model's topic evaluation made before it was asked; surveys saved before that fall back to coverage.
  const evaluation = (question || list[list.length - 1])?.status;
  const stateOf = topic => evaluation?.[topic.id]?.status || (covered.has(topic.id) ? 'sufficient' : 'unasked');
  const settled = topics.filter(topic => stateOf(topic) === 'sufficient').length;
  const pending = topics.filter(topic => stateOf(topic) === 'needs_detail').length;
  const progress = complete ? 100 : topics.length ? Math.round(settled / topics.length * 90) : 0;
  const chipNote = { sufficient: ' 확인 완료', needs_detail: ' 세부 확인 필요', unasked: ' 아직 확인 전' };
  useEffect(() => { setError(false); if (question) { heading.current?.focus({ preventScroll: true }); window.scrollTo({ top: 0 }); } }, [question?.id]);
  function change(patch) { onChange(question.id, { ...answer, ...patch }); setError(false); }
  function valid() {
    if (answerText(answer)) return true;
    setError(true); custom.current.focus(); return false;
  }
  function submit(event) {
    event.preventDefault();
    if (valid()) onNext();
  }
  const number = generating === 'first' ? 1 : generating === 'next' ? index + 2 : index + 1;
  return <section className="panel focus-survey" aria-labelledby="question-title">
    <div className="survey-topline"><div><span className="eyebrow">PROMPT MAKING</span><span className="survey-task">{project.name}</span></div><button className="text-button" onClick={onBack}><ArrowLeft size={14} />과제 정의로 돌아가기</button></div>
    <div className="focus-progress"><span>QUESTION {String(number).padStart(2, '0')}</span><div role="progressbar" aria-label="확인 항목 진행률" aria-valuemin={0} aria-valuemax={100} aria-valuenow={progress}><span style={{ width: `${progress}%` }} /></div><span>확인 완료 {settled}/{topics.length}{pending > 0 && ` · 세부 확인 ${pending}`}</span></div>
    {topics.length > 0 && <ul className="topic-chips" aria-label="이 과제에서 확인할 항목">{topics.map(topic => { const state = stateOf(topic); const reason = evaluation?.[topic.id]?.reason;
      return <li key={topic.id} title={reason ? `${topic.description}\n부족한 부분: ${reason}` : topic.description} className={`${state} ${question?.topic === topic.id ? 'current' : ''}`}>{state === 'sufficient' && <Check size={12} />}{state === 'needs_detail' && <i className="chip-dot" />}{topic.label}<span className="visually-hidden">{chipNote[state]}{question?.topic === topic.id ? ', 지금 질문' : ''}</span></li>; })}</ul>}
    {generating ? <GenerationProgress mode={generating} /> : !question ? <div className="survey-generating">
      <p className="error" role="alert">{generationError || '질문을 불러오지 못했습니다.'}</p>
      <div className="focus-actions"><button type="button" className="button" onClick={onBack}><ArrowLeft size={15} />과제 정의로</button><span /><button type="button" className="button primary" onClick={onRetry}><RotateCcw size={15} />다시 시도</button></div>
    </div> : <form onSubmit={submit}><div className="question-heading"><span className="category-label">{question.label} · {question.multi ? '복수 선택' : '하나 선택'}</span><h2 id="question-title" ref={heading} tabIndex={-1}>{question.title}</h2><p>{question.help}</p></div>
      <fieldset className="answer-cards"><legend className="visually-hidden">{question.title}</legend>{question.cards.map((card, i) => <label className={`answer-card ${i === 0 ? 'recommended' : ''}`} key={card.title}><span className="answer-card-top"><span className="answer-letter">{String.fromCharCode(65 + i)}</span>{i === 0 && <span className="answer-recommended">시작점 추천</span>}<input aria-label={card.title} type={question.multi ? 'checkbox' : 'radio'} name={question.id} checked={answer.selected.includes(card.title)} onChange={event => change({ custom: '', selected: question.multi ? event.target.checked ? [...answer.selected, card.title] : answer.selected.filter(value => value !== card.title) : [card.title] })} /></span><strong className="answer-card-title">{card.title}</strong><span className="answer-card-description">{card.description}</span><span className="answer-card-reason"><Sparkles size={14} /><span><strong>추천 이유</strong> {card.reason}</span></span></label>)}</fieldset>
      <div className={`custom-answer-box ${answer.custom.trim() ? 'active' : ''}`}><div className="custom-heading"><label htmlFor="custom-answer">Custom Answer <span>카드에 맞는 답이 없으면 직접 입력</span></label></div><textarea id="custom-answer" ref={custom} rows={2} maxLength={3000} value={answer.custom} aria-invalid={error || undefined} aria-describedby={error ? 'survey-error' : 'custom-hint'} placeholder="카드에 없는 답변을 적어주세요. 적어주신 내용에 맞춰 다음 질문이 달라져요." onFocus={() => { if (answer.selected.length) change({ selected: [] }); }} onChange={event => change({ custom: event.target.value, selected: [] })} /><span id="custom-hint" className="custom-hint">여기를 누르면 위에서 고른 카드는 해제되고, 카드를 고르면 입력한 내용은 지워져요.</span></div>
      {(error || generationError) && <p id="survey-error" className="error" role="alert">{error ? '카드를 선택하거나 Custom Answer에 답변을 적어주세요.' : generationError}</p>}
      <div className="focus-actions"><button type="button" className="button" onClick={() => index === 0 ? onBack() : setIndex(index - 1)}><ArrowLeft size={15} />{index === 0 ? '과제 정의로' : '이전 질문'}</button>{canFinish && !complete ? <button type="button" className="text-button" onClick={() => valid() && onFinish()}>여기까지 답하고 프롬프트 만들기</button> : <span>답변에 맞춰 다음 질문이 만들어져요.</span>}<button className="button primary" type="submit">{complete ? '개발 프롬프트 완성하기' : '다음 질문'}<ArrowRight size={16} /></button></div>
    </form>}
  </section>;
}
