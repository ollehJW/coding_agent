import { useEffect, useRef, useState } from 'react';
import { Bot, Loader2, Send, X } from 'lucide-react';

export function PromptDiff({ proposal, working, onDecision, error, readOnly = false }) {
  const firstChange = useRef(null);
  useEffect(() => { firstChange.current?.scrollIntoView({ block: 'nearest' }); }, [proposal.id]);
  const first = proposal.diff.findIndex(row => row.changed);
  return <div className="prompt-review" aria-label="프롬프트 수정안 비교">
    <div className="review-title"><span>변경 내용 미리보기</span><small>{readOnly ? '실제로 반영된 변경 내용입니다.' : '강조된 부분을 확인한 뒤 수정 여부를 선택하세요.'}</small></div>
    <div className="review-columns"><strong>수정 전 <span>− 삭제·변경</span></strong><strong>수정 후 <span>+ 추가·변경</span></strong></div>
    <div className="review-scroll" tabIndex={0}>
      {proposal.diff.map((row, index) => <div key={index} ref={index === first ? firstChange : undefined} className="review-row">
        {['before', 'after'].map(side => <div key={side} className={`review-cell ${side} ${row.changed && row[side] ? 'changed' : ''} ${!row[side] ? 'empty' : ''}`}>
          <span className="review-line-number" aria-hidden="true">{row[side]?.line || ''}</span>
          <pre>{row[side]?.parts.map((part, i) => part.changed ? <mark key={i}>{part.text || ' '}</mark> : <span key={i}>{part.text}</span>) || ' '}</pre>
        </div>)}
      </div>)}
    </div>
    {!readOnly && <div className="review-decision" role="dialog" aria-modal="false" aria-labelledby="review-decision-title" aria-busy={working}>
      <div><strong id="review-decision-title">이 수정안을 반영할까요?</strong><p>‘수정’을 누르면 프롬프트에 반영됩니다.</p>{error && <p className="error" role="alert">{error}</p>}</div>
      <div className="review-decision-actions"><button type="button" className="button" disabled={working} onClick={() => onDecision('reject')}>반려</button>
        <button type="button" className="button primary" disabled={working} onClick={() => onDecision('accept')}>{working && <Loader2 className="spin" size={15} />}수정</button></div>
    </div>}
  </div>;
}

export function AgentMessages({ turns, userLabel = '나' }) {
  return <>{turns.map(turn => <div className="edit-turn" key={turn.id}>
        <div className="edit-chat user"><span>{userLabel}</span><p>{turn.message}</p></div>
        {turn.reply && <div className={`edit-chat assistant ${turn.status === 'failed' ? 'failed' : ''}`}><span>Agent</span><p>{turn.reply}</p>
          {turn.status === 'proposed' && <small className="edit-chat-status">왼쪽에서 수정 전·후를 확인해주세요.</small>}</div>}
        {turn.decisionMessage && <><div className="edit-decision-label">{turn.status === 'accepted' ? '수정 승인' : turn.status === 'rejected' ? '수정 반려' : '수정안 만료'}</div>
          <div className="edit-chat assistant"><span>Agent</span><p>{turn.decisionMessage}</p></div></>}
      </div>)}</>;
}

export default function PromptAgent({ turns, working, loading, error, pending, onSend, onReload, onClose }) {
  const [message, setMessage] = useState('');
  const [optimistic, setOptimistic] = useState('');
  const bottom = useRef(null);
  const composer = useRef(null);
  useEffect(() => { bottom.current?.scrollIntoView({ block: 'nearest' }); }, [turns, working, optimistic]);
  useEffect(() => { if (!loading && !working && !pending) composer.current?.focus(); }, [loading, working, pending]);
  async function submit(event) {
    event.preventDefault();
    if (!message.trim() || working || pending || loading) return;
    const text = message.trim(); setOptimistic(text); setMessage('');
    try { await onSend(text); } catch { setMessage(text); }
    finally { setOptimistic(''); }
  }
  return <aside className="prompt-agent" aria-label="프롬프트 수정 Agent">
    <header className="prompt-agent-head"><span className="prompt-agent-symbol"><Bot size={20} /></span><div><strong>프롬프트 Agent</strong><small>대화로 함께 다듬어요</small></div>
      <button type="button" className="icon-action" aria-label="Agent 닫기" onClick={onClose} disabled={working}><X size={17} /></button></header>
    <div className="prompt-agent-messages" role="log" aria-label="Agent 대화" aria-live="polite">
      <div className="edit-chat assistant"><span>Agent</span><p>어떤 부분을 바꿀까요? 원하는 내용을 알려주시면 수정안을 보여드릴게요.</p></div>
      {loading && <p className="agent-loading"><Loader2 size={16} className="spin" />대화를 불러오고 있어요.</p>}
      <AgentMessages turns={turns} />
      {optimistic && !turns.some(turn => turn.message === optimistic && turn.status === 'generating') && <div className="edit-chat user"><span>나</span><p>{optimistic}</p></div>}
      {(working || turns.some(turn => turn.status === 'generating')) && <p className="agent-loading" role="status"><Loader2 className="spin" size={16} />{pending ? '선택을 반영하고 있어요.' : '프롬프트를 살펴보고 있어요.'}</p>}
      <div ref={bottom} />
    </div>
    {error && <div className="agent-error" role="alert">{error}<button type="button" className="text-button" onClick={onReload} disabled={working}>대화 다시 불러오기</button></div>}
    <form className="prompt-agent-compose" onSubmit={submit}>
      <label className="visually-hidden" htmlFor="prompt-agent-message">프롬프트 수정 요청</label>
      <textarea id="prompt-agent-message" ref={composer} value={message} maxLength={3000} rows={3} disabled={loading || working || pending}
        onChange={event => setMessage(event.target.value)} placeholder={pending ? '수정안을 수정 또는 반려해주세요.' : '수정할 내용을 요청해주세요.'}
        onKeyDown={event => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); event.currentTarget.form.requestSubmit(); } }} />
      <div><small>Enter 전송 · Shift+Enter 줄바꿈</small><button type="submit" className="button primary" aria-label="수정 요청 보내기" disabled={loading || working || pending || !message.trim()}><Send size={15} /></button></div>
    </form>
  </aside>;
}
