> 2026-10-02: PostgreSQL 및 AX for Works 통합 로그인으로 전환했습니다. 현재 DB 설정·이관·운영 절차는 [wiacoding PostgreSQL 가이드](../POSTGRESQL.md)를 따르세요. 아래 SQLite/app.db 및 서비스별 로그인 설명은 전환 전 기록입니다.

# WiaCoding FastAPI backend

Python 3.12 이상, FastAPI, Uvicorn 및 Python 내장 sqlite3를 사용합니다. 백엔드 실행에는 Node.js가 필요하지 않습니다.

## 설치 및 실행

아래 명령은 프로젝트 루트에서 실행합니다.

```bash
cd /home/wia/projects/wiacoding
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
backend/.venv/bin/python -m backend
```

- 프론트엔드: http://localhost:6173 (frontend에서 `npm run dev`)
- API: http://127.0.0.1:6174
- Swagger UI: http://127.0.0.1:6174/docs
- OpenAPI: http://127.0.0.1:6174/openapi.json
- 기본 DB 파일: **backend/app.db** (실행 디렉터리와 무관)

개발 중 자동 재시작:

```bash
backend/.venv/bin/python -m uvicorn backend.main:app --host 127.0.0.1 --port 6174 --reload
```

## 테스트

```bash
backend/.venv/bin/python -m pip install -r backend/requirements-dev.txt
backend/.venv/bin/python -m pytest backend/tests -q
cd frontend
npm test
npm run build
```

API 통합 테스트는 저장·복원, 재시작, 세션 분리·만료, 실제 동시 수정 충돌, 입력 검증, 추가 질문 분기, 이전 Node 프롬프트와의 결과 일치, DB 이전 및 보안 쿠키를 확인합니다. 운영 DB 대신 임시 DB를 사용합니다.

## API

| Method | Path | 설명 |
|---|---|---|
| GET | /api/health | DB 연결 및 실행 모드 |
| POST | /api/auth/login | `{ employee_id, password }` 로그인 (WiaNews와 같은 규칙) |
| GET | /api/auth/me | 로그인 사용자 |
| POST | /api/auth/logout | 로그아웃 |
| POST | /api/auth/password | `{ current_password, new_password }` 비밀번호 변경 (초기 비밀번호 사용 시 필수) |
| GET | /api/prompts | 내 프롬프트 목록 `{ prompts: [{ promptId, title, stage, updatedAt }] }` (수정 최신순) |
| POST | /api/prompts | 새 프롬프트 생성, 작업 응답 반환 |
| GET | /api/prompts/{id} | 프롬프트 작업 조회 |
| POST | /api/prompts/{id}/personal | 소유자의 확정 원본을 독립 개인 사본으로 열기 (반복 호출은 같은 사본 반환) |
| PUT | /api/prompts/{id} | `{ revision, state }` 저장 |
| DELETE | /api/prompts/{id} | 완전 삭제 (대화·정의서·설문·문서 함께 삭제) |
| POST | /api/prompts/{id}/generate | `{ revision, state }` LLM으로 설문 결과를 정리해 초기 프롬프트 생성·저장 |
| POST | /api/prompts/{id}/background | `{ revision, requestId, message, resetProject? }`로 Agent 대화 |
| POST | /api/prompts/{id}/survey | `{ revision, state, position }` 다음 설문 질문 |
| POST | /api/prompts/{id}/survey/prefetch | `{ state, position }` 다음 질문 미리 생성 |
| GET | /api/prompts/{id}/questions | 지금까지 생성된 설문 질문 |
| GET | /api/shared | 모두의 프롬프트 목록 (`q`, `type`, `sort=latest|recommended`), 작성자는 팀만 |
| GET | /api/shared/{id} | 공유된 프롬프트 상세: 개발 프롬프트, 과제 정의서, 설문 흐름 (대화 원문·발언 근거 제외) |
| PUT·DELETE | /api/shared/{id}/recommendation | 추천해요 추가·취소 (내 프롬프트는 불가) |
| GET | /api/context | 이전 배경 질문 (호환용) |
| GET | /api/background | 배경 항목 정의와 시작 안내 |
| GET | /api/guides | 가이드 목록 (`q`, `category` 필터) |

