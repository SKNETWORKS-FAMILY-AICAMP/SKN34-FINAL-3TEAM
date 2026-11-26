# 사고뭉치 웹 화면

React + TanStack Query 기반 학생·학부모·관리자 화면입니다. 동작 기준은 `docs/design/`(화면 흐름은 [user-flow](../../docs/design/user-flow.md)), 구현 결정과 검증 기록은 [웹 프론트 보고서](../../docs/report/frontend.md)입니다.

## 실행

Node.js 22 기준입니다(Web CI `.github/workflows/_web.yml`과 같음).

```powershell
npm ci
npm run dev        # API 모드: Vite가 /api/v1 요청을 core-service(기본 8080)로 전달
```

- **API 모드(기본)**: 저장소 루트 `.env`(`.env.example` 참고)를 채우고 `docker compose up --build -d`로 백엔드를 띄운 뒤 **http://localhost:5173**으로 엽니다. `127.0.0.1`로 열면 `AUTH_WEB_ORIGIN`(기본 `http://localhost:5173`)과 달라 refresh가 403이 됩니다. 서버 미구현·실패를 샘플 데이터로 덮지 않습니다
- **MSW 목업 모드**: 백엔드 없이 화면만 봅니다. 앱은 목 여부와 무관하게 같은 apiClient·SSE·Query 경로를 씁니다

### 다른 개발 환경에서 학부모 화면 확인

화면은 선택한 자녀 ID로 `/api/v1/children/{childId}/reports`와 `/api/v1/reports/{reportId}`를 조회합니다. 개인 PC의 DB 파일이나 특정 테스트 자녀 ID를 참조하지 않습니다. 프론트와 함께 변경된 core·learning·report 코드도 같은 버전으로 빌드해야 일일 리포트의 테마 정보가 전달됩니다.

- **실제 생성 리포트:** API 모드에서 해당 보호자와 연결된 자녀의 `COMPLETED` 리포트를 표시합니다. 목록은 화면 진입·재조회 때 서버에서 읽습니다. 화면을 계속 열어 둔 상태에서 새 리포트를 실시간으로 추가하는 기능은 없습니다. 정상 스케줄은 KST 매일 00:00에 전날 일일 리포트, 월요일 00:00에 지난주 주간 리포트를 생성합니다. core 스케줄러·RabbitMQ·report-worker와 필수 동의가 준비돼 있어야 합니다.
- **저장소 합성 데이터:** 아래 MSW 모드에서 동일한 학부모 화면을 사용합니다. `reportDemo=structured`는 저장소의 가상 답변 3건을 추가하는 개발 전용 진입입니다. 기존 로컬 DB 데이터와 섞이지 않습니다.
- **Gemma 예시 설명:** 아래 생성 명령이 각 환경에 저장한 파일을 읽습니다. 파일이 없으면 설명 미포함으로 표시하며, 한화의 실제 리포트나 다른 개발자의 생성 결과를 가져오지 않습니다. 실제 리포트 본문은 이 예시 파일 대신 리포트 API를 사용합니다.
- **API 포트:** 루트 `.env`의 `CORE_HOST_PORT`를 바꾸면 Vite 프록시도 같은 포트를 읽습니다. 별도 서버는 `CORE_PROXY_TARGET`으로 지정할 수 있습니다. 변경 뒤 Vite를 다시 실행합니다.
- **캐릭터 선택:** 계정·자녀 설정과 기기 화면의 뭉치 선택은 현재 브라우저 저장소에 보관합니다. 다른 PC로 선택값을 동기화하지 않습니다.

그림책 표지는 서버의 `imageUrl`을 사용합니다. 로컬 MinIO에서 새 테마 그림을 생성·저장하려면 루트 `.env`에 `ASSET_S3_BUCKET=sagomungchi-local-assets`와 기존 MinIO 자격 증명을 설정하고, 저장소 루트에서 실행합니다. `ASSET_S3_BUCKET`을 비워 두면 기존처럼 그림 생성을 건너뜁니다.

