# 사고뭉치 웹 화면

React + TanStack Query 기반 학생·학부모 화면입니다. 화면은 Seesaw 레퍼런스의 공책 피드와 전체 화면 작성기를 참고했고, 동작 기준은 `docs/design/`입니다.

## 실행

Node.js 24 기준입니다.

```powershell
npm ci
npm run dev
```

새로 클론한 저장소에서 확인한 실행 순서(2026-10-27):

1. 백엔드까지 실제로 띄우기: 저장소 루트 `.env`에 `POSTGRES_PASSWORD`·`RABBITMQ_PASSWORD`·`INTERNAL_TOKEN`(필수)과 Google 로그인용 `AUTH_JWT_SECRET`·`GOOGLE_CLIENT_ID`·`GOOGLE_CLIENT_SECRET`을 채우고 Docker Desktop을 켠 뒤 `docker compose up --build -d` → 이 폴더에서 `npm ci && npm run dev` → **http://localhost:5173** 접속. `127.0.0.1`로 열면 `AUTH_WEB_ORIGIN`(기본 `http://localhost:5173`)과 달라 refresh가 403이 됩니다. 학생 기기·PIN API는 #104로 구현되어 PostgreSQL·Redis 및 Google 재인증 설정이 필요합니다.
2. 백엔드 없이 화면만 보기: 아래 MSW 목업 모드(`VITE_API_MOCK=true`). 목업 없이 백엔드도 없으면 "서버(core-service)에 연결하지 못했습니다" 안내만 나옵니다.

기본은 **API 모드**입니다. Vite가 `/api/v1` 요청을 core-service(기본 8080)로 전달합니다. 최신 develop에는 #36 인증, #37 동의·자녀 등록, #58 기기·PIN 및 Google 재인증 연결이 포함됩니다. 실제 연결 범위와 검증 조건은 각 이슈 보고서를 참고하세요. 서버 미구현·실패를 샘플 데이터로 덮지 않습니다.

이슈 #7 기준, 개발 중에는 MSW를 켜 실제 API 요청을 가로채서 확인합니다. 앱은 목 여부와 무관하게 같은 apiClient·SSE·Query 경로를 사용합니다.

```powershell
$env:VITE_API_MOCK='true'
npm run dev
```

채워진 가상 계정으로 로그인 → 자녀 선택 → ‘이 자녀로 학습 시작’ → 미션 → 작성·추가 질문 → 마무리 → 돌아보기 순서입니다. 학부모 화면은 대시보드·분석 대화·리포트·정보 관리로 연결됩니다. 상단 상태 선택기로 저장 실패·충돌·AI 실패·권한 거부 등을 시연합니다. 학생 초안/가상 세션/멱등 응답은 개발용 sessionStorage fixture로 복원되지만 access/refresh token과 비밀번호는 저장하지 않습니다. 새로고침 시 대화·관리자 저장소 등 메모리 목업은 초기화됩니다. 실제 개인정보를 입력하지 마세요.

MSW 시연의 이메일 로그인 비밀번호는 모두 `demo-only`입니다(개발 전용, 실제 모드는 Google 로그인만 제공). `parent@example.test`는 기본 보호자, `admin@example.test`는 전체 관리자, `content@example.test`·`ops@example.test`·`payment@example.test`·`refund@example.test`는 권한별 계정입니다. 가입 시 가상 `@example.test` 이메일만 사용합니다. 새 계정 자녀 목록은 비어 있으며 법정대리인 동의 후 최대 3명까지 등록할 수 있습니다. P02에 따라 다른 보호자의 기존 학생 연결은 제공하지 않습니다.

