// The finished survey drawn as a flow: every question in order, with its topic, the decision it settled and the answer.
import { useEffect, useRef, useState } from 'react';
import { CheckCircle2, ChevronDown, CornerDownRight, GitBranchPlus, History, X } from 'lucide-react';
import { UNKNOWN } from './content.js';

const palette = ['#345f96', '#2f8a5b', '#b7791f', '#7c5cc4', '#c2536b', '#1f8a9a', '#8a6d3b', '#5a6f8f', '#b45309'];

function Step({ question, answer, number, color, topicLabel, followUp, addedTopic }) {
  const [others, setOthers] = useState(false);
  const chosen = answer?.selected || [];
  const custom = answer?.custom?.trim();
  const rest = question.cards.map(card => card.title).filter(title => title !== UNKNOWN && !chosen.includes(title));
  return <li className="history-step" style={{ '--topic': color }}>
    {addedTopic && <div className="history-branch"><GitBranchPlus size={14} />답변에 따라 새 확인 주제 추가 · <strong>{addedTopic}</strong></div>}
    <div className="history-node" aria-hidden="true">{number}</div>
    <article className="history-card">
      <div className="history-card-head">
        <span className="history-topic">{topicLabel}</span>
        {followUp && <span className="history-follow"><CornerDownRight size={12} />후속 질문</span>}
      </div>
      <h4>{question.decision || question.title}</h4>
      {question.decision && <p className="history-question">{question.title}</p>}
      <div className="history-answer">
        {chosen.map(title => <span key={title} className={`history-pill ${title === UNKNOWN ? 'unknown' : ''}`}>{title === UNKNOWN ? '미정' : title}</span>)}
        {custom && <blockquote className="history-custom">{custom}</blockquote>}
        {!chosen.length && !custom && <span className="history-pill empty">답변 없음</span>}
      </div>
      {rest.length > 0 && <button type="button" data-html2canvas-ignore className={`history-others ${others ? 'open' : ''}`} aria-expanded={others} onClick={() => setOthers(!others)}>
        다른 선택지 {rest.length}개<ChevronDown size={13} /></button>}
      {others && <ul className="history-other-list">{rest.map(title => <li key={title}>{title}</li>)}</ul>}
    </article>
  </li>;
}

export function SurveyFlow({ survey, answers, showLegend = true }) {
  const colors = Object.fromEntries(survey.topics.map((topic, index) => [topic.id, palette[index % palette.length]]));
  const labels = Object.fromEntries(survey.topics.map(topic => [topic.id, topic.label]));
  const added = Object.fromEntries(survey.topics.filter(topic => topic.origin > 0).map(topic => [topic.origin, topic.label]));
  const asked = new Set();
  return <>
    {showLegend && <div className="history-legend" aria-label="확인 주제">{survey.topics.map(topic =>
      <span key={topic.id} style={{ '--topic': colors[topic.id] }}><i />{topic.label}</span>)}</div>}
    <ol className="history-flow">
      <li className="history-start"><span className="history-dot" />과제 확정 · 설문 시작</li>
      {survey.questions.map((question, index) => {
        const followUp = asked.has(question.topic);
        asked.add(question.topic);
        return <Step key={question.id} question={question} answer={answers[question.id]} number={index + 1} followUp={followUp}
          color={colors[question.topic] || palette[0]} topicLabel={labels[question.topic] || question.label} addedTopic={added[index]} />;
      })}
      <li className="history-end"><CheckCircle2 size={18} />답변을 정리해 개발 프롬프트 생성</li>
    </ol>
  </>;
}

export default function SurveyHistory({ project, survey, answers, onClose }) {
  const dialog = useRef(null);
  useEffect(() => { dialog.current?.showModal(); }, []);
  return <dialog ref={dialog} className="history-dialog" aria-labelledby="history-title" onClose={onClose}
    onClick={event => { if (event.target === dialog.current) dialog.current.close(); }}>
    <header className="history-head">
      <span className="history-icon"><History size={19} /></span>
      <div><span className="eyebrow">SURVEY HISTORY</span><h3 id="history-title">{project.name}</h3>
        <p>질문 {survey.questions.length}개 · 확인 주제 {survey.topics.length}개 — 답변에 따라 이어진 질문 흐름이에요.</p></div>
      <button type="button" className="history-close" aria-label="닫기" onClick={() => dialog.current.close()}><X size={18} /></button>
    </header>
    <SurveyFlow survey={survey} answers={answers} />
  </dialog>;
}
