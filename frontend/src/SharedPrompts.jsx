// 모두의 프롬프트: completed development prompts of every user, shown with the author's team only.
import { useEffect, useRef, useState } from 'react';
import { Bot, Check, Copy, FolderPlus, Heart, Search, Trash2, Users, X } from 'lucide-react';
import { request } from './api.js';
import { formatDate } from './promptList.js';
import PromptLines from './PromptLines.jsx';
import PromptCard from './PromptCard.jsx';
import PromptCardList from './PromptCardList.jsx';
import { SurveyFlow } from './SurveyHistory.jsx';
import TaskDefinition from './TaskDefinition.jsx';
import { AgentMessages, PromptDiff } from './PromptAgent.jsx';

const tabs = [['prompt', '개발 프롬프트'], ['definition', '과제 정의서'], ['survey', 'Survey 흐름'], ['agent', 'Agent 수정 이력']];

function Recommend({ item, onChange, notify }) {
  const [busy, setBusy] = useState(false);
  async function toggle(event) {
    event.stopPropagation();
    setBusy(true);
    try { onChange(await request(`/shared/${item.promptId}/recommendation`, { method: item.recommended ? 'DELETE' : 'PUT' })); }
    catch (error) { notify(error.message || '좋아요를 반영하지 못했어요. 다시 시도해주세요.'); }
    finally { setBusy(false); }
  }
  return <button type="button" className={`recommend-button ${item.recommended ? 'on' : ''}`} onClick={toggle} disabled={busy}
    aria-pressed={item.recommended} aria-label={`추천해요 ${item.recommendations}`}><Heart size={14} />추천해요 {item.recommendations}</button>;
}

function ImportPrompt({ item, onImported, notify, compact = false }) {
  const [busy, setBusy] = useState(false);
  async function bring(event) {
    event.stopPropagation(); setBusy(true);
    try {
      const result = await request(`/shared/${item.promptId}/import`, { method: 'POST' });
      onImported(item.promptId);
      notify(result.restored ? '나만의 프롬프트 목록에 다시 추가했습니다.' : result.created ? '나만의 프롬프트에 개인 복사본을 저장했습니다.' : '이미 가져온 프롬프트입니다.');
    } catch (error) { notify(error.message); }
    finally { setBusy(false); }
  }
  return <button type="button" className={compact ? 'shared-import' : 'button'} disabled={busy || item.imported}
    aria-label={item.imported ? '나만의 프롬프트에 보관됨' : '나만의 프롬프트로 가져오기'}
    title={item.imported ? '나만의 프롬프트에 보관됨' : '나만의 프롬프트로 가져오기'} onClick={bring}>
    {item.imported ? <Check size={15} /> : <FolderPlus size={15} />}{!compact && (item.imported ? '보관됨' : busy ? '가져오는 중' : '나만의 프롬프트로 가져오기')}
  </button>;
}

