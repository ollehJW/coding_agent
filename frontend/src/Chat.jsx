import { useEffect, useRef, useState } from 'react';
import { ArrowRight, ArrowUp, Check, LoaderCircle, Sparkles } from 'lucide-react';
import TaskDefinition, { limits } from './TaskDefinition.jsx';

const fieldLabels = { name: '과제 이름', background: '해결할 문제와 현재 업무 배경', users: '사용자와 업무 담당자', scope: '원하는 변화와 첫 과제 범위' };

const statuses = { missing: '확인 필요', partial: '보완 필요', complete: '정리 완료', not_applicable: '해당 없음', deferred: '추후 확인' };

// A turn can take from a few seconds up to the 150s server limit, so show that work is still going on.
function Thinking() {
  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 500);
    return () => clearInterval(timer);
  }, []);
  const step = elapsed < 3 ? '보내주신 내용을 읽고 있어요' : elapsed < 9 ? '업무 배경 항목을 정리하고 있어요' : elapsed < 25 ? '다음 질문을 준비하고 있어요' : '조금 더 걸리고 있어요. 창을 닫지 말고 기다려주세요';
  return <div className="chat-message assistant thinking" role="status" aria-live="polite">
    <span className="agent-emblem"><Sparkles size={16} /></span>
    <div className="chat-message-content"><span className="chat-message-name">WiaCoding</span>
      <div className="thinking-bubble"><span className="typing-dots" aria-hidden="true"><i /><i /><i /></span><span>{step}</span><small>{elapsed}초</small></div>
    </div>
  </div>;
}

