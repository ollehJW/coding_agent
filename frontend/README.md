# WiaCoding frontend

React/Vite 기반 WiaCoding 화면입니다. WiaNews의 색상, 카드, 내비게이션과 로컬 Pretendard 폰트를 참고했습니다.

```bash
cd frontend
npm install
npm run dev
```

기본 주소는 http://localhost:6173 입니다. 프로젝트 루트에서 `backend/.venv/bin/python -m backend`로 6174 포트의 FastAPI 백엔드를 먼저 실행하세요. 설치 방법은 [백엔드 문서](../backend/README.md)를 참고하세요. Vite가 `/api` 요청을 백엔드로 전달합니다.

```bash
npm test
npm run build
npm run preview
```

빌드 결과 `dist/`를 사이트 루트에서 제공하고 `/api`를 백엔드에 프록시합니다. 운영 HTTPS 서버는 `server.mjs`이며, 프록시는 원래 Host 헤더를 유지합니다.

- 과제 정의 대화와 맞춤 설문, LLM 개발 프롬프트 생성
- 직접 수정 및 Agent 수정 제안·승인·반려와 이력 조회
- 프롬프트 확정, 공유 관리, 독립된 개인 사본 보관
- Markdown 복사·다운로드 및 과제 정의서·설문 이력 PDF 다운로드
- 관리자 계정·운영·프롬프트·토큰 관리

인증 계정별로 대화·과제·설문·문서가 백엔드에 저장됩니다. 공통 콘텐츠는 `../shared/content.json`, 화면 코드는 `src/`, 진입 HTML은 `index.html`에 있습니다. WiaCanDX 소개 페이지는 `public/wiacandx.html`, 폰트 라이선스는 `public/fonts/LICENSE.txt`에 있습니다.
