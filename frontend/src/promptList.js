// Items for the "my prompts" cards, from GET /api/prompts (the server picks the title).
const statuses = ['과제 정의 중', '프롬프트 메이킹 중', '완성'];

export function listItem({ promptId, title, stage, updatedAt, confirmed = false, personal = false, team, goal, tags }) {
  return { id: promptId, title: title || '새 프롬프트', stage, status: personal ? '완성' : stage === 3 && !confirmed ? '확정 대기' : statuses[stage - 1], updatedAt,
    ...(team !== undefined ? { team, goal: goal || '', tags: tags || [] } : {}) };
}

export function formatDate(value) {
  const time = new Date(value);
  if (Number.isNaN(time.getTime())) return '';
  const pad = number => String(number).padStart(2, '0');
  return `${time.getFullYear()}.${pad(time.getMonth() + 1)}.${pad(time.getDate())}`;
}
