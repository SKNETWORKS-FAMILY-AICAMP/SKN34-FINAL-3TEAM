# 사고뭉치 웹 화면

React + TanStack Query 기반 학생·학부모 화면입니다. 화면은 Seesaw 레퍼런스의 공책 피드와 전체 화면 작성기를 참고했고, 동작 기준은 `docs/design/`입니다.

## 실행

Node.js 24 기준입니다.

```powershell
npm ci
npm run dev
```

기본은 **API 모드**입니다. Vite가 `/api/v1` 요청을 core-service(기본 8080)로 전달합니다. 로컬 기반 66f6052에는 로그인·학습·리포트 공개 Controller가 없으며, 2026-10-26 착수 시 fetch한 `origin/develop` c8cb58f에도 core/learning 공개 Controller 추가는 없습니다. 원격 병합은 사용자 요청으로 보류 중이고 실제 로그인 연동은 아직 검증되지 않았습니다. 오류를 샘플 데이터로 덮지 않습니다.

이슈 #7 기준, 개발 중에는 MSW를 켜 실제 API 요청을 가로채서 확인합니다. 앱은 목 여부와 무관하게 같은 apiClient·SSE·Query 경로를 사용합니다.

```powershell
$env:VITE_API_MOCK='true'
npm run dev
```

채워진 가상 계정으로 로그인 → 자녀 선택 → ‘이 자녀로 학습 시작’ → 미션 → 작성·추가 질문 → 마무리 → 돌아보기 순서입니다. 학부모 화면은 대시보드·분석 대화·리포트·정보 관리로 연결됩니다. 상단 상태 선택기로 저장 실패·충돌·AI 실패·권한 거부 등을 시연합니다. 학생 초안/가상 세션/멱등 응답은 개발용 sessionStorage fixture로 복원되지만 access/refresh token과 비밀번호는 저장하지 않습니다. 새로고침 시 대화·관리자 저장소 등 메모리 목업은 초기화됩니다. 실제 개인정보를 입력하지 마세요.

로그인 비밀번호는 모두 `demo-only`입니다. `parent@example.test`는 기본 보호자, `admin@example.test`는 전체 관리자, `content@example.test`·`ops@example.test`·`payment@example.test`·`refund@example.test`는 권한별 계정입니다. 가입 시 가상 `@example.test` 이메일만 사용합니다. 새 계정 자녀 목록은 비어 있으며 법정대리인 동의 후 최대 3명까지 등록할 수 있습니다. P02에 따라 다른 보호자의 기존 학생 연결은 제공하지 않습니다.

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
- JSON·SSE 모두 만료 시 refresh 1회를 공유하며, 원 요청은 한 번만 재시도합니다. 실패 시 메모리 토큰을 지우고 재로그인 오류를 표시합니다. 실제 httpOnly 쿠키/역할 유지 검증은 백엔드 통합 대상입니다.
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
# 별도 운영 build + preview 주소. 실제 backend 대신 404 응답 스텁으로 경로/오류 표시 확인
node tests/api-mode-browser.mjs
```

이슈 #7은 `docs/report/issue-7-student-completion.md`, #8·#9 구현/예외/검증/미확정 사항은 `docs/report/issue-8-9-parent-admin.md`에 기록합니다. 실제 backend 통합·원격 CI·배포 검증은 별도입니다. 커밋·push·PR은 보류 중입니다.

## 미체크 후속 회귀

`docs/report/unchecked-followup.md`에 추가 구현과 최신 검증을 기록했습니다. 단위 테스트 48개, 학생 브라우저 23개, 학부모·관리자 브라우저 27개를 검증했습니다. 두 브라우저 스크립트 모두 `QA_FILTER`로 이름 일부를 지정해 특정 사례만 재실행할 수 있습니다.

신규 가입 자녀는 FREE이므로 연속 시나리오는 먼저 무료 분석 차단을 검증합니다. 그 뒤 **DEV+MSW에서만** 등록되는 `sagomungchi:test-child-plan` 테스트 이벤트로 현재 가상 계정의 자녀 플랜을 설정해 프리미엄 전제의 분석·근거·다운로드를 확인합니다. 이는 구독 API나 체험 상품이 아니며 UI에 결제 성공을 표시하지 않습니다. 새 계정 기본 플랜과 실제 사용자 권한을 바꾸지 않습니다. `tests/production-mocks.mjs`는 이 이벤트와 설정 함수도 운영 번들에서 제외되는지 검사합니다.
