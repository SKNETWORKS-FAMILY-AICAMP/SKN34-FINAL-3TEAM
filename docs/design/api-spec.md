# API 명세서

- 근거: [기능명세서](functional-spec.md), [유스케이스](usecase.md), [프로젝트 기획서](<../outputs/프로젝트 기획서_사고뭉치_최종.pdf>), [아키텍처 설계](architecture.md)
- 범위: 공개 API(core-service, 웹이 호출) 전체 + 서비스 간 내부 API
- 우선순위: 유스케이스 우선순위(핵심·제안·우선1·우선2·선택)
- `(P04)` 형태는 확정 정책 번호, 내용은 [기능명세서 1.4](functional-spec.md#14-확정-정책)
- 구현 시 이 문서 → `contracts/openapi/<service>.yaml` 순으로 반영

---

## 1. 공통 규칙

### 1.1 기본
| 항목 | 규칙 |
|---|---|
| Base URL | 공개 `/api/v1` (core만 외부 노출), 내부 `/internal` |
| 형식 | JSON(UTF-8), 필드 camelCase, 시각 ISO-8601 오프셋 포함(`2026-11-02T19:00:00+09:00`), 날짜 `YYYY-MM-DD`(KST) |
| 식별자 | 문자열 ID(UUID). 학부모 경로의 `{childId}`는 학생 ID |
| 기간 조회 | `from`, `to`(날짜, 양 끝 포함). 응답에 실제 조회 기간 `period` 반환 (FN-DSH-10) |
| 목록 | `page`(0부터), `size`(기본 20, 최대 100) → `{items, page, size, totalElements}` |
| 스트리밍 | `text/event-stream`, 각 이벤트 `event: <이름>` + `data: <JSON>` (1.6) |

### 1.2 인증·권한
- 인증: `Authorization: Bearer <accessToken>`. access token은 메모리 보관, refresh token은 httpOnly·Secure·SameSite=Strict 쿠키
- 학생 기기 자격증명: 학부모가 등록한 기기에만 httpOnly·Secure·SameSite=Strict 쿠키(`student_device`, path `/api/v1/auth/student`)로 발급. PIN 로그인에만 사용하며 그 자체로 API 접근 권한 없음 (P01, 3.11)
- 역할: `STUDENT`, `PARENT`, `ADMIN`. 관리자 권한은 승인 계정에만 부여, 가입 시 선택 불가 (FBN-02)
- 관리자 세부 권한

| 권한 | 범위 |
|---|---|
| `CONTENT` | 미션·기준표 작성·검토·공개·중단 (학생 원문 열람 불가) |
| `PAYMENT_VIEW` | 결제·구독 조회, PG 대조 |
| `PAYMENT_REFUND` | 환불 승인 |
| `SERVICE_OPS` | 운영 현황, 작업 재처리, 신고·문의·공지, 모델·프롬프트 버전, AI 사용량 |
| 학생 원문 열람 | `SERVICE_OPS`가 오류 신고·문의에 연결된 시도의 답변·판정만, 열람마다 `audit_log` (P07) |

- 리소스 권한 (FN 1.1, NFR-SEC-02)
  - 학생: 본인 기록만
  - 학부모: 연결된 자녀만. 아닌 경우 `403 CHILD_NOT_LINKED`
  - 화면 API·다운로드·에이전트 도구·내부 조회 모두 동일 검사

### 1.3 오류 응답 (RFC 9457)
```json
{
  "type": "https://sagomungchi.dev/errors/attempt-draft-conflict",
  "title": "초안 충돌",
  "status": 409,
  "code": "ATTEMPT_DRAFT_CONFLICT",
  "detail": "다른 화면에서 더 최신 초안이 저장됨",
  "instance": "/api/v1/attempts/7b1.../draft",
  "traceId": "4bf92f3577b34da6a3ce929d0e0e4736"
}
```

| code | status | 상황 |
|---|---|---|
| `UNAUTHENTICATED` / `TOKEN_EXPIRED` | 401 | 미인증 / 만료 → 재인증 안내 (FN-ACC-04) |
| `FORBIDDEN` | 403 | 역할·관리자 권한 부족 |
| `CHILD_NOT_LINKED` | 403 | 연결되지 않은 자녀 요청 (FN-AGT-02, FN-RPT-12) |
| `REAUTH_REQUIRED` | 403 | 중요 정보 변경 전 재확인 필요 (FN-ACC-10) |
| `STUDENT_DEVICE_INVALID` | 401 | 학생 기기 자격증명 없음·해제·만료, 해당 기기에 등록되지 않은 자녀 (FN-ACC-05) |
| `STUDENT_PIN_INVALID` | 401 | PIN 불일치, `remainingAttempts` 포함 (FN-ACC-05) |
| `STUDENT_PIN_LOCKED` | 423 | PIN 연속 5회 실패로 잠금, 학부모 PIN 재설정 필요 (FN-ACC-05) |
| `STUDENT_PIN_NOT_SET` | 409 | PIN 미설정 자녀의 PIN 로그인 → 학부모 동석 진입 안내 (FN-ACC-05) |
| `PAIRING_CODE_INVALID` | 400 | 페어링 코드 없음·만료·이미 사용 (FN-ACC-14) |
| `NOT_FOUND` | 404 | 리소스 없음 |
| `DATA_UNAVAILABLE` | 410 | 삭제된 근거 → "이용 불가" 표시 (FN-ACC-13) |
| `VALIDATION_FAILED` | 400 | 형식 오류 (`errors[]`에 필드별 사유) |
| `ANSWER_INCOMPLETE` | 422 | 필요한 선택·입력 누락 (FN-LRN-04) |
| `IDEMPOTENCY_KEY_REUSED` | 422 | 같은 키에 다른 요청 본문 |
| `ATTEMPT_DRAFT_CONFLICT` | 409 | 초안 버전 충돌, 응답에 최신 초안 포함 (FN-LRN-17) |
| `ATTEMPT_CLOSED` | 409 | 완료된 학습 시도에 쓰기, 마무리(`finished_at`) 이후 답변 제출 (P04) |
| `REVEAL_CONDITION_UNMET` | 409 | 마무리 조건(판정 `DONE` 1회 이상) 미충족 → 정답·예시 답 비공개 (FN-LRN-11, P04) |
| `MISSION_NOT_AVAILABLE` | 409 | 비공개·범위 밖 미션 |
| `MISSION_PUBLISH_INCOMPLETE` | 422 | 필수 정보 누락으로 공개 불가, `missingFields[]` (FN-ADM-11) |
| `SUBSCRIPTION_DUPLICATE` | 409 | 같은 자녀 중복 구독 (FN-PAY-02) |
| `PAYMENT_AMOUNT_MISMATCH` | 422 | 요청 금액과 승인 정보 불일치 (FN-PAY-03) |
| `REFUND_NOT_ALLOWED` | 409 | 중복·초과 환불, 환불 조건(결제 7일 이내·프리미엄 기능 미사용) 불충족 (FN-ADM-16, P14) |
| `CHILD_LIMIT_REACHED` | 409 | 학부모당 자녀 3명 초과 등록 (FN-ACC-06, P02) |
| `REGENERATE_NOT_ALLOWED` | 409 | 학부모의 같은 리포트 재생성 1회 초과 (FN-RPT-12, P06) |
| `WITHDRAWAL_BLOCKED` | 409 | 진행 중 구독·미처리 환불이 있어 탈퇴 불가, 정리 대상 포함 (FN-ACC-12, P09) |
| `USAGE_LIMIT_REACHED` | 429 | 요금제 사용 한도 도달(무료: 하루 미션 3개·분석 대화 없음, 프리미엄: 하루 피드백 50회·분석 대화 30회), 가능 범위·사유·초기화 시점 포함 (FN-ADM-19, P13) |
| `AI_UNAVAILABLE` | 503 | AI 처리 실패, `retryable` 포함 (처리 실패 상태, 보류와 구분) |

### 1.4 멱등성·동시성
- `Idempotency-Key`(UUID) 필수 대상
  - 답변 제출
  - 결제 주문·승인
  - 환불 요청
  - 작업 재처리
  - 신고 제출
- 같은 키 재요청 처리: 최초 결과를 그대로 반환하고 1회만 반영 (NFR-REL-01)
- 키 보관 기간 24시간 (P12)
- 초안은 `ETag`/`If-Match`(초안 버전)로 처리. 불일치 시 409를 반환하고 조용히 덮어쓰지 않음
- 피드백 요청은 키 대신 answerId의 판정 처리 상태로 중복 방지 (실패 후 재시도가 같은 요청이므로 키 재사용 불가)
  - `DONE`: 저장된 결과 반환
  - `RUNNING`: 새로 실행하지 않고 `status` 이벤트 후 종료, 클라이언트가 잠시 후 재요청
  - `PENDING`·`FAILED`·리스 만료된 `RUNNING`(처리 Pod 종료로 고착): 조건부 상태 전이 후 실행 (리스 90초, P12)

### 1.5 상태 코드값 (FN 1.2 대응)
| 대상 | 값 |
|---|---|
| 미션 수행 | `NOT_STARTED` 시작 전 · `IN_PROGRESS` 진행 중 · `COMPLETED` 완료 |
| 미션 운영 | `DRAFT` 작성 중 · `REVIEW_REQUIRED` 검토 필요 · `PUBLISHED` 공개 · `UNPUBLISHED` 비공개 |
| 초안 저장 | `SAVED` (저장 중·저장 실패는 클라이언트 상태) |
| 판정 처리 | `PENDING` · `RUNNING` · `DONE` · `FAILED` |
| 판정 결과 | `CORRECT` 정답 · `PARTIAL` 부분 정답 · `RETHINK` 다시 생각 · `HELD` 판정 보류 (처리 실패는 처리 상태 `FAILED`) |
| 되묻기 유형 | `ONE_STEP_MORE` 한 걸음 더 · `TELL_MORE` 더 말해 보기 · `LOOK_AGAIN` 다시 살펴보기 |
| 작업 (대화·리포트·알림) | `QUEUED` 대기 · `RUNNING` 처리 중 · `COMPLETED` 완료 · `FAILED` 실패 |
| 조회 결과 | `OK` · `NO_RECORD` 기록 없음(집계 대상 시도 0건) · `INSUFFICIENT_SAMPLE` 표본 부족(1~4건, 비율 대신 개수만, P08) · `PROCESSING` 처리 중 · `FAILED` 조회 실패 |
| 신고 | `RECEIVED` 접수 · `IN_REVIEW` 검토 중 · `RESOLVED` 처리 완료 |
| 결제 거래 | `APPROVED` 승인 · `CONFIRMING` 확인 중 · `FAILED` 실패 · `CANCELED` 취소 · `REFUND_REVIEW` 환불 검토 중 · `REFUNDED` 환불 |
| 구독 | `ACTIVE` 이용 중 · `RENEWAL_FAILED` 갱신 실패(이용 제한 예정) · `CANCELED` 해지 |
| 생각 유형 | `ANALYZE` 분석하기 · `EVALUATE` 따져 보기 · `CREATE` 새로 만들기 · `SOLVE` 문제 해결하기 · `REFLECT` 돌아보기 |
| 입력 방식 | `CHOICE` 선택지 · `ORDERING` 순서 · `CLASSIFICATION` 분류 · `NARRATIVE` 서술 · `SOLUTION_STEPS` 풀이 단계 · `ESSAY` 논술 |
| 출처 유형 | `RECORD` 기록 · `RULE` 규칙 · `ANSWER_KEY` 정답 키 · `AI_OBSERVATION` AI 관찰 |
| 생성 출처 | `LLM` · `LLM_RETRY` · `BANK` 질문 은행(되묻기) · `TEMPLATE` 규칙 응답(분석 대화)·템플릿 요약(리포트) (P16) |

### 1.6 공통 스키마
```jsonc
// Metric: 모든 건수·비율 (FN 1.3 수치 근거, FN-RPT-03)
{
  "label": "되묻기 후 생각을 더한 비율",
  "value": 0.6,                 // 분모 5 미만이면 null, count만 표시 (P08)
  "count": 3,
  "numerator": 3,
  "denominator": 5,
  "formula": "보완 답변 제출 시도 수 / 되묻기 받은 시도 수",
  "period": { "from": "2026-11-02", "to": "2026-11-08" },
  "sourceType": "RECORD",
  "state": "OK"                 // QueryState
}

// Evidence: 원문 근거 (FN-AGT-07)
{ "attemptId": "...", "missionTitle": "...", "answerId": "...", "answerVersion": 1,
  "submittedAt": "...", "quote": "아이 원문 일부", "available": true }   // 삭제 시 available=false

// Versions: 결과에 연결된 버전 (NFR-DAT-02)
// model: M2 활성 판정은 M2 버전, M2 미활성 판정·되묻기는 LLM 모델 ID(예: claude-sonnet-5-5), 규칙 판정은 null
{ "mission": "m-12@3", "rubric": "r-12@2", "model": "m2-klue-narrative@1.0", "prompt": "judge@4" }
```

- SSE 이벤트

| event | data | 용도 |
|---|---|---|
| `status` | `{state, message}` | 처리 중 단계 안내 |
| `clarification` | `{question, options[]}` | 대상·기간 확인 요청 (FN-AGT-03) |
| `delta` | `{text}` | 답변 스트리밍 조각 (대조 전 임시 표시) |
| `result` | 엔드포인트별 최종 결과 | 대조 완료된 확정 결과 |
| `error` | Problem Details + `retryable` | 처리 실패 |
| `done` | `{}` | 스트림 종료 |

- heartbeat: 15초마다 주석 줄 `: ping` 전송 (CloudFront·ALB 유휴 타임아웃 방지, 클라이언트는 무시)
- 알림 스트림 재연결 시 `GET /notifications?unreadOnly=true`로 누락분 재조회

---

## 2. 공개 API 목록

### 2.1 계정·동의·자녀 (FN-ACC)
| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/consent-documents` | 공개 | 현재 이용 안내·동의 문서(버전) 조회 | ACC-02 | 제안 |
| GET | `/auth/google/authorize` | 공개 | Google 로그인·가입 시작 (Authorization Code + PKCE) | ACC-01, ACC-03 | 제안 |
| GET | `/auth/google/callback` | 공개 | Google 코드 교환·ID 토큰 검증 → refresh 쿠키 → web 복귀 | ACC-03 | 제안 |
| POST | `/auth/refresh` | 쿠키 | access token 재발급 | ACC-04 | 제안 |
| POST | `/auth/logout` | 인증 | refresh token 폐기 | ACC-04 | 제안 |
| POST | `/auth/student-sessions` | 학부모 | 학생 진입(동석): `{childId}` 연결 자녀 확인 후 학생 세션(`STUDENT` 토큰) 발급. 시연 링크·URL 식별값 진입 없음 (P01) | ACC-05 | 제안 |
| POST | `/auth/student/devices` | 공개 | 페어링 코드로 기기 등록 `{pairingCode, label}` → 기기 자격증명 쿠키 발급, 등록 자녀 프로필 반환 (P01, 3.11) | ACC-14 | 제안 |
| GET | `/auth/student/profiles` | 기기 쿠키 | 이 기기에 등록된 자녀 프로필 `{childId, nickname, pinSet, locked}` (P01) | ACC-05 | 제안 |
| POST | `/auth/student/login` | 기기 쿠키 | 학생 진입(단독): `{childId, pin}` → 학생 세션(`STUDENT` 토큰) 발급. refresh 미발급 (P01, 3.11) | ACC-05 | 제안 |
| GET | `/me` | 인증 | 본인 정보·역할·관리자 권한 | ACC-09 | 우선1 |
| PATCH | `/me` | 인증 | 본인 정보 수정 | ACC-09 | 우선1 |
| POST | `/me/reauth` | 인증 | 재확인 → 단기 `reauthToken` 발급 | ACC-10 | 우선1 |
| GET | `/me/consents` | 학부모 | 동의 이력(주체·문서 버전·시점·철회 상태) | ACC-02 | 제안 |
| POST | `/me/consents/{consentId}/withdrawal` | 학부모 | 동의 철회. 필수 동의면 해당 자녀(또는 계정) 이용 차단 후 삭제·탈퇴 안내, 선택 동의면 해당 기능만 중단 (P09) | ACC-02 | 제안 |
| GET | `/children` | 학부모 | 연결 자녀 목록(닉네임·학년·기록 유무, PIN 상태 `pinSet`·`pinLocked`). 빈 목록이면 자녀 등록 안내 | ACC-07, ACC-14 | 제안 |
| POST | `/children` | 학부모 | 자녀 프로필 등록 `{nickname, grade(3~6), birthYear}` + 법정대리인 동의(전원 만 14세 미만 간주). 3명 초과 시 409 (P01, P02, P03) | ACC-06, ACC-02 | 제안 |
| PATCH | `/children/{childId}` | 학부모 | 닉네임·학년(3~6) 수정 (학년은 이후 제공 문제에만 적용) | ACC-09 | 우선1 |
| PUT | `/children/{childId}/pin` | 학부모 | PIN 설정·변경 `{pin}` (`X-Reauth-Token`). 실패 횟수·잠금 해제 (P01) | ACC-14, ACC-10 | 제안 |
| POST | `/student-devices/pairings` | 학부모 | 1회용 페어링 코드 발급 `{childIds[]}` → `{pairingCode, expiresAt}` (10분, QR은 클라이언트가 코드로 생성) (P01) | ACC-14 | 제안 |
| GET | `/student-devices` | 학부모 | 등록 기기 목록 `{deviceId, label, children[], createdAt, lastUsedAt, expiresAt}` | ACC-14 | 제안 |
| DELETE | `/student-devices/{deviceId}` | 학부모 | 기기 등록 해제 → 이후 해당 기기 PIN 로그인 거부 | ACC-14 | 제안 |
| GET | `/children/{childId}/deletion-impact` | 학부모 | 연결 해제·프로필 삭제·기록 삭제별 범위·영향 안내 | ACC-11 | 우선2 |
| DELETE | `/children/{childId}/link` | 학부모 | 연결 해제 (`X-Reauth-Token`) | ACC-11, ACC-10 | 우선2 |
| POST | `/children/{childId}/deletion-requests` | 학부모 | 프로필·학습 기록 삭제 요청 `{scope: PROFILE\|RECORDS}` → 확정 시 `student.deleted` | ACC-11, ACC-13 | 우선2 |
| GET | `/me/withdrawal/precheck` | 인증 | 탈퇴 전 진행 중 구독·미처리 환불·보관 거래(5년) 안내 (P09, P14) | ACC-12 | 우선2 |
| POST | `/me/withdrawal` | 인증 | 탈퇴 요청 (`X-Reauth-Token`). 진행 중 구독·미처리 환불이 있으면 409, 요청 즉시 처리·이후 로그인 불가 (P09) | ACC-12 | 우선2 |
| GET | `/me/withdrawal` | 인증 | 탈퇴 처리 상태 | ACC-12 | 우선2 |

- 삭제 후 처리 (FN-ACC-13)
  - 삭제가 끝난 기록은 학습·대화·리포트·대시보드 응답에서 제외
  - 근거로 참조된 경우에는 `available: false` 또는 `410 DATA_UNAVAILABLE` 반환
  - 다른 기록으로 대체하지 않음

### 2.2 미션 학습·판정·되묻기 (FN-LRN, FN-JDG)
| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/missions` | 학생 | 학년·입력 방식 범위의 공개 미션 목록(제목·교과·생각 유형·수행 상태), 진행 위치 | LRN-02, DSH-02 | 핵심 |
| GET | `/missions/{missionId}` | 학생 | 장면(애니메이션·정적 대체)·질문·안내·입력 방식 틀. 정답·예시 답 미포함 | LRN-03, LRN-05 | 핵심 |
| POST | `/missions/{missionId}/attempts` | 학생 | 학습 시도 시작. 진행 중 시도가 있으면 그 시도 반환(이어하기) | LRN-01, LRN-16 | 핵심 |
| GET | `/attempts/{attemptId}` | 학생 | 시도 상세: 상태, 최신 초안(`ETag`), 답변·판정·되묻기 타임라인, 가능한 다음 행동 | LRN-16, JDG-08, JDG-09 | 핵심 |
| PUT | `/attempts/{attemptId}/draft` | 학생 | 초안 자동 저장 (`If-Match`), 응답에 저장 시점·새 버전. `content: {answer, memo}` (P05) | LRN-15, LRN-16, LRN-17 | 우선1 |
| POST | `/attempts/{attemptId}/hints` | 학생 | 생각 열기 질문 열람 기록 → 질문 반환 (정답·제출용 답 미포함) | LRN-06 | 핵심 |
| POST | `/attempts/{attemptId}/answers` | 학생 | 답변 제출(최초·보완). 별도 버전 저장, 보완은 `followupId`에 연결. `Idempotency-Key` | LRN-04, LRN-05, LRN-08, LRN-09, LRN-10 | 핵심 |
| POST | `/answers/{answerId}/feedback` | 학생 | **SSE**. 판정 + 되묻기 생성. 이미 완료됐으면 저장된 결과 반환, `FAILED`면 재실행 | JDG-01~07, JDG-09, JDG-10 | 핵심 |
| POST | `/attempts/{attemptId}/finish` | 학생 | 마무리 → 정답(닫힌 문제)·예시 답(열린 문제)·근거 확인된 체크리스트 공개. 판정 `DONE` 1회 이상 아니면 409 (P04) | LRN-11, JDG-09 | 핵심 |
| POST | `/attempts/{attemptId}/self-assessment` | 학생 | 자기 체크 저장 → AI 확인 항목과 나란히 반환 (원본·판정 불변) | LRN-13 | 선택 |
| POST | `/attempts/{attemptId}/reflection` | 학생 | 돌아보기 `{difficulty(필수), text(선택)}` 저장 → 학습 완료 처리 (P04) | LRN-12, LRN-14 | 핵심 |

- 음성 시범(FN-LRN-18): 미구현 (P03)
- 질문 읽어주기(FN-LRN-19): 브라우저 TTS(Web Speech API), API 없음 (P03)
- 메모(FN-LRN-07): 초안 `content.memo`로 저장, 학생 본인 조회에만 포함 (P05)
- 되묻기·마무리 (P04)
  - 되묻기는 시도당 최대 2회, 2회째 답변 후 `nextActions: ["FINISH"]`
  - 고르기 `CORRECT`면 되묻기 없이 `nextActions: ["FINISH"]`
  - 되묻기에 답하지 않고 `FINISH` 가능("이대로 돌아보기")
- 무료 플랜은 하루 3개 미션까지 시도 시작 가능, 초과 시 `USAGE_LIMIT_REACHED` (P13)
- 목록 접기·펼치기(FN-LRN-20): 프론트 전용, API 없음
- 판정 규칙 (FN-JDG-01~05)
  - 고르기·수학 최종 답: 규칙 판정
  - 서술·논술: LLM 근거 추출 → 코드 원문 대조
  - 근거 없는 요소는 `satisfied: false`
  - 검증 전 결과는 `trial: true`("AI 채점(시범)")
  - 숫자 레벨은 응답에 포함하지 않음
- 판정 보류(`HELD`)와 처리 실패(`FAILED`)는 서로 다른 필드로 구분 (NFR-REL-04)

### 2.3 대시보드 (FN-DSH)
| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/students/me/home` | 학생 | 학생 정보, 이어할 시도, 시작 가능한 미션 경로 | DSH-01, DSH-02 | 제안 |
| GET | `/students/me/attempts` | 학생 | 최근 학습 기록(미션·시점·완료 여부, `status` 필터) | DSH-03, LRN-16 | 제안 |
| GET | `/students/me/thinking-activities` | 학생 | 수행 미션의 생각 유형·본인 돌아보기 (레벨·등급·순위 없음) | DSH-04 | 제안 |
| GET·PUT | `/students/me/preferences` | 학생 | 생각 지도 테마·동행 캐릭터 설정 (3.12) | - | 제안 |
| GET | `/children/{childId}/summary?from&to` | 학부모 | 학습 건수·상태 `Metric[]`, 집계 기준·기간 (P08) | DSH-06, DSH-07, DSH-10 | 제안 |
| GET | `/children/{childId}/thinking-types?from&to` | 학부모 | 다섯 유형별 미션·기록, 없는 유형은 `NO_RECORD`("미관찰") | DSH-08 | 제안 |
| GET | `/children/{childId}/attempts?from&to` | 학부모 | 기간 내 학습 목록 | DSH-07, DSH-09 | 제안 |
| GET | `/children/{childId}/attempts/{attemptId}` | 학부모 | 최초 답변·되묻기·추가 답변·도움 이용·돌아보기 원문 연결 | DSH-09 | 제안 |

- 모든 응답에 `state`(QueryState)와 `period` 포함
- 기록 없음과 조회 실패를 구분하고, 미확인 수치는 채우지 않음 (FN-DSH-05, FN-DSH-11)

### 2.4 분석 대화 (FN-AGT)
| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| POST | `/conversations` | 학부모 | 대화 생성 `{childId, from, to}` (기본 기간 최근 7일·오늘 포함, P06). 무료 플랜은 `USAGE_LIMIT_REACHED` (P13) | AGT-01 | 핵심 |
| GET | `/conversations?childId` | 학부모 | 본인 대화 목록 | AGT-11 | 핵심 |
| GET | `/conversations/{conversationId}` | 학부모 | 질문·답변·대상 자녀·기간·참조 기록 | AGT-11 | 핵심 |
| POST | `/conversations/{conversationId}/messages` | 학부모 | **SSE**. 질문 → 범위 확인 → 기록 조회·계산 → 숫자·인용 대조 → 확정 답변. 범위 변경 시 `scope` 동봉 | AGT-02~06, AGT-08~10 | 핵심 |
| POST | `/conversations/{conversationId}/messages/{messageId}/retry` | 학부모 | **SSE**. 실패한 질문 재처리 | AGT-10 | 핵심 |
| GET | `/conversations/{conversationId}/messages/{messageId}/evidence` | 학부모 | 답변 근거(미션·답변 시점·원문, 전후 답변 연결) | AGT-07 | 핵심 |
| GET | `/agent/example-questions?childId` | 학부모 | 예시 질문(숫자·유형별 활동·아이가 쓴 생각·전후 변화·돌아보기·수학 점검), 가능 여부 표시 | AGT-12 | 선택 |

- 예시 질문(FN-AGT-12): core `conversation`이 learning `/internal/records/...`로 기록 유무 확인 후 가능 여부 표시
- 대화 이력은 이용 중 보관, 탈퇴·자녀 삭제 시 파기. 삭제된 근거는 `available: false` (P09)
- 대조 실패·LLM 장애 시 LLM 답변을 보내지 않고 규칙 응답 모드 결과를 보냄 (3.3, FN-AGT-06·10, P16)

### 2.5 주간 리포트 (FN-RPT)
| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/children/{childId}/reports?status` | 학부모 | 대상 주·생성 상태별 목록 | RPT-10, RPT-11 | 핵심 |
| GET | `/reports/{reportId}?revision` | 학부모 | 상세: 기간·포함 기준·`Metric[]`·생각 유형 요약·전후 변화·돌아보기·원문 인용·저녁 질문·버전. 기본 최신판, `revision`으로 이전판 조회 (P06) | RPT-02~10, RPT-12 | 핵심 |
| GET | `/reports/{reportId}/evidence/{itemId}` | 학부모 | 리포트 항목의 원본 기록 | RPT-03, RPT-12 | 핵심 |
| GET | `/reports/{reportId}/download?format=pdf\|md` | 학부모 | 권한 확인 후 `{url, expiresAt}`(단기 presigned URL) 반환, 웹이 해당 URL로 이동. Bearer 인증이라 302 대신 JSON (PDF·Markdown, P06) | RPT-13 | 핵심 |
| POST | `/reports/{reportId}/regenerate` | 학부모·관리자 | 같은 주 재생성 → `report.generate`, 새 판(`revision + 1`) 추가·기존 판 보존. 학부모 리포트당 1회(초과 409), 관리자 무제한 (P06) | RPT-12 | 핵심 |

- 자동 생성(FN-RPT-01)은 core 스케줄러가 매주 월요일 07:00 KST에 직전 월~일(KST) 대상으로 수행하며 공개 API는 없음 (P06)
- 생성 내용(FN-RPT-02~09)은 report-service가 계산하고, 그 결과를 상세 응답 스키마(3.4)로 제공
- 기록 없는 주·표본 부족 주는 `COMPLETED` + `state: NO_RECORD|INSUFFICIENT_SAMPLE`로 표시하며, 생성 실패(`FAILED`)와 구분 (FN-RPT-11). `NO_RECORD`는 LLM 미호출 (P06)
- 무료 플랜은 수치만 제공(`narrative: null`, 생각 유형 `summary` 없음) (P13)

### 2.6 결제·구독 (FN-PAY) — 토스페이먼츠 테스트 환경만
| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/products` | 공개 | 상품 목록(무료·프리미엄 월 14,900원): 가격·청구 주기·기능·사용 한도·대상 자녀 수·기간. 값은 `product` 데이터 (P13) | PAY-01 | 우선2 |
| POST | `/orders` | 학부모 | 결제 요청 생성 `{productId, childId}` → `orderId`·금액·위젯 파라미터. 중복 구독 409. `Idempotency-Key` | PAY-02, PAY-03 | 우선2 |
| POST | `/payments/confirm` | 학부모 | 위젯 성공 리다이렉트 값(`paymentKey, orderId, amount`)으로 서버 승인 → 금액 대조 → 구독·권한 반영. `Idempotency-Key` | PAY-03, PAY-04, PAY-05 | 우선2 |
| GET | `/payments/{orderId}` | 학부모 | 결제 상태 (`CONFIRMING`이면 PG 상태 조회 후 갱신) | PAY-04 | 우선2 |
| GET | `/payments` | 학부모 | 본인 거래 내역(결제·취소·환불) | PAY-07 | 우선2 |
| GET | `/subscriptions` | 학부모 | 구독 상태·대상 자녀·이용 기간·다음 결제 예정일 | PAY-07 | 우선2 |
| POST | `/subscriptions/{subscriptionId}/billing-key` | 학부모 | 자동결제 수단 등록·변경 (PG `authKey` → 빌링키 발급, 카드 정보 미저장) | PAY-08 | 우선2 |
| DELETE | `/subscriptions/{subscriptionId}/auto-renewal` | 학부모 | 자동 갱신 해지, 해지 시점·남은 기간 반환. `period_end`까지 이용 유지 (P14) | PAY-09 | 우선2 |
| PUT | `/subscriptions/{subscriptionId}/auto-renewal` | 학부모 | 해지 철회(자동 갱신 재설정), `period_end` 전 `ACTIVE` 구독만 (P14) | PAY-09 | 우선2 |
| POST | `/payments/{paymentId}/refund-requests` | 학부모 | 취소·환불 요청, `Idempotency-Key`. 결제 7일 이내 + 프리미엄 기능 미사용 시 전액만(부분 환불 없음), 아니면 409 (P14) | PAY-10 | 우선2 |
| POST | `/webhooks/tosspayments` | PG | 상태 변경 통지. 본문을 신뢰하지 않고 PG 조회 API로 재확인 후 1회 반영 | PAY-04, PAY-06 | 우선2 |

- 정기 청구(FN-PAY-06)는 core 스케줄러가 수행하며 공개 API는 없음
  - 매일 09:00 KST, 최초 결제일 기준 매월 같은 날(없으면 말일) 도래 구독을 빌링키로 자동결제 (P13)
  - 결과를 거래별로 기록
  - 실패 시 `RENEWAL_FAILED`, 유예 3일 동안 이용 유지·매일 1회 최대 3회 재청구, 모두 실패 시 `CANCELED` (P13)
- 화면 복귀만으로 결제 완료를 판단하지 않음. 결과가 불명확하면 `CONFIRMING`으로 두고 재결제를 안내하지 않음

### 2.7 신고·지원·알림 (FN-SUP)
| Method | Path | 역할 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| POST | `/error-reports` | 학생·학부모 | 오류 신고 `{targetType: FOLLOWUP\|JUDGMENT\|ANALYSIS\|REPORT, targetId, category, comment}` (`category`: `WRONG_JUDGMENT` 판정이 틀려요 · `ODD_QUESTION` 질문이 이상해요 · `MISMATCH` 숫자·인용이 달라요 · `INAPPROPRIATE` 부적절한 표현 · `OTHER` 기타, P10) | SUP-01 | 우선1 |
| GET | `/error-reports` | 학생·학부모 | 본인 신고 목록·상태 | SUP-04 | 우선1 |
| GET | `/error-reports/{reportId}` | 학생·학부모 | 상태·허용된 처리 결과 | SUP-04 | 우선1 |
| GET | `/help?role` | 인증 | 역할별 도움말·최초 이용 안내 | SUP-05 | 우선2 |
| POST | `/inquiries` | 학생·학부모 | 계정·이용·결제 문의 | SUP-06 | 우선2 |
| GET | `/inquiries`, `/inquiries/{inquiryId}` | 학생·학부모 | 본인 문의 상태·답변 | SUP-06 | 우선2 |
| GET | `/notices` | 인증 | 대상 역할·공개 기간 내 공지·점검 안내 | SUP-07 | 우선2 |
| GET | `/notifications?unreadOnly` | 인증 | 본인 알림 목록 (자녀별 사건은 `childId` 포함) | SUP-09 | 우선2 |
| PATCH | `/notifications/{notificationId}/read` | 인증 | 읽음 처리 | SUP-09 | 우선2 |
| POST | `/notifications/read-all` | 인증 | 전체 읽음 | SUP-09 | 우선2 |
| GET | `/notifications/stream` | 인증 | **SSE**. 새 알림 (`event: notification`) | SUP-08 | 우선2 |
| GET | `/notification-settings` | 인증 | 알림 유형별 수신 설정 (앱 내 알림만, P10) | SUP-10 | 우선2 |
| PUT | `/notification-settings` | 인증 | 수신 설정 변경 (유형별 on/off, 이메일·푸시 없음, P10) | SUP-10 | 우선2 |

- 알림 생성(FN-SUP-08)은 내부 사건(리포트 완료, 신고·문의 처리, 구독·결제 변경)에서 발생
  - 사건 ID 기준으로 1회만 생성
  - 알림 본문에는 학생 원문·결제 민감 정보를 넣지 않고 상세 화면 링크만 담음 (FN-SUP-11)

### 2.8 관리자 (FN-ADM, FN-SUP 관리 측) — `/api/v1/admin`
| Method | Path | 권한 | 설명 | FN | 우선순위 |
|---|---|---|---|---|---|
| GET | `/admin/overview?from&to` | 관리자 | 학습 시도·완료 건수, 대화·리포트 처리 현황, 미션 공개 현황 (학생 원문 없음) | ADM-01, ADM-02, ADM-04 | 제안 |
| GET | `/admin/jobs?type=CONVERSATION\|REPORT\|NOTIFICATION&status` | SERVICE_OPS | 작업 상태별 목록, 요약 수치 → 상세 이동 | ADM-03, ADM-05, SUP-11 | 제안 |
| GET | `/admin/jobs/{jobId}` | SERVICE_OPS | 실패 원인·처리 이력 | ADM-07 | 제안 |
| POST | `/admin/jobs/{jobId}/retry` | SERVICE_OPS | 권한·중복 확인 후 재처리, 실제 결과로 갱신 (`SERVICE_OPS` 전원, `audit_log`, P07). `Idempotency-Key` | ADM-07, SUP-11 | 제안 |
| GET | `/admin/queues` | SERVICE_OPS | 큐 길이·DLQ 적재 현황 | ADM-03 | 제안 |
| GET | `/admin/audit-logs?targetType&from&to` | 관리자 | 운영 조치·콘텐츠 변경 이력(수행자·대상·시점·결과) | ADM-06, ADM-13 | 제안 |
| GET | `/admin/missions?status&grade&thinkingType` | CONTENT | 미션 목록·상태별 건수 | ADM-04, ADM-08 | 제안 |
| POST | `/admin/missions` | CONTENT | 미션 작성 (학년·생각 유형·입력 방식·장면·질문·교과·성취기준, 시연 전용 여부) | ADM-09 | 제안 |
| GET | `/admin/missions/{missionId}` | CONTENT | 미션 상세·버전 이력 | ADM-09, ADM-10 | 제안 |
| PATCH | `/admin/missions/{missionId}` | CONTENT | 미션 수정 (새 버전 생성, 기존 학습은 당시 버전 유지) | ADM-09, ADM-12 | 제안 |
| PUT | `/admin/missions/{missionId}/rubric` | CONTENT | 기준표(요소·배점·흔한 오답)·정답·예시 답·들어가면 좋은 생각·생각 열기 질문 → 새 기준 버전 | ADM-10 | 제안 |
| GET | `/admin/missions/{missionId}/preview` | CONTENT | 학생 화면 미리보기 데이터 | ADM-09 | 제안 |
| POST | `/admin/missions/{missionId}/review-request` | CONTENT | 검토 요청 `DRAFT → REVIEW_REQUIRED` (현재 미션·기준표 버전 필요) (P07) | ADM-11 | 제안 |
| POST | `/admin/missions/{missionId}/review` | CONTENT | 검토 결과 기록, `CONTENT` 1인 가능(작성자 포함) (P07) | ADM-11 | 제안 |
| POST | `/admin/missions/{missionId}/publish` | CONTENT | 게시, 필수 누락 시 422. 재게시 시 새 버전이 신규 시도부터 적용, 진행 중 시도는 시작 당시 버전 유지 (P07) | ADM-11 | 제안 |
| POST | `/admin/missions/{missionId}/unpublish` | CONTENT | 신규 제공 중단 (진행 중 시도는 시작 당시 버전으로 계속, P07) | ADM-12 | 제안 |
| GET | `/admin/error-reports?status` | SERVICE_OPS | 신고 목록·상태별 | SUP-02 | 우선1 |
| GET | `/admin/error-reports/{reportId}` | SERVICE_OPS | 신고 상세 + 연결 시도의 답변·판정 원문 (열람마다 `audit_log`, P07) | SUP-02 | 우선1 |
| PATCH | `/admin/error-reports/{reportId}` | SERVICE_OPS | 상태·검토 결과·처리 이유 (접수만으로 판정 변경 없음) | SUP-02 | 우선1 |
| POST | `/admin/error-reports/{reportId}/corrections` | SERVICE_OPS | 정정: 기존 결과·사유·시점 보존, 영향받는 대화·집계·리포트 반영 여부 (원본 답변 불변) | SUP-03 | 우선1 |
| GET | `/admin/inquiries?status` | SERVICE_OPS | 문의 목록 | SUP-06 | 우선2 |
| POST | `/admin/inquiries/{inquiryId}/answer` | SERVICE_OPS | 문의 답변 | SUP-06 | 우선2 |
| POST / PATCH / DELETE | `/admin/notices`, `/admin/notices/{noticeId}` | SERVICE_OPS | 공지 등록·수정·종료 (공개 기간·대상 역할) | SUP-07 | 우선2 |
| GET | `/admin/payments?status&from&to` | PAYMENT_VIEW | 결제·구독 상태, 대상 자녀 권한 반영 여부 | ADM-14 | 우선2 |
| GET | `/admin/payments/reconciliation?from&to` | PAYMENT_VIEW | 내부 기록 vs PG 상태 대조, 누락·중복·불일치 분리 | ADM-15 | 우선2 |
| GET | `/admin/refund-requests?status` | PAYMENT_VIEW | 환불 요청 목록 | ADM-16 | 우선2 |
| POST | `/admin/refund-requests/{requestId}/approve` | PAYMENT_REFUND | 대상·금액·사유 확인 후 PG 취소, 결과·수행자 기록. `Idempotency-Key` | ADM-16 | 우선2 |
| POST | `/admin/refund-requests/{requestId}/reject` | PAYMENT_REFUND | 반려 사유 기록 | ADM-16 | 우선2 |
| GET | `/admin/model-versions?kind=RUBRIC\|MODEL\|PROMPT\|GENERATION` | SERVICE_OPS | 버전 목록·활성 상태·평가 결과 | ADM-17 | 우선1 |
| POST | `/admin/model-versions` | SERVICE_OPS | 버전 등록 (평가 기록 첨부) | ADM-17 | 우선1 |
| POST | `/admin/model-versions/{versionId}/activate` | SERVICE_OPS | 승인 조건(NFR-AIQ-05) 확인 후 활성화 → `model.version.activated` | ADM-18 | 우선1 |
| POST | `/admin/model-versions/{versionId}/rollback` | SERVICE_OPS | 이전 승인 버전 복귀, 재분석 여부 기록 | ADM-18 | 우선1 |
| GET | `/admin/ai-usage?from&to&callType` | SERVICE_OPS | 되묻기·판정·분석·리포트별 호출량·실패·지연·토큰·비용 (요금제 한도 P13, 월 LLM 비용 예산 80% 경보 P10) | ADM-19 | 우선1 |

---

## 3. 주요 요청·응답

### 3.1 답변 제출 — `POST /attempts/{attemptId}/answers`
```http
Idempotency-Key: 5c0e...  
```
```jsonc
// 요청: 서술(최초 답변)
{ "inputType": "NARRATIVE", "text": "나는 ...라고 생각해. 왜냐하면 ...", "dictatedByGuardian": false }
// 요청: 보완 답변 (되묻기에 대한 답)
{ "inputType": "ESSAY", "followupId": "f-31",
  "essay": { "claim": "...", "reasons": ["...", "..."], "rebuttal": "..." } }
// 요청: 고르기
{ "inputType": "ORDERING", "choiceIds": ["c3", "c1", "c2"] }
```
```jsonc
// 201 Created
{ "answerId": "a-102", "attemptId": "t-7", "version": 2, "followupId": "f-31",
  "submittedAt": "2026-11-03T19:12:04+09:00",
  "feedback": { "status": "PENDING" } }
```

### 3.2 피드백 — `POST /answers/{answerId}/feedback` (SSE)
```
event: status
data: {"state":"RUNNING","message":"생각을 살펴보는 중"}

event: result
data: {
  "status":"DONE",
  "judgment":{
    "result":"PARTIAL", "trial":true,
    "elements":[
      {"elementId":"e1","label":"주장","satisfied":true,"quote":"나는 ...라고 생각해","sourceType":"AI_OBSERVATION"},
      {"elementId":"e2","label":"까닭","satisfied":false,"quote":null}
    ],
    "heldReason":null
  },
  "followup":{"followupId":"f-32","type":"TELL_MORE","question":"왜 그렇게 생각했는지 하나 더 말해 볼까?","source":"LLM"},
  "nextActions":["ANSWER_FOLLOWUP","FINISH"],
  "versions":{"mission":"m-12@3","rubric":"r-12@2","model":"claude-sonnet-5-5","prompt":"judge@4"}
}

event: done
data: {}
```
- 보류인 경우: `judgment.result: "HELD"`, `heldReason`(`INSUFFICIENT_EVIDENCE`·`QUOTE_MISMATCH`·`TOO_SHORT`·`UNVERIFIED_SCOPE`·`MODEL_DISAGREEMENT`·`LOW_CONFIDENCE`)
- 실패한 경우
  - `event: error` 데이터: `{"code":"AI_UNAVAILABLE","retryable":true}`
  - 답변은 저장된 상태로 유지
  - 같은 엔드포인트를 다시 호출해 재시도 (상태별 처리는 1.4)
- 클라이언트 연결이 끊겨도 처리는 끝까지 진행·저장, 재요청 시 저장 결과 반환

### 3.3 분석 대화 — `POST /conversations/{conversationId}/messages` (SSE)
```jsonc
// 요청 (scope 생략 시 대화의 확인된 자녀·기간 유지)
{ "question": "질문을 받고 뭐가 달라졌어?", "scope": { "from": "2026-10-27", "to": "2026-11-08" } }
```
```
event: status
data: {"state":"RUNNING","message":"기록을 조회하는 중"}

event: delta
data: {"text":"되묻기를 받은 5번 중 3번 ..."}

event: result
data: {
  "messageId":"msg-9",
  "answer":"되묻기를 받은 5번 중 3번 생각을 더 썼어요. ...",
  "scope":{"childId":"s-1","from":"2026-10-27","to":"2026-11-08","changed":true},
  "metrics":[{ "label":"되묻기 후 생각을 더한 비율","count":3,"numerator":3,"denominator":5,"value":0.6,
               "formula":"보완 답변 제출 시도 수 / 되묻기 받은 시도 수","period":{"from":"2026-10-27","to":"2026-11-08"},
               "sourceType":"RECORD","state":"OK" }],
  "evidence":[{"attemptId":"t-7","missionTitle":"...","answerId":"a-102","answerVersion":2,"quote":"...","available":true}],
  "verification":{"numbersMatched":true,"quotesMatched":true},
  "recordCount":5
}

event: done
data: {}
```
- 범위가 불명확한 경우
  - `event: clarification`을 보내고 스트림 종료
  - 사용자 선택을 `scope`에 담아 다시 질문
- 대조 실패·LLM 장애: 규칙 응답 모드 (P16)
  - `delta`로 보낸 임시 텍스트는 폐기
  - `event: result`에 계산된 `metrics`·`evidence`만 템플릿 문장으로 담고 `"source":"TEMPLATE"`, `"fallback":{"reason":"VERIFICATION_FAILED|AI_UNAVAILABLE"}` 표시
  - 기록 조회 자체가 실패하면 `event: error`

### 3.4 리포트 상세 — `GET /reports/{reportId}`
```jsonc
{
  "reportId": "r-44", "childId": "s-1", "status": "COMPLETED", "state": "OK",
  "period": { "from": "2026-11-02", "to": "2026-11-08" },
  "revision": 1, "revisions": [{ "revision": 1, "generatedAt": "2026-11-09T07:00:00+09:00" }],
  "inclusionRule": "기간 내 답변 제출이 있는 시도(미완료 포함), 처리 실패만 있는 시도·삭제 기록 제외",
  "metrics": [ /* Metric[] */ ],
  "thinkingTypes": [
    { "type": "ANALYZE", "state": "OK", "missions": [{ "attemptId": "t-7", "title": "..." }], "summary": "..." },
    { "type": "CREATE", "state": "NO_RECORD", "summary": "확인된 기록 없음" }
  ],
  "changes": [{ "attemptId": "t-7", "followup": "...", "first": { "answerId": "a-101", "text": "..." },
                "revised": { "answerId": "a-102", "text": "..." },
                "counts": { "chars": [42, 88], "sentences": [2, 4], "reasonConnectives": [0, 2] } }],
  "reflections": [{ "attemptId": "t-7", "difficulty": "보통", "text": "...", "written": true }],
  "quotes": [{ "attemptId": "t-7", "answerId": "a-102", "text": "...", "verified": true }],
  "eveningQuestion": "...",
  "narrative": { "text": "...", "source": "LLM", "modelExplanation": null },   // 대조 실패 시 source=TEMPLATE (P16), 무료 플랜은 null (P13)
  "verification": { "numbersMatched": true, "quotesMatched": true },
  "versions": { "prompt": "report@2", "model": null },
  "generatedAt": "2026-11-09T07:00:00+09:00"
}
```

### 3.5 결제 승인 — `POST /payments/confirm`
```jsonc
// 요청 (결제위젯 successUrl 쿼리 값)
{ "paymentKey": "tgen_2026...", "orderId": "ord-88", "amount": 14900 }
// 200
{ "orderId": "ord-88", "status": "APPROVED",
  "subscription": { "subscriptionId": "sub-3", "childId": "s-1", "status": "ACTIVE",
                    "periodEnd": "2026-12-03", "nextBillingDate": null } }
// 202: PG 응답 지연·불명확
{ "orderId": "ord-88", "status": "CONFIRMING" }
```
- 처리 순서: 주문 금액·대상 자녀 대조 → PG 승인 API 호출 → 구독 반영
- 권한 반영이 실패한 경우
  - 결제는 `APPROVED`로 두고 복구 대상으로 기록 (FN-PAY-05)
  - 추가 청구 없이 재시도

### 3.6 초안 충돌 — `PUT /attempts/{attemptId}/draft`
```http
If-Match: "7"
```
```jsonc
// 409
{ "code": "ATTEMPT_DRAFT_CONFLICT", "status": 409,
  "latest": { "version": 8, "content": { "answer": { "text": "..." }, "memo": "..." }, "savedAt": "2026-11-03T19:10:00+09:00" } }
```

---

### 3.7 이슈 #7 프론트 목업용 최소 DTO 초안 (백엔드 확인 대기)

공개 Controller가 없는 상태에서 MSW와 화면 어댑터를 같은 형태로 검증하기 위한 **초안**이다. 확정된 백엔드 응답/OpenAPI가 아니며 담당자 확인 전 실연동 완료로 간주하지 않는다. 기존 3.1·3.2·3.6 계약은 유지한다.

- #36 이후 이메일·비밀번호 로그인/가입은 제공하지 않는다. Google core 콜백 → web `/oauth/complete` → refresh → `/me`로 로그인 상태·시작 화면을 복원한다. 개발 전용 MSW의 이메일 fixture는 운영 계약이 아니다. 학생 단독 진입은 3.11을 따른다(P01 개정).
- `POST /auth/refresh`: 학부모·관리자만 httpOnly 쿠키로 갱신한다. 학생은 refresh 미발급이며 3.11에 따라 재진입한다. 동시 만료 요청은 refresh 1회 공유, 원 요청은 1회만 재시도한다.
- `POST /auth/student-sessions`: 기존 `{childId}` → `{accessToken,role:STUDENT}`.
- `GET /children`: 1.1 목록 봉투의 items에 `{childId,nickname,grade,birthYear,plan:FREE|PREMIUM}`. plan의 실제 상품/권한 응답 위치는 확인 대상이다.
- 학생 조회의 목업 DTO는 `frontend/web/src/domain/classroom.ts`의 화면 모델을 잠정 사용한다. Mission(제목·교과·학년·유형·질문·장면 표시 정보), Attempt(attemptId·studentId·mission·status·answers·도움·돌아보기), 목록은 1.1 봉투. draft는 3.6처럼 `{version,content:{answer,memo},savedAt}`로 직렬화한다. finish 전 reveal은 전송하지 않는다.
- 학생 홈·입력 틀 상세·최종 체크리스트의 완전한 DTO, SOLUTION_STEPS·CLASSIFICATION 제출 필드는 아직 미확정이다. 이 초안으로 임의 확정하거나 완료 체크하지 않는다.
- 시나리오 선택은 개발 브라우저 내부 이벤트로 전달하며 `/api/v1`에 가짜 운영 경로를 추가하지 않는다.

### 3.8 이슈 #7 학생 화면 확장 목업 계약 (백엔드 확인 대기)

아래는 6종 입력·홈·이어하기·마무리를 MSW로 구현하기 위한 프론트 계약 초안이다. 실제 Controller/OpenAPI 확정을 대신하지 않는다. 목 OFF에서도 같은 직렬화·경로를 사용하며, 실제 통합 검증은 별도다.

- `SOLUTION_STEPS` 제출: `{inputType:"SOLUTION_STEPS",finalAnswer:"...",steps:["..."]}`. 최종 답과 비어 있지 않은 풀이 단계 1개 이상 필수.
- `CLASSIFICATION` 제출: `{inputType:"CLASSIFICATION",assignments:[{choiceId:"c1",categoryId:"g1"}]}`. 미션의 모든 choice를 정확히 한 그룹에 배정한다. 미션 상세에 `categories:[{id,label}]`를 제공한다. 미정 그룹·항목·중복 배정은 422.
- `CHOICE`는 choiceIds 1개, `ORDERING`은 모든 choiceIds를 중복 없이 순서대로 전달한다. 모든 방식에 `dictatedByGuardian`(boolean)과 보완 시 `followupId`를 공통 적용한다. 메모는 제출에 포함하지 않는다.
- 미션 목록 항목: 기존 Mission + `status:NOT_STARTED|IN_PROGRESS|COMPLETED`, `attemptId?`, `position`, `total`. 공개 문항은 초3·초5 각 5개를 유지하고, 6종 입력 계약 시험용 추가 문항은 별도 개발 시나리오에만 제공한다.
- `GET /students/me/home`: `{student:Child,state:QueryState,period:{from,to},resume:Attempt|null,missions:Mission[]}`. 제출 전 초안만 있는 시도도 resume에 포함한다. 정답/예시/reveal/checklist는 마무리 전에 제공하지 않는다.
- `GET /me`: `{role:PARENT|ADMIN}` 또는 `{role:STUDENT,child:Child}`. 학부모·관리자만 refresh로 복원하며 학생은 메모리 access가 없으면 재진입한다. 토큰·로그인 정보는 브라우저 영구 저장소에 보관하지 않는다.
- Attempt의 `answers[].content?`는 제출 답변 내용만 담으며 메모는 없다. `draft`는 3.6의 version/content/savedAt 형식을 유지한다. 저장·제출·피드백 요청은 분리한다.
- finish 성공 후에만 `reveal`, `revealKind:ANSWER|EXAMPLE`, `checklist:Element[]`가 생긴다. Element는 3.2의 elementId/label/satisfied/quote/sourceType 형식을 사용한다. 체크는 satisfied와 원문 인용 존재가 모두 확인된 요소만 표시한다.
- 미검증 판정은 trial:true, HELD와 FAILED는 구분한다. 개발 시나리오 PARTIAL/RETHINK/CORRECT는 실제 모델 성능 판정이 아닌 고정 UI 시험 상태다.
- 브라우저 개발 목업의 새로고침 시험은 sessionStorage의 **가상 fixture 상태만** 복원한다. 실제 아동 정보를 입력하지 않으며 access/refresh 토큰·비밀번호는 저장하지 않는다. 실제 서버 저장·쿠키 보안 검증을 대신하지 않는다.

### 3.9 이슈 #8 학부모 목업 계약 보완 (백엔드 확인 대기)

기존 1.6·3.3·3.4 스키마를 그대로 사용한다. 목록은 1.1 봉투이며 아래 보완은 구현용 초안이다.

- 동의 문서: `{documentId,kind:TERMS|PRIVACY|GUARDIAN,version,title,content,required}`. Google 인증 뒤 동의 저장은 #37에서 제공한다. 자녀 등록은 기존 프로필 + 같은 `consents` 배열, 법정대리인 문서 동의 필수. P02에 따라 `/children/link`는 제공하지 않는다.
- `GET /me`: `{userId,name,email,role,permissions?:AdminPermission[]}`. 이름 수정은 `PATCH /me {name}`. `/me/reauth`는 Google 재인증 기반 `{reauthToken,expiresAt}`(#45). 닉네임·학년 변경은 `PATCH /children/{id}`이며 중요 변경은 `X-Reauth-Token` 헤더 사용(토큰 메모리 한정).
- summary: `{childId,state,period,inclusionRule,metrics:Metric[]}`. thinking-types: `{childId,state,period,items:[{type,state,missions:[{attemptId,title}],summary?}]}`. 학습 목록 봉투는 `childId,state,period,inclusionRule`도 포함한다. 상세는 학생 메모·draft를 제외한 시도 원문만 반환한다.
- 대화 목록/상세: `{conversationId,childId,period,title,createdAt,messages?:ConversationMessage[]}`. 메시지 `{messageId,question,status,scope,answer?,metrics?,evidence?,source?,fallback?,verification?,failureCode?,retryable?}`. SSE clarification 선택지는 `{label,scope:{childId,from,to}}[]`, status에 `messageId?`를 동봉해 실패 재시도 경로를 식별한다. scope가 다른 자녀면 해당 전역 범위로 명시 전환하며 이전 자녀 결과는 표시하지 않는다.
- evidence 조회는 `{items:Evidence[]}`. 삭제된 항목은 `available:false`이며 quote를 재사용하지 않는다. 410도 이용 불가로 표시한다. 대조 실패는 P16의 검증된 TEMPLATE result와 error 시나리오를 각각 시험한다. delta는 확정 데이터/캐시에 저장하지 않는다.
- 리포트 목록 항목은 3.4의 식별·기간·상태·revision 필드, 상세는 3.4 그대로 제공한다. 상세의 `items` 식별용으로 Metric/생각 유형/전후 변화 등에 `itemId?`만 추가한다. download는 `{url,expiresAt}`를 사용하며 목업 파일에는 가상 시연임을 명시한다. 재생성 202 이후 목록/상세를 재조회하며 기존 판을 보존한다.

### 3.10 이슈 #9 관리자 목업 계약 (백엔드 확인 대기)

ERD 3.2 report_job/job_execution, 3.5 model_version/audit_log/llm_usage, 4.1 mission/mission_version/rubric_version/mission_review를 camelCase로 매핑한다. 학생 이름·답변 원문·메모를 운영 DTO에 포함하지 않는다.

- `/me.permissions`: `CONTENT|PAYMENT_VIEW|PAYMENT_REFUND|SERVICE_OPS` 배열. 미제공이면 권한 없는 것으로 취급한다. UI 숨김과 별개로 모든 목 핸들러에서 권한 검사한다.
- overview: `{period,state,inclusionRule,attempts,completed,jobCounts:[{type,status,count}],missionCounts:[{status,count}]}`. 숫자는 목업 데이터에서 집계한다. 작업/미션 클릭 시 해당 필터 목록으로 연결한다.
- jobs 목록: 1.1 봉투. 항목 `{jobId,type,status,retryCount,failureReason,createdAt,updatedAt,executions:[{executionId,attemptNo,status,errorCode,errorDetail,triggeredBy,startedAt,finishedAt}]}`. retry는 같은 키의 최초 응답을 반환한다. 재시도 결과가 실패면 FAILED 유지. queues: `{items:[{name,length,dlq}]}`. audit 항목 `{id,actorUserId,action,targetType,targetId,result,detail,createdAt}`.
- 운영 요약 → 작업 목록의 집계 범위 유지를 위해 jobs 조회에 선택적 `from&to` 필터를 목업에서 함께 사용한다. 실제 backend의 필터 계약 확인 대상이다. 전후 변화 연결어는 목업만 `왜냐하면·때문·그래서·따라서` 고정 목록으로 시험하며 실제 서버의 확정 집계 목록을 대신하지 않는다.
- mission: `{missionId,status,demoOnly,currentVersion,currentRubricVersion,publishedVersion,versions:[{version,title,subject,gradeMin,gradeMax,thinkingType,inputType,question,guide,scene,sceneUri,staticSceneUri,achievementStandards,choices?,categories?,createdAt}],rubrics:[{version,elements:[{code,label,description,points,commonErrors,goodThought,judgeVerified}],answerKey?,exampleAnswer?,forbiddenTerms,hints}],reviews:[{missionVersion,rubricVersion,result,comment,createdAt}]}`.
- POST/PATCH mission는 위 version 필드+demoOnly를 받는다. PATCH와 rubric PUT은 새 불변 버전 추가. review-request는 `{missionVersion,rubricVersion}`, review는 같은 버전+`result:APPROVED|CHANGES_REQUESTED,comment`. publish 검증은 현재 버전 검토와 필수 콘텐츠/기준 확인, 422의 `missingFields[]` 표시. preview는 `{mission:Mission,missionVersion,rubricVersion}`이며 학생 장면/입력 컴포넌트만 재사용하고 답안은 포함하지 않는다. 업로드는 미구현(URI만 입력).
- model-version: ERD 필드 `{id,kind,name,version,status,artifactUri?,evalResult?,approvedBy?,activatedAt?,createdAt}`. 등록/활성화는 평가 근거와 승인자 필요, rollback은 이전 승인 버전을 재활성화하고 재분석 여부를 기록한다. ai-usage: `{period,items:[{callType,calls,failures,latencyMs,inputTokens,outputTokens,costUsd}]}`(원문·학생 ID 없음).
- error-report 목록/상세는 `{reportId,status,targetType,targetId,category,comment,reviewReason?,corrections:[{reason,corrected,createdAt,impact}],linkedAttempt?:PublicAttempt}`. SERVICE_OPS만 신고 연결 시도 원문을 상세에서 열람하고 매번 감사 기록한다. 정정은 기존 판정을 덮지 않고 새 이력과 영향 반영 여부를 반환한다.

### 3.11 학생 기기 등록·PIN 로그인 (P01 개정)

학부모 부재 시 자녀 단독 학습을 위한 경로다. 근거·대안 비교는 [보고서](../report/student-login-separation.md)를 따른다. 기존 `POST /auth/student-sessions`(학부모 동석)는 유지한다.

- 페어링 `POST /student-devices/pairings`
  - 학부모 토큰, `childIds[]`는 모두 `guardianship LINKED`이어야 함 (아니면 `403 CHILD_NOT_LINKED`)
  - 응답 `{pairingCode, expiresAt}`. 코드는 8자리 영숫자, 10분 유효·1회 사용, Redis 저장(원문 대신 해시 키)
  - 기본 등록 방식은 학부모 기기에서 코드·QR 발급 → 자녀 기기에서 입력·스캔. 로그인이 Google OAuth(#36)이므로 학부모가 자녀 기기에서 직접 로그인하면 브라우저에 Google 세션이 남을 수 있어 비권장
  - 부득이 자녀 기기에서 학부모가 로그인한 경우 클라이언트가 발급 직후 등록 API를 호출하고 학부모 세션을 로그아웃하며, Google 계정 로그아웃을 안내한다
- 등록 `POST /auth/student/devices`
  - 요청 `{pairingCode, label}` → 응답 `201 {deviceId, children:[{childId,nickname}]}` + `Set-Cookie: student_device=<랜덤 256bit>`
  - 서버는 토큰 해시만 저장, 만료 90일(설정값). 코드 오류·만료·재사용은 `400 PAIRING_CODE_INVALID`, IP 단위 시도 제한
- PIN 로그인 `POST /auth/student/login`
```jsonc
// 요청 (Cookie: student_device=...)
{ "childId": "c1...", "pin": "4831" }
// 200
{ "accessToken": "...", "role": "STUDENT", "child": { "childId": "c1...", "nickname": "별빛", "grade": 3 } }
// 401
{ "code": "STUDENT_PIN_INVALID", "status": 401, "remainingAttempts": 2 }
```
  - 검사 순서: 기기 쿠키 유효(해시 일치·미해제·미만료) → 자녀가 기기에 등록됨 → 기기 소유 학부모와 `LINKED`·`student ACTIVE`·필수 동의 유지 → PIN 설정 → 잠금 아님 → PIN 일치
  - 기기·자녀 불일치는 `401 STUDENT_DEVICE_INVALID`, 연결·동의 문제는 `403 CHILD_NOT_LINKED`
  - 불일치 시 `pin_failed_count` 증가, 5회째 `pin_locked_at` 기록 후 `423 STUDENT_PIN_LOCKED`. 성공 시 실패 횟수 0, 기기 `last_used_at` 갱신
  - refresh token 미발급. access 만료 시 PIN 재입력(초안은 자동 저장으로 보존). 학생 토큰 권한은 동석 경로와 동일
- PIN 설정 `PUT /children/{childId}/pin`
  - `X-Reauth-Token` 필수. 숫자 4~6자리, 동일 숫자 반복(`1111`)·연속(`1234`, `4321`) 거부 `422 VALIDATION_FAILED`
  - 해시 저장, 실패 횟수 0·잠금 해제. 잠긴 PIN의 해제 수단은 재설정뿐
- 기기 해제 `DELETE /student-devices/{deviceId}`: `revoked_at` 기록, 기존 학생 access token은 만료까지 유효
- 학부모 화면의 PIN 상태: `GET /children` 각 항목에 `pinSet`(설정 여부)·`pinLocked`(5회 실패 잠금 여부)를 함께 반환. PIN 원문·해시·실패 횟수는 반환하지 않음 (#59)
- 기기 등록·해제·PIN 설정은 `audit_log` 기록 (FN-ACC-10). PIN 잠금 시 학부모 알림은 알림 유형 추가와 함께 후속 확정

### 3.12 학생 화면 꾸미기 설정 (목업 계약 초안, 백엔드 확인 대기)

학생이 고른 생각 지도 테마와 동행 캐릭터를 기기와 관계없이 유지하기 위한 학생 본인 설정이다. 학습 기록·판정·리포트에 쓰지 않으며 학부모 화면에 노출하지 않는다. 대응 FN 항목이 없는 화면 개선 제안이므로 기능 명세 반영 여부도 함께 확인한다.

| Method | Path | 역할 | 설명 |
|---|---|---|---|
| GET | `/students/me/preferences` | 학생 | 현재 설정. 저장한 적 없으면 기본값과 `updatedAt:null` |
| PUT | `/students/me/preferences` | 학생 | 설정 전체 교체 `{theme, companion}` |

```jsonc
// GET 200 / PUT 200
{ "theme": "lake", "companion": "mungchi", "updatedAt": "2026-10-27T05:00:00Z" }
```
- `theme`: `lake`(호수)·`forest`(숲)·`factory`(공장)·`space`(소행성)·`sea`(바닷속). 기본 `lake`
- `companion`: `mungchi`(뭉치)·`tori`(토리)·`mongdol`(몽돌)·`kongi`(콩이)·`monggeul`(몽글). 기본 `mungchi`
- 목록에 없는 값은 `422 VALIDATION_FAILED`. 학생 토큰 전용, 학부모·관리자 토큰은 `403 FORBIDDEN`
- 숫자 레벨·보상·잠금 해제 조건 없이 언제든 바꿀 수 있다 (기능 명세 1.3의 숫자 레벨·등급·순위 비표시 원칙과 충돌하지 않음)
- 저장 위치(core 학생 테이블 컬럼 또는 별도 설정 테이블)와 값 목록 관리 방식은 백엔드 확정 대상

## 4. 내부 API (`/internal`)
- 인증: `X-Internal-Token` + 사용자 컨텍스트 헤더 `X-User-Id`, `X-User-Role`, `X-Student-Scope`(허용 학생 ID, 콤마 구분), `traceparent`
  - ai는 받은 컨텍스트 헤더를 learning 호출에 그대로 전달
  - 사용자 요청 없는 호출(report-worker): `X-User-Role: SYSTEM`, `X-Student-Scope` = 이벤트 `subject` 학생
- 외부에 노출하지 않음. NetworkPolicy로 호출 관계만 허용
- 범위 밖 학생 요청은 403

### 4.1 learning-service (호출: core, ai, report)
| Method | Path | 호출자 | 설명 |
|---|---|---|---|
| GET | `/internal/missions`, `/internal/missions/{id}` | core | 학생용 미션 조회 (2.2 프록시) |
| POST · GET · PUT | `/internal/attempts/...` | core | 시도·초안·도움·답변·마무리·돌아보기·자기 평가 (2.2 경로와 1:1) |
| POST | `/internal/answers/{answerId}/feedback` | core | 판정 오케스트레이션: 규칙 판정 또는 ai 호출 → 저장 → 결과 반환 (동기) |
| POST | `/internal/judgments/{judgmentId}/corrections` | core | 신고 정정 반영(SUP-03): `{reportId, reason, corrected}` → 기존 판정·사유·시점 보존 후 정정 이력 저장 (원본 답변 불변), `Idempotency-Key` |
| GET | `/internal/records/students/{studentId}/summary?from&to` | core, ai | 건수·상태 `Metric[]` |
| GET | `/internal/records/students/{studentId}/thinking-types?from&to` | core, ai, report | 유형별 미션·기록 |
| GET | `/internal/records/students/{studentId}/attempts?from&to` | core, ai, report | 시도 목록·상세(답변 버전·되묻기·도움·돌아보기 원문) |
| GET | `/internal/records/students/{studentId}/changes?from&to` | ai, report | 되묻기 전후 답변 쌍 |
| GET | `/internal/records/evidence?answerIds=` | core, ai, report | 원문 근거 조회 (삭제 시 `available:false`) |
| GET | `/internal/stats?from&to` | core | 운영 현황용 집계 (학생 원문 없음) |
| * | `/internal/admin/missions/...` | core | 2.8 미션 관리 프록시 |

### 4.2 ai-service (호출: learning, core, report)
| Method | Path | 호출자 | 요청 → 응답 |
|---|---|---|---|
| POST | `/internal/judgments` | learning | `{answerText, inputType, grade, rubric{elements[]}, versions}` → `{result, elements[{elementId, quote, verified, satisfied}], heldReason, trial, versions}` (M2 활성 시 scoring 교차 확인) |
| POST | `/internal/followups` | learning | `{timeline[], judgment, rubric, mission, grade}` → `{type, question, source, leakCheck{passed}, versions}` (정답·금지어 검사 실패 시 1회 재생성 `LLM_RETRY`, 재실패 시 `question` 없이 `leakCheck.passed = false` → learning이 질문 은행 `BANK` 선택, P16) |
| POST | `/internal/analysis/stream` | core | **SSE**. `{conversationId, question, scope{studentId, from, to}, history[]}` → 3.3과 같은 이벤트 |
| POST | `/internal/report-narratives` | report | `{metrics[], thinkingTypes[], changes[], reflections[], quotes[]}` → `{narrative, eveningQuestion, citedQuotes[]}` |
| GET | `/internal/versions` | core | 활성 프롬프트 버전 |

- LLM 요청에는 학생 이름·식별정보를 넣지 않음. 학생 ID는 가명 토큰으로 치환 (NFR-SEC-03)

### 4.3 scoring-service (호출: ai)
| Method | Path | 설명 |
|---|---|---|
| POST | `/internal/m2/scores` | `{prompt, text, grade, inputType}` → 총점 1~4점·8개 항목 1~5점·버전 (활성 범위 밖이면 `{active:false}`). `inputType`(`NARRATIVE`·`ESSAY`)으로 모델 선택(`m2-klue-narrative`·`m2-klue-essay`). `grade`(3~6)는 scoring이 `초{grade}`로 바꿔 모델 입력에 사용, 학습 데이터 학년(초5·6) 밖은 활성 범위 밖 |
| POST | `/internal/m1/checks` | `{problem, answerKey, solution}` → 정답 여부·실수 위치·확신도 (확신도 0.8 미만은 보류, P15) |
| GET | `/internal/versions` | 활성 모델 버전 |

### 4.4 report-service (호출: core)
- 호출 대상은 `report-api` Deployment (KEDA로 0까지 줄어드는 `report-worker`와 분리, [아키텍처 4.4](architecture.md#44-확장))

| Method | Path | 설명 |
|---|---|---|
| GET | `/internal/reports?studentId&status` | 리포트 목록 |
| GET | `/internal/reports/{reportId}` | 상세 (3.4 스키마) |
| GET | `/internal/reports/{reportId}/evidence/{itemId}` | 항목 근거 |
| GET | `/internal/reports/{reportId}/files/{format}` | 단기 presigned URL 발급 → `{url, expiresAt}` |

### 4.5 core-service (호출: ai, scoring, learning, report)
| Method | Path | 설명 |
|---|---|---|
| GET | `/internal/model-versions/active` | 기동 시 활성 모델·프롬프트 버전 조회 |
| POST | `/internal/deletion-requests/{deletionRequestId}/completions` | learning·report가 `student.deleted` 처리 후 완료 보고 `{service}`. 두 서비스 모두 보고 시 `COMPLETED` (멱등, P09) |

- 비동기 메시지(`report.generate` 등)는 [아키텍처 1.4](architecture.md#14-메시지-목록) 참고


### 5.1 #36 Google OAuth·토큰 구현 계약 (개정 P01 정렬)

구현된 6개 인증 경로의 정식 공개 계약은 [core-service OpenAPI](../../contracts/openapi/core-service.yaml)를 따른다. #58 신규 기기·PIN API는 이 파일에 구현된 것으로 포함하지 않는다.

- #58 인계 경계: `POST /auth/student/devices`, `GET /auth/student/profiles`, `POST /auth/student/login`만 Bearer 검사에서 제외한다. POST는 기존 쿠키 API와 같은 정확한 web Origin·X-Requested-With 검사를 유지한다. 실제 페어링 코드·기기 쿠키·PIN 검증은 #58 핸들러가 수행한다. 다른 메서드·하위/유사 경로와 `/auth/student-sessions`는 제외하지 않는다. 현재 #58 핸들러가 없어 이 3개 경로는 유효한 요청 출처에서 Bearer 없이 MVC까지 도달한 뒤 404가 된다.

학생 기기·PIN 정책은 3.11을 따른다. 이 절은 부모·관리자 Google 인증과 기존 동석 경로의 실제 구현 계약이다. 기기 등록·PIN 신규 API 7개는 아직 미구현이며 준비 상태를 성공으로 대체하지 않는다.

- 학부모·관리자: Google core 콜백 → refresh 쿠키 → web `/oauth/complete` → refresh → `/me`. access는 HS256, 기본 15분·메모리 보관. refresh는 256비트 난수·SHA-256 해시 저장, 최초 로그인부터 최대 7일이며 회전으로 연장하지 않는다. 재사용 시 해당 세션 폐기.
- 학생(동석·단독 공통): access 전용, refresh 미발급. 동석 `/auth/student-sessions`는 부모 refresh를 소비하고 세션 버전·역할·학생 범위를 변경하며 부모 refresh 쿠키를 만료시킨다. 학생 상태에서 `/auth/refresh`는 401이다. 기존 부모 access도 거부한다. 단독 PIN 로그인은 3.11 후속 구현 범위다.
- JWT에는 `sub`(계정 UUID), `sid`, `ver`, `role`, `studentId`(학생만), `iss`, `aud`, `iat`, `exp`, `jti`를 넣는다. 매 요청에서 세션·현재 계정·자녀 연결·동의를 확인한다. 기기 해제 시 기존 학생 access를 즉시 폐기하는 별도 정책은 추가하지 않는다.
- 학부모 access 기본 15분, 학생은 `AUTH_STUDENT_ACCESS_TTL`로 별도 관리하며 초기 기본값은 15분이다. 학생 만료·새로고침 시 자동 refresh하지 않고 학생 진입 화면으로 이동한다. 기기·PIN API 구현 전에는 단독 진입 준비 상태와 학부모 동석 진입을 안내한다. 토큰을 영구 저장해 새로고침을 우회하지 않는다.
- 부모 refresh 응답 `{accessToken,expiresIn,role,nextAction,startPath}` + 회전 쿠키. 동석 응답 `{accessToken,expiresIn,role:STUDENT,child,nextAction:READY,startPath:/student/home}` + refresh 쿠키 삭제. child는 `{id,nickname,grade,birthYear}`(기존 #7 소비자 계약)이다. 향후 단독 경로 3.11의 `childId`는 프론트 경계에서 정규화한다.
- `GET /me`는 부모/관리자에게 `{userId,name,email,role,permissions,nextAction,startPath}`, 학생에게 `{role,child,nextAction,startPath}`만 반환한다. 학생에게 부모 개인정보·권한을 반환하지 않는다. 학생은 `/me/consents` 등 부모 계정 관리 API를 사용할 수 없다.
- 로그아웃은 현재 쿠키의 부모 세션 또는 Bearer로 전달된 학생 세션을 종료하고 refresh 쿠키를 삭제한다. 다른 기기는 유지한다. 쿠키 API는 정확한 web Origin과 `X-Requested-With: XMLHttpRequest`를 요구한다.
- web/API 동일 origin. refresh 쿠키 `sagomungchi_refresh`: HttpOnly·Secure·SameSite=Strict·Path=/api/v1/auth. OAuth 상태 쿠키 `sagomungchi_oauth`: HttpOnly·Secure·SameSite=Lax·Path=/api/v1/auth/google, 10분. 로컬 HTTP만 Secure=false.
- Google state·nonce·PKCE S256 및 ID 토큰 JWKS 서명·iss·aud·exp·nonce 검증. 서비스 토큰을 URL에 넣지 않는다. callback 성공은 `/oauth/complete`, 실패는 `/login?oauthError=<고정 코드>`.
- 부모/관리자 refresh는 Web Locks로 탭 간 직렬화한다. 학생 전환·로그아웃 알림을 받은 다른 탭은 토큰·캐시를 지우며 학생 refresh로 다시 로그인하지 않는다. 학생→부모 복귀는 Google 로그인부터 시작한다.
- 학생 access 수명·기기/PIN 기능은 #58, Google 재인증은 #45, 기기/PIN migration은 V8 이후 다음 버전으로 분리한다. 세부 TTL 등은 후속 기능에서 확정한다. 계정 복구·비밀번호 변경 API는 Google 단일 로그인 범위에서 제외한다.
