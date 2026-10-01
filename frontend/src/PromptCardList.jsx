import { useLayoutEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

export default function PromptCardList({ items, renderCard, itemKey, disabled = false }) {
  const grid = useRef(null);
  const [columns, setColumns] = useState(1);
  const [page, setPage] = useState(0);
  const pageSize = columns * 2;
  const pages = Math.max(1, Math.ceil(items.length / pageSize));
  const current = Math.min(page, pages - 1);

  useLayoutEffect(() => {
    const element = grid.current;
    let measuredColumns = 1;
    const measure = () => {
      const count = getComputedStyle(element).gridTemplateColumns.split(' ').filter(Boolean).length;
      if (measuredColumns !== count) {
        measuredColumns = count;
        setColumns(count);
        setPage(0);
      }
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  useLayoutEffect(() => { if (page !== current) setPage(current); }, [page, current]);

  return <div className="prompt-card-list">
    <ul className="shared-cards" ref={grid}>{items.slice(current * pageSize, (current + 1) * pageSize).map(item =>
      <li key={itemKey(item)}>{renderCard(item)}</li>)}</ul>
    {pages > 1 && <nav className="card-pagination" aria-label="프롬프트 목록 페이지">
      <button type="button" disabled={disabled || current === 0} onClick={() => setPage(current - 1)}><ChevronLeft size={16} />이전</button>
      <span role="status" aria-live="polite">{current + 1} / {pages}</span>
      <button type="button" disabled={disabled || current === pages - 1} onClick={() => setPage(current + 1)}>다음<ChevronRight size={16} /></button>
    </nav>}
  </div>;
}