```powershell
docker compose -f compose.yaml -f compose.minio.yaml up -d minio
docker compose -f compose.yaml -f compose.minio.yaml run --rm minio-init
docker compose -f compose.yaml -f compose.minio.yaml up --build -d
```

이 구성은 ai의 저장 주소, learning의 브라우저용 이미지 주소, report-worker의 PDF 이미지 조회 주소를 연결합니다. 이미 존재하는 그림은 다시 생성하지 않습니다. 새 테마 생성에는 기존 프로젝트의 모델·이미지 API 설정이 별도로 필요하고, 저장소 주소만으로 그림이나 AI 설명이 생기지는 않습니다. 다른 환경의 버킷·객체는 복사하지 않습니다. 기존에 `theme`가 없던 저장 리포트는 정상 재생성 후 새 테마 분류를 표시합니다.

### MSW 목업 실행

```powershell
$env:VITE_API_MOCK='true'
npm run dev
Remove-Item Env:VITE_API_MOCK   # 끝나면 지워야 API 모드로 돌아감
```

목업 계정 비밀번호는 모두 `demo-only`입니다(개발 전용). `parent@example.test` 기본 보호자, `admin@example.test` 전체 관리자, `content@example.test`·`ops@example.test`·`payment@example.test`·`refund@example.test` 권한별 관리자. 상단 상태 선택기로 저장 실패·충돌·AI 실패·권한 거부를 시연하고, 학생 초안·가상 세션·멱등 응답은 개발용 sessionStorage로 복원됩니다(토큰·비밀번호는 저장하지 않음). 실제 개인정보를 입력하지 마세요. 운영 빌드는 변수가 true여도 MSW·핸들러·fixture를 포함하지 않습니다(`node tests/production-mocks.mjs`가 검사).

자녀 단독 진입(P01)은 학부모 `/parent/devices`에서 자녀 PIN 설정 → 등록 코드(또는 QR) 발급 → 로그아웃 → `/student/login`에서 코드 → PIN 순서입니다. 목업은 httpOnly 기기 쿠키 대신 sessionStorage를 쓰고 "기기 상태 시연" 선택기로 해제·만료·잠김을 보여 줍니다.

### 주간 리포트 RunPod 상세 설명 시연

저장소 루트에서 Python 평가 환경(`httpx`)으로 실행합니다. 로컬 환경 파일에
`SAGOMUNGCHI_SLLM_SERVERLESS_GEMMA`와 `SAGOMUNGCHI_SLLM_SERVERLESS_KEY_GEMMA`를 둡니다.

```powershell
python evaluation/runners/structured_report_demo.py --env-file .env
```

