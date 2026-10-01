import { formatDate } from './promptList.js';

// Shared visual structure for the public gallery and the personal library.
export default function PromptCard({ item, onOpen, actions, disabled = false }) {
  return <article className="shared-card" onClick={() => { if (!disabled) onOpen(); }}>
    <div className="shared-card-bar"><i /><i /><i /><span className="shared-card-team">{item.team}</span>{actions}</div>
    <ol className="shared-card-code">
      <li className="code-title"><span className="shared-title-line"><b aria-hidden="true">#</b>
        <button type="button" className="shared-card-link" disabled={disabled} onClick={event => { event.stopPropagation(); onOpen(); }}>{item.title}</button></span></li>
      {item.goal && <li className="code-goal"><span><b aria-hidden="true">&gt; </b>{item.goal}</span></li>}
      {item.tags?.length > 0 && <li className="code-tags"><span>{item.tags.map(tag => <em key={tag}>#{tag}</em>)}</span></li>}
      <li className="code-comment"><span>{'// '}{formatDate(item.date)}</span></li>
    </ol>
  </article>;
}
