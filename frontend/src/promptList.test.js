import test from 'node:test';
import assert from 'node:assert/strict';
import { formatDate, listItem } from './promptList.js';

test('목록 항목에 단계 이름을 붙이고 빈 제목을 대신한다', () => {
  assert.deepEqual(listItem({ promptId: 'p1', title: '주간 실적 보고', stage: 2, updatedAt: 'x' }),
    { id: 'p1', title: '주간 실적 보고', stage: 2, status: '프롬프트 메이킹 중', updatedAt: 'x' });
  assert.equal(listItem({ promptId: 'p2', title: '', stage: 1, updatedAt: 'x' }).title, '새 프롬프트');
  assert.equal(listItem({ promptId: 'pending', stage: 3 }).status, '확정 대기');
  assert.equal(listItem({ promptId: 'p3', title: 't', stage: 3, updatedAt: 'x', confirmed: true }).status, '완성');
});

test('날짜를 표시한다', () => {
  assert.equal(formatDate('2026-09-03T01:05:00'), '2026.09.03');
  assert.equal(formatDate(''), '');
});
