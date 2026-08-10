# 소방용품 안전지킴이 AI — FastAPI + HTML/CSS/JS (2026 KFI AI 혁신 경진대회)

KFI(한국소방산업기술원) 공공데이터를 활용해 ①구매·거래 단계의 사칭사기/미인증 제품을 판별하고,
②수령·보유 단계의 내용연수·정비이력·리콜(승인취소)을 지속 관리하는 서비스입니다.
백엔드는 FastAPI(Python), 프론트엔드는 커스텀 HTML/CSS/JS(직접 디자인한 화면)로 구성했습니다.

- 백엔드: FastAPI + SQLite(Python 내장 `sqlite3`) + JWT 인증
- 프론트엔드: `public/`의 정적 페이지(랜딩 → 로그인 → 사이드바 대시보드), 서버가 같은 포트에서 함께 서빙
- 알림: 실제 발송 대신 DB 로그 기록 방식
- OCR: 브라우저에서 Tesseract.js(CDN)로 처리 — 별도 서버 설치 불필요

## 1. 실행 방법 (Mock 데이터로 바로 체험)

```bash
pip install -r requirements.txt
copy .env.example .env      # Windows (Mac/Linux는 cp .env.example .env)
uvicorn main:app --reload --port 4000
```

브라우저에서 `http://localhost:4000` 접속 → 랜딩페이지 → 시작하기 → 회원가입/로그인 →
**챗봇 화면(로그인 직후 기본 화면)**. 이 앱은 챗봇 하나로 운영됩니다 — 화면에는 프리셋 카드
(공문판별/승인번호조회/업체확인/소화기조회·등록/내 소화기함 보기/내 알림 확인) 6개만 있고, 카드를
누르면 채팅 입력창에 빈칸이 있는 완성형 예시 문구가 채워집니다(예: "형식승인 제0000-0-000호
진짜예요?"에서 번호 부분이 선택된 상태로 채워짐). 빈칸만 채워 넣거나 직접 문장을 고쳐서 전송하면
그 자리에서 조회·등록·신고까지 끝납니다. 기본값은 `USE_MOCK=true`라서
**KFI 실 API 키가 없어도 전부 동작**합니다.

**관제 대시보드는 관리자 전용입니다.** 일반 회원가입으로는 관리자 권한을 가질 수 없고(서버가 클라이언트가
보낸 role을 무시하고 항상 일반 사용자로 가입시킴), 서버 최초 실행 시 아래 관리자 계정이 자동으로
시딩됩니다. 로그인 화면에서 이 계정으로 로그인하면 사이드바에 "관제 대시보드"가 나타납니다.

| 이메일 | 비밀번호 |
|---|---|
| `admin@kfi.go.kr` (`.env`의 `ADMIN_EMAIL`로 변경 가능) | `admin1234!` (`.env`의 `ADMIN_PASSWORD`로 변경 가능) |

관제 대시보드 관련 API(`GET /api/reports`, `/api/reports/stats`, `POST /api/admin/simulate-recall`,
`POST /api/admin/sync-kfi`)는 프론트에서 메뉴를 숨기는 것뿐 아니라 백엔드에서도 관리자 JWT가 아니면
403을 반환하도록 막아뒀습니다(데모지만 권한 체크는 실제 서비스와 동일하게 동작).

## 2. 테스트

```bash
pip install pytest httpx
pytest tests/ -v            # 순수 로직 + FastAPI TestClient API 통합 = 77건

cd test && npm install && cd ..
# 별도 터미널에서 서버를 띄운 상태로:
uvicorn main:app --port 4600 &
node test/frontend_e2e.js       # 실서버 + jsdom 프론트엔드 E2E 40건 (로그인/권한 가드/관제 대시보드 접근제어)
node test/chat_widget_e2e.js    # 챗봇 위젯 E2E 35건 (프리셋 카드, 빈칸 미입력 안내, 채팅 기반 조회·등록·신고, OCR 아이콘 등)
```

총 152건(Python 77 + JS E2E 75)을 검증했습니다. 프리셋 카드를 눌러도 채팅 말풍선이 추가되거나 API가
바로 호출되지 않고 입력창에 완성형 예시 문구만 채워지는 것, 채팅창에 승인번호·업체명·합격표시번호·
공문 텍스트를 그냥 문장으로 입력해도 실제 조회/등록이 실행되는 것, 위험한 결과가 나오면 채팅 버블
안에서 바로 신고를 접수해 서버에 저장되는 것, 리콜 발생 시 관리자가 트리거 → 일반 사용자가 채팅으로
재조회하면 최신 상태(취소/위험 등급/알림)로 반영되는 것, 일반 사용자가 관제 API를 직접 호출해도
403이 나는 것까지 실제 클릭·API 호출을 재현해 확인합니다.

## 3. 실제 KFI 데이터 연동하기 (data.go.kr API)

`USE_MOCK=false` + `KFI_SERVICE_KEY` 설정 시 실 API 모드로 동작합니다. 상세 스펙과 절차는
`kfi_client.py` 상단 주석에 정리했습니다. 요약:

- 승인정보/취소정보/업체정보는 단건조회가 안 되고 날짜범위+품목분류코드 목록조회만 지원 →
  `POST /api/admin/sync-kfi`로 로컬 캐시에 동기화하는 구조.
- 정비이력(합격표시번호)은 실시간 단건조회 가능 → `GET /api/units/:code` 호출 시 바로 조회.
- `.env`에 `USE_MOCK=false`, `KFI_SERVICE_KEY`(디코딩 버전), `KFI_GDS_CL_CODES` 설정 후
  `curl -X POST http://localhost:4000/api/admin/sync-kfi` 실행.

## 4. 챗봇 하나로 운영 (프리셋 카드 + 실제 기능 실행)

이 서비스는 챗봇 단일 화면으로 운영됩니다. 로그인하면 사이드바에는 "챗봇 상담"과(관리자에게만 보이는)
"관제 대시보드" 두 개만 있고, 나머지 기능(공문판별/승인번호조회/업체확인/소화기조회·등록/내 소화기함
보기/내 알림 확인)은 전부 채팅으로 처리합니다. 채팅 메시지 입력창 바로 위에 6개의 프리셋 칩이 있는데, 카드를 누르면
그 기능을 실제로 실행하는 대신 채팅 입력창에 빈칸이 있는 완성형 예시 문구가 채워지고 그 빈칸 부분이
선택 상태가 됩니다(예: "승인번호 조회" 카드 클릭 → 입력창에 "형식승인 제0000-0-000호 진짜예요?"가
채워지고 번호 부분이 선택됨 → 사용자가 그 자리에 실제 번호를 타이핑하거나 문장을 통째로 고쳐서 전송
→ 그제서야 실제 조회 실행). "내 소화기함 보기"/"내 알림 확인"처럼 빈칸이 필요 없는 카드는 바로 전송
가능한 완성 문구가 채워집니다. "공문 판별"·"소화기 조회·등록" 카드에는 📷 배지가 붙어 있는데, 이 두
기능은 문장을 직접 입력하는 대신 입력창 옆 📷 아이콘으로 사진을 올려도 됩니다(Tesseract.js OCR로
텍스트를 읽어 입력창에 채워줌). 만약 빈칸을 채우지 않고 예시 문구를 그대로 전송하면(예: "합격표시번호
조회해줘"), `chat_tools.py`가 이를 감지해 LLM에게 넘기지 않고 "실제 번호로 바꾸거나 📷 버튼으로 사진을
올려달라"는 안내를 바로 돌려줍니다 — 빈 값으로 LLM이 엉뚱하게 답하는 것을 막기 위한 안전장치입니다.

`chat_tools.py`가 메시지에서 승인번호/업체명("...업체/회사/판매자"라는 단서 단어와 함께)/합격표시번호
(`AXZG-45271` 형태)/공문·안내문 텍스트/"내 소화기함 보여줘"/"내 알림 확인" 같은 명령형 문구를 정규식으로
감지하면, `kfi_client`/`unit_service`/`notification_service`/`doc_analyzer`를 직접 호출해 실제 조회·등록
결과를 답변합니다(`OPENAI_API_KEY` 유무와 무관하게 항상 동작). 위험한 결과(미등록/취소·리콜/고위험 공문/
안전등급 이상)가 나오면 채팅 말풍선 안에 바로 "🚨 신고하기" 버튼이 붙어서, 화면 이동 없이 그 자리에서
신고까지 접수됩니다. `OPENAI_API_KEY` 없이도 지식베이스(`data/kb/*.md`) 검색결과를 그대로 보여주는
폴백 모드로 동작하며, 키를 설정하면 자연어 생성 + 임베딩 기반 검색으로 자동 업그레이드됩니다. 사실
판정(정품 여부, 리콜, 내용연수)은 절대 LLM에 맡기지 않고 DB 조회 결과를 그대로 프롬프트에 주입해
"설명"만 시킵니다. LLM 호출이 실패해도 이미 확정된 조회 결과는 그대로 답변됩니다(사실 확인이 LLM
가용성에 의존하지 않음). 공문/소화기 라벨 사진은 채팅 입력창 옆 📷 아이콘으로 업로드하면 Tesseract.js
OCR로 텍스트를 읽어 입력창에 채워줍니다.

## 5. 페이지 구조

| 페이지 | 설명 | 로그인 |
|---|---|---|
| `/index.html` | 랜딩(서비스 소개) | 불필요 |
| `/login.html` | 회원가입/로그인 | 불필요 |
| `/app.html` | 챗봇 화면(기본, 프리셋 카드 6개 포함). 관제 대시보드는 관리자 로그인 시에만 메뉴에 나타남 | 필요 |

## 6. API 요약

| Method | Path | 설명 | 인증 |
|---|---|---|---|
| GET | /api/health | 서버/모드 상태 | - |
| POST | /api/auth/register, /login | 회원가입/로그인 (JWT 발급) | - |
| POST | /api/approvals/analyze-doc | 공문 사기위험도 분석 | - |
| GET | /api/approvals/{number} | 승인번호 조회 | - |
| GET | /api/companies/{name} | 업체 등록여부 조회 | - |
| GET | /api/units/{code} | 합격표시번호 조회 | - |
| POST | /api/units/{code}/register | 내 소화기함 등록 | ✅ |
| GET | /api/units/mine | 내 소화기함 목록 | ✅ |
| POST | /api/reports | 신고 접수 | 선택 |
| GET | /api/reports, /reports/stats | 관제 대시보드용 조회 | ✅(admin) |
| GET | /api/notifications/mine | 내 알림 목록 | ✅ |
| POST | /api/admin/simulate-recall | (데모용) 리콜 강제 발생 | ✅(admin) |
| POST | /api/admin/sync-kfi | 실 API 모드 동기화 | ✅(admin) |
| POST | /api/chat | RAG 상담 챗봇 | - |

## 7. 폴더 구조

```
main.py                 # FastAPI 앱 진입점 (CORS, 정적파일 서빙, 라우터 등록)
deps.py                  # JWT 인증 의존성 (require_auth/soft_auth)
auth.py                  # bcrypt + JWT 발급/검증
db.py                    # sqlite3 스키마 + mock 데이터 시딩
kfi_client.py             # KFI 데이터 어댑터 (mock/real, sync)
lifecycle.py              # 내용연수/정비이력 판정 로직
doc_analyzer.py            # 공문 사기위험도 분석
rag.py / llm_client.py / chat_service.py / chat_tools.py   # RAG 챗봇 + 채팅 기반 기능 실행(도구 호출)
routers/                 # FastAPI 라우터 (auth/approvals/companies/units/reports/notifications/admin/chat)
services/                # 신고/알림/리콜시뮬레이션/유닛등록 서비스 계층
data/mock/, data/kb/     # mock 데이터, 챗봇 지식베이스
public/                  # 프론트엔드 정적 페이지(index/login/app.html) + js/
tests/                   # pytest (순수로직 + API 통합)
test/                    # Node jsdom 기반 프론트엔드 E2E (별도 package.json)
```

## 8. 알려진 한계

- 실 KFI API 연동은 확인된 스펙 기준으로 작성했으나 일부 하위 엔드포인트(성능인증/KFI인정 취소정보 등)는
  최초 실호출로 재확인이 필요합니다 (동기화 응답의 `errors` 필드에 표시됨).
- 리콜 ↔ 개별 유닛 매칭은 형식명 텍스트 근사 매칭입니다.
- 로컬 실행 전용으로 구성했습니다(배포 설정 없음).
- 인증은 JWT 기반이라 Node판과 동일하게 동작하며, 여러 브라우저/기기에서 같은 계정으로 동시 로그인 가능합니다.
- 역할은 `facility_manager`(일반)와 `admin`(관제 대시보드) 두 가지뿐입니다. 회원가입으로는 admin이 될 수 없고,
  관리자 계정은 서버 시작 시 한 번만 시딩됩니다(위 1번 항목 참고).