function AgentHistory({ promptId, apiBase = '/shared' }) {
  const [items, setItems] = useState(null);
  const [next, setNext] = useState(null);
  const [conversation, setConversation] = useState(null);
  const [chatNext, setChatNext] = useState(null);
  const [chatBusy, setChatBusy] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    Promise.all([request(`${apiBase}/${promptId}/editor-history`), request(`${apiBase}/${promptId}/editor-chat`)]).then(([data, chat]) => {
      if (active) { setItems(data.turns); setNext(data.nextCursor); setConversation(chat.turns); setChatNext(chat.nextCursor); setError(''); }
    }).catch(error => { if (active) setError(error.message); });
    return () => { active = false; };
  }, [promptId,retry,apiBase]);
  async function more() {
    setBusy(true); setError('');
    try { const data = await request(`${apiBase}/${promptId}/editor-history?before=${next}`);
      setItems(current => [...current,...data.turns]); setNext(data.nextCursor);
    } catch (error) { setError(error.message); }
    finally { setBusy(false); }
  }
  async function moreChat() {
    setChatBusy(true); setError('');
    try { const data = await request(`${apiBase}/${promptId}/editor-chat?before=${chatNext}`);
      setConversation(current => [...data.turns,...current]); setChatNext(data.nextCursor);
    } catch (error) { setError(error.message); }
    finally { setChatBusy(false); }
  }
  return <div className="shared-agent-history">
    {error && <p className="error" role="alert">{error} <button type="button" className="text-button" onClick={() => setRetry(value => value + 1)}>다시 시도</button></p>}
    {!items && !error && <p role="status">수정 이력을 불러오는 중이에요.</p>}
    <aside className="shared-history-chat" aria-label="전체 Agent 대화 이력">
      <header><Bot size={18} /><strong>전체 대화</strong></header>
      <div className="shared-history-chat-scroll" tabIndex={0}>
        {chatNext && <button type="button" className="text-button" disabled={chatBusy} onClick={moreChat}>{chatBusy ? '불러오는 중…' : '이전 대화 더 보기'}</button>}
        {conversation?.length === 0 && <p className="shared-chat-empty">Agent와 대화한 이력이 없습니다.</p>}
        <AgentMessages turns={conversation || []} userLabel="작성자" />
      </div>
    </aside>
    <section className="shared-history-revisions" aria-label="반영된 수정 목록">
    <h4>반영된 수정</h4>
    {items?.length === 0 && <p className="shared-empty-note">Agent를 통해 수정한 이력이 없습니다.</p>}
    {items?.map(turn => <article className="shared-edit-entry" key={turn.id}>
      <div className="shared-edit-date"><span>반영된 수정</span><time dateTime={turn.createdAt}>{formatDate(turn.createdAt)}</time></div>
      <div className="shared-edit-request"><strong>수정 요청</strong><p>{turn.message}</p></div>
      <div className="shared-edit-response"><strong>Agent</strong><p>{turn.reply}</p><p className="shared-edit-applied">{turn.decisionMessage}</p></div>
      <details><summary>수정 전·후 보기</summary><PromptDiff proposal={turn} readOnly /></details>
    </article>)}
    {next && <button type="button" className="button" disabled={busy} onClick={more}>{busy ? '불러오는 중…' : '이전 수정 이력 보기'}</button>}
    </section>
  </div>;
}