작업 응답은 `{ state, backgroundAgent, revision, updatedAt }`, 오류는 `{ error }`와 HTTP 상태 코드입니다. 먼저 GET /api/workspace로 세션 쿠키와 revision을 받습니다. Pydantic과 업무 규칙 검증 오류는 기존 프론트엔드와 호환되는 400으로 반환합니다. 동시 수정은 409로 거부합니다. JSON 요청은 최대 512KiB입니다.

## 구성

- `main.py`: API 경로, Pydantic 요청 모델, 쿠키·출처·요청 크기 검증
- `database.py`: SQLite 연결, 트랜잭션, revision 기반 동시 수정 보호
- `state.py`: 과제·설문 검증과 생성 흐름
- `survey.py`: 이전 답변에 맞춘 개발 설문 질문 생성, 미리 생성(prefetch)
- `content.py`: 공통 JSON 콘텐츠 조회와 Python 프롬프트 생성
- `../shared/content.json`: 질문·가이드·프롬프트 템플릿의 공통 원본
- `migrate_db.py`: 이전 DB를 안전하게 app.db로 복사하는 일회성 도구

## 환경변수

| 변수 | 기본값 | 설명 |
|---|---|---|
| HOST | 127.0.0.1 | `python -m backend` 바인딩 주소 |
| PORT | 6174 | `python -m backend` API 포트 |
| DB_PATH | backend/app.db의 절대 경로 | 다른 DB 경로 지정 |
| COOKIE_SECURE | false | HTTPS 서비스에서는 true |

프로젝트 루트의 `.env`를 자동 로딩합니다. 셸·배포 환경변수가 `.env`보다 우선합니다. DB_PATH의 상대 경로는 현재 작업 디렉터리가 아닌 프로젝트 루트를 기준으로 해석합니다. uvicorn CLI를 직접 실행할 경우 호스트·포트는 CLI 인자를 사용하세요.

## 기존 DB 이전

기존 서버를 먼저 종료한 뒤 실행합니다.

```bash
backend/.venv/bin/python -m backend.migrate_db
# 다른 경로에서 이전할 경우
backend/.venv/bin/python -m backend.migrate_db --source /기존/데이터.sqlite --target /새경로/app.db
```

기본 원본은 `backend/data/wiacoding.sqlite`, 대상은 `backend/app.db`입니다. SQLite 백업 API로 WAL에 반영된 데이터까지 복사한 후 무결성과 모든 작업 행을 비교합니다. 대상 파일이 이미 있으면 덮어쓰지 않습니다. 원본 DB는 백업으로 남깁니다. 기존 테이블, 세션 토큰 해시, revision, 작업 내용을 유지하므로 이전 브라우저 쿠키로 이어갈 수 있습니다.

## 저장·운영 범위

제출된 대화, 과제 정의, 설문 답변·단계 및 문서 수정 내용을 자동 저장합니다. 동일 브라우저에서 하나의 작업을 이어가며 새 과제 시작은 기존 작업을 대체합니다. 쿠키는 HttpOnly/SameSite=Strict이며 세션은 마지막 저장 후 30일간 유효합니다. 쿠키를 지우면 기존 작업에 다시 접근할 수 없습니다. 만료 작업은 새 세션 생성 시 정리합니다.

배경 대화는 Azure OpenAI를 사용하는 실제 Agent입니다. 이후 설문은 LLM이 한 번에 한 질문씩 만들고, 최종 프롬프트는 템플릿으로 생성합니다. 사내 SSO와 과제 이력 목록은 미연결입니다. 입력은 변경 후 350ms에 저장하며, 저장 중 종료하면 최신 변경이 보존되지 않을 수 있으므로 저장 완료 표시를 확인하세요.

프론트엔드의 `/api` 프록시는 원래 Host 헤더를 유지해야 합니다. 배포 시 프론트엔드와 API를 같은 출처로 제공하고 HTTPS에서는 COOKIE_SECURE=true를 설정하세요. 정식 사내 공개 전에는 조직 인증·권한을 연결해야 합니다.

