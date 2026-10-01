// The finished work: the prompt, the task definition and the survey flow in tabs, then what to do next.
import { useEffect, useRef, useState } from 'react';
import { Bot, Check, ClipboardCopy, Copy, Download, Loader2, Pencil, Rocket, SquareTerminal } from 'lucide-react';
import PromptLines from './PromptLines.jsx';
import PromptAgent, { PromptDiff } from './PromptAgent.jsx';
import { request } from './api.js';
import { SurveyFlow } from './SurveyHistory.jsx';
import TaskDefinition from './TaskDefinition.jsx';
import { fileName, savePdf } from './pdf.js';

const tabs = [['prompt', 'Prompt'], ['definition', '과제 정의서'], ['history', 'Survey History']];

function IconButton({ label, onClick, children, pressed, busy, disabled }) {
  return <button type="button" className={`icon-action ${pressed ? 'on' : ''}`} onClick={onClick} aria-label={label} title={label}
    aria-pressed={pressed} disabled={busy || disabled}>{busy ? <Loader2 size={18} className="spin" /> : children}</button>;
}

function NextSteps() {
  const steps = [
    { icon: <ClipboardCopy size={20} />, title: '프롬프트 복사', text: 'Prompt 탭에서 개발 프롬프트를 복사해요.' },
    { icon: <SquareTerminal size={20} />, title: '바이브코딩 도구에 붙여 넣기', text: 'Codex, Claude Code 같은 도구에 붙여 넣어요. AGENTS.md나 CLAUDE.md로 저장해 두면 다음에도 이어서 쓸 수 있어요.' },
    { icon: <Rocket size={20} />, title: '첫 화면부터 함께 만들기', text: '에이전트가 보여주는 계획을 확인하고, 첫 번째 목표부터 하나씩 함께 만들어요.' },
  ];
  return <section className="next-steps" aria-labelledby="next-steps-title">
    <h3 id="next-steps-title">다음은 이렇게 해보세요</h3>
    <ol>{steps.map((step, index) => <li key={step.title} className="next-step">
      <div className="next-step-marker"><span className="next-step-icon">{step.icon}</span><span className="next-step-number">{String(index + 1).padStart(2, '0')}</span></div>
      <strong>{step.title}</strong><p>{step.text}</p>
    </li>)}</ol>
  </section>;
}

