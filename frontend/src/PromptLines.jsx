// Renders the generated Markdown prompt: headings, the goal quote and paragraphs.
export default function PromptLines({ text }) {
  return text.split('\n').map((line, i) => line.startsWith('# ') ? <h2 key={i}>{line.slice(2)}</h2>
    : line.startsWith('## ') ? <h3 key={i}>{line.slice(3)}</h3>
    : line.startsWith('### ') ? <h4 key={i}>{line.slice(4)}</h4>
    : line.startsWith('> ') ? <blockquote key={i}>{line.slice(2)}</blockquote>
    : line.trim() ? <p key={i}>{line}</p> : null);
}