`app.db`와 `app.db-wal`, `app.db-shm`, 가상환경은 버전 관리에서 제외합니다. 실행 중 백업은 SQLite 백업 API를 사용하거나 서버를 정상 종료한 뒤 복사하세요. 실행 중 DB 파일만 복사하면 WAL 데이터가 빠질 수 있습니다.


## LLM 클라이언트와 .env

`backend/llm_client.py`는 WiaNews의 Azure OpenAI 클라이언트를 기준으로 구성했습니다. WiaNews의 인증·뉴스레터 추적 DB에는 의존하지 않으며, 요청 ID·상태·소요 시간만 애플리케이션 로그에 남깁니다. 프롬프트, 응답 본문, 키는 로그에 기록하지 않습니다.

실제 설정은 프로젝트 루트 `.env`, 공유용 예시는 `.env.example`입니다. `.env`는 버전 관리에서 제외하고 접근 권한은 0600으로 설정합니다. 기존 `.env`가 없을 때만 예시를 복사하세요. 설정 변경 후 백엔드를 재시작해야 합니다.

| 변수 | 의미 / 기본값 |
|---|---|
| OPENAI_MODEL | Azure에 생성한 배포 이름 (필수) |
| OPENAI_API_KEY | Azure API 키 (필수) |
| OPENAI_BASE_URL | Azure 리소스 HTTPS 엔드포인트 (필수) |
| OPENAI_API_VERSION | 2025-04-01-preview |
| OPENAI_TIMEOUT_SECONDS | 요청 타임아웃 60초 |
| OPENAI_CONNECT_TIMEOUT_SECONDS | 연결 타임아웃 10초 |
| OPENAI_MAX_RETRIES | 재시도 1회, 즉 최대 2회 호출 (0~5) |
| OPENAI_SURVEY_REASONING_EFFORT | 설문 질문 생성의 추론 강도 `low` (`none`이면 더 빠름, 빈 값이면 모델 기본값) |
| OPENAI_PROMPT_REASONING_EFFORT | 초기 프롬프트 작성의 추론 강도 `low` |

```python
import json
from backend.llm_client import chat_completion

schema = {
    'type': 'object',
    'properties': {'title': {'type': 'string'}},
    'required': ['title'],
    'additionalProperties': False,
}

# FastAPI async 엔드포인트나 비동기 서비스 안에서 호출
async def suggest_title(description: str):
    result = await chat_completion(
        messages=[
            {'role': 'system', 'content': '업무 설명을 읽고 간결한 과제 제목을 JSON으로 반환하세요.'},
            {'role': 'user', 'content': description},
        ],
        schema=schema,
        schema_name='task_title',
        operation='task_definition',
        max_tokens=1000,
    )
    return json.loads(result)
```

`schema=None`이면 일반 텍스트를 반환합니다. 결과는 문자열처럼 사용할 수 있는 `CompletionText`이며 `request_id`, `usage` 속성이 있습니다. 스키마 지정 시 SDK의 `json_schema/strict`와 로컬 JSON Schema 검증을 함께 사용합니다. 거절, 토큰 제한에 의한 잘림, 빈 결과, 형식 불일치는 `InvalidLLMResponse`로 처리합니다.

429, 연결 오류, 타임아웃, 5xx만 재시도합니다. 재시도 대기는 Retry-After 또는 retry-after-ms를 참고해 최대 5초로 제한하며, SDK 내부 재시도는 꺼서 중복 재시도를 방지합니다. 취소는 재시도하지 않고 전파합니다.

배경 대화, 설문 질문, 초기 프롬프트 작성이 이 클라이언트를 호출합니다. 자동 테스트는 모의 응답과 MockTransport로 외부 호출 없이 수행합니다. 실제 연결 검증에는 별도의 모델 호출이 필요합니다.