export function Detail({ promptId, template, onClose, onRecommend, onImported, notify, admin = false }) {
  const dialog = useRef(null);
  const [adminTemplate, setAdminTemplate] = useState('');
  const [notice, setNotice] = useState('');
  const apiBase = admin ? '/admin/prompts' : '/shared';
  const [detail, setDetail] = useState(null);
  const [error, setError] = useState('');
  const [tab, setTab] = useState('prompt');
  useEffect(() => { dialog.current?.showModal(); }, []);
  useEffect(() => {
    let active = true;
    Promise.all([request(`${apiBase}/${promptId}`), admin ? request('/templates/task-definition') : Promise.resolve(null)])
      .then(([data, taskTemplate]) => { if (active) { setDetail(data); if (taskTemplate) setAdminTemplate(taskTemplate.html); } })
      .catch(err => { if (active) setError(err.message); });
    return () => { active = false; };
  }, [promptId, apiBase, admin]);
  function recommended(result) { setDetail(current => ({ ...current, ...result })); onRecommend(promptId, result); }
  async function copy() {
    try { await navigator.clipboard.writeText(detail.document); (notify || setNotice)('프롬프트를 복사했습니다.'); }
    catch { (notify || setNotice)('복사하지 못했어요. 프롬프트를 직접 선택해 복사해주세요.'); }
  }
  return <dialog ref={dialog} className={`shared-dialog ${tab === 'agent' ? 'agent-history-open' : ''}`} aria-labelledby="shared-detail-title" onClose={onClose}
    onClick={event => { if (event.target === dialog.current) dialog.current.close(); }}>
    <header className="shared-dialog-head">
      <div><span className="shared-team"><Users size={13} />{detail?.team || ' '}</span>
        <h3 id="shared-detail-title">{detail?.title || '불러오는 중…'}</h3>
        {detail?.goal && <p>{detail.goal}</p>}</div>
      <button type="button" className="history-close" aria-label="닫기" onClick={() => dialog.current.close()}><X size={18} /></button>
    </header>
    {error ? <p className="error shared-dialog-error" role="alert">{error}</p> : detail && <>
      <div className="shared-tabs" role="tablist" aria-label="보기">{tabs.map(([key, label]) =>
        <button key={key} type="button" role="tab" aria-selected={tab === key} className={tab === key ? 'active' : ''} onClick={() => setTab(key)}>{label}</button>)}</div>
      <div className="shared-dialog-body" role="tabpanel">
        {tab === 'prompt' && <article className="prompt-lines shared-document"><PromptLines text={detail.document || '아직 개발 프롬프트가 생성되지 않았습니다.'} /></article>}
        {tab === 'definition' && (detail.definition
          ? <TaskDefinition html={admin ? adminTemplate : template} draft={detail.definition} readOnly />
          : <p className="shared-empty-note">과제 정의서가 없어요.</p>)}
        {tab === 'agent' && <AgentHistory promptId={promptId} apiBase={apiBase} />}
        {tab === 'survey' && <div className="shared-survey"><SurveyFlow survey={detail.survey} answers={detail.answers} showLegend={false} /></div>}
      </div>
      <footer className="shared-dialog-actions">
        <span>{formatDate(admin ? detail.updatedAt : detail.sharedAt)} {admin ? '수정' : '공유'}</span>
        {notice && <span role="status">{notice}</span>}
        {!admin && <>
        <ImportPrompt item={detail} notify={notify} onImported={id => { setDetail(current => ({ ...current, imported: true })); onImported(id); }} />
        <Recommend item={detail} onChange={recommended} notify={notify} />
        </>}
        <button type="button" className="button primary" onClick={copy}><Copy size={15} />프롬프트 복사</button>
      </footer>
    </>}
  </dialog>;
}

function SharingManager({ onChange, notify, onDelete }) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let active = true;
    request('/sharing').then(data => { if (active) { setItems(data.prompts.filter(item => item.canShare)); setError(''); } })
      .catch(error => { if (active) setError(error.message); });
    return () => { active = false; };
  }, [retry]);
  async function toggle(item) {
    setBusy(item.promptId);
    try {
      const result = await request(`/prompts/${item.promptId}/sharing`, { method: 'PUT', body: { enabled: !item.enabled } });
      setItems(current => current.map(row => row.promptId === item.promptId ? { ...row, enabled: result.enabled } : row));
      onChange();
      notify(result.enabled ? '모두의 프롬프트에 공유했습니다.' : '공유를 비활성화했습니다. 다른 사람에게 표시되지 않아요.');
    } catch (error) { notify(error.message); }
    finally { setBusy(null); }
  }
  async function remove(item) {
    setBusy(item.promptId);
    try {
      if (await onDelete({ id: item.promptId, title: item.title || '새 프롬프트' })) {
        setItems(current => current.filter(row => row.promptId !== item.promptId));
        onChange();
      }
    } finally { setBusy(null); }
  }
  return <section className="panel sharing-manager" aria-labelledby="sharing-title">
    <div className="sharing-heading"><h2 id="sharing-title">내 프롬프트 공유 관리</h2>
      <p>공유를 활성화하면 프롬프트·과제 정의서·설문 답변·Agent 전체 대화와 수정 이력이 다른 사람에게 공개됩니다. 새 프롬프트는 비활성화 상태로 시작해요.</p></div>
    {error ? <p className="error" role="alert">{error} <button className="text-button" onClick={() => setRetry(value => value + 1)}>다시 시도</button></p>
      : items === null ? <p className="sharing-empty" role="status">내 프롬프트를 불러오는 중이에요.</p>
      : !items.length ? <p className="sharing-empty">아직 확정된 프롬프트가 없어요.</p>
      : <ul className="sharing-list">{items.map(item => <li key={item.promptId}>
        <div className="sharing-info"><strong>{item.title || '새 프롬프트'}</strong>
          <span>{formatDate(item.updatedAt)} 수정</span></div>
        <button type="button" role="switch" aria-checked={item.enabled} aria-label={`${item.title || '새 프롬프트'} 공유`}
          className={`sharing-toggle ${item.enabled ? 'on' : ''}`} disabled={busy !== null || (!item.canShare && !item.enabled)}
          onClick={() => toggle(item)}><span className="sharing-track" aria-hidden="true"><i /></span>
          <span>{busy === item.promptId ? '처리 중' : item.enabled ? '활성화' : '비활성화'}</span></button>
        <button type="button" className="sharing-delete" disabled={busy !== null}
          aria-label={`${item.title || '새 프롬프트'} 전체 삭제`} onClick={() => remove(item)}><Trash2 size={15} />전체 삭제</button>
      </li>)}</ul>}
  </section>;
}

