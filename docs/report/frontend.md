# 웹 프론트 (#7·#8·#9·#59, 테마·대시보드·QR 시연)

통합 원본: frontend-backend-ux-alignment, issue-7-fe-common, issue-7-student-completion, issue-8-9-parent-admin, unchecked-followup, pr-fe-workspace, issue-59-student-device, parent-dashboard, student-theme-world, qr-device-demo

실행 방법과 브라우저 테스트 경로는 [frontend/web/README](../../frontend/web/README.md), 목업 계약은 [API 명세](../design/api-spec.md) 3.7~3.12.

## 1. 공통 기반 (#7)

- MSW는 DEV + `VITE_API_MOCK=true`에서만 동적으로 기동하고 앱 데이터 경로는 항상 실제 API 어댑터. API 오류 때 목업 데이터로 자동 전환하지 않음. `tests/production-mocks.mjs`가 운영 번들에 MSW·fixture·개발 worker가 없는지 검사
- 토큰은 메모리에만. 만료 시 refresh 1회를 공유하고 원 요청은 1회만 재시도, 실패하면 재로그인 안내. 멱등 키·초안 버전 유지
- 계층: presentation → data(API 어댑터·Query 훅) → domain(화면 규칙). 어댑터는 응답의 최소 필드를 검사하고 불일치는 계약 오류로 표시
- 명세에 없는 DTO는 확정 계약처럼 가정하지 않고 api-spec 목업 절에 먼저 기록
- 웹 단위 테스트는 Node 내장 type stripping으로 실행(`npm test`). `.tsx`·CSS는 Node에서 import할 수 없어 화면 테스트는 Playwright 스크립트(수동)

## 2. 학생 화면 (#7·#59, 테마)

- 역할별 URL·가드, 6종 입력, 상태별 SSE 피드백·재시도(AI 실패는 같은 answerId의 feedback만 재요청), 마무리·난이도 필수 돌아보기, 초안 자동 저장·409 비교(입력 보존), 새로고침 시 초안 복원
- 메모(P05): 서버 초안에 저장하되 학생 본인만 열람. 학생이 고른 답변 칸(서술 생각 칸, 풀이 최종 답·각 단계, 논술 네 칸)에 복사한 글만 제출. 원본 메모·기존 입력 보존, 빈 메모·길이 초과·제출 후·충돌 중에는 복사 비활성. 선택형 입력으로 글을 변환하지 않음
- 좁은 화면(390×500)에서 제출 버튼이 가려지던 문제는 앱 클립을 `overflow: clip`, 작성기 헤더를 sticky로 수정
- 테마(생각 지도): 홈은 오늘의 미션 카드 + 다섯 생각 유형 지도("끝낸 미션 n"은 홈 응답의 미션 상태로 센 수, 레벨·점수 아님). 꾸미기(테마 5종·캐릭터 5종)는 홈의 창에서만, 고르는 즉시 반영·저장(`/students/me/preferences`, api-spec 3.12 목업). 캐릭터는 질문·되묻기·생각 열기를 말풍선으로 보여 주는 역할만(되묻기 출처 표시 유지). 문제 화면은 위아래 배치 유지(사용자 피드백). 학년·단계는 자녀 정보·시도 상태에서 정해지며 아이가 바꿀 수 없음
- 학생 PIN 로그인(`/student/login`): 미등록 기기는 등록 코드·기기 이름만(`?code=`로 QR 링크 자동 입력), 등록 기기는 프로필 선택 → 숫자 키패드 PIN(물리 키보드도 가능). 자녀가 1명이면 프로필 선택 생략. 오류 코드별 안내(`STUDENT_PIN_INVALID` 남은 기회, `STUDENT_PIN_LOCKED` 키패드 숨김, `STUDENT_PIN_NOT_SET` 동석 로그인 안내, `STUDENT_DEVICE_INVALID` 재등록)
- 학생 access 만료·새로고침은 refresh 없이 `/student/login`으로 이동하고, PIN 뒤 원래 경로로 복귀(토큰·입력 원문은 저장하지 않음). `/auth/student/*`의 401은 로그인 단계 오류라 재로그인 신호로 바꾸지 않음
- PIN 로그인 응답의 `child.childId`와 동석 응답의 `child.id`는 어댑터 경계에서 정규화

## 3. 학부모 화면 (#8, 대시보드)