스크립트는 목업 화면에 쓰는 가상 답변 3건을 RunPod Gemma의 `explain` 어댑터에 보내고, 결과를
`frontend/web/.taste-skill/structured-report-demo/gemma-explanations.json`에 저장합니다. 목업 모드에서
[주간 리포트 시연](http://localhost:5173/parent/report?reportDemo=structured&childId=demo-report-grade5&reportId=demo-report-grade5-2026-11-09)을 열면
답변 원문과 버전이 일치하는 상세 설명을 표시합니다. 새로고침해도 저장된 결과만 읽습니다.

### 노트북·태블릿 QR 등록 시연

```powershell
npm run dev:qr     # 기본 포트 5196, 바꿀 때: npm run dev:qr -- --port 5197
```

보호자 노트북에서 `http://127.0.0.1:5196` → 시연 계정 로그인 → **자녀 기기·PIN** → PIN 설정 → **등록 코드 만들기**. 'QR에서 열 주소'는 태블릿과 같은 Wi-Fi의 주소를 고르고, 태블릿 카메라로 QR을 읽거나 '등록 화면 열기' 주소를 엽니다. Vite 안 메모리 목업이 등록 코드·PIN·기기 목록만 공유하며(서버를 다시 시작하면 초기화), 학습 데이터의 기기 간 동기화는 범위 밖입니다. 공용 인터넷에 노출하지 말고 가상 자녀 정보만 쓰세요.

### 토스 테스트 결제 확인

```powershell
npm run dev:payment -- --port 5251
```

결제창과 서버 승인은 실제 토스 테스트 API, 주문은 메모리에만 두고 이용권은 주지 않습니다(`scripts/payment-test-plugin.ts`). 자세한 범위는 frontend 보고서 47절.

## 구성

- `presentation/`: 역할별 화면(학생 `student/`·학부모 `parent/`·관리자 `admin/`)과 공용 부품
- `domain/`: 답변 입력 틀, 마무리·완료 규칙, KST 기간, 주간 테마·리텐션 규칙. 교과 점수나 사고력 레벨을 만들지 않음
- `data/`: Query 훅과 core 공개 API 어댑터. 컴포넌트가 HTTP를 직접 부르지 않음
- `mocks/`: 개발 전용 worker·핸들러·typed fixture. 작성하지 않은 목 경로는 501로 명시
- 인증: 부모·관리자 access는 메모리, refresh는 httpOnly 쿠키(기본 access 15분·최초 로그인부터 최대 7일). 학생 access는 탭 sessionStorage에 저장해 새로고침·복제 시 유지한다. 실제 pointerdown·keydown 조작 때 학생 renew API를 최소 60초 간격으로 호출하며 자동 조회는 미사용 시간을 연장하지 않는다. 학생은 기본 미사용 30분, 총 시간 상한 없음. 같은 세션의 복제 탭에 갱신 토큰·로그아웃을 전파한다. 탭 종료만으로 서버 즉시 로그아웃을 보장하지 않고, 다음 요청에서 서버가 만료·폐기를 판단한다. 저장소 제한 시 메모리로 동작하므로 새로고침 후 PIN이 필요하다. 쿠키 요청은 `X-Requested-With`·Web Locks를 사용한다.

## 검증

| 명령 | 내용 |
|---|---|
| `npm test` | Node 단위·HTTP 계약·React 쿼리 훅 테스트(`tests/*.test.ts`) |
| `npm run test:types` | `tests/`와 Playwright 설정까지 타입 검사 |
| `npm run lint` | oxlint |
| `npm run build` | 앱·테스트 타입 검사 + 운영 빌드 |
| `npm run test:browser` | MSW 화면 테스트(`tests/browser`, 노트북·태블릿 폭). 먼저 `npx playwright install chromium` |
| `npm run test:rewards` · `test:models` · `test:auth` | 보상·꾸미기(`tests/reward-browser`), 모델 운영(`tests/model-browser`), 운영 빌드의 로그인 유지·재인증(`tests/auth-browser`) |
| `npm run test:e2e` | 실서버 E2E(`tests/e2e`, compose 스택 필요, [testing-ci 2장](../../docs/report/testing-ci.md)) |
| `node tests/production-mocks.mjs` | 운영 번들에 목업이 들어가지 않았는지 |

- 브라우저 테스트 서버는 localhost에만 열고 실제 PG·Google 인증은 부르지 않습니다. 실패하면 `test-results/`에 스크린샷·trace가 남습니다(`test-results/`·`playwright-report/`는 Git 제외). 로컬 Chrome을 쓰려면 `CHROME_PATH`
- 서로 다른 브라우저 검사 명령은 같은 `test-results/`를 쓰므로 차례로 실행합니다
- `tests/*-browser.mjs`는 수동 회귀 스크립트입니다(CI 대상 아님, `PLAYWRIGHT_PACKAGE`·`CHROME_PATH`·`QA_OUTPUT_DIR` 지정). `QA_FILTER`로 사례 일부만 다시 돌릴 수 있습니다
- 단위·목업 브라우저 테스트는 실제 백엔드 통합 검증이 아닙니다
