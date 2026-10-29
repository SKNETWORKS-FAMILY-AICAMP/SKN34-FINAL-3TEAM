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
- 실서버 모드 계약 차이: `/children`의 `plan` 부재로 저녁 질문 숨김, 리포트 목록 봉투, `PATCH /children` 재인증 헤더([점검 기록 B11·B13](audit.md))
- 장면 파일 업로드 방식 결정, 화면 단위 자동 테스트(Playwright 스크립트는 `npm test`·CI 밖)