export default function SharedPrompts({ template, notify, onImported, onDelete }) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState('latest');
  const [open, setOpen] = useState(null);
  const [refresh, setRefresh] = useState(0);
  useEffect(() => {
    let active = true;
    const timer = setTimeout(() => {
      const params = new URLSearchParams({ q: query.trim(), sort });
      request(`/shared?${params}`).then(data => { if (active) { setItems(data.prompts); setError(''); } }).catch(err => { if (active) setError(err.message); });
    }, query ? 250 : 0);
    return () => { active = false; clearTimeout(timer); };
  }, [query, sort, refresh]);
  function imported(promptId) {
    setItems(current => current?.map(item => item.promptId === promptId ? { ...item, imported: true } : item));
    setRefresh(value => value + 1);
    onImported?.();
  }
  function updated(promptId, result) {
    setItems(current => current.map(item => item.promptId === promptId ? { ...item, ...result } : item));
  }
  return <section className="shared-page" aria-label="모두의 프롬프트">
    <SharingManager key={refresh} onChange={() => setRefresh(value => value + 1)} notify={notify} onDelete={onDelete} />
    <h2 className="shared-list-title">공유된 프롬프트</h2>
    <div className="shared-toolbar">
      <label className="shared-search"><Search size={16} /><span className="visually-hidden">검색</span>
        <input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="과제, 기술, 팀으로 검색" /></label>
      <label className="shared-sort"><span className="visually-hidden">정렬</span>
        <select value={sort} onChange={event => setSort(event.target.value)}><option value="latest">최신순</option><option value="recommended">추천순</option></select></label>
    </div>
    {error && <p className="error" role="alert">{error}</p>}
    {items && (items.length ? <PromptCardList key={JSON.stringify([query, sort])} items={items} itemKey={item => item.promptId} renderCard={item => (
      <PromptCard item={{ ...item, date: item.sharedAt }} onOpen={() => setOpen(item.promptId)}
        actions={<><Recommend item={item} onChange={result => updated(item.promptId, result)} notify={notify} />
          <ImportPrompt compact item={item} notify={notify} onImported={imported} /></>} />)} />
      : <div className="panel shared-empty"><span className="shared-empty-icon"><Users size={26} /></span>
        <h2>{query ? '검색 결과가 없어요' : '아직 공유된 프롬프트가 없어요'}</h2>
        <p>{query ? '다른 검색어로 찾아보세요.' : '내 프롬프트의 공유를 활성화하면 이곳에 표시돼요. 작성자는 팀 이름으로만 표시됩니다.'}</p></div>)}
    {open && <Detail promptId={open} template={template} onClose={() => setOpen(null)} onRecommend={updated} onImported={imported} notify={notify} />}
  </section>;
}