export default function ResultView({ promptId, onAgentLoad, onAgentSend, onAgentDecision, project, survey, answers, template, documentText, manualEdited, confirmed, onConfirm, onEditText, editing, setEditing, editor, onCopy, onDownload, notify }) {
  const [tab, setTab] = useState('prompt');
  const [saving, setSaving] = useState(false);
  const [agentOpen, setAgentOpen] = useState(false);
  const [turns, setTurns] = useState([]);
  const [agentLoading, setAgentLoading] = useState(false);
  const [agentWorking, setAgentWorking] = useState(false);
  const [agentError, setAgentError] = useState('');
  const retryMessage = useRef(null);
  const pending = !confirmed && turns.find(turn => turn.status === 'proposed');
  const generating = turns.some(turn => turn.status === 'generating');
  const agentLocked = agentLoading || agentWorking || generating || Boolean(pending);
  async function loadAgent() {
    setAgentLoading(true); setAgentError('');
    try { setTurns((await onAgentLoad()).turns); }
    catch (error) { setAgentError(error.message); }
    finally { setAgentLoading(false); }
  }
  async function toggleAgent() {
    if (agentOpen) { setAgentOpen(false); return; }
    setEditing(false); setAgentOpen(true); await loadAgent();
  }
  async function sendAgent(message) {
    setAgentWorking(true); setAgentError('');
    retryMessage.current = retryMessage.current?.message === message ? retryMessage.current : { message, id: crypto.randomUUID() };
    try { setTurns((await onAgentSend(message, retryMessage.current.id)).turns); retryMessage.current = null; }
    catch (error) {
      setAgentError(error.message);
      // Recover the persisted turn when a response is lost or the model call fails.
      try { const data = await request(`/prompts/${promptId}/editor`); setTurns(data.turns);
        if (data.turns.some(turn => turn.id === retryMessage.current?.id && turn.status === 'failed')) retryMessage.current = null;
      } catch { /* Keep the request id so a network retry cannot duplicate the turn. */ }
      throw error;
    } finally { setAgentWorking(false); }
  }
  async function decideAgent(decision) {
    if (!pending || agentWorking) return;
    setAgentWorking(true); setAgentError('');
    try { setTurns((await onAgentDecision(pending.id, decision)).turns); }
    catch (error) { setAgentError(error.message); }
    finally { setAgentWorking(false); }
  }
  useEffect(() => {
    if (!generating || agentWorking) return;
    let active = true;
    const timer = setTimeout(() => request(`/prompts/${promptId}/editor`).then(data => { if (active) setTurns(data.turns); })
      .catch(error => { if (active) setAgentError(error.message); }), 2000);
    return () => { active = false; clearTimeout(timer); };
  }, [generating, turns, agentWorking, promptId]);

  const definition = useRef(null);
  const history = useRef(null);
  useEffect(() => { if (tab === 'prompt' && editing) editor.current?.focus(); }, [tab, editing, editor]);
  function copyPrompt() { setTab('prompt'); onCopy(); }
  async function pdf(element, suffix) {
    if (saving || !element) return;
    setSaving(true);
    try { await savePdf(element, fileName(project.name, suffix, 'pdf')); notify(`${suffix} PDF를 다운로드합니다.`); }
    catch { notify('PDF를 만들지 못했어요. 다시 시도해주세요.'); }
    finally { setSaving(false); }
  }
  function keyDown(event) {
    const index = tabs.findIndex(([key]) => key === tab);
    const next = { ArrowRight: index + 1, ArrowLeft: index - 1, Home: 0, End: tabs.length - 1 }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    const key = tabs[(next + tabs.length) % tabs.length][0];
    setTab(key); document.getElementById(`result-tab-${key}`).focus();
  }
  return <section aria-label="개발 프롬프트 결과">
    {confirmed && <>
      <div className="result-heading"><div><span className="eyebrow">YOUR DEVELOPMENT PROMPT</span><h2 id="result-title">이제 첫 개발 요청을 시작할 수 있어요.</h2>
        <p>대화로 정한 과제와 설문 답변을 정리했어요. 이 개발 프롬프트가 나의 개발 정의서입니다.</p></div></div>
      <NextSteps />
    </>}
    <div className="panel result-panel">
      <div className="result-tabbar">
        <div className="result-tabs" role="tablist" aria-label="결과 보기" onKeyDown={keyDown}>{tabs.map(([key, label]) =>
          <button key={key} id={`result-tab-${key}`} type="button" role="tab" aria-selected={tab === key} aria-controls={`result-panel-${key}`}
            tabIndex={tab === key ? 0 : -1} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>)}</div>
        <div className="result-actions">
          {tab === 'prompt' && <>
            {manualEdited && <span className="result-note">직접 수정한 내용이 복사·다운로드에 반영돼요</span>}
            <IconButton label="다운로드 (.md)" onClick={onDownload}><Download size={18} /></IconButton>
            <IconButton label="복사" onClick={copyPrompt}><Copy size={17} /></IconButton>
            <IconButton label={editing ? '수정 완료' : '직접 수정'} pressed={editing} disabled={agentLocked} onClick={() => setEditing(!editing)}>{editing ? <Check size={18} /> : <Pencil size={17} />}</IconButton>
            {!confirmed && <IconButton label="Agent로 프롬프트 수정" pressed={agentOpen} disabled={agentWorking || agentLoading} onClick={toggleAgent}><Bot size={19} /></IconButton>}
          </>}
          {tab === 'definition' && <IconButton label="PDF로 다운로드" busy={saving} onClick={() => pdf(definition.current, '과제정의서')}><Download size={18} /></IconButton>}
          {tab === 'history' && <IconButton label="PDF로 다운로드" busy={saving} onClick={() => pdf(history.current, 'SurveyHistory')}><Download size={18} /></IconButton>}
        </div>
      </div>
      <div className={`result-workspace ${tab === 'prompt' && agentOpen && !confirmed ? 'with-agent' : ''}`}>
      <div id={`result-panel-${tab}`} role="tabpanel" aria-labelledby={`result-tab-${tab}`} tabIndex={0} className="result-body">
        {tab === 'prompt' && (pending ? <PromptDiff proposal={pending} working={agentWorking} onDecision={decideAgent} error={agentError} /> : editing
          ? <textarea id="document-editor" ref={editor} aria-label="개발 프롬프트 직접 수정" spellCheck={false} value={documentText} onChange={event => onEditText(event.target.value)} />
          : <article id="document-preview" className="prompt-lines" tabIndex={0}><PromptLines text={documentText} /></article>)}
        {tab === 'definition' && <div ref={definition} className="result-definition">
          <TaskDefinition html={template} draft={project} readOnly /></div>}
        {tab === 'history' && <div ref={history} className="result-history">
          <SurveyFlow survey={survey} answers={answers} showLegend={false} /></div>}
      </div>
      {tab === 'prompt' && agentOpen && !confirmed && <PromptAgent turns={turns} loading={agentLoading} working={agentWorking || generating}
        error={agentError} pending={Boolean(pending)} onSend={sendAgent} onReload={loadAgent} onClose={() => setAgentOpen(false)} />}
      </div>
    </div>
    {!confirmed && <div className="result-confirm">
      <button type="button" className="button primary" disabled={agentLocked} onClick={onConfirm}><Check size={16} />확정</button>
    </div>}
  </section>;
}
