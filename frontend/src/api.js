export async function request(path, { method = 'GET', body } = {}) {
  const response = await fetch(`/api${path}`, { method, credentials: 'same-origin',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined });
  let data;
  try { data = await response.json(); } catch { throw new Error('백엔드 응답을 확인할 수 없습니다. 서버 연결을 확인해주세요.'); }
  if (!response.ok) {
    if (response.status === 401 && !path.startsWith('/auth/')) window.dispatchEvent(new Event('wiacoding-session-expired'));
    const error = new Error(data.error || '요청에 실패했습니다.'); error.status = response.status; throw error;
  }
  return data;
}
// Saves for one prompt, serialized so each write carries the revision returned by the previous one.
export function createWorkspaceClient(promptId) {
  let revision = 0, blocked = null, tail = Promise.resolve();
  function enqueue(path, method, body, retrySafe = false) {
    const operation = tail.then(async () => {
      if (blocked) throw blocked;
      try {
        const data = await request(path, { method, body: { ...body, revision } });
        revision = data.revision;
        return data;
      } catch (error) {
        if ((!error.status && !retrySafe) || [401, 409].includes(error.status)) blocked = error;
        throw error;
      }
    });
    tail = operation.catch(() => {});
    return operation;
  }
  return {
    edit(message, requestId) { return enqueue(`/prompts/${promptId}/editor`, 'POST', { message, requestId }, true); },
    decideEdit(turnId, decision) { return enqueue(`/prompts/${promptId}/editor/${turnId}/decision`, 'POST', { decision }, true); },
    confirm() { return enqueue(`/prompts/${promptId}/confirm`, 'POST', {}); },
    initialize(value) { revision = value; },
    write(state, generate = false) { return enqueue(`/prompts/${promptId}${generate ? '/generate' : ''}`, generate ? 'POST' : 'PUT', { state }); },
    converse(message, requestId, resetProject) { return enqueue(`/prompts/${promptId}/background`, 'POST', { message, requestId, resetProject }); },
    survey(state, position) { return enqueue(`/prompts/${promptId}/survey`, 'POST', { state, position }); },
    prefetch(state, position) { return request(`/prompts/${promptId}/survey/prefetch`, { method: 'POST', body: { state, position } }); },
  };
}
