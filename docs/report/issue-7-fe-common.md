# 이슈 #7: 프론트 공통 기반 착수

> 이 문서는 공통 기반 착수 당시의 기록이다. 후속 구현 상태는 [학생 화면 검증](issue-7-student-completion.md)과 [#8·#9 기록](issue-8-9-parent-admin.md)을 따른다. 아래 미완료 표를 현재 최종 상태로 해석하지 않는다.

## 기준과 기존 작업 보존

- 이슈: https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/7
- 링크의 `event-34228175120`은 `kim-4480` 담당자 지정 이벤트이며, 작업 범위는 이슈 본문이다. 댓글은 조회 시 0개.
- 착수 시 `develop` / `origin/develop` 확인, fetch(prune 없음) 후 ahead/behind 0/0. 진행 중 Git 작업 없음.
- 이전 대화의 프론트 로컬 변경이 있으므로 pull·stash·reset 없이 보존한다. 이번 수정은 그 화면의 API 경계와 공통 기반을 바로잡는다.
- `feature/fe-common` → `feature/fe-student` 분리와 PR은 아직 수행하지 않는다. 기존 학생·학부모 로컬 시안까지 공통 기반 PR에 섞지 않도록 변경 분리가 먼저 필요하다. 커밋·push·GitHub 본문 체크 변경은 수행하지 않는다.

## 필독 및 정책 불일치

docs/README.md, architecture 3장, api-spec 인증·오류·SSE·로그인·학생 경로·3.1·3.2·3.6, functional-spec 공통 규칙·확정 정책·FN-LRN/JDG/DSH·NFR-UX, usecase 4.1~4.5 확인.

- 이슈의 P01/P03/P04 ‘확인 필요’는 현재 functional-spec 1.4에서 확정됐다. 학생 임시 계정 대신 학부모 → 자녀 → 학생 세션 흐름을 유지한다.
- 이슈의 ‘메모 클라이언트만’은 현행 P05·api-spec 2.2/3.6과 다르다. 현재 정책(학생 전용 초안 서버 저장, 제출·학부모·분석 제외)을 유지한다. 이슈 본문 정정은 담당자 확인 대상이다.
- 명세에 없는 DTO를 확정된 백엔드 계약처럼 가정하지 않는다. 공통 목업에 필요한 최소 필드는 api-spec에 **프론트 목업 계약 초안(백엔드 확인 대기)**으로 구분한다. 미정 입력 제출 필드는 차단한다.

## 이번 순서

1. 스켈레톤 apiClient/SSE/QueryClient 재사용, MSW 개발 의존성·worker 생성.
2. DEV + VITE_API_MOCK=true에서만 목 기동 후 렌더. 앱 데이터 경로는 항상 실제 API 어댑터.
3. 메모리 토큰 만료 시 단일 refresh와 동일 요청 1회 재시도, 실패 시 재로그인 안내. 멱등 키·초안 버전 유지.
4. 공통 상태·오류 컴포넌트와 인증/학생 기본 목 핸들러 검증.
5. 역할별 URL·레이아웃 정식 분리, 학생 홈/상태/장면/6종 입력/요소별 근거 등 나머지는 학생 단계에서 검증 후 체크.

## 체크박스 운영 기준

- `미착수 → 진행 중 → 검증 통과 → PR 반영`을 작업 기록에 남긴다. 이슈 체크박스는 구현과 해당 정상·예외 검증이 끝났을 때만 `[x]`로 바꾼다.
- 체크한 항목에는 파일, 실행 명령, 결과, PR/커밋(있을 때)을 근거로 남긴다. 일부 구현이나 미확정 계약이 있으면 체크하지 않는다.
- ‘공통 기반 먼저 PR’은 실제 PR이 만들어져야 완료다. 로컬 성공·목업 성공은 실제 API·원격 CI·배포 성공과 구분한다.
- GitHub 수정 권한이 있으면 체크박스를 직접 클릭하거나 본문 Edit에서 `- [ ]` → `- [x]`로 수정할 수 있다. 권한이 없다면 검증 근거를 작성자에게 전달한다. 착수만으로 체크하지 않는다.

## 검증 결과

- `npm test`: 17개 통과. 기존 답변/초안/권한 12개 + 동시 refresh 공유·실패·SSE 재시도·1회 제한·로그아웃 경합 5개.
- `npm run lint`: 경고·오류 없음. `npm run build`: 통과.
- `VITE_API_MOCK=true npm run build` 후 `node tests/production-mocks.mjs`: 운영 JS에 MSW·핸들러·가상 학생 fixture 없음. public 원본은 보존하고 빌드 복사본의 mockServiceWorker.js만 제외됨.
- Chromium에서 `VITE_API_MOCK=true` 개발 서버(5175) 검증: 정상 제출·AI 실패 후 피드백만 재요청·추가 답변 2회·마무리·난이도 필수 돌아보기·공책 복귀, 409 비교·저장 실패·나가기 확인 통과.
- 브라우저에서 관찰된 `/api/v1` 요청 61건 모두 실제 Service Worker 응답(`fromServiceWorker`) 확인. 답변 제출·피드백도 HTTP/SSE 경로 사용. pageerror 0건.
- 기본 API 빌드에서 404 응답 스텁으로 오류 표시·예시 자동 대체 없음 확인. 실제 core/쿠키/DB/LLM 통합·원격 CI·배포 검증은 수행하지 않음.
- 캡처/검증 JSON: 저장소 외부 신규 `C:/Users/playdata2/outputs/issue7-msw-20261026/verified/`. 이전 대화의 시안/캡처는 보존.
- MSW 3.0.3 설치 타입과 공식 문서에 맞춰 `msw/http`, `setupWorker`, `onUnhandledFrame` 사용. 출처: https://mswjs.io/api/setup-worker/ 및 https://mswjs.io/guides/integrations/browser

## 이슈 체크박스에 옮길 때의 현재 판정

| 이슈 항목 | 상태 | 체크 판단 |
|---|---|---|
| msw 개발 의존성·worker 생성 | 검증 통과 | 체크 가능 |
| DEV + VITE_API_MOCK 동적 기동·운영 제외 | 검증 통과 | 체크 가능 |
| 핸들러 경로·typed fixture·ReadableStream | 기본 구현/흐름 검증 통과 | 목업 DTO 초안의 백엔드 확인 전까지 보수적으로 미체크 |
| 역할별 레이아웃·라우팅 | 기존 시안 내부 화면 전환만 존재 | 미체크: 역할별 URL·가드·레이아웃 분리 필요 |
| 로그인·역할 시작·refresh·재로그인 안내 | HTTP/SSE 갱신·실패 단위 테스트 통과 | 묶인 항목 전체(역할 라우팅 포함) 검증 전 미체크 |
| QueryState·ProblemDetail·재시도 | 공통 컴포넌트 및 일부 화면 연결 | 전체 상태별 화면 확인 후 체크 |
| 학생 홈 API·목록 수행 상태·진행 위치 | 미완료 | 미체크 |
| 장면·6종 입력·근거·마무리 체크리스트 | 부분 구현/계약 미정 포함 | 미체크 |
| 전체 상태 시나리오 | HELD·AI 실패·초안409 검증 | CORRECT/PARTIAL/RETHINK/RUNNING-only/finish409 등 전부 확인 전 미체크 |
| VITE_API_MOCK 기본 학습 전 과정 | 서술형 대표 경로 검증 통과 | 대표 경로 완료 근거로 사용, 6종 전체 완료와 구분 |
| 목 OFF 시 실제 core 요청 | 기본 API 빌드 경로·404 UI 검증 | 실제 core 서비스 정상 통합 완료로 체크하지 않음 |
| 공통 기반 PR | 미수행 | 미체크: 기존 로컬 시안과 변경 분리 후 진행 |

GitHub 이슈 본문의 체크박스 자체는 이 작업에서 수정하지 않았다. 위 표는 체크 가능한 근거와 남은 범위를 구분하는 로컬 기록이다.
