# WiaCoding frontend

`../wiacoding.html`의 전체 UI와 동작을 React로 구현했습니다. WiaNews의 색상, 카드, 내비게이션과 로컬 Pretendard 폰트를 참고했습니다.

```bash
cd /home/wia/projects/wiacoding/frontend
npm install
npm run dev
```

기본 주소는 http://localhost:6173 입니다. 프로젝트 루트에서 `backend/.venv/bin/python -m backend`로 6174 포트의 FastAPI 백엔드를 먼저 실행하세요. 설치 방법은 `../backend/README.md`를 참고하세요. Vite가 `/api` 요청을 백엔드로 전달합니다.

```bash
npm test
npm run build
npm run preview
```

빌드 결과 `dist/`를 사이트 루트에서 제공하고 `/api`를 백엔드에 프록시합니다. 프록시는 원래 Host 헤더를 유지해야 합니다. `npm run preview`에도 개발용 API 프록시가 설정되어 있습니다.

- 업무 배경 Agent와 자유 대화, 13개 항목의 수집 상태·제외 이유·발언 근거 확인
- 부족한 항목에 대한 후속 질문, 추후 확인 표시, 한글 조합 및 Enter 전송
- 과제 정의 필드 편집, 필수 입력 검증, 확정 및 기존 설문 재개
- 이전 답변에 맞춰 한 질문씩 만드는 개발 설문, 생성 진행 표시, 답을 고르면 다음 질문 미리 생성, 복수 선택 및 Custom Answer
- 결과 미리보기·직접 편집·복사·Markdown 다운로드
- 원본 가이드 6개, 카테고리·본문 검색, 상세 모달
- 모바일 대응, 키보드 접근성, 폰트 라이선스 `public/fonts/LICENSE.txt`

백엔드와 연결되어 제출한 대화·과제·답변·문서 수정 내용이 자동 저장됩니다. 저장 완료 후 새로고침하면 복원됩니다. 저장 중에는 페이지를 닫지 마세요. 같은 브라우저에서 하나의 작업을 이어가며, 새 과제 시작은 기존 작업을 초기화합니다.

배경 대화는 백엔드의 Azure OpenAI Agent와 연결됩니다. 핵심 정보를 정리하면 편집 가능한 과제 초안을 표시합니다. 과제 유형에 따라 다음 설문이 달라지며 최종 프롬프트는 템플릿 기반으로 생성합니다. 정식 계정 인증은 아직 없으며 작업은 브라우저 세션 쿠키로 분리됩니다.

공통 콘텐츠는 `../shared/content.json` (프론트엔드는 `content.mjs`와 `src/content.js`로 사용), 화면은 `Chat.jsx`, `Survey.jsx`, `Guides.jsx`, 전체 흐름과 결과는 `App.jsx`, 스타일은 `styles.css`에서 관리합니다.