- 가입·동의 문서 조회와 `{documentId, version, agreed}` 전송, 자녀 등록(법정대리인 동의 포함, 최대 3명). P02에 따라 다른 보호자의 기존 자녀 연결(`/children/link`)은 만들지 않음
- 자녀·기간을 URL 쿼리로 대시보드·분석·리포트 간 유지하고 응답의 실제 기간을 표시. 자녀 변경 시 이전 자녀 결과 비노출(분석 중이면 AbortSignal로 취소)
- 분석 대화: SSE `status·delta·clarification·result·error·done`. delta는 임시 표시 후 result로 교체, error·화면 이탈 시 폐기. 실패 메시지만 재시도. 삭제된 근거(`available:false`·410)는 이용 불가 표시
- 주간 리포트: 생성 상태 구분, 상세·근거, 서버 URL 기반 PDF·Markdown 다운로드, 재생성 후 이전판이 반환되면 새 판 완료로 표시하지 않음. 저녁 질문은 응답 필드만 사용
- 무료 자녀는 분석 대화 잠금·리포트 수치만. 연속 시험의 프리미엄 전제는 DEV+MSW 전용 가상 자녀 설정(결제·무료 체험 구현 아님)
- 이용권 표시 기준(#134): core `/children`에는 `plan`이 없다(api-spec 5.3). 이용권 계약(#129) 전까지 실서버의 `plan`은 미확인("이용권 확인 필요")으로 두고 무료로 단정하지 않는다. 화면 제한은 `plan: FREE`가 명시된 경우(목업 fixture)만 적용하고, 리포트 서술·저녁 질문·생각 유형 요약은 서버 응답에 있는지로 표시한다(무료는 서버가 `narrative: null`, api-spec 2.5). 서술이 있으면 이용권과 관계없이 숫자·인용 대조 결과를 검사한다. 분석 대화의 이용 가능 여부도 서버 응답(오류 코드)을 따른다
- 대시보드 시안: 왼쪽 메뉴(대시보드·공책, 기록에 물어보기, 주간 리포트, 정보 관리, 자녀 기기·PIN), 위쪽 자녀 선택. 지표는 서버 Metric 그대로(비율은 표본 5건 이상일 때만, 아니면 분자/분모). "관찰된 생각 유형 n/5"는 `thinking-types`의 관찰 유형 수를 센 것(새 서버 계산 아님). "관찰 기록이며 사고력 진단이 아닙니다" 표시
- 자녀 기기 관리(`/parent/devices`): 자녀별 Google 재인증 → PIN 설정·재설정(잠금 해제), 페어링 코드·남은 시간·QR, 기기 목록과 해제. QR은 `/student/login?code=…` 링크 표시만(앱 내 스캐너 없음, `qrcode` 패키지로 클라이언트 생성). 자녀 기기에서 보호자 계정으로 로그인하지 않도록 안내

## 4. 관리자 화면 (#9)

- `/me.permissions`(CONTENT·SERVICE_OPS·PAYMENT_VIEW·PAYMENT_REFUND)로 메뉴·버튼 구분, 목 핸들러도 403 검사
- 운영 요약·작업 필터·이력·멱등 재처리(실패는 FAILED 유지)·큐/DLQ·감사 이력, 미션·기준표 버전 작성·검토·게시(422 `missingFields`)·중단, 학생 화면 컴포넌트를 재사용한 미리보기
- 모델 레지스트리·AI 사용량·오류 신고 검토·정정 목업. 장면 업로드 API가 없어 URI 입력만
- 미해결: 모델 레지스트리 요청 모양과 `/auth/login`·`/auth/signup`·`/me/reauth {password}` 잔존 호출([점검 기록 B12](audit.md), #93·#97)

## 5. QR 기기 등록 시연 (`npm run dev:qr`)

브라우저별 sessionStorage 목업으로는 다른 기기에서 등록할 수 없어 Vite 개발 서버(기본 5196)에 공유 기기 목업을 붙임. 실제 `npm run dev`는 core API(#58)를 사용하고 `dev:qr`만 시연 모드.

1. 보호자 노트북 `http://127.0.0.1:5196` → 시연 계정 로그인 → 자녀 기기·PIN
2. 자녀별 Google 본인 확인(개발 fixture) → PIN 설정
3. 등록 코드 만들기. QR 주소는 실제 Wi-Fi 어댑터 우선 제안(직접 변경 가능)
4. 같은 Wi-Fi의 태블릿 기본 카메라로 QR 읽기 → 기기 이름 → 등록 → PIN → 학생 홈
5. 보호자 기기 목록은 3초 간격 갱신, 해제하면 다음 PIN 로그인 거부

- 구현: `scripts/device-demo.ts`(서버 메모리 저장소, 코드 10분·1회, 기기 90일, PIN 5회 잠금, scrypt 해시), `scripts/device-demo-plugin.ts`(`/__demo/device` serve 전용 middleware, 크기 제한·동일 Origin·전용 헤더·no-store), `src/mocks/sharedDevice.ts`·`sharedRuntime.ts`(LAN HTTP에서 MSW 핸들러를 fetch 어댑터로 실행)
- 기기 식별은 HttpOnly·SameSite=Strict 임의 자격증명 쿠키(공개 deviceId를 자격증명으로 쓰지 않음). randomUUID·Web Locks 대체 경로는 개발 공유 목업 모드에만
- 한계: 공유 대상은 등록 코드·PIN·기기 목록뿐(답변·리포트는 브라우저별), 서버 재시작 시 초기화, 실제 태블릿 카메라·방화벽은 현장 확인 필요

```powershell
npm run build -- --mode qr-demo
node tests/production-mocks.mjs
npm run dev:qr            # 별도 터미널
$env:DEMO_URL='http://127.0.0.1:5196'
node tests/qr-device-browser.mjs
```

## 6. 남은 확인

- api-spec 3.8~3.12 목업 DTO의 백엔드 확정(학생 홈·대화·관리자·꾸미기 설정)
- 이용권 정보를 받을 API(core와 협의, #129). 확정되면 3장의 이용권 표시 기준을 그 계약으로 바꾼다([점검 기록 B11](audit.md))
- 장면 파일 업로드 방식 결정, 화면 단위 자동 테스트(Playwright 스크립트는 `npm test`·CI 밖)

## 관리자 화면 추가 — 2026-10-29

작업 브랜치: `feature/admin-screen-completion` · 기준 develop `26f3788`.
작업 디렉터리: `C:\Users\playdata2\Documents\GitHub\SKN34-FINAL-3TEAM-fe-integration`.

화면설계서 A00·A04·A10 중 현재 앱에 없던 관리자 로그인, 문의·공지 관리, 결제·환불·PG 대조 화면을 추가했다. 기존 `feature/admin-monochrome`의 레이아웃·로그인·UI 부품을 선별 재사용했고 실제 API 어댑터와 최신 모델·정정 로직을 유지했다. 다른 작업본은 변경하지 않았다.

- `/admin/login`: 개발 모드만 가상 이메일 계정. 실제 모드는 Google 인증 링크만 제공한다. 인증 응답으로 역할·시작 화면을 결정하며 URL로 관리자 권한을 부여하지 않는다.
- 관리자 전역: 흑백 좌측 메뉴, 권한별 노출과 직접 URL 접근 제한, 기간 선택, 태블릿 접이식 메뉴. 운영·작업·큐·오류 신고·모델·AI 사용량·감사·미션을 기존 최신 컴포넌트로 연결했다.
- `/admin/support`: 문의 선택 후 답변 POST, 완료 답변 재편집 차단. 공지/점검 작성·수정·종료와 공개 대상·기간 설정.
- `/admin/payments`: 환불 요청/거래 내역/PG 대조 탭, 페이지 이동, 체크리스트·최종 확인, 반려 사유와 조회/환불 승인 권한 분리.
- 실제 `PaymentController`의 승인 POST는 body 없이 Idempotency-Key를 사용한다. 반려는 `{reason}`. APPROVED/202는 PG 확인 중이며 COMPLETED만 환불 완료로 표시한다. 적격 여부는 서버가 재검증하며 UI에서 가짜 withinSevenDays·premiumUnused 값을 만들지 않는다.
- 실제 `SupportController`의 문의 상태 RESOLVED, `noticeId/kind/body/targetRoles/visibleFrom/visibleTo/endedAt`와 POST 답변 계약을 반영했다.
- 현재 core에는 `GET /admin/notices` 전체 목록이 없다. `GET /notices`의 관리자 대상 공개 공지 첫 20건과 로그인 세션에서 작성·수정한 공지만 관리한다. 예약/종료 공지 전체 조회 API는 후속이다.
- 새 기능은 실제 공개 API 어댑터를 호출한다. DEV는 별도 adminServiceHandlers가 가상 응답을 처리하고 운영 빌드에는 포함되지 않는다. 실서버 오류 때 데모 데이터로 자동 전환하지 않는다.

검증: 단위·계약 114개, TypeScript·운영 빌드·lint·운영 목업 제외 검사 통과. 관리자 브라우저에서 로그인·문의 답변·공지 생성/수정/종료·환불 PG 대기·거래/대조·권한 분리, 9개 화면×1440/1024/768/390의 가로 넘침을 확인했다. Google 관리자 로그인은 운영 빌드/API 대역으로 확인했다. 실제 DB·Google OAuth·PG 결제/취소 통합 검증은 하지 않았다. 청크 500kB 경고는 남아 있다.

직접 확인: `http://127.0.0.1:5242/admin/login` → 기본 `admin@example.test` / `demo-only` 로그인. `payment@example.test`는 결제 조회만, `ops@example.test`는 운영만 가능하다. 같은 LAN에서는 `http://192.168.0.125:5242/admin/login`(접근 가능한 네트워크일 때).
재실행: frontend/web에서 `npm run dev:qr -- --port 5242`.
새 브라우저 상태는 새로고침하면 초기화되는 개발 목업이며 실제 결제·환불은 발생하지 않는다.

증거: `C:\Users\playdata2\outputs\admin-completion-20261029-final`, `C:\Users\playdata2\outputs\admin-completion-20261029\inspection`.
로그인 디자인 검사 0FAIL/3WARN: 개발 서버 경고는 별도 운영 빌드 검사로 보완했고, 여백/캔버스 경고는 가운데 정렬된 400px 인증 폼을 유지하기 위해 수용했다. 학생 5개 테마는 변경하지 않았다.

추가 테스트: `tests/adminScreenCompletion.test.ts`, `tests/admin-completion-browser.mjs`. 기존 API 모드 브라우저에 관리자 전용 Google 로그인 검증을 추가했다. 사용자 요청에 따라 관리자 화면 보완 PR로 제출한다. 게시 전 최신 develop을 일반 merge로 반영하며 원본 작업본은 보존한다.

추가 UI 수정: 큐·DLQ와 작업 재처리의 중복 선택 조건을 제거했다. 학부모 로그인 하단의 도움말·관리자 링크, 가입 버튼, 데모 안내를 별도 행으로 나누고 1440/1024/768/390px에서 간격과 가로 넘침을 확인했다.

### 2026-10-30 develop 동기화 및 PR 검증

- 기존 작업을 커밋으로 보존하고 최신 develop `5f32ee6`(#82·#145·#146 포함)을 일반 merge로 반영했습니다. 충돌 파일 없이 합쳐졌고, 이번 PR의 변경은 프론트·화면설계서·보고서입니다.
- 실제 #145 DTO의 nullable 정답/안내/URI/요소 설명과 공개 기준표 버전을 대조했습니다. 미션·기준표의 공개 포인터는 재게시까지 유지하며, 비공개 편집 상태도 보존합니다.
- 최신 #82 피드백 처리와 #146 judgmentId 기반 신고를 유지합니다. 임시 대기였던 판정 ID 연결은 이제 최신 develop에 포함됩니다.
- 단위·계약 테스트 124개, lint·TypeScript·운영 빌드·운영 목업 제외 검사 통과. 브라우저 관리자 36조합·학습/미션 편집 9조합에서 가로 넘침과 실행 오류 없음. 운영 빌드 다중 탭 인증 회귀도 통과했습니다.
- 브라우저 검증은 가상 데이터/API 대역이며 실제 core/learning/DB·Google OAuth·PG 통합 성공을 뜻하지 않습니다. JS 청크 500kB 경고는 남아 있습니다.

### #170 시연 학생 진입의 계층 분리 (2026-10-30)

- `DemoStudentEntry`의 직접 `apiFetch`·TanStack Query 설정과 목업 fixture 참조를 제거했습니다. 기존 `data/studentDevice/api.ts`의 시연 준비 함수와 `queries.ts` mutation 훅을 사용합니다. 새 계층·라이브러리는 추가하지 않았습니다.
- data 계층에서 시연 기기 준비 결과의 deviceId를 검증하고, 성공할 때만 시연 PIN을 반환합니다. mutation 성공 후 기존 `student-device` 쿼리를 무효화해 프로필/PIN 화면을 다시 읽습니다. 준비 실패·잘못된 응답은 성공 안내로 바꾸지 않습니다.
- 개발 화면은 기존 DEV+MSW 조건부 지연 로딩을 유지하며 준비 후 PIN을 표시합니다. `/auth/student/demo-device`의 요청·응답은 변경하지 않았습니다. 실제 인증 API 계약 변경은 없습니다.
- `npm test` 125개·lint·운영 빌드·`node tests/production-mocks.mjs` 통과. 운영 JS에 시연 경로·fixture·시연 PIN 문자열이 포함되지 않음을 확인했습니다. JS 청크 500kB 경고는 기존과 같습니다.
- Chrome 가상 데이터 검증: 시연 준비 → 프로필 재조회 → PIN 안내 → 5090 로그인 → 학생 홈 통과. 캡처는 `C:/Users/playdata2/outputs/issue170-20261030/`에 보존했습니다. 실제 DB/OAuth 검증을 수행한 것은 아닙니다.
