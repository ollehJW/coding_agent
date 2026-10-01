import { ArrowRight, ChevronRight, FileText, Plus, Trash2, X } from 'lucide-react';
import { formatDate } from './promptList.js';
import PromptCard from './PromptCard.jsx';
import PromptCardList from './PromptCardList.jsx';

const stageNames = ['과제 정의', '프롬프트 메이킹', '개발 프롬프트'];

export default function PromptHome({ items, onOpen, onCreate, onDelete, onRemove, disabled, personal = false }) {
  const shown = items.filter(item => (item.status === '완성') === personal);
  if (personal) return <section className="personal-prompts" aria-labelledby="personal-list-title">
    <h2 id="personal-list-title" className="shared-list-title">프롬프트 목록</h2>
    {shown.length ? <PromptCardList items={shown} itemKey={item => item.id} disabled={disabled} renderCard={item => (
      <PromptCard item={{ ...item, date: item.updatedAt }} onOpen={() => onOpen(item)} disabled={disabled}
        actions={<button type="button" className="shared-import personal-remove" disabled={disabled}
          aria-label={`${item.title} 목록에서 제거`} title="목록에서 제거" onClick={event => { event.stopPropagation(); onRemove(item); }}><X size={15} /></button>} />
    )} /> : <div className="panel shared-empty"><FileText size={30} /><h2>아직 확정된 프롬프트가 없어요</h2>
      <p>프롬프트를 확정하거나 모두의 프롬프트에서 가져와보세요.</p></div>}
  </section>;

  return <div className={`prompt-home ${personal ? 'personal-prompts' : ''}`}>
    {!personal && <button type="button" className="new-prompt-card" onClick={onCreate} disabled={disabled}>
      <span className="new-prompt-icon"><Plus size={24} /></span>
      <strong>새 프롬프트 만들기</strong>
      <small>업무 이야기를 나누며 과제를 정하고, 맞춤 질문에 답해 첫 개발 프롬프트를 완성해요.</small>
      <span className="new-prompt-steps">{stageNames.map((name, index) => <span key={name}>{index > 0 && <ChevronRight size={13} />}{name}</span>)}</span>
      <span className="new-prompt-go">시작하기<ArrowRight size={16} /></span>
    </button>}
    <section className="panel prompt-list-panel" aria-labelledby="prompt-list-title">
      <div className="prompt-list-head"><div><h2 id="prompt-list-title">{personal ? '프롬프트 목록' : '진행 중인 프롬프트'}</h2>
        <p>{personal ? '직접 확정하거나 모두의 프롬프트에서 가져온 문서입니다.' : '이어서 작업하고, 최종 내용을 확정해주세요.'}</p></div></div>
      {shown.length ? <ul className="prompt-cards">{shown.map(item => <li key={item.id} className="prompt-card-wrap">
        <button type="button" className={`prompt-card stage-${item.stage}`} onClick={() => onOpen(item)} disabled={disabled}
          aria-label={`${item.title}, ${item.status}${item.updatedAt ? ', ' + formatDate(item.updatedAt) : ''}`}>
          <span className="prompt-card-bar" aria-hidden="true"><i /><i /><i /><span>prompt.md</span></span>
          <ol className="prompt-card-code">
            <li className="code-title"><span><b aria-hidden="true"># </b>{item.title}</span></li>
            {!personal && stageNames.map((name, index) => {
              const state = item.stage > index + 1 || item.status === '완성' ? 'done' : item.stage === index + 1 ? 'current' : 'todo';
              return <li key={name} className={`code-step ${state}`}><span><b aria-hidden="true">- [{state === 'done' ? 'x' : ' '}] </b>{name}
                {state === 'current' && <span className="code-now">{item.stage === 3 ? '확정 대기' : '진행 중'}<span className="code-cursor" aria-hidden="true" /></span>}
                <span className="visually-hidden">{state === 'done' ? ' 완료' : state === 'current' ? '' : ' 전'}</span></span></li>;
            })}
            <li className="code-comment"><time dateTime={item.updatedAt}>{'// '}{formatDate(item.updatedAt)} 수정</time></li>
          </ol>
        </button>
        <button type="button" className="prompt-card-delete" onClick={() => (personal ? onRemove : onDelete)(item)} disabled={disabled} aria-label={`${item.title} ${personal ? '목록에서 제거' : '삭제'}`} title={personal ? '목록에서 제거' : '삭제'}>{personal ? <X size={15} /> : <Trash2 size={15} />}</button></li>)}</ul>
        : <div className="prompt-empty"><FileText size={30} /><strong>{personal ? '아직 확정된 프롬프트가 없어요' : '진행 중인 프롬프트가 없어요'}</strong>
          <p>{personal ? '프롬프트를 확정하거나 모두의 프롬프트에서 가져와보세요.' : '새 프롬프트 만들기로 첫 과제를 시작해보세요.'}</p></div>}

    </section>
  </div>;
}