구조화 응답 참고: [OpenAI 공식 Structured Outputs 문서](https://developers.openai.com/api/docs/guides/structured-outputs).

## 업무 배경 Agent

`background_agent.py`는 전체 대화에서 5개 항목(문제·목적, 현재 방식, 사용자, 영향·사례, 원하는 변화·범위)을 갱신하고, 부족한 항목 중 1~2개를 이어서 질문합니다. 모두 핵심 항목이며, 도구·자료와 사례·빈도·규모는 현재 방식과 영향·사례 항목에 포함합니다. 제약사항과 성공 기준은 다음 단계 설문에서 확인합니다.

각 항목은 미확인, 보완 필요, 완료, 추후 확인 상태를 갖습니다. 완료·추후 확인에는 사용자 원문 근거를 기록하며 추후 확인에는 이유도 필요합니다. 서버가 근거 인용의 일치와 상태 규칙을 검사하고 완료 여부를 계산합니다. 항목은 제외할 수 없지만 신규 업무의 기존 절차 없음처럼 해당 사실 자체로 정리할 수 있습니다. 모든 항목이 완료되어야 과제를 확정할 수 있습니다. 과제 초안의 범위 칸에는 원하는 변화·범위가 들어갑니다.

대화·항목 상태는 app.db의 background_agent 열에 서버가 저장합니다. 기존 DB는 시작 시 열을 추가하며 기존 작업은 보존합니다. 새로고침 후 이어서 대화할 수 있습니다. 확정 후 대화를 수정하려면 화면에서 기존 설문·문서를 초기화한다는 확인을 받으며, Agent 응답이 성공한 뒤 초기화합니다.

입력은 1회 3,000자, 누적 대화는 60,000자까지입니다. 요청 전체 제한은 150초이며 동시에 최대 4개 모델 호출을 처리합니다. 같은 세션의 대화는 순차 처리하고 revision으로 다른 탭의 변경을 보호합니다. 같은 requestId와 메시지 재전송은 직전 처리 결과를 재사용합니다. 항목 규칙 검증 실패는 전체 제한 시간 안에서 1회 재정리를 요청합니다. 재정리에도 실패한 모델 응답은 대화에 저장하지 않으며 화면에 입력을 유지합니다. 전송 결과를 알 수 없는 통신 오류나 충돌은 새로고침으로 저장 상태를 먼저 확인하세요.

## 개발 설문

과제를 확정하면 `survey.py`가 첫 질문과 함께 이 과제에서 확인할 주제 4~7개를 정합니다(한 번의 호출). 주제는 사용성(사용 흐름·화면), 데이터 모델(저장 대상·항목·관계), 업무 규칙, 기술 선택(검색 API, LLM, 알림, 로그인 등 외부 서비스), 사용 환경 중 과제에 필요한 것만 고르며 완료 기준·일정은 묻지 않습니다. 이후에는 과제 정의, 주제별 직전 평가, 지금까지의 모든 질문·답변만 짧은 JSON으로 보내 다음 질문 1개를 만듭니다. 원문 대화 전체는 보내지 않아 응답이 빠릅니다.

매 호출마다 모델이 모든 주제를 `unasked / needs_detail / sufficient`로 다시 평가하고 부족한 점을 적습니다. 서버는 답이 없는 주제를 완료로 볼 수 없게 보정하고, sufficient 주제 재질문, 이전 질문과 거의 같은 질문(유사도 0.8 이상), 한 주제 4번째 질문을 거부해 다시 만들게 합니다. 지금까지의 답변은 확정된 결정으로 취급해 모순된 선택지를 내지 않고, 답변끼리 모순되면 그 해소를 가장 먼저 묻습니다. 그다음 needs_detail, unasked 주제 순이며 남은 질문 수가 묻지 않은 주제 수 이하가 되면 묻지 않은 주제만 허용합니다. 답변으로 새 영역이 필요해지면(예: 검색 기능 → 검색 API 선택) 주제를 추가합니다(최대 9개). 모든 주제가 sufficient면 종료하며, 질문 한도는 주제 수 × 2(8~16)입니다. 한도에 도달해도 마지막 답변까지 평가하고, 남은 needs_detail 주제는 이유와 함께 최종 프롬프트의 확인 필요 항목에 들어갑니다. `아직 정하지 않았어요` 선택지는 서버가 붙이고, 최종 프롬프트는 주제별 섹션으로 만듭니다.

생성된 질문은 서버에만 저장하고 브라우저가 보낸 질문은 사용하지 않습니다. 각 질문은 생성 근거가 된 앞선 답변(`basis`)을 기록하므로, 앞의 답변을 바꾸면 이후 질문과 답변을 새로 만듭니다. 바뀌지 않았으면 기존 질문을 재사용합니다. 사용자가 답을 고르고 잠시 멈추면 화면이 `/api/survey/prefetch`로 다음 질문을 미리 만들고, 다음 버튼을 누르면 그 결과를 이어받습니다. 같은 위치의 오래된 미리 생성 작업은 취소합니다. 고정 질문 방식으로 저장된 기존 작업은 불러올 때 새 형식으로 변환합니다.

## 로그인과 계정

`auth.py`는 WiaNews의 계정 기능을 옮긴 것으로 `teams`, `roles`, `users`, `sessions`, `login_attempts` 테이블 스키마, PBKDF2-SHA256 비밀번호 해시, 로그인 시도 제한(사번 10회·IP 40회/15분), 8시간 세션, 초기 비밀번호 변경 강제가 같습니다. 헬스 체크와 `/api/auth/*`를 제외한 모든 API는 로그인과 비밀번호 변경을 마친 사용자만 사용할 수 있고, 작업(workspace)은 계정별로 하나씩 저장됩니다. 로그인 도입 전 브라우저 쿠키로 만든 작업은 그 브라우저에서 처음 로그인한 계정으로 옮겨집니다.

계정은 WiaNews DB에서 ID와 비밀번호 해시까지 그대로 복사합니다. 한 번 복사하는 방식이라 이후 WiaNews의 계정 추가·비밀번호 변경은 다시 실행해야 반영되고, WiaCoding에서 바꾼 비밀번호는 WiaNews에 반영되지 않습니다. 다시 실행하면 WiaNews 값으로 덮어씁니다.

```bash
backend/.venv/bin/python -m backend.import_users   # 기본 원본: ../wianews/backend/app.db
```

## 저장 구조

프롬프트마다 아래 테이블에 최신본만 저장합니다. API는 이를 하나의 작업 상태(`state`)로 조립해 주고받으며, 저장 시 검증된 상태를 다시 테이블로 나눠 씁니다. 프롬프트를 삭제하면 하위 행이 모두 지워지고(CASCADE), `llm_requests`는 `prompt_id`만 비워 남겨 전체·날짜·사용자별 토큰 합계가 유지됩니다.

| 테이블 | 내용 |
|---|---|
| prompts | 소유자, 목록 제목(확정 전 첫 메시지, 확정 후 과제명), 단계, 과제 유형, 설문 위치·완료 여부, revision, 생성·수정·완성 시각 |
| chat_messages | 과제 정의 대화 (답변을 만든 `llm_request_id` 포함) |
| background_items | 업무 배경 5개 항목의 상태·요약·근거 |
| task_definitions | 과제 정의서 편집 중 초안(draft)과 확정본(confirmed) |
| survey_topics | 과제별 확인 주제와 최신 평가 |
| survey_questions | 생성된 질문, 선택지, 생성 근거 답변, 당시 주제 평가, `llm_request_id` |
| survey_answers | 선택한 카드와 직접 입력 |
| prompt_documents | 초기 프롬프트 (생성본 또는 직접 수정본), 생성한 LLM 호출 `llm_request_id`, 정리된 명세 `spec`(JSON) |
| prompt_recommendations | 공유된 프롬프트의 추천해요 (프롬프트·사용자 삭제 시 함께 삭제) |
| llm_requests | LLM 호출 1회당 1행: 사용자, 프롬프트, 단계, 모델, 입력·출력·캐시·추론 토큰, 시도 번호, 성공 여부, 소요 시간 |

LLM 사용량은 `llm_client.chat_completion`에서 재시도·형식 오류를 포함해 호출마다 기록합니다. 요청·응답 본문은 저장하지 않습니다. 이전 `workspaces` 테이블의 계정 연결 작업은 서버 시작 시, 로그인 전 익명 작업은 그 브라우저로 목록을 처음 열 때 프롬프트로 옮겨지고 원래 행은 삭제됩니다.

## 초기 프롬프트 작성

`prompt_writer.py`가 과제 정의, 업무 배경 항목, 답한 순서대로의 설문 결정 전체를 한 번의 LLM 호출로 정리합니다. 뒤 답변이 바꾼 결정은 최종값만 남기고, 같은 내용은 합치고, 끝까지 풀리지 않은 모순과 미정 항목은 확인 필요로 보냅니다. 입력에 없는 내용은 만들지 않도록 지시하며, 결과는 JSON 명세(한 줄 목표, 배경, 첫 번째 목표, 요구사항, 반드시 지킬 제약, 기술 구성, 범위 밖, 확인 필요, 완료 확인)로 받아 서버가 Codex·Claude Code용 Markdown으로 조립합니다. 마지막 "작업 방식" 절(AGENTS.md/CLAUDE.md 저장, 계획 승인, `.env`, 샘플 데이터 등)은 고정 문구입니다. 호출은 `llm_requests`에 `prompt_generation` 단계로 기록되고, 실패하면 기존 문서를 바꾸지 않고 오류를 반환합니다.

## 모두의 프롬프트

개발 프롬프트가 완성되면(3단계, 문서 있음) `prompts.shared_at`이 채워져 모든 사용자에게 자동 공유되고, 다시 미완성 상태가 되면 비워집니다. 목록과 상세에는 작성자의 팀 이름만 표시하고 이름·사번은 내보내지 않습니다. 상세에는 개발 프롬프트, 과제 정의서, 설문 질문·답변만 포함하며 과제 정의 대화 원문과 발언 근거 인용은 포함하지 않습니다. 이 기능 도입 전에 완성된 프롬프트는 공유 안내 없이 만들어졌으므로 소급 공유하지 않고, 다시 생성할 때부터 공유됩니다.

### 개인 사본과 공유 원본

`personal_prompts`는 개인 사본의 ID·소유자·원본 연결을 관리합니다. 문서·설문·Agent 이력은 별도 프롬프트 ID로 기존 정규화 테이블을 재사용합니다. 직접 만든 확정 프롬프트는 개인 목록에서 처음 열 때 사본을 생성하며, 기존 비공개 가져오기 사본은 시작 시 관계 테이블에 등록합니다. 개인 사본의 수정·재확정은 공유 원본을 변경하지 않고, 개인 사본은 공유 관리와 공개 전환에서 제외합니다. 개인 목록 제거는 보관 상태만 바꾸며, 공유 관리의 전체 삭제는 원본과 작성자 자신의 개인 사본을 삭제합니다. 다른 사용자가 가져온 사본은 유지됩니다.

### 관리자 화면

관리자(`is_admin=1`)는 계정 관리·운영 관리·프롬프트 관리·토큰 관리 화면으로 진입합니다. 일반 사용자의 관리자 API 접근은 403, 미로그인은 401로 차단합니다. 계정 등록·편집·검색·삭제·비밀번호 초기화는 WiaNews의 계정 UI와 규칙을 사용합니다. 권한 변경·초기화는 해당 계정의 기존 세션을 만료시킵니다.

- `/api/admin/users`, `/api/admin/options`: 계정과 팀·직급 관리
- `/api/admin/operations?start=YYYY-MM-DD&end=YYYY-MM-DD`: 현재 현황과 선택 기간의 이용·오류 요약
- `/api/admin/prompts?q=&kind=all&offset=0`: 원본·개인 사본 목록(20건), 상세 조회, 공유 전환 및 전체 삭제
- `/api/admin/tokens?start=&end=&user_id=&model=&status=&offset=0`: 토큰 합계, 모델·사용자·일별 집계 및 호출 기록(50건)

기간은 최대 366일이며 기본은 최근 30일입니다. 호출 수에는 재시도가 포함됩니다. 토큰 값이 없는 호출은 별도 집계하고 사용량 합계에서는 제외합니다. 캐시 입력은 입력 토큰의 일부이며 총 토큰에 다시 더하지 않습니다. 비용 추정은 포함하지 않습니다.