자녀 단독 진입(#59)은 학부모 `/parent/devices`에서 본인 재확인 → 자녀 PIN 설정 → 등록 코드(또는 QR) 발급 후, 같은 브라우저를 자녀 기기로 보고 로그아웃 → `/student/login`에서 코드 입력 → PIN 순서입니다. MSW가 httpOnly 기기 쿠키를 만들 수 없어 개발용 sessionStorage 상태로 대신하며, "기기 상태 시연" 선택기로 해제·만료·잠김·PIN 미설정을 시연합니다. 자세한 내용은 `docs/report/frontend.md`입니다.

### 노트북·태블릿 QR 등록 시연

다른 기기에서 같은 등록 코드와 PIN을 확인하려면 일반 MSW 대신 전용 명령을 실행합니다.

```powershell
npm run dev:qr
# 포트를 바꿀 때: npm run dev:qr -- --port 5197
```

기본 포트는 **5196**입니다. 보호자 노트북에서 `http://127.0.0.1:5196`을 열고 시연 계정 로그인 → **자녀 기기·PIN** → 본인 재확인(`demo-only`) → PIN 설정 → 등록할 자녀 선택 → **등록 코드 만들기** 순서로 진행합니다. ‘QR에서 열 주소’는 기본적으로 실제 네트워크 어댑터의 주소를 제안하며, Wi-Fi가 여러 개면 태블릿과 연결된 주소를 직접 고릅니다. 태블릿의 기본 카메라로 QR을 읽거나 ‘등록 화면 열기’의 주소를 태블릿에서 열면 됩니다. **기기 등록하기**를 누르면 코드가 주소에서 지워지고 PIN 화면으로 이어집니다. 보호자 기기 목록은 3초마다 갱신됩니다.

두 기기를 같은 Wi-Fi에 연결하고 개발 서버 포트 접근이 허용된 환경에서 사용합니다. `localhost`·`127.0.0.1`은 다른 기기에서 사용할 QR 주소가 아닙니다. 공용 인터넷에 노출하지 않고 가상 자녀 정보와 시연용 PIN만 사용합니다.

이 모드는 Vite 안의 메모리 목업이 등록 코드·PIN·기기 목록만 공유합니다. 기기 자격증명은 시연 서버의 HttpOnly 쿠키이고, QR에는 10분 동안 한 번 쓸 수 있는 등록 코드만 넣습니다. LAN HTTP에는 서비스 워커를 등록하지 않고 기존 MSW 핸들러를 개발용 fetch 어댑터에서 실행합니다. 실제 API 모드의 인증·보안 컨텍스트 요구는 그대로입니다. **답변·리포트 등 학습 데이터의 기기 간 동기화는 이 기능의 범위가 아닙니다.** 서버를 다시 시작하면 공유 등록 정보와 PIN이 초기화되므로 PIN 설정과 기기 등록을 다시 진행합니다.

구조·검증은 [QR 기기 시연 보고서](../../docs/report/frontend.md)를 참고하세요.

학생 화면은 테마 캔버스 기준의 "생각 지도"입니다. 첫 화면의 꾸미기 버튼으로 테마 5종·캐릭터 5종을 고르면 `/students/me/preferences`(API 명세 3.12 목업 계약)에 저장됩니다. 자세한 내용은 `docs/report/frontend.md`입니다.

시연을 끝낸 뒤 환경 변수를 제거해야 기본 API 모드가 됩니다.

```powershell
Remove-Item Env:VITE_API_MOCK
```

`import.meta.env.DEV && VITE_API_MOCK === 'true'`에서만 worker를 동적 import하고 기동한 뒤 렌더합니다. 운영 빌드는 변수가 true여도 MSW·핸들러·fixture를 포함하지 않으며, 복사된 개발 worker도 빌드에서 제외합니다. 기존 `VITE_DEMO_MODE` 방식은 폐지했습니다.

## 구성과 범위

- `presentation/`: 로그인, 공책, 미션 작성기, 학부모 리포트·분석, 적응형 레이아웃.
- `domain/classroom.ts`: 답변 입력 틀, 마무리·완료 규칙, KST 기간, 집계 기준. 교과 점수나 사고력 레벨을 만들지 않습니다.
- `data/classroom/`: Query 훅과 core 공개 API 어댑터. 기존 가상 저장소는 MSW 내부 fixture 생성에만 사용합니다. 컴포넌트가 HTTP나 내부 서비스에 직접 접근하지 않습니다.
- `mocks/`: 개발 전용 worker·핸들러·typed fixture. `/api/v1`의 미작성 목 경로는 501로 명시하며 실제 서버로 조용히 흘려보내지 않습니다.
- JSON·SSE 모두 만료 시 refresh 1회를 공유하며, 원 요청은 한 번만 재시도합니다. 실패 시 메모리 토큰을 지우고 재로그인 오류를 표시합니다. 실제 httpOnly 쿠키·역할 전환 검증 결과는 #36 보고서를 따릅니다.
- 초안은 ETag/If-Match로 저장하고 409 시 비교합니다. 제출은 Idempotency-Key, 피드백은 별도 SSE입니다. 메모 원본은 제출 내용·학부모 응답에 포함하지 않습니다. 학생이 서술/풀이/논술의 대상 칸을 골라 명시적으로 복사한 글만 답변에 포함합니다. 기존 답에 덧붙이고 메모 원본은 보존하며 길이 초과 시 잘라 넣지 않습니다.
- 시연용 그림 연습은 화면을 떠나면 유지되지 않습니다. 글 메모만 초안 저장 대상입니다. 시연 그림과 가상 기록은 AI Hub 데이터가 아닙니다.
- 계정 복구·실제 결제·알림은 이번 화면 로직 작업의 구현 범위가 아닙니다. 가입·자녀·관리자·리포트 다운로드는 #8·#9 목업 범위로 확장했습니다.
- 공개 Controller DTO가 나오면 데이터 어댑터 경계를 맞춰야 합니다. 6종 입력·학부모·관리자 DTO 보완은 `api-spec` 3.8~3.10의 목업 계약 초안이며 백엔드 확인 대기입니다. 목 ON/OFF는 같은 직렬화·공개 경로를 사용합니다. 실제 backend/OpenAPI 계약 확정이나 실연동 완료를 뜻하지 않습니다.
- 학부모 `/parent/journal?childId&from&to`의 범위가 대화·리포트·정보 관리 이동 시 유지됩니다. 대화 delta는 임시 표시하며 대조 실패/취소 시 폐기합니다. `clarification` 선택·실패 메시지 retry·전용 evidence endpoint를 사용합니다.
- 리포트는 3.4 응답 필드를 표시하고 재생성 시 기존 판을 유지합니다. 다운로드는 서버의 `{url,expiresAt}`를 따릅니다. 목업 PDF/Markdown은 가상 데이터 검증용 파일이며 실제 보고서 렌더러·S3 검증이 아닙니다. 만료 티켓/자녀 범위를 검사합니다.
- 관리자 `/me.permissions`에 따라 메뉴를 구분하며 서버 403도 별도 처리합니다. 미션/기준표 수정은 새 버전, 게시 전 검토 및 422 누락 항목 확인, 학생 장면/입력 컴포넌트 미리보기, 작업 재처리·감사·모델 버전·신고 정정 목업을 제공합니다. 업로드 API가 없어 장면 URI만 입력합니다.

## 검증

```powershell
npm test
npm run lint
npm run build
node tests/production-mocks.mjs
```

단위·어댑터 테스트는 실제 백엔드 통합 검증이 아닙니다. 브라우저 스모크 테스트는 Playwright와 Chromium이 있는 환경에서 별도로 실행합니다.

```powershell
# Playwright가 프로젝트 외부에 설치됐다면 해당 package.json의 절대 경로 지정
$env:PLAYWRIGHT_PACKAGE='C:/path/to/playwright/package.json'
$env:CHROME_PATH='C:/path/to/chrome.exe'
$env:DEMO_URL='http://127.0.0.1:5173'
$env:EXPECT_MSW='true'
# 선택: 기본 API 빌드를 서비스하는 preview 주소 (404 응답 스텁 검증)
$env:API_URL='http://127.0.0.1:5174'
# 선택: 저장소 외부의 새 캡처 폴더
$env:QA_OUTPUT_DIR='C:/path/to/new-qa-folder'
node tests/browser-smoke.mjs
```

현재 역할별 회귀 검증은 다음 스크립트를 사용합니다(같은 Playwright/Chrome 환경 변수, DEV 서버 MSW ON 필요). 이전 `browser-smoke.mjs`는 #7 초기 화면용 기록이며 새 학부모 UI에는 맞지 않습니다.

```powershell
node tests/student-browser.mjs
node tests/parent-admin-browser.mjs
node tests/student-device-browser.mjs
node tests/student-world-browser.mjs
node tests/parent-dashboard-browser.mjs
# 별도 운영 build + preview 주소. 실제 backend 대신 404 응답 스텁으로 경로/오류 표시 확인
node tests/api-mode-browser.mjs
```

#7~#9 구현 결정과 미확정 사항은 [웹 프론트 보고서](../../docs/report/frontend.md)에 정리했습니다. 실제 backend 통합·원격 CI·배포 검증은 별도입니다. 이후 사용자 요청으로 보류를 해제하고 `feature/fe-parent`에서 `develop` 대상 PR을 준비했습니다. PR 본문은 `docs/report/frontend.md`이며, develop 직접 push·자동 PR 병합은 하지 않습니다.

## 미체크 후속 회귀

추가 구현 결정은 [웹 프론트 보고서](../../docs/report/frontend.md)에 정리했습니다. 단위 테스트 48개, 학생 브라우저 23개, 학부모·관리자 브라우저 27개를 검증했습니다. 두 브라우저 스크립트 모두 `QA_FILTER`로 이름 일부를 지정해 특정 사례만 재실행할 수 있습니다.

신규 가입 자녀는 FREE이므로 연속 시나리오는 먼저 무료 분석 차단을 검증합니다. 그 뒤 **DEV+MSW에서만** 등록되는 `sagomungchi:test-child-plan` 테스트 이벤트로 현재 가상 계정의 자녀 플랜을 설정해 프리미엄 전제의 분석·근거·다운로드를 확인합니다. 이는 구독 API나 체험 상품이 아니며 UI에 결제 성공을 표시하지 않습니다. 새 계정 기본 플랜과 실제 사용자 권한을 바꾸지 않습니다. `tests/production-mocks.mjs`는 이 이벤트와 설정 함수도 운영 번들에서 제외되는지 검사합니다.


## #36 실제 인증
운영/API 모드의 로그인·가입 버튼은 `/api/v1/auth/google/authorize`로 이동한다. core 콜백이 refresh 쿠키를 설정하고 `/oauth/complete`로 돌아오면 refresh → `/me`로 역할·온보딩 단계를 복원한다. access는 메모리에만 있고 refresh는 JS가 읽지 않는다. 쿠키 인증 요청에 X-Requested-With를 붙이며 브라우저가 Origin을 보낸다. Web Locks로 탭 간 쿠키 회전을 직렬화하고 BroadcastChannel로 역할 전환·로그아웃을 알린다. 이 기능을 지원하는 보안 컨텍스트 브라우저가 필요하다. localhost HTTP는 로컬 예외다. 역할 전환 이벤트는 캐시를 비우고 서버 상태를 다시 조회한다.

개발 MSW 이메일/비밀번호 fixture는 시연 테스트 전용이다. 실제 API에는 이메일 로그인/가입을 제공하지 않는다. 신규 Google 계정은 #37 동의·자녀 등록 흐름을 따른다. 자녀 PIN 변경은 #104에 포함된 자녀별 Google 재인증을 사용한다. 공유 QR 시연에서도 동일한 자녀·세션별 단회 재확인 계약을 유지하며 Google 응답만 개발 fixture로 제공한다. 서버 미구현·실패를 mock으로 대체하지 않는다.


### P01 정렬
부모·관리자만 refresh로 복원한다. 학생 동석 진입은 access 전용이며 서버가 부모 refresh를 폐기한다. 등록 기기·PIN 로그인은 #104의 별도 학생 access 세션을 사용하며 보호자 세션을 유지한다. 학생 만료·새로고침 시 `/student/login`에서 PIN을 다시 입력한다. 학생 원문 작성 요청은 만료 후 부모 refresh로 자동 재시도하지 않는다. MSW도 학생 refresh를 거부한다.
