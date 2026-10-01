// Task definition shown as an editable HTML document (backend/templates/task_definition.html).
import { memo, useEffect, useRef, useState } from 'react';
import { Check, Quote, X } from 'lucide-react';

export const limits = { name: 80, background: 6000, users: 3000, scope: 3000 };
const statuses = { missing: '확인 필요', partial: '보완 필요', complete: '정리 완료', not_applicable: '해당 없음', deferred: '추후 확인' };

// The template is trusted markup from our own backend; it is mounted once so React never rewrites what the user is typing.
const Template = memo(function Template({ html }) { return <div dangerouslySetInnerHTML={{ __html: html }} />; });

// 'plaintext-only' keeps typed input as plain text; older browsers reject it, so fall back to 'true'.
const editable = (() => {
  try { const probe = document.createElement('div'); probe.contentEditable = 'plaintext-only'; return probe.contentEditable; } catch { return 'true'; }
})();

function read(element) {
  return element.innerText.replace(/\n$/, '');
}

function EvidenceDialog({ keys, categories, collected, onClose }) {
  const dialog = useRef(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  const shown = categories.filter(category => keys.includes(category.id));
  return <dialog ref={dialog} className="evidence-dialog" aria-labelledby="evidence-title" onClose={onClose} onClick={event => { if (event.target === dialog.current) dialog.current.close(); }}>
    <div className="evidence-head"><span className="evidence-icon"><Quote size={18} /></span><div><h3 id="evidence-title">발언 근거</h3><p>대화에서 수집한 배경과, 그렇게 정리한 근거가 된 내 발언이에요.</p></div>
      <button type="button" className="icon-button evidence-close" aria-label="닫기" onClick={() => dialog.current.close()}><X size={18} /></button></div>
    <div className="evidence-list">{shown.map(category => {
      const item = collected[category.id] || { status: 'missing', summary: '', reason: '', evidence: [] };
      return <section key={category.id} className={`evidence-item status-${item.status}`}>
        <div className="evidence-item-head"><h4>{category.label}</h4><span className="evidence-status">{item.status === 'complete' && <Check size={12} />}{statuses[item.status]}</span></div>
        <p className="evidence-summary">{item.summary || '아직 대화에서 확인하지 않았어요.'}</p>
        {item.reason && <p className="evidence-reason">{item.reason}</p>}
        {item.evidence.length > 0 ? <ul className="evidence-quotes">{item.evidence.map((evidence, index) => <li key={index}><blockquote>{evidence.quote}</blockquote></li>)}</ul>
          : <p className="evidence-empty">연결된 발언이 없어요.</p>}
      </section>;
    })}</div>
  </dialog>;
}

export default function TaskDefinition({ html, draft, setDraft, categories, collected, invalid, readOnly = false }) {
  const root = useRef(null);
  const [evidence, setEvidence] = useState(null);
  useEffect(() => {
    // Push outside changes (a new draft from the agent) into fields that are not being edited.
    for (const element of root.current.querySelectorAll('[data-field]')) {
      const key = element.dataset.field;
      if (element !== document.activeElement && read(element) !== draft[key]) element.textContent = draft[key];
      const mode = readOnly ? 'false' : editable;
      if (element.contentEditable !== mode) element.contentEditable = mode;
      if (readOnly) element.setAttribute('aria-readonly', 'true');
      else element.removeAttribute('aria-readonly');
      element.setAttribute('aria-invalid', invalid === key ? 'true' : 'false');
    }
    for (const count of root.current.querySelectorAll('[data-count]')) {
      const key = count.dataset.count;
      count.textContent = `${draft[key].length.toLocaleString()} / ${limits[key].toLocaleString()}자`;
      count.classList.toggle('over', draft[key].length > limits[key]);
    }
  }, [draft, invalid, html, readOnly]);
  function input(event) {
    const element = event.target.closest('[data-field]');
    if (!element) return;
    const value = read(element);
    if (!value.trim() && element.innerHTML !== '') element.textContent = '';  // Keep :empty so the placeholder returns.
    setDraft(previous => ({ ...previous, [element.dataset.field]: value.trim() ? value : '' }));
  }
  function paste(event) {
    if (!event.target.closest('[data-field]')) return;
    event.preventDefault();  // Only plain text goes into the document.
    const text = event.clipboardData.getData('text/plain');
    const single = event.target.closest('[data-single]');
    document.execCommand('insertText', false, single ? text.replace(/\s*\n\s*/g, ' ') : text);
  }
  function keyDown(event) {
    if (event.key === 'Enter' && event.target.closest('[data-single]')) event.preventDefault();
  }
  function click(event) {
    const button = event.target.closest('[data-evidence]');
    if (button) setEvidence(button.dataset.evidence.split(','));
  }
  if (readOnly) return <div ref={root} className="task-definition read-only"><Template html={html} /></div>;
  return <div ref={root} className="task-definition" onInput={input} onPaste={paste} onKeyDown={keyDown} onClick={click}>
    <Template html={html} />
    {evidence && <EvidenceDialog keys={evidence} categories={categories} collected={collected} onClose={() => setEvidence(null)} />}
  </div>;
}