export default function Chat({ agent, metadata, template, pendingMessage, chatError, context, draft, setDraft, onSend, onConfirm, canResume, onResume }) {
  const [input, setInput] = useState('');
  const [invalid, setInvalid] = useState(null);
  const complete = agent ? agent.ready : Object.keys(context).length === 5;
  const messages = agent?.messages || [
    { id: 'intro', role: 'assistant', content: metadata.introduction },
    ...Object.entries(context).map(([id, content]) => ({ id, role: 'user', content })),
  ];
  const categories = metadata.categories;
  const collected = agent?.categories || {};
  const settled = categories.filter(category => ['complete', 'not_applicable', 'deferred'].includes(collected[category.id]?.status)).length;
  const log = useRef(null);
  const proposal = useRef(null);
  const textarea = useRef(null);
  useEffect(() => { if (log.current) log.current.scrollTop = log.current.scrollHeight; }, [messages.length, pendingMessage]);
  useEffect(() => { if (complete) proposal.current?.scrollIntoView({ block: 'start', behavior: 'smooth' }); }, [complete]);
  function confirm(event) {
    event.preventDefault();
    const key = Object.keys(fieldLabels).find(field => !draft[field].trim() || draft[field].length > limits[field]);
    setInvalid(key || null);
    if (key) { proposal.current.querySelector(`[data-field="${key}"]`)?.focus(); return; }
    onConfirm(event);
  }
  async function submit(event) {
    event.preventDefault();
    if (!input.trim()) { textarea.current.setCustomValidity('업무 문제나 답변을 적어주세요.'); textarea.current.reportValidity(); return; }
    const value = input;
    setInput('');  // The message moves into the conversation right away; it comes back if sending fails.
    if (!await onSend(value)) setInput(current => current || value);
    requestAnimationFrame(() => textarea.current?.focus({ preventScroll: true }));
  }
  return <section className={`panel chat-panel ${complete ? 'definition-ready' : ''}`} aria-labelledby="chat-title">
    <div className="chat-header"><span className="agent-emblem"><Sparkles size={21} /></span><div><h2 id="chat-title">먼저, 업무의 배경부터 알아볼게요.</h2><p>필요한 배경은 하나씩 확인하고, 과제에 해당하지 않는 항목은 이유와 함께 정리합니다.</p></div><span className={`chat-label ${pendingMessage ? 'working' : complete ? 'complete' : ''}`}>{pendingMessage ? '답변 작성 중' : complete ? (agent?.deferred.length ? '확인 사항 검토' : '배경 정리 완료') : '배경 파악 중'}</span></div>
    <div className="context-checklist" aria-label="배경 정보 수집 현황">{categories.map(category => {
      const item = collected[category.id]; const status = item?.status || 'missing';
      return <span key={category.id} className={`context-status status-${status} ${status === 'complete' ? 'collected' : ''}`} title={`${statuses[status]}${item?.reason ? ': ' + item.reason : ''}`} aria-label={`${category.label}: ${statuses[status]}`}>{status === 'complete' ? <Check size={13} /> : <i />}{category.label}{status === 'not_applicable' && ' · 제외'}{status === 'deferred' && ' · 추후 확인'}</span>;
    })}</div>
    <p className="context-example-note">{settled} / {categories.length}개 항목 검토 · 질문에 자유롭게 답해주세요. 모르는 내용은 그대로 말씀해주셔도 괜찮아요.</p>
    <div className="chat-messages" ref={log} role="log" aria-label="과제 정의 대화" aria-live="polite">
      {messages.map(message => <div className={`chat-message ${message.role}`} key={message.id}>{message.role === 'assistant' && <span className="agent-emblem"><Sparkles size={16} /></span>}<div className="chat-message-content"><span className={message.role === 'user' ? 'visually-hidden' : 'chat-message-name'}>{message.role === 'user' ? '나' : 'WiaCoding'}</span><p>{message.content}</p></div></div>)}
      {pendingMessage && <><div className="chat-message user"><div className="chat-message-content"><span className="visually-hidden">나</span><p>{pendingMessage}</p></div></div><Thinking /></>}
    </div>
    <form className="chat-form" onSubmit={submit}><label className="visually-hidden" htmlFor="chat-input">업무 문제 또는 답변</label><div className="chat-composer"><textarea ref={textarea} id="chat-input" rows={2} maxLength={3000} required value={input} placeholder={pendingMessage ? 'WiaCoding이 답변을 작성하고 있어요. 답변이 오면 이어서 입력할 수 있어요.' : complete ? '정리한 내용에 수정하거나 더 이야기할 부분이 있나요?' : '현재 업무와 불편한 점, 또는 질문에 대한 답변을 적어주세요.'} onChange={event => { setInput(event.target.value); event.target.setCustomValidity(''); }} onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) { event.preventDefault(); event.currentTarget.form.requestSubmit(); } }} /><button className="button primary" type="submit" disabled={Boolean(pendingMessage)} aria-label={pendingMessage ? '답변 작성 중' : '메시지 보내기'}>{pendingMessage ? <LoaderCircle size={20} className="spin" /> : <ArrowUp size={20} />}</button></div><div className="composer-note"><span>Enter로 전송 · Shift + Enter로 줄바꿈</span><span>대화와 수집 내용은 자동으로 저장됩니다</span></div>{chatError && <p className="error" role="alert">{chatError} 입력한 내용은 유지됩니다.</p>}</form>
    {complete && Boolean(agent?.deferred.length) && <div className="background-caution" role="status">아직 확인이 필요한 항목이 있습니다: {categories.filter(category => agent.deferred.includes(category.id)).map(category => category.label).join(', ')}. 과제 초안에도 확인 필요 사항으로 남겨두었습니다.</div>}
    {complete && <form className="task-proposal" ref={proposal} onSubmit={confirm} noValidate aria-labelledby="task-definition-title"><div className="definition-heading"><span className="agent-emblem"><Check size={20} /></span><div><span className="eyebrow">READY TO DEFINE</span><h3 id="task-definition-title">이 과제로 시작해보면 어떨까요?</h3><p>대화로 정리한 과제 정의서예요. 내용을 눌러 바로 고치고, 항목마다 발언 근거를 확인한 뒤 확정해주세요.</p></div></div><TaskDefinition html={template} draft={draft} setDraft={value => { setInvalid(null); setDraft(value); }} categories={categories} collected={collected} invalid={invalid} />
      {invalid && <p className="error" role="alert">{fieldLabels[invalid]}: {draft[invalid].trim() ? `${limits[invalid].toLocaleString()}자 이하로 줄여주세요.` : '내용을 입력해주세요.'}</p>}
      <div className="definition-confirm"><span>확정한 과제를 바탕으로 프롬프트 메이킹을 시작합니다.</span><button className="button primary" type="submit">과제 확정 · 프롬프트 메이킹<ArrowRight size={17} /></button></div>{canResume && <button className="text-button resume-button" type="button" onClick={onResume}>기존 서베이 이어가기 →</button>}</form>}
  </section>;
}
