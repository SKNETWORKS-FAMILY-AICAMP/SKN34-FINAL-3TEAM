# 웹 프론트 (#7·#8·#9·#59 이후)

실행 방법과 브라우저 테스트 경로는 [frontend/web/README](../../frontend/web/README.md), 화면 계약은 [API 명세](../design/api-spec.md) 2·3·5장. 브라우저 화면 테스트는 MSW 합성 데이터 기준이고 실서버 흐름은 [testing-ci](testing-ci.md) 2장 E2E 범위만 검증. 2026-11-06 결정 화면(이번 주 테마·되돌아보기·커뮤니티·포인트·일일 리포트 상세·관리자 주간 테마·꾸미기 아이템)은 #393~#395로 구현([서비스 기획 방향](service-direction.md))

## 1. 공통 기반 (#7)

- MSW는 DEV + `VITE_API_MOCK=true`에서만 동적으로 기동하고 앱 데이터 경로는 항상 실제 API 어댑터. API 오류 때 목업 데이터로 자동 전환하지 않음. `tests/production-mocks.mjs`가 운영 번들에 MSW·fixture·개발 worker가 없는지 검사
- 토큰은 메모리에만. 만료 시 refresh 1회를 공유하고 원 요청은 1회만 재시도, 실패하면 재로그인 안내. 멱등 키·초안 버전 유지
- 계층: presentation → data(API 어댑터·Query 훅) → domain(화면 규칙). 어댑터는 응답의 최소 필드를 검사하고 불일치는 계약 오류로 표시
- 명세에 없는 DTO는 확정 계약처럼 가정하지 않음
- 웹 단위 테스트는 Node 내장 type stripping으로 실행(`npm test`). 화면 테스트는 `npm test`와 분리된 `npm run test:browser`(Playwright 개발 의존성 고정, 별도 CI job, 실패 시 trace·스크린샷 보관). 1440×900·1024×768, 새 패널은 390×844도 포함
- `tsconfig.tests.json`을 build reference에 포함해 테스트·Playwright 설정까지 타입 검사. MSW 3의 `onUnhandledFrame`으로 미처리 요청을 오류로 검사
- 훅 테스트(#141)는 실제 React root와 TanStack Query로 키·범위·disabled·실패·무효화·낙관 갱신 롤백·폴링 종료·세션 복원을 검증

### MSW 목업 규칙

- 개발 전용 MSW fixture(이메일 로그인 등)는 운영 계약이 아님. 로그인·토큰·`/me`·`/children`·동의·리포트·모델 레지스트리·AI 사용량은 api-spec 5장과 core OpenAPI 기준
- `GET /children`의 실제 식별자는 `id`. 목업의 `childId`·`plan`은 계약이 아님(core는 `plan`을 만들지 않음)
- 시나리오 선택은 개발 브라우저 내부 이벤트로 전달하며 `/api/v1`에 가짜 경로를 추가하지 않음
- 새로고침 시험은 sessionStorage의 가상 fixture 상태만 복원. 실제 아동 정보·토큰·비밀번호는 저장하지 않음
- 개발 시나리오 PARTIAL·RETHINK·CORRECT는 고정 UI 시험 상태이며 모델 판정이 아님
- 관리자 목 핸들러도 `/me.permissions`로 403 검사. 브라우저 목업 시험은 서버 집계·연동 검증을 대신하지 않음

### 번들 분할 (#247)

라우터에서 학생(`ClassroomApp`)·학부모·관리자 작업 공간과 로그인 외 계정·결제 결과·가입·관리자 로그인 화면을 `lazy`로 받음. 학생 기기 로그인(`DeviceLogin`)·도움말·공지·신고 화면은 첫 묶음. 로딩 중 `RoleLayout`과 최상위 `Suspense`가 "화면을 불러오고 있습니다." 표시. vendor chunk는 분리하지 않음(분할만으로 500kB 경고 해소, `index` 686kB → 278kB).

### data 계층 정리 (#170·#255)

- 신고·문의 결과 조회는 `data/support/{api,queries}.ts`, 결제 결과 조회·폴링·승인·빌링 등록은 `data/payment/queries.ts`, 결제창 복귀 대기 정보는 `data/payment/checkoutStorage.ts`. `domain/payment.ts`에는 순수 검증(`validPending`·`validBilling`·`checkoutConfirmation`·`billingConfirmation`)만
- 결제 폴링 조건: PENDING·CONFIRMING·APPROVED+RECOVERY_REQUIRED, 3초, 첫 응답 뒤 최대 10회, 오류 시 중단. StrictMode 중복 요청은 공유 Map. 승인 응답을 결과 캐시에 넣어 승인 직후 상태 재조회 없음
- 시연 학생 진입(`DemoStudentEntry`)은 `data/studentDevice/api.ts`·`queries.ts`만 사용. deviceId를 검증하고 성공할 때만 시연 PIN 반환, 성공 후 `student-device` 쿼리 무효화

### 실시간 알림 (#239)

`data/notifications.ts`의 `useNotificationStream`을 `RoleLayout`에서 호출해 학부모·관리자 로그인 중 `GET /notifications/stream` 1개 유지(학생, 동의·자녀 등록 전 학부모, 로그아웃 상태는 요청 안 함). `ready`·`notification`을 받으면 `['parent','notifications']` 캐시만 무효화해 알림 화면과 메뉴의 읽지 않음 수(`unreadOnly=true` 첫 쪽)를 다시 읽음. 서버가 5분 뒤 닫으면 1초 뒤, 실패가 이어지면 2·4·…·30초 간격 재연결, 401·403은 중단. 이벤트를 캐시에 직접 병합하지 않는 이유는 api-spec 2.7의 "id로 병합·Last-Event-ID 없음" 규칙을 목록 API 한 곳에서 지키기 위해서.

## 2. 학생 화면 (#7·#59, 테마)

- 역할별 URL·가드, 6종 입력, 상태별 SSE 피드백·재시도(AI 실패는 같은 answerId의 feedback만 재요청), 마무리·난이도 필수 돌아보기, 초안 자동 저장·409 비교(입력 보존), 새로고침 시 초안 복원
- 메모(P05): 서버 초안에 저장하되 학생 본인만 열람. 학생이 고른 답변 칸(서술 생각 칸, 풀이 최종 답·각 단계, 논술 네 칸)에 복사한 글만 제출. 원본 메모·기존 입력 보존, 빈 메모·길이 초과·제출 후·충돌 중에는 복사 비활성. 선택형 입력으로 글을 변환하지 않음
- 좁은 화면(390×500)에서 제출 버튼이 가려지던 문제는 앱 클립을 `overflow: clip`, 작성기 헤더를 sticky로 수정
- 테마(생각 지도): 홈은 오늘의 미션 카드 + 다섯 생각 유형 지도("끝낸 미션 n"은 홈 응답의 미션 상태로 센 수, 레벨·점수 아님). 꾸미기(테마 5종·캐릭터 5종)는 홈의 창에서만, 고르는 즉시 반영·저장. 캐릭터는 질문·되묻기·생각 열기를 말풍선으로 보여 주는 역할만(되묻기 출처 표시 유지). 문제 화면은 위아래 배치 유지(사용자 피드백). 학년·단계는 자녀 정보·시도 상태에서 정해지며 아이가 바꿀 수 없음
- 꾸미기 설정(#234): core `GET/PUT /students/me/preferences`(api-spec 3.12). 저장 실패 시 이전 모습으로 되돌린 뒤 "저장하지 못해서 전에 고른 모습으로 돌아갔어요." 안내. 꾸미기 보상화는 2026-11-06에 결정됨: `lake`·`mungchi` 외 테마·캐릭터와 캐릭터 아이템은 포인트 해금(유료 판매 없음, #389·#393 구현, [서비스 기획 방향](service-direction.md))
- 학생 PIN 로그인(`/student/login`): 미등록 기기는 등록 코드·기기 이름만(`?code=`로 QR 링크 자동 입력), 등록 기기는 프로필 선택 → 숫자 키패드 PIN(물리 키보드도 가능). 자녀가 1명이면 프로필 선택 생략. 오류 코드별 안내(`STUDENT_PIN_INVALID` 남은 기회, `STUDENT_PIN_LOCKED` 키패드 숨김, `STUDENT_PIN_NOT_SET` 동석 로그인 안내, `STUDENT_DEVICE_INVALID` 재등록)
- 학생 access 만료·새로고침은 refresh 없이 `/student/login`으로 이동하고, PIN 뒤 원래 경로로 복귀(토큰·입력 원문은 저장하지 않음). `/auth/student/*`의 401은 로그인 단계 오류라 재로그인 신호로 바꾸지 않음
- PIN 로그인 응답의 `child.childId`와 동석 응답의 `child.id`는 어댑터 경계에서 정규화
- 개발 전용 시연: `/student/login`의 "가상 학생으로 PIN 로그인 준비" → 임시 PIN **5090**. QR·보호자 기기 등록과 별도의 가상 학생/기기, 운영 빌드에는 시연 경로·fixture·PIN 문자열 미포함(`src/mocks/fixtures/studentPinDemo.ts`)
- learning 계약 반영(#82·#145): 돌아보기 화면 문구는 한글, 요청은 `EASY/NORMAL/HARD`. 자기 평가는 마무리 뒤·완료 전에만, `{checks:[{elementId,checked}]}` 일부 저장·false 변경 허용, 응답의 `selfChecked/aiChecked/quote`를 나란히 표시(FINAL_ANSWER 포함 서버 요소를 생략하지 않음). 풀이 답 뒤 `answerUnit` 고정 표시(요청 값에 결합하지 않음). 분류 그룹은 서버 categories label, 풀이·논술 입력 틀 이름은 서버 inputTemplate(답을 미리 채우지 않음). 신고는 실제 judgmentId가 있을 때만 표시
- 공개 설정·재시도 비교(#206·#207): 학생 메뉴 '공개 설정', 마무리 결과의 이전/이번 공책으로 연결. 공개 상태는 저장 성공 응답 기준 표시, 저장 중 중복 조작 차단, 실패를 기본값 저장 성공으로 표시하지 않음. 설정 변경 시 공유 브라우저의 parent/records/report 캐시 제거. 부모 화면은 자녀별 읽기 전용 안내. 비교는 같은 폭 두 공책·20px 간격, 700px 이하 한 열. 첫 시도/기준 변경/조회 실패를 정상 비교와 구분
- 생각 활동(#240, 담당자 결정: 섬 화면 안과 별도 화면 모두): core `GET /students/me/thinking-activities`를 `useThinkingActivities`로 연결(키가 `['records', …]` 아래라 시도·돌아보기 저장 뒤 함께 갱신). 학생 메뉴 "생각 활동"(최근 7일·지난주, 생각 유형별 묶음), 미션 고르기에서 섬을 고르면 "최근 7일 이 섬에서 해 본 생각". 미션 제목과 돌아보기(난이도·내가 쓴 말)만 표시, 숫자 레벨·등급·순위·점수 없음

## 3. 학부모 화면 (#8, 대시보드)

- 가입·동의 문서 조회와 `{documentId, version, agreed}` 전송, 자녀 등록(법정대리인 동의 포함, 최대 3명). P02에 따라 다른 보호자의 기존 자녀 연결(`/children/link`)은 만들지 않음
- 자녀·기간을 URL 쿼리로 대시보드·분석·리포트 간 유지하고 응답의 실제 기간을 표시. 자녀 변경 시 이전 자녀 결과 비노출(분석 중이면 AbortSignal로 취소)
- 분석 대화: SSE `status·delta·clarification·result·error·done`. delta는 임시 표시 후 result로 교체, error·화면 이탈 시 폐기. 실패 메시지만 재시도하며 재시도는 core `ConversationController.retry`처럼 본문 없이 POST(저장된 메시지의 원래 질문·범위 사용). 요청은 `scope.childId`를 명시. 삭제된 근거(`available:false`·410)는 이용 불가 표시
- 예시 질문(#240): `GET /agent/example-questions` 다섯 문구를 버튼으로, 고르면 질문을 채우고 현재 자녀·기간 범위로 전송. `available=false`(기록 없음)는 비활성화하고 가능 범위 안내
- 주간·일일 리포트(#394: 리포트 메뉴 종류 선택으로 일일 리포트, 일일 상세에서 "이 리포트로 물어보기"): 생성 상태 구분, 상세·근거, 서버 URL 기반 PDF·Markdown 다운로드, 재생성 후 이전판이 반환되면 새 판 완료로 표시하지 않음. 저녁 질문은 응답 필드만 사용
- 이용권 표시(#134·#129): 화면에서 `child.plan`으로 리포트 표시를 판단하지 않음. core가 현재 상품 권한으로 선택한 `narrative`·`eveningQuestion` 존재 여부로 표시(무료는 `narrative: null`). 서술이 있으면 숫자·인용 대조 결과를 검사. 분석 대화 이용 가능 여부도 서버 오류 코드를 따름. 별도 브라우저용 이용권 API 없음
- 대시보드: 왼쪽 메뉴(대시보드·공책, 기록에 물어보기, 주간 리포트, 정보 관리, 자녀 기기·PIN), 위쪽 자녀 선택. 지표는 서버 Metric 그대로(비율은 표본 5건 이상일 때만, 아니면 분자/분모). "관찰된 생각 유형 n/5"는 `thinking-types`의 관찰 유형 수. "관찰 기록이며 사고력 진단이 아닙니다" 표시
- 자녀 기기 관리(`/parent/devices`): 자녀별 Google 재인증 → PIN 설정·재설정(잠금 해제), 페어링 코드·남은 시간·QR, 기기 목록과 해제. QR은 `/student/login?code=…` 링크 표시만(앱 내 스캐너 없음, `qrcode` 패키지로 클라이언트 생성). 자녀 기기에서 보호자 계정으로 로그인하지 않도록 안내
- 계정 관리: 로그인 복구 안내, 자녀 연결 해제·정보/기록 삭제 요청, 탈퇴 사전 확인·Google 재확인·접수 상태 확인. 삭제·탈퇴 접수와 실제 삭제 완료를 구분. 자녀 이관(#289)은 대상 조회/목록/요청/수락/거절/취소/일괄 취소, 요청·수락의 재인증 헤더, 비활성 기능 404·이미 처리된 요청 409 전파
- 도움말·공지·문의·오류 신고와 처리 결과 확인을 역할별로 연결. 문제풀이·리포트·대화 화면에서 관련 항목을 선택한 상태로 신고(커뮤니티 공유물 신고 `COMMUNITY_POST`, #393)

## 4. 관리자 화면 (#9)

- `/admin/login`: 개발 모드만 가상 이메일 계정, 실제 모드는 Google 인증 링크만. 인증 응답으로 역할·시작 화면 결정, URL로 관리자 권한을 부여하지 않음
- `/me.permissions`(CONTENT·SERVICE_OPS·PAYMENT_VIEW·PAYMENT_REFUND)로 메뉴·버튼·직접 URL 접근 구분. 흑백 좌측 메뉴, 기간 선택, 태블릿 접이식 메뉴
- 운영 요약·작업 필터·이력·멱등 재처리(실패는 FAILED 유지)·큐/DLQ·감사 이력, 모델 레지스트리(구조화된 평가 근거, 승인·활성화·되돌리기)·AI 사용량(호출 종류·미집계 비용 구분)·오류 신고 검토·정정
- 미션·기준표: 버전 작성·검토·게시(422 `missingFields`)·중단, 학생 화면 컴포넌트를 재사용한 미리보기. 정답 키는 입력 방식별 객체(고르기 `choiceIds` 1개, 순서 정답 순서 `choiceIds`, 분류 모든 항목 `assignments`, 풀이 `finalAnswer` 수, 서술·논술 `answerKey:null`)를 선택·순서·분류·수 입력으로 구성. `missingFields` 영문 코드(`rubric.elements[0].points` 등)는 화면에서 한글 표시, 모르는 코드는 원래 코드. 공개 중 수정·검토는 공개 상태와 `publishedVersion`·기준표 버전을 재게시까지 유지, 편집본과 공개본 구분 표시. 쓰기는 `answerUnit`·`inputTemplate`·`sceneUri/staticSceneUri`만(장면 업로드 API 없어 URI 입력). 전체 상태별 counts와 필터 목록 분리, 페이지 이동
- `/admin/support`: 문의 선택 후 답변 POST, 완료 답변 재편집 차단. 공지/점검 작성·수정·종료와 공개 대상·기간. 공지 목록은 SERVICE_OPS 전용 전체 목록(#242, 상태·대상 필터, 페이지)으로 예약·공개 중·종료 구분
- `/admin/payments`: 환불 요청/거래 내역/PG 대조 탭, 체크리스트·최종 확인, 반려 사유, 조회/환불 승인 권한 분리. 승인 POST는 body 없이 Idempotency-Key, 반려는 `{reason}`. APPROVED/202는 PG 확인 중, COMPLETED만 환불 완료. 적격 여부는 서버가 재검증하며 UI에서 가짜 `withinSevenDays`·`premiumUnused` 값을 만들지 않음
- DEV는 별도 adminServiceHandlers가 가상 응답 처리, 운영 빌드 미포함
- 장면 파일은 URI 입력만(업로드 방식 미정, api-spec 관리자 미션 "업로드 없음")

시연: `frontend/web`에서 `npm run dev:qr -- --port 5242` → `/admin/login` → `admin@example.test` / `demo-only`(`payment@example.test`는 결제 조회만, `ops@example.test`는 운영만). 개발 전용 `/review`는 요구사항 기능 ID 검색·역할별 시연 점검표.

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

## 6. 2026-11-06 결정 참여 기능 웹 (#389 웹 몫·#393·#394·#395, 에픽 #396)

[서비스 기획 방향](service-direction.md)의 확정 설계를 API 명세 2.4·2.5·2.8~2.11·3.12의 "구현 예정" 계약대로 웹에 먼저 붙였다. 서버(core #387~#392, learning #385·#386)는 아직 없어 MSW 목업으로만 확인했고, 명세의 "구현 예정" 표기는 서버 구현 때 지운다.

- 공통 데이터 계층: `domain/retention.ts`(읽기 함수가 모르는 사건·칸·요일·반응을 버림), `data/retention/`(학생·학부모 참여 API), `data/admin/retentionApi.ts`. 참여 조회는 `retry: false`로 학습 화면을 막지 않는다. 해금·신고는 Idempotency-Key, 같은 버튼 재시도는 같은 키
- 꾸미기(#389 웹, P22): 해금 목록 실패 시 기본·현재 저장된 모습만 유지하고, 다른 유료 항목은 해금 정보를 다시 확인할 때까지 선택을 막는다(2026-11-09 보완). `equipped`는 서버가 줄 때만 읽고 보낸다(#234 현행 응답 호환). 호수·뭉치는 목록이 없어도 열림
- 학생(#393): 생각 지도 위 이번 주 테마(월요일 도입 이야기·요일 상태·당일 문제), 토·일 되돌아보기(마무리 문제 다시 풀기, 놓친 문제는 표시만, 열면 주 1회 기록), 시작 맥락 `context`(`THEME_DAY`·`THEME_REVIEW`·`EXTRA`)는 고른 경로에서 붙이고 맥락 없는 기존 시작은 그대로 보낸다. 미션 고르기는 `EXTRA`(무료는 프리미엄 안내). 친구 생각(같은 미션 마무리 후 무작위 순서, 반응 4종, 신고), 공개 설정에 커뮤니티 공개(보호자 동의 전 비활성), 내 포인트(잔액·내역·적립 규칙). 순위·인기순·다른 학생 반응 수는 표시하지 않음
- 학부모(#394): 리포트 목록 일일·주간 구분(`periodType`, 없으면 주간), 일일 상세는 문제별 기록만(서술·저녁 질문 없음), 주간 상세에 테마 요약. "이 리포트로 물어보기"는 일일이면 `{childId, reportId}` 고정 대화(다른 날 질문은 새 대화 안내), 주간이면 리포트 기간 대화. 대시보드에 자녀 공유물·받은 반응·포인트, 정보 관리에 `COMMUNITY` 선택 동의·철회, 알림 유형 일일 2종
- 가입·계정 동의는 `isAccountDocument`(이용 안내·개인정보)로만 고른다. 서버가 동의 문서에 `COMMUNITY`를 더해도 가입 필수 항목으로 섞이지 않게
- 관리자(#395): 콘텐츠 메뉴에 주간 테마(작성·검토 요청·게시·중단, 422 `WEEKLY_THEME_PUBLISH_INCOMPLETE`의 `errors` 표시)와 꾸미기 아이템(등록·수정·판매 중단, 삭제 없음). 오류 신고 목록에 `COMMUNITY_POST` 대상 이름
- 목업: `mocks/fixtures/retention.ts`·`handlers/retention.ts`. 요일은 sessionStorage `sagomungchi:msw-weekday`(0=월~6=일)로 바꿔 볼 수 있다. 원문 비공개(#206)면 일일 리포트 문제별 원문도 숨긴다. 보호자 동의 확인은 법정대리인 문서만 본다(선택 동의 철회가 이용 제한으로 읽히지 않게)
- 확인: `npm run lint`·`npm test`(목업 계약 `tests/retentionMock.test.ts`, 읽기·어댑터 `tests/retention.test.ts`)·`npm run build`, 개발 서버 목업 모드에서 학생·학부모·관리자 흐름

## 7. 2026-11-09 리포트 생성 시각 안내 자정 변경 (#401)

[서비스 기획 방향](service-direction.md) 7장 결정(PR #399)에 맞춰 학부모 화면의 생성 시각 안내를 대상 기간이 끝나는 자정 기준으로 바꿨다. 학부모가 읽는 시각 그대로 일일은 "매일 자정", 주간은 "일요일 자정"으로 쓴다(서버 실행 시각은 다음 날·월요일 00:00 KST).

- 문구: 리포트 목록(`ParentReports`) 일일·주간 생성 안내, 주간 리포트 화면(`ParentFeatures`) 기간 안내·생성 중 안내, 대시보드(`ParentDashboard`) 빈 목록 안내
- 목업 `generatedAt`: 주간은 직전 주 종료 자정 `2026-10-26T00:00:00+09:00`, 일일은 대상일 다음 날 00:00 KST(`${date}T15:00:00Z`). 실서버 어댑터 테스트 예시 시각과 e2e 주간 cron 주석도 같은 기준으로 정리
- e2e `queueWeeklyReport`: #398(V30)로 NOT NULL이 된 `report_job.period_type`에 `WEEKLY`를 넣는다. outbox 명령은 `ReportGenerateWriter`처럼 주간이면 `periodType`을 생략
- API 경로·스키마 변경 없음
- core 스케줄 변경(#400) 반영 전까지 실서버는 07:00에 생성하므로 안내와 실제 생성 시각이 잠시 다를 수 있다

## 8. 남은 확인

- 참여 기능 실서버 연결: core·learning 구현 후 응답 필드(일일 `problems[]` 세부, 테마 요약, 게시 검사 `errors` 형식)를 다시 대조
- lint의 기존 `AdminOperations.tsx` immutability 경고 1건(재확인 필요)


## 9. #389 실제 reward 브랜치 계약과 꾸미기 연결 (2026-11-09)

- 기준: 초기 대조는 develop `b44e3c4e`와 `feature/reward-points`의 `a9cfd34b`, 최종 대조는 PR #407이 병합된 develop `8defa1f3`이다. 전달받은 `service-direction.md`는 초기 제안본이므로, 저장소의 최신 결정(테마 100·캐릭터 150)과 #389 `RewardController`·`LookUnlockService`·`StudentLookService`의 구현을 대조했다.
- 작업 중 PR #407이 develop에 반영되어 최종 로컬 병합에 포함했다. 최종 reward 구현 `7a0fb9c9`의 경로·응답·멱등 계약을 재대조했고 초기 브랜치의 V29 중복은 V35로 정리됐다. 적립 사건 호출 연결은 core 후속이며 웹에서 임의 적립 API나 잔액 계산을 추가하지 않는다.
- 조회는 잔액·원장 페이지(`page/size/totalElements`)·해금 목록·`assetKey`를 보존하고 `no-store`로 읽는다. 누락·비정상 응답을 0포인트나 무료 해금으로 처리하지 않는다. 내 포인트에서 20건 이후 내역도 조회할 수 있다.
- 해금은 비용·예상 잔액·환급 불가를 확인한 뒤 본문 없는 POST와 UUID 멱등 키를 보낸다. 성공 응답의 `itemKey/unlocked/balance`를 검사해 해당 학생 캐시에만 반영하고, 목록·원장·학부모 포인트를 다시 읽는다. 응답 유실 후 같은 항목 재시도는 같은 키를 쓴다. 성공 잔액은 서버 값만 사용한다.
- 꾸미기 목록/잔액/현재 설정 조회 실패를 화면 안에서 재시도할 수 있다. 목록 미확인 상태를 모든 항목 해금으로 읽지 않는다. 저장·해금 중 다른 조작을 막아 낙관적 저장의 경합을 줄인다. 테마·캐릭터만 바꿀 때 `equipped`를 생략해 기존 착용을 보존하고, 슬롯 변경은 네 슬롯을 함께 보낸다. 판매 중단된 보유 아이템은 계속 선택한다.
- 기존 생각 지도·캐릭터·글꼴·색을 유지하는 컴포넌트 확장으로 작업했다(새 디자인 추첨 없음). 질문은 "내 포인트로 어떤 꾸미기를 열어 사용할 수 있나"이며 상단 잔액과 해금 확인이 먼저 보인다. 실제 아이템 그림의 배포·URL 변환 계약은 없어서 `assetKey`를 임의 외부 URL로 해석하지 않는다. 기존의 슬롯 이름/선택 저장을 연결하고 그림 키를 보존한다.
- MSW도 실제 서버처럼 UUID 키·페이지 정보·그림 키·같은 키의 원래 해금 응답을 유지한다. 브라우저 검증은 `playwright.reward.config.ts`로 운영 빌드를 띄우고 MSW 없이 #389 모양의 합성 HTTP 응답을 사용한다. 실제 서버 검증과 구분한다. 실행: `npm run build` 후 `npm run test:rewards`.
- 실서버·PostgreSQL 검증은 로컬에서 미실행이다. 최종 develop에는 reward API가 포함됐지만 로컬 Docker 엔진을 사용할 수 없어 core/DB 적립·차감 종단 확인은 별도다.


검증 결과: 웹 단위 236건, 운영 빌드 API 대역 브라우저 9건(1440/768/390), 기존 MSW 브라우저 24건, 테스트 포함 TypeScript·lint·운영 빌드·운영 목업 제외 검사 통과. 실제 core/DB 적립·차감 종단 검증은 포함하지 않는다.

화면 점검: 기존 디자인의 컴포넌트 확장으로 새 방향 추첨 없이 적용했다. 상단의 뭉치·현재 테마·잔액을 이 화면의 표정으로 유지한다. 디자인 검사기에는 실제 모달의 그림자(`heavy-shadow`)·비활성 배경 가림(`covered-text`)·기존 개발 안내의 바깥 여백(`edge-text`)을 명시적 예외로 줬다. 결과는 0 FAIL·8 WARN이며, 경고는 기존 종이색·글꼴·강조 테두리·아이콘/테마 그림의 다색과 배경 화면의 안내 대비·숫자/제목 규칙이다. 이번 연동 작업에서 기존 학생 디자인 전체를 바꾸지 않기 위해 유지했다. 소스 lint의 `unlock` 경고는 사용자 문구가 아닌 API 식별자 오탐이다. 캡처/측정은 `frontend/web/.taste-skill/reward-after/`와 `reward-inspection/final/`에 로컬 보관했다.

## 10. #366·#367 모델 버전 운영 화면 (2026-11-09)

- 최신 develop `8defa1f3`(앞선 `239fc8cc`와 reward PR #407 포함)를 로컬 병합했다. 감사 통합 테스트·OpenAPI·API 명세·계약 테스트는 자동 병합됐으며 미해결 충돌은 없다.
- 공용 범위·사유·승인을 제거했다. 등록 폼의 평가 범위와 카드별 활성화/복귀 범위를 분리하고, 최초 활성화는 평가 범위에서 기본 미선택, 복귀는 원 승인 범위 안에서 선택한다. 사유·승인·재분석 계획과 처리 상태는 버전마다 독립이다.
- 평가셋·비교·검토·한계, 미적용 평가 범위, 비활성 이유를 함께 표시한다. ACTIVE는 core 활성화 완료만 나타내며 scoring replica별 로딩/readiness와 합성 추론은 별도 확인하도록 안내한다. 알려진 범위 목록 밖 값은 경고이며 유효한 키를 막지 않는다.
- 브라우저에서 2MB 이하 registration·manifest JSON을 읽어 모델별 편집 폼으로 가져온다. 각 항목을 기존 등록 API로 따로 보내며 파일 업로드·자동 활성화는 하지 않는다. `<버킷>` 일괄 치환, 전체 페이지 목록과 가져온 항목 간 중복, 필수 근거·범위 형식·manifest 일치·알 수 없는 요청 필드를 검증한다. 수정 표시, 항목별 422, 이름·버전에 연결한 409를 제공한다.
- 최상위/manifest `주의`를 한계 후보로 모으고 명시한 `evaluation.limitations`(빈 목록 포함)는 그대로 우선한다. core에도 기본 빈 목록 필드를 추가해 재조회 때 보존한다. MODEL artifactUri 필수 검증 및 OpenAPI 조건을 맞췄다.
- MODEL_VERSION 감사 detail은 name/version/scopes/reason/reanalysisPlanned/previousVersionId만 조회·펼치기 한다. 다른 대상의 원문과 허용되지 않은 필드는 반환하지 않는다. 관련 HTTP·저장 테스트를 추가했다.
- 전달받은 실제 `registration_1103.json`·`manifest.json`으로 1440/768/390에서 가져오기→버킷 치환→두 항목 개별 등록을 확인했다. 이 검증의 서버는 운영 빌드에 연결한 HTTP 대역이다. 실제 core/DB 등록·모델 산출물 해시·scoring 로딩 검증으로 간주하지 않는다. 기존 운영 ACTIVE 레코드는 변경하지 않았다. 원본 두 파일·가중치는 커밋하지 않았다.
- 검증: 웹 단위 243건, 기존 MSW 브라우저 24건, 모델 운영 브라우저 9건, 꾸미기 운영 브라우저 9건, TypeScript·lint·운영 빌드 통과. 모델·감사·주간 테마 계약 테스트 14건 통과. 브라우저 검증은 `npm run build` 후 `npm run test:models` / `npm run test:rewards`. 실제 파일 재현은 `MODEL_REGISTRATION_FILE`·`MODEL_MANIFEST_FILE` 환경 변수로 경로를 전달한다(없으면 합성 JSON 사용).
- 로컬 core 검증 제약: 설치된 JDK/Gradle이 프로젝트 컴파일 전 `Unable to establish loopback connection`으로 실패했다. 로컬 Docker 엔진도 사용할 수 없어 core/DB 테스트 통과를 주장하지 않는다. CI의 core 테스트 확인이 필요하다.
- #367 core 후속 범위: 등록 감사의 source·가져온 JSON SHA-256·변경 필드·산출물 해시 저장은 별도 계약/구현이 남는다. 웹은 가져온 원본의 SHA-256와 manifest 파일 해시를 확인용으로 표시하며, 아직 없는 감사 입력 필드를 임의로 POST하지 않는다. 따라서 이 변경으로 #367 전체 완료를 선언하지 않는다.


### #367 등록 감사 계약 통합 (2026-11-09)

PR #409 화면 구현을 core 등록 계약과 연결했다. 원본 registration·manifest 바이트의 SHA-256, 원본 항목 대비 수정 필드, 해당 모델의 산출물 파일 목록을 registration 메타데이터로 전달한다. 자동으로 채운 limitations도 원본과 다르면 변경 항목이다. 수동 등록에는 가져오기 메타데이터를 붙이지 않는다. limitations의 빈 줄·길이·개수와 manifest 상대 파일 경로를 서버 계약에 맞춰 검증한다.

위의 “감사 입력 필드 미연결” 기록은 PR #409 단독 상태다. 후속 통합 결과와 실제 core/DB 검증 절차는 [#367 등록 API 문서](ai.md#11-모델-등록-api-367)를 기준으로 한다.

## 11. #356 관리자 성취기준 고르기·성취수준 단계·미션 초안 화면 (2026-11-09)

#336 설계(기획서 6.2: 성취기준·성취수준 선택 → LLM 초안 → 자동 검사 → 검수 → 공개)의 web 몫과 #262 web 인계(요소 종류·code 고르기, 저장 전 code 검사). learning #353·ai #354·core #355의 공개 계약(api-spec 2.8)만 사용함.

| 화면 | 내용 |
|---|---|
| 미션 편집 `MissionManager` | 성취기준 줄바꿈 입력 → 표 조회·고르기(교과·학년군·검색어·쪽), 고른 성취기준마다 성취수준 단계(`levelScale` 3이면 A~C, 5이면 A~E, 고르지 않음 허용). 요소마다 종류(유형 공통·성취기준 고유·정답) → code → 연결 성취기준. 생성 방식(사람 작성·LLM 초안 채택) 표시. 검토 버튼 위에 학년·내용·행동(성취기준 동사) 확인 안내와 성취기준 문장·학년군·단계 목록 |
| 미션 초안 `MissionDraftManager` (메뉴 콘텐츠 › 미션 초안, CONTENT) | 요청(성취기준·단계·생각 유형·학년·입력 방식, 202) → 목록(상태·시도 `attempts/maxAttempts`) → 상세(입력, 회차별 검사 실패 사유, 실패 코드, 생성 버전, 마지막 초안) → 채택(`/admin/missions?missionId=`로 이동)·버리기 |

### 결정

| 항목 | 결정 | 근거 |
|---|---|---|
| 저장·요청 전 검사 | web이 learning 400 규칙을 먼저 검사: 요소 code 모양·중복·연결 성취기준 공백(기준표 저장), 학년군·논술 학년·단계 범위·표에 없는 코드(초안 요청) | core가 learning 400의 detail을 지우고 제목만 전달(`AdminLearningService.sanitize`)해 서버 오류만으로는 무엇이 틀렸는지 알 수 없음 |
| 게시 전 확인 | `missingMissionFields`를 learning `PublishSnapshot.missingFields`와 같은 코드·순서로 확장(`achievementLevels`·`rubric.elements.code`·`rubric.elements.standardCode`, 한글 이름 추가). 표·학년군·단계 수는 미션 성취기준 코드를 표에서 찾은 뒤에만 확인 | 표 조회 전·실패 때 틀린 누락을 띄우지 않음. 최종 판단은 서버 422 |
| 저장된 코드의 표 행 | 코드마다 `GET /admin/achievement-standards?q=<코드>`로 찾아 같은 코드만 사용 | 코드 목록 조회 API가 없고 미션당 성취기준은 1~3개 |
| 표준 요소 14개 | `domain/admin/missionStandards.ts`에 learning `Standards.kt`와 같은 표를 둠 | 표준 요소를 주는 API 없음. 바뀌면 두 곳을 함께 고쳐야 함 |
| 새 요소 기본 code | 고르기·순서·분류는 `ANSWER_KEY`, 그 밖에는 아직 안 쓴 유형 공통 요소, 다 쓰면 다음 `e`+숫자 | 이전 `crypto.randomUUID()`는 #262 저장 검사에서 항상 400 |
| 모양이 틀린 옛 code | 종류를 "확인 필요"로 보이고 저장 전 검사에서 막음(자동으로 바꾸지 않음) | 요소 의미는 관리자가 정함 |
| 열린 미션 | 로컬 state → URL `missionId` | 초안 채택 뒤 바로 편집 화면을 열고, 새로고침해도 유지 |
| 초안 상태 확인 | 생성 중 초안이 있으면 목록·상세를 5초마다 다시 조회(`useAdminQuery`에 선택 인자 `poll` 추가) | 생성 1회 15~70초, 주기 작업 10초(state-diagram 3.4) |
| 성취수준 저장 | `missionWritePayload`에 `achievementLevels` 추가, 고른 성취기준의 단계만 보냄 | 빠져 있어 미션을 고칠 때마다 저장된 단계가 지워졌음 |

### API 변경

경로·스키마 변경 없음. 기존 계약(api-spec 2.8·4.1, `contracts/openapi/learning-service.yaml`)의 성취기준 표·초안 경로를 web에서 처음 호출함. 미션 저장 본문에 계약에 있던 `achievementLevels`를 보내기 시작함(지워짐 수정). 사용량 호출 종류 이름에 `MISSION_DRAFT` 추가(learning.md 23절 인계).

### 목업

- 성취기준 표 일부 12행(learning `db/seed/achievement_standards.sql`에서 옮김), 초안 3건(`READY`·`CHECK_FAILED`·`FAILED`)
- 초안 요청은 202 `GENERATING`, 두 번째 조회부터 1회 시도로 `READY`(실제는 주기 작업). 채택은 learning `DraftRules`대로 교과·입력 틀·배점 1·`source: LLM_DRAFT`
- 기준표 저장은 learning처럼 code 모양·중복·`standardCode` 공백을 400, 미션 저장은 단계 모양을 400, 게시는 목업 표로 검사. 새 400은 core가 다시 쓴 제목만 줌
- 시연 미션 `content-1`의 성취기준을 표에 있는 `4과03-01`(단계 B)로, 요소에 연결 성취기준을 넣음

### 검증

- web `lint`·`test`(262건)·`test:types`·`build` 통과, 브라우저 `test:browser` 37건 통과(새 `tests/browser/admin-missions.spec.ts` 2건 × laptop·tablet, develop 2026-11-09 리베이스 뒤)
- 새 단위 테스트: `tests/missionStandards.test.ts`(code 모양·적합, 학년군·단계, 초안 요청 검사, 게시 전 확인, 저장 본문), `tests/adminMockLifecycle.test.ts`(표 조회·초안 요청→READY→채택·버리기 409, 기준표 PUT 400, 대괄호 코드 게시 422)
- 바뀐 테스트: `tests/learningAlignment.test.ts`의 자유 code `STEPS`를 `e2`로, 고르기는 `ANSWER_KEY`만(#262 규칙)
- 수동 스크립트 `tests/parent-admin-browser.mjs`·`tests/learning-alignment-browser.mjs`의 성취기준·요소 code 입력을 새 화면에 맞춤. 두 스크립트는 이번 변경 전 단계(학생 `내 생각과 까닭`, 학부모 `이 자녀로 학습 시작`)에서 멈춰 고친 부분까지 실행하지 못함(CI 대상 아님)
- 실제 core·learning·ai 연동 확인은 하지 않음(이 문서 9·10절과 같이 로컬 Docker·JDK 실행 제약). 완료 조건의 "실제 관리자 흐름 확인"은 #451로 넘김
