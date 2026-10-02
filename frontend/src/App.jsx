import { PlatformReturnLink, PlatformHomeLink } from './PlatformNavigation.jsx';
import { useEffect, useRef, useState } from 'react';
import { ArrowLeft, Check, CheckCircle2, UserRound, CodeXml, FileText, FolderHeart, LogOut, Users } from 'lucide-react';
import { answerBasis, answerText, contextSteps } from './content.js';
import Chat from './Chat.jsx';
import { request, createWorkspaceClient } from './api.js';
import Survey from './Survey.jsx';
import SharedPrompts from './SharedPrompts.jsx';
import PromptHome from './PromptHome.jsx';
import ResultView from './ResultView.jsx';
import { fileName } from './pdf.js';
import { listItem } from './promptList.js';

const steps = [['과제 정의', '대화로 해결할 문제 찾기'], ['프롬프트 메이킹', '내 과제에 맞는 질문에 답하기'], ['개발 프롬프트', '복사하고 개발 시작하기']];
const emptyDraft = { name: '', background: '', users: '', scope: '' };
const emptySurvey = { signature: '', topics: [], questions: [], done: false, doneBasis: '' };

export default function App({ user, onLogout }) {
  const [agent, setAgent] = useState(null);
  const [agentMetadata, setAgentMetadata] = useState({ categories: [], introduction: '' });
  const [pendingMessage, setPendingMessage] = useState('');
  const [chatError, setChatError] = useState('');
  const [view, setView] = useState('home');
  const [updatedAt, setUpdatedAt] = useState('');
  const [stage, setStage] = useState(1);
  const [context, setContext] = useState({});
  const [draft, setDraft] = useState(emptyDraft);
  const [project, setProject] = useState(null);
  const [answers, setAnswers] = useState({});
  const [survey, setSurvey] = useState(emptySurvey);
  const [generating, setGenerating] = useState('');
  const [surveyError, setSurveyError] = useState('');
  const [questionIndex, setQuestionIndex] = useState(0);
  const [documentText, setDocumentText] = useState('');
  const [manualEdited, setManualEdited] = useState(false);
  const [editing, setEditing] = useState(false);
  const [confirmed, setConfirmed] = useState(false);
  const [personalWorkspace, setPersonalWorkspace] = useState(false);
  const [toast, setToast] = useState('');
  const [template, setTemplate] = useState('');
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [apiError, setApiError] = useState('');
  const client = useRef(null);
  const [promptId, setPromptId] = useState(null);
  const [prompts, setPrompts] = useState([]);
  const startup = useRef(null);
  const saveTimer = useRef(null);
  const saved = useRef('');
  const snapshot = { context, draft, project, answers, survey, questionIndex, stage, documentText, manualEdited };
  const serialized = JSON.stringify(snapshot);
  const latest = useRef(serialized);
  latest.current = serialized;
  function applyState(state) {
    setContext(state.context); setDraft(state.draft); setProject(state.project);
    setAnswers(state.answers); setSurvey(state.survey); setQuestionIndex(state.questionIndex); setStage(state.stage);
    setDocumentText(state.documentText); setManualEdited(state.manualEdited);
  }
  useEffect(() => {
    let cancelled = false;
    startup.current ??= Promise.all([request('/prompts'), request('/background'), request('/templates/task-definition')]);
    startup.current.then(([list, metadata, definition]) => {
      if (cancelled) return;
      setPrompts(list.prompts); setTemplate(definition.html); setAgentMetadata(metadata); setReady(true);
    }).catch(error => { if (!cancelled) setApiError(error.message); });
    return () => { cancelled = true; };
  }, []);
  async function persist(value) {
    try {
      const data = await client.current.write(JSON.parse(value));
      saved.current = value; setUpdatedAt(data.updatedAt);
      if (latest.current === value) { setApiError(''); setConfirmed(Boolean(data.confirmed)); }
    } catch (error) { setApiError(error.message); }
  }
  useEffect(() => {
    if (!ready || !promptId || busy || serialized === saved.current) return;
    saveTimer.current = setTimeout(() => persist(serialized), 350);
    return () => clearTimeout(saveTimer.current);
  }, [serialized, ready, promptId, busy]);
  useEffect(() => {
    function warn(event) { if (ready && latest.current !== saved.current) { event.preventDefault(); event.returnValue = ''; } }
    window.addEventListener('beforeunload', warn);
    return () => window.removeEventListener('beforeunload', warn);
  }, [ready]);
  const editor = useRef(null);
  const toastTimer = useRef();
  useEffect(() => () => clearTimeout(toastTimer.current), []);
  useEffect(() => { window.scrollTo({ top: 0 }); }, [view, stage]);
  function notify(message) {
    setToast(message);
    clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(''), 4000);
  }
  async function sendMessage(value) {
    if (!value.trim() || busy) return false;
    if (project && !window.confirm('배경을 다시 수정하면 기존 설문 답변과 프롬프트가 초기화됩니다. 계속할까요?')) return false;
    clearTimeout(saveTimer.current);
    setBusy(true); setPendingMessage(value.trim()); setChatError('');
    try {
      if (latest.current !== saved.current) {
        await client.current.write(snapshot);
        saved.current = serialized;
      }
      const requestId = globalThis.crypto?.randomUUID?.() || `turn_${Date.now()}_${Math.random().toString(36).slice(2)}`;
      const data = await client.current.converse(value.trim(), requestId, Boolean(project));
      saved.current = JSON.stringify(data.state); setUpdatedAt(data.updatedAt);
      applyState(data.state); setConfirmed(Boolean(data.confirmed)); setAgent(data.backgroundAgent); setApiError('');
      return true;
    } catch (error) {
      setChatError(error.message);
      return false;
    } finally { setBusy(false); setPendingMessage(''); }
  }
  const signature = JSON.stringify(draft);
  function confirmTask(event) {
    event.preventDefault();
    if (agent && !agent.ready) { notify('부족한 배경 정보를 먼저 확인해주세요.'); return; }
    if (Object.values(draft).some(value => !value.trim())) return;
    if (project && project.signature !== signature && Object.keys(answers).length && !window.confirm('과제가 바뀌면 기존 서베이 답변과 프롬프트가 초기화됩니다. 수정한 과제로 진행할까요?')) return;
    if (!project || project.signature !== signature) {
      setProject({ ...draft, type: 'general', signature, messages: agent ? agent.messages.filter(message => message.role === 'user').map(message => message.content) : contextSteps.map(step => context[step.id]) });
      setAnswers({}); setSurvey(emptySurvey); setQuestionIndex(0); setDocumentText(''); setManualEdited(false); setSurveyError('');
    }
    setStage(2);
  }
  function updateAnswer(id, answer) {
    setAnswers(previous => ({ ...previous, [id]: answer }));
  }
  // Ask the server for the question after `position` answered ones; it reuses or generates it.
  async function advance(position) {
    clearTimeout(saveTimer.current);
    setBusy(true); setGenerating(position === 0 ? 'first' : 'next'); setSurveyError('');
    try {
      const data = await client.current.survey(JSON.parse(latest.current), position);
      saved.current = JSON.stringify(data.state); setUpdatedAt(data.updatedAt);
      applyState(data.state); setApiError('');
      if (data.state.survey.done && position === data.state.survey.questions.length) {
        setGenerating('');
        await finish(data.state);
      }
    } catch (error) { setSurveyError(error.message); }
    finally { setBusy(false); setGenerating(''); }
  }
  const nextPosition = questionIndex + 1;
  const nextBasis = answerBasis(survey.questions, answers, nextPosition);
  const nextQuestion = survey.questions[nextPosition];
  const surveyComplete = !nextQuestion && survey.done && survey.doneBasis === nextBasis;
  const coveredTopics = new Set(survey.questions.filter(question => answerText(answers[question.id])).map(question => question.topic));
  const canFinishEarly = questionIndex === survey.questions.length - 1 && survey.topics.length > 0 && survey.topics.every(topic => coveredTopics.has(topic.id));
  function nextStep() {
    if (nextQuestion && nextQuestion.basis === nextBasis) { setQuestionIndex(nextPosition); return; }
    if (surveyComplete) { finish(); return; }
    const laterAnswers = survey.questions.slice(nextPosition).some(question => answerText(answers[question.id]));
    if (laterAnswers && !window.confirm('앞의 답변이 바뀌어 이후 질문을 새로 만듭니다. 이후 질문의 답변은 초기화됩니다. 계속할까요?')) return;
    advance(nextPosition);
  }
  useEffect(() => {
    // The first question is generated as soon as the survey opens without one.
    if (ready && promptId && view === 'definition' && stage === 2 && project && !busy && !surveyError && !survey.questions.length) advance(0);
  }, [ready, promptId, view, stage, project, busy, surveyError, survey.questions.length]);
  useEffect(() => {
    // Prefetch: start generating the next question once the user pauses on an answer.
    const current = survey.questions[questionIndex];
    if (stage !== 2 || busy || !current || !answerText(answers[current.id])) return;
    if ((nextQuestion && nextQuestion.basis === nextBasis) || surveyComplete) return;
    const timer = setTimeout(() => {
      client.current?.prefetch(JSON.parse(latest.current), nextPosition).catch(() => {});
    }, 900);
    return () => clearTimeout(timer);
  }, [stage, busy, questionIndex, nextBasis, survey]);
  useEffect(() => {
    // Planning the first question is the slowest call, so start it while the user reviews the task draft.
    if (stage !== 1 || busy || !agent?.ready || Object.values(draft).some(value => !value.trim())) return;
    if (project?.signature === signature && survey.questions.length) return;
    const timer = setTimeout(() => {
      const state = { ...JSON.parse(latest.current), project: { ...draft, type: 'general', signature, messages: [] }, stage: 2, answers: {}, questionIndex: 0 };
      client.current?.prefetch(state, 0).catch(() => {});
    }, 1500);
    return () => clearTimeout(timer);
  }, [stage, busy, agent, signature]);
  async function finish(state = JSON.parse(latest.current)) {
    const missing = state.survey.questions.findIndex(question => !answerText(state.answers[question.id]));
    if (missing >= 0) { setQuestionIndex(missing); return; }
    if (manualEdited && !window.confirm('답변으로 다시 만들면 직접 수정한 프롬프트가 교체됩니다. 계속할까요?')) return;
    clearTimeout(saveTimer.current);
    // The model consolidates every answer into the prompt, which takes a while; show it like question generation.
    setBusy(true); setApiError(''); setSurveyError(''); setGenerating('prompt');
    try {
      const data = await client.current.write(state, true);
      saved.current = JSON.stringify(data.state); setUpdatedAt(data.updatedAt);
      applyState(data.state); setEditing(false); setConfirmed(Boolean(data.confirmed));
      notify('개발 프롬프트를 생성하고 저장했습니다.');
    } catch (error) { setSurveyError(error.message); }
    finally { setBusy(false); setGenerating(''); }
  }
  const promptItems = prompts.map(listItem);
  async function refreshPrompts() {
    try { setPrompts((await request('/prompts')).prompts); } catch (error) { setApiError(error.message); }
  }
  function openWorkspace(data) {
    setPersonalWorkspace(Boolean(data.personal));
    client.current = createWorkspaceClient(data.promptId);
    client.current.initialize(data.revision);
    saved.current = JSON.stringify(data.state); setUpdatedAt(data.updatedAt);
    applyState(data.state); setConfirmed(Boolean(data.confirmed)); setAgent(data.backgroundAgent); setPromptId(data.promptId);
    setChatError(''); setSurveyError(''); setEditing(false); setApiError(''); setView('definition');
  }
  async function loadInto(load) {
    setBusy(true);
    try { openWorkspace(await load()); } catch (error) { setApiError(error.message); refreshPrompts(); } finally { setBusy(false); }
  }
  function openPrompt(item) {
    if (view === 'personal') loadInto(() => request(`/prompts/${item.id}/personal`, { method: 'POST' }));
    else if (item.id === promptId) setView('definition');
    else loadInto(() => request(`/prompts/${item.id}`));
  }
  function startNew() { loadInto(() => request('/prompts', { method: 'POST', body: {} })); }
  async function removePersonalPrompt(item) {
    setBusy(true);
    try {
      await request(`/prompts/${item.id}/library-entry`, { method: 'DELETE' });
      setPrompts(current => current.filter(prompt => prompt.promptId !== item.id));
      notify('나만의 프롬프트 목록에서 제거했습니다. 원본과 공유 상태는 유지됩니다.');
    } catch (error) { setApiError(error.message); }
    finally { setBusy(false); refreshPrompts(); }
  }
  async function deletePrompt(item) {
    if (!window.confirm(`'${item.title}' 프롬프트를 삭제할까요?\n대화, 과제 정의, 설문 답변, 개발 프롬프트, Agent 수정 이력이 모두 지워지며 되돌릴 수 없어요.`)) return;
    setBusy(true);
    try {
      await request(`/prompts/${item.id}`, { method: 'DELETE' });
      if (item.id === promptId) { clearTimeout(saveTimer.current); client.current = null; setPromptId(null); saved.current = latest.current; }
      notify('프롬프트를 삭제했습니다.');
      return true;
    } catch (error) { notify(error.message); return false; }
    finally { setBusy(false); refreshPrompts(); }
  }
  async function goHome() { return goList('home'); }
  async function goPersonal() { return goList('personal'); }
  async function goList(destination) {
    // Save pending edits first so the list shows the latest title and step.
    clearTimeout(saveTimer.current);
    if (promptId && latest.current !== saved.current) await persist(latest.current);
    setView(destination); refreshPrompts();
  }
  async function saveBeforeAgent() {
    clearTimeout(saveTimer.current);
    const value = latest.current;
    if (value !== saved.current) {
      const data = await client.current.write(JSON.parse(value));
      saved.current = value; setUpdatedAt(data.updatedAt);
    }
  }
  async function loadAgent() {
    await saveBeforeAgent();
    return request(`/prompts/${promptId}/editor`);
  }
  async function sendAgent(message, requestId) {
    setBusy(true);
    try { await saveBeforeAgent(); return await client.current.edit(message, requestId); }
    finally { setBusy(false); }
  }
  async function decideAgent(turnId, decision) {
    setBusy(true);
    try {
      await saveBeforeAgent();
      const data = await client.current.decideEdit(turnId, decision);
      saved.current = JSON.stringify(data.state); latest.current = saved.current;
      applyState(data.state); setConfirmed(data.confirmed); setUpdatedAt(data.updatedAt); setEditing(false);
      return data;
    } finally { setBusy(false); }
  }
  async function confirmPrompt() {
    clearTimeout(saveTimer.current);
    setBusy(true); setApiError('');
    try {
      const value = latest.current;
      if (value !== saved.current) {
        await client.current.write(JSON.parse(value));
        saved.current = value;
      }
      const data = await client.current.confirm();
      setConfirmed(data.confirmed); setUpdatedAt(data.updatedAt); setEditing(false);
      notify('개발 프롬프트를 확정했습니다. 공유 여부는 모두의 프롬프트에서 관리할 수 있어요.');
      await refreshPrompts();
      setView('personal');
    } catch (error) { setApiError(error.message); }
    finally { setBusy(false); }
  }
  async function copy() {
    try { await navigator.clipboard.writeText(documentText); notify('프롬프트를 복사했습니다. 바이브코딩 도구에 붙여 넣어주세요.'); }
    catch {
      setEditing(true);
      requestAnimationFrame(() => { editor.current?.focus(); editor.current?.select(); });
      notify('Ctrl+C 또는 ⌘C로 선택된 프롬프트를 복사해주세요.');
    }
  }
  function download() {
    const url = URL.createObjectURL(new Blob(['\ufeff' + documentText], { type: 'text/markdown;charset=utf-8' }));
    const link = document.createElement('a');
    link.href = url; link.download = fileName(project.name, '개발프롬프트', 'md');
    document.body.append(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    notify('개발 프롬프트를 다운로드합니다.');
  }

  const confirmedResult = view === 'definition' && stage === 3 && (confirmed || personalWorkspace);
  const personalView = view === 'personal' || confirmedResult || (view === 'definition' && personalWorkspace);
  const creationView = view === 'home' || (view === 'definition' && !confirmedResult && !personalWorkspace);

  if (!ready) return <div className="startup panel" role="status"><h1>WiaCoding</h1><p>{apiError || '저장된 작업을 불러오고 있어요.'}</p>{apiError && <button className="button primary" onClick={() => window.location.reload()}>다시 연결</button>}</div>;
  return <div className={`app-shell ${stage === 2 && view === 'definition' ? 'focus-mode' : ''}`}>
    <a className="skip-link" href="#main-content">본문으로 건너뛰기</a>
    <aside className="sidebar">
      <a className="brand" href="#home" onClick={goHome}><CodeXml size={32} /><div><strong>WiaCoding</strong><small>바이브코딩 길잡이 Agent</small></div></a>
      <div className="nav-caption">WORKSPACE</div>
      <nav aria-label="WiaCoding 메뉴">
        <button className={creationView ? 'active' : ''} aria-current={creationView ? 'page' : undefined} disabled={busy} onClick={goHome}><FileText size={18} />개발 프롬프트 만들기</button>
        <button className={personalView ? 'active' : ''} aria-current={personalView ? 'page' : undefined} disabled={busy} onClick={goPersonal}><FolderHeart size={18} />나만의 프롬프트</button>
        <button className={view === 'shared' ? 'active' : ''} aria-current={view === 'shared' ? 'page' : undefined} disabled={busy} onClick={() => setView('shared')}><Users size={18} />모두의 프롬프트</button>
      </nav>
      <div className="lab-note"><strong>작은 아이디어가<br />업무의 변화를 만듭니다.</strong><p>처음 만드는 분도<br />차근차근 시작할 수 있도록.</p></div>
      <div className="sidebar-bottom"><div className="lab-profile"><span className="lab-avatar" aria-hidden="true"><UserRound size={20} /></span><div><strong>{user.full_name}</strong><small>{user.team_name}</small></div><i /></div><button className="sidebar-logout" disabled={busy} onClick={() => { if (latest.current === saved.current || window.confirm('저장되지 않은 변경이 있습니다. 로그아웃할까요?')) onLogout(); }}><LogOut size={15} />로그아웃</button></div>
    </aside>
    <div className="main-shell">
      <div className="topbar"><div className="breadcrumb"><PlatformHomeLink/> <span aria-hidden="true">&gt;</span> WiaCoding <span aria-hidden="true">&gt;</span>{view === 'definition' && <><button className="text-button crumb-link" disabled={busy} onClick={confirmed || personalWorkspace ? goPersonal : goHome}>{confirmed || personalWorkspace ? '나만의 프롬프트' : '진행 중인 프롬프트'}</button><span aria-hidden="true">&gt;</span></>}<strong>{view === 'shared' ? '모두의 프롬프트' : view === 'personal' ? '나만의 프롬프트' : view === 'home' ? '개발 프롬프트 만들기' : steps[stage - 1][0]}</strong></div><PlatformReturnLink/></div>
      <main id="main-content">
        {apiError && <div className="error" role="alert">{apiError} <button className="text-button" onClick={() => persist(latest.current)}>저장 재시도</button></div>}
        <fieldset className="workspace-fields" disabled={busy} aria-busy={busy}>
        {!confirmedResult && <header className="page-head"><div><span className="eyebrow">{view === 'shared' ? 'SHARED PROMPTS' : view === 'personal' ? 'MY PROMPTS' : view === 'home' ? 'IN PROGRESS' : 'YOUR FIRST CODING PROMPT'}</span><h1>{view === 'shared' ? '모두의 프롬프트' : view === 'personal' ? '나만의 프롬프트' : view === 'home' ? '개발 프롬프트 만들기' : '문제에서 과제로, 과제에서 첫 프롬프트로.'}</h1><p>{view === 'shared' ? '동료들이 만든 개발 프롬프트를 둘러보고 내 과제에 참고하세요.' : view === 'personal' ? '확정된 프롬프트와 동료에게서 가져온 프롬프트를 모아보세요.' : view === 'home' ? '진행 중인 프롬프트를 이어서 만들거나, 새 프롬프트를 시작하세요.' : '대화로 해결할 과제를 정하고, 맞춤 질문에 답하며 나의 첫 개발 프롬프트를 완성하세요.'}</p></div><div className="hero-tag"><CodeXml size={30} /><span>나의 업무 아이디어가<br /><b>첫 개발 프롬프트로.</b></span></div></header>}
        {view === 'shared' ? <SharedPrompts template={template} notify={notify} onImported={refreshPrompts} onDelete={deletePrompt} /> : (view === 'home' || view === 'personal') ? <PromptHome personal={view === 'personal'} items={promptItems} onOpen={openPrompt} onCreate={startNew} onDelete={deletePrompt} onRemove={removePersonalPrompt} disabled={busy} /> : <>
          {!confirmedResult && <><button type="button" className="text-button back-to-list" onClick={goHome}><ArrowLeft size={14} />내 프롬프트 목록</button>
          <div className="flow-steps" aria-label="프롬프트 작성 단계">{steps.map(([title, subtitle], index) => <div className={`flow-step ${stage === index + 1 ? 'active' : stage > index + 1 ? 'done' : ''}`} key={title} aria-current={stage === index + 1 ? 'step' : undefined}><span>{stage > index + 1 ? <Check size={17} /> : `0${index + 1}`}</span><div><strong>{title}</strong><small>{subtitle}</small></div>{index < 2 && <i />}</div>)}</div></>}
          {stage === 1 && <Chat agent={agent} metadata={agentMetadata} template={template} pendingMessage={pendingMessage} chatError={chatError} context={context} draft={draft} setDraft={setDraft} onSend={sendMessage} onConfirm={confirmTask} canResume={project?.signature === signature} onResume={() => setStage(2)} />}
          {stage === 2 && <Survey project={project} survey={survey} answers={answers} index={questionIndex} setIndex={setQuestionIndex} onChange={updateAnswer} onBack={() => { setSurveyError(''); setStage(1); }} onNext={nextStep} onFinish={() => finish()} onRetry={() => advance(survey.questions.length ? nextPosition : 0)} generating={generating} error={surveyError} complete={surveyComplete} canFinish={canFinishEarly} />}
          {stage === 3 && <ResultView key={promptId} promptId={promptId} onAgentLoad={loadAgent} onAgentSend={sendAgent} onAgentDecision={decideAgent} project={project} survey={survey} answers={answers} template={template} documentText={documentText} manualEdited={manualEdited}
            confirmed={confirmed} onConfirm={confirmPrompt} onEditText={value => { setDocumentText(value); setManualEdited(true); setConfirmed(false); }} editing={editing} setEditing={setEditing} editor={editor}
            onCopy={copy} onDownload={download} notify={notify} />}
        </>}
        </fieldset>
        <footer><span>© 2026 WIA · DX추진랩</span><span>WiaCoding · 아이디어에서 개발까지</span></footer>
      </main>
    </div>
    <div className={`toast ${toast ? 'visible' : ''}`} role="status" aria-live="polite">{toast && <><CheckCircle2 size={18} />{toast}</>}</div>
  </div>;
}
