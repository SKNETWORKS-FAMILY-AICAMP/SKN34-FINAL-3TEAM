# 시퀀스 다이어그램

- 근거: [아키텍처 설계](architecture.md) 1장(통신 원칙·메시지·신뢰성 규칙), [API 명세서](api-spec.md), [ERD](erd.md), [클래스 다이어그램](class-diagram.md), [유스케이스](usecase.md) 4장
- 범위: 서비스 간 호출이 있거나 상태 전이·멱등 처리가 필요한 핵심 흐름. 단순 조회(CRUD)는 생략
- 상태값 전이 조건은 [상태 다이어그램](state-diagram.md)
- `(P04)` 형태는 확정 정책 번호, 내용은 [기능명세서 1.4](functional-spec.md#14-확정-정책)

---

## 1. 공통 규칙

| 항목 | 규칙 |
|---|---|
| 참여자 | `Web` · `core` · `learning` · `ai` · `scoring` · `report-api` · `report-worker` · `MQ`(RabbitMQ) · `Redis` · `DB`(해당 서비스 DB) · `LLM` · `Toss` · `S3` |
| 화살표 | `->>` 동기 호출, `-->>` 동기 응답, `-)` 비동기 발행(메시지·이벤트) |
| 내부 호출 | 모든 서비스 간 HTTP에 `X-Internal-Token`·`X-User-*`·`X-Student-Scope`·`traceparent` 자동 첨부 (`InternalRestClientFactory`·`internal_client`), 다이어그램에서는 생략 |
| 트랜잭션 | `rect` 영역 = DB 트랜잭션 1개. 영역 안에 서비스 간 HTTP·AMQP 호출 없음 (아키텍처 2.2) |
| 재시도 | LLM 호출만 ai `LlmClient`에서 재시도, 서비스 간 호출은 재시도 없음 (아키텍처 1.3) |
| SSE | 15초 heartbeat `: ping`은 모든 SSE 공통이라 생략 |

---

## 2. 계정·자녀 연결

### 2.1 로그인·토큰 재발급 (#36 Google OAuth)

학부모·관리자만 해당. 학생은 refresh 없이 2.4 경로로 진입. 세부 계약은 [API 명세 5.1](api-spec.md#51-36-google-oauth토큰-구현-계약-개정-p01-정렬)·[OpenAPI](../../contracts/openapi/core-service.yaml)

```mermaid
sequenceDiagram
  autonumber
  actor U as 사용자
  participant W as Web
  participant C as core
  participant G as Google
  participant DB as core_db

  U->>W: Google 계정으로 계속하기
  W->>C: GET /auth/google/authorize
  C-->>W: 302 Google 인가 URL (state·nonce·PKCE S256) + Set-Cookie sagomungchi_oauth (SameSite=Lax, 10분)
  W->>G: 계정 선택·동의
  G-->>W: 302 /auth/google/callback?code&state
  W->>C: GET /auth/google/callback (상태 쿠키)
  C->>C: state 쿠키 대조
  C->>G: 코드 교환 (code_verifier) → ID 토큰 JWKS·iss·aud·exp·nonce 검증
  alt 취소·검증 실패·같은 이메일 기존 계정
    C-->>W: 302 /login?oauthError=CANCELLED|OAUTH_FAILED|ACCOUNT_EXISTS|OAUTH_UNAVAILABLE
  else 성공
    rect rgba(128,128,128,0.12)
      C->>DB: user_account 조회 (provider+sub), 없으면 PARENT 생성 (이메일 자동 연결 없음)
      C->>DB: auth_session·refresh_token(token_hash) 저장 (최초 로그인부터 7일)
    end
    C-->>W: 302 /oauth/complete + Set-Cookie sagomungchi_refresh (HttpOnly·SameSite=Strict·Path=/api/v1/auth)
  end
  W->>C: POST /auth/refresh (쿠키, Origin·X-Requested-With)
  C-->>W: 200 {accessToken, expiresIn, role, nextAction, startPath} + 회전 쿠키
  W->>C: GET /me (Bearer)
  C-->>W: 200 역할·nextAction(CONSENT_REQUIRED·CHILD_REGISTRATION_REQUIRED·READY)·startPath
  Note over W: access token은 메모리 보관
  W->>C: API 호출 (Bearer)
  C-->>W: 401 TOKEN_EXPIRED
  W->>C: POST /auth/refresh (쿠키, 탭 간 Web Locks로 1회)
  rect rgba(128,128,128,0.12)
    C->>DB: auth_session 행 잠금 → refresh_token 재조회
    alt 이미 사용한 토큰 (재사용)
      C->>DB: auth_session 폐기 (commit)
    else 유효
      C->>DB: used_at 기록 + 새 refresh 저장 (세션 만료 연장 없음)
    end
  end
  C-->>W: 200 새 accessToken (재사용이면 401 REFRESH_REUSED)
  W->>C: 원래 요청 재시도
```

### 2.2 자녀 등록·법정대리인 동의

```mermaid
sequenceDiagram
  autonumber
  participant W as Web
  participant C as core
  participant DB as core_db

  W->>C: GET /consent-documents
  C-->>W: 현재 문서 버전 (TERMS·PRIVACY·GUARDIAN)
  W->>C: POST /children {nickname, grade, birthYear, consents[]}
  C->>C: GuardianshipService.registerChild
  C->>DB: 현재 필수 문서(required)·LINKED 자녀 수 조회
  alt 필수 GUARDIAN 동의 누락·학년 3~6 밖
    C-->>W: 400 VALIDATION_FAILED
  else 자녀 3명 이미 등록
    C-->>W: 409 CHILD_LIMIT_REACHED
  else
    rect rgba(128,128,128,0.12)
      C->>DB: student 저장 (가명 닉네임·학년·출생연도)
      C->>DB: guardianship 저장 (REGISTER, LINKED)
      C->>DB: consent 저장 (주체·문서 버전·시점)
    end
    C-->>W: 201 childId
  end
```

- 자녀는 전원 만 14세 미만으로 간주, GUARDIAN 동의를 항상 필수로 받음 (P01)
- 다른 보호자의 기존 자녀 연결 없음 (P02). 연결 해제(`unlink`)는 `X-Reauth-Token` 확인 후 처리, `audit_log` 기록 (FN-ACC-10)

### 2.4 학생 진입 (P01)

진입 경로는 학부모 동석(아래 첫 다이어그램)과 등록 기기 + PIN 단독 진입(기기 등록·PIN 로그인 다이어그램) 두 가지다 (2026-10-27 개정, API 명세 3.11).

```mermaid
sequenceDiagram
  autonumber
  participant W as Web
  participant C as core
  participant DB as core_db

  Note over W: 학부모 로그인 상태에서 상단 자녀 전환으로 자녀 선택
  W->>C: POST /auth/student-sessions {childId} (학부모 Bearer + refresh 쿠키)
  C->>DB: auth_session 잠금·Bearer와 같은 세션 확인, guardianship (parent, childId, LINKED)·student ACTIVE·필수·법정대리인 동의 확인
  alt 미연결·삭제·필수 동의 철회
    C-->>W: 403 CHILD_NOT_LINKED
  else
    rect rgba(128,128,128,0.12)
      C->>DB: 부모 refresh 소비, auth_session role=STUDENT·student_id·version+1·만료=학생 access TTL
    end
    C-->>W: 200 {accessToken, expiresIn, role STUDENT, child, nextAction READY, startPath} + refresh 쿠키 삭제
  end
  Note over W: 학생 refresh 미발급. 기존 부모 access는 version 불일치로 거부
  Note over W: 이후 학생 API는 학생 토큰으로 호출. URL 식별값(?student=) 진입 없음
```

기기 등록 (학부모 1회 승인)

```mermaid
sequenceDiagram
  autonumber
  participant P as Web(학부모)
  participant K as Web(자녀 기기)
  participant C as core
  participant R as Redis
  participant DB as core_db

  P->>C: POST /student-devices/pairings {childIds[]} (학부모 Bearer)
  C->>DB: 각 childId guardianship LINKED 확인
  alt 미연결 자녀 포함
    C-->>P: 403 CHILD_NOT_LINKED
  else
    C->>R: 페어링 코드 해시 저장 (parentId, childIds, 10분, 1회용)
    C-->>P: 200 {pairingCode, expiresAt} → QR 표시
  end
  K->>C: POST /auth/student/devices {pairingCode, label}
  C->>R: 코드 조회 후 즉시 삭제
  alt 없음·만료·재사용
    C-->>K: 400 PAIRING_CODE_INVALID
  else
    rect rgba(128,128,128,0.12)
      C->>DB: student_device 저장 (token_hash, expires_at)
      C->>DB: student_device_child 저장
      C->>DB: audit_log 기록
    end
    C-->>K: 201 {deviceId, children[]} + Set-Cookie student_device (httpOnly)
  end
```

PIN 로그인 (학부모 부재 시 단독 진입)

```mermaid
sequenceDiagram
  autonumber
  participant K as Web(자녀 기기)
  participant C as core
  participant DB as core_db

  K->>C: GET /auth/student/profiles (Cookie student_device)
  C-->>K: 200 [{childId, nickname, pinSet, locked}]
  Note over K: 자녀 프로필 선택 → PIN 입력
  K->>C: POST /auth/student/login {childId, pin} (Cookie student_device)
  C->>DB: student_device token_hash 조회·미해제·미만료·자녀 등록 확인
  alt 기기 무효·자녀 미등록
    C-->>K: 401 STUDENT_DEVICE_INVALID
  else 미연결·삭제·필수 동의 철회
    C-->>K: 403 CHILD_NOT_LINKED
  else PIN 미설정
    C-->>K: 409 STUDENT_PIN_NOT_SET
  else 잠금 상태
    C-->>K: 423 STUDENT_PIN_LOCKED
  else PIN 불일치
    C->>DB: pin_failed_count 증가 (5회째 pin_locked_at 기록)
    C-->>K: 401 STUDENT_PIN_INVALID {remainingAttempts} 또는 423
  else
    C->>DB: pin_failed_count 0, student_device.last_used_at 갱신
    C-->>K: 200 학생 accessToken (role STUDENT, refresh 없음)
  end
  Note over K: access 만료 시 PIN 재입력. 학부모 화면은 학부모 로그인 필요
```

- PIN 잠금 해제는 학부모 `PUT /children/{childId}/pin`(재확인 필요)으로만 가능
- 학부모가 기기를 해제하면(`DELETE /student-devices/{deviceId}`) 이후 PIN 로그인은 `401 STUDENT_DEVICE_INVALID`

### 2.3 자녀 범위 권한 확인 (모든 자녀 대상 API 공통)

```mermaid
sequenceDiagram
  autonumber
  participant W as Web
  participant C as core
  participant DB as core_db
  participant L as learning

  W->>C: GET /children/{childId}/summary?from&to (Bearer)
  C->>C: PublicAuthFilter → UserContext(userId, PARENT)
  C->>DB: guardianship (parent, childId, LINKED) 존재 확인
  alt 미연결
    C-->>W: 403 CHILD_NOT_LINKED
  else 연결됨
    C->>C: UserContext.studentScope = {childId}
    C->>L: GET /internal/records/students/{childId}/summary (X-Student-Scope: childId)
    L->>L: InternalAuthFilter → requireStudent(childId)
    L-->>C: Metric[] + state + period
    C-->>W: 200
  end
```

---

## 3. 미션 학습

### 3.1 시작·초안 저장·답변 제출

```mermaid
sequenceDiagram
  autonumber
  participant W as Web
  participant C as core
  participant L as learning
  participant DB as learning_db

  W->>C: POST /missions/{missionId}/attempts
  C->>L: POST /internal/missions/{missionId}/attempts?grade&demo
  L->>DB: 진행 중 시도 확인
  alt 진행 중 시도 있음
    L-->>C: 200 기존 attempt (이어하기, 공개 중단·학년 변경과 무관)
  else
    L->>DB: 공개·학년·시연 범위 미션 확인
    alt 비공개·범위 밖 미션
      L-->>C: 409 MISSION_NOT_AVAILABLE
    else
      L->>DB: attempt 저장 (IN_PROGRESS, 당시 mission·rubric 버전 고정) + 빈 초안(version 0)
      L-->>C: 201 attempt
    end
  end
  C-->>W: attempt

  W->>C: PUT /attempts/{id}/draft (If-Match: "7")
  C->>L: PUT /internal/attempts/{id}/draft
  L->>DB: UPDATE attempt_draft ... WHERE version = 7
  alt 영향 0행
    L-->>C: 409 ATTEMPT_DRAFT_CONFLICT + latest
    C-->>W: 409 (현재 입력 유지, 충돌 안내)
  else
    L-->>C: 200 version 8·savedAt (ETag)
    C-->>W: 200
  end

  W->>C: POST /attempts/{id}/answers (Idempotency-Key: k1)
  C->>C: IdempotencyService (user, k1) 조회
  alt 같은 키·같은 본문 기록 있음
    C-->>W: 저장된 최초 응답 그대로
  else 같은 키·다른 본문
    C-->>W: 422 IDEMPOTENCY_KEY_REUSED
  else 새 요청
    C->>L: POST /internal/attempts/{id}/answers (Idempotency-Key: k1)
    rect rgba(128,128,128,0.12)
      L->>DB: attempt 행 잠금(FOR UPDATE)·본인 시도 확인
      L->>DB: 같은 시도·키의 answer 조회 (같은 본문이면 201 그 답변, 다른 본문이면 422 IDEMPOTENCY_KEY_REUSED)
      L->>L: 마무리·완료 409 ATTEMPT_CLOSED · 입력 방식 다름 400 · 누락 422 ANSWER_INCOMPLETE
      L->>DB: 보완이면 가장 최근 미답 되묻기와 followupId 확인 (아니면 422 ANSWER_INCOMPLETE)
      L->>DB: answer 저장 (version = 이전+1, previous_answer_id·followup_id 연결)
      L->>DB: judgment 저장 (PENDING)
      L->>DB: attempt_draft 답 칸 비움 (memo 유지, version +1)
    end
    L-->>C: 201 answerId·version·feedback.status=PENDING
    C->>C: idempotency_record 저장
    C-->>W: 201
  end
```

- 저장 성공(201)과 이후 피드백 처리 성공을 분리 (FN-LRN-10). 피드백은 3.2의 별도 요청
- learning도 시도·키(ERD UK)로 같은 키를 처리. core가 learning 응답을 받기 전에 끊겨 다시 보내도 답변은 1건
- 메모는 초안 `content.memo`로 함께 저장, 학생 본인 조회에만 포함 (P05)
- 무료 플랜은 시도 시작 시 하루 3개 미션 한도 확인, 초과 시 `429 USAGE_LIMIT_REACHED` (P13)

### 3.2 피드백 SSE (판정·되묻기)

```mermaid
sequenceDiagram
  autonumber
  participant W as Web
  participant C as core
  participant L as learning
  participant DB as learning_db
  participant A as ai
  participant S as scoring
  participant LLM as LLM

  W->>C: POST /answers/{answerId}/feedback (SSE)
  C-->>W: event status {RUNNING}
  C->>L: POST /internal/answers/{answerId}/feedback (동기)
  L->>DB: judgment 조건부 전이 PENDING·FAILED·리스 만료 RUNNING → RUNNING
  alt 이미 DONE
    L-->>C: 저장된 결과
  else 유효 리스 RUNNING (다른 요청이 처리 중)
    L-->>C: 200 {status: RUNNING, judgment·followup·versions: null, nextActions: []}
  else 전이 성공
    alt 고르기·수학 최종 답
      L->>L: ChoiceJudge·MathEquivalenceJudge
    else 서술·논술·풀이 단계
      L->>A: POST /internal/judgments {answerText, rubric(judge_verified 포함), grade, versions}
      A->>LLM: 기준표 요소별 근거 구절 추출 (학생 이름 미포함)
      LLM-->>A: quotes[]
      A->>A: QuoteVerifier 원문 대조 → JudgmentService 요소 충족·결과 결정 (JUDGE_REQUIRE_VERIFIED=true면 미검증 요소 HELD(UNVERIFIED_SCOPE))
      opt M2 활성 범위
        A->>S: POST /internal/m2/scores
        S-->>A: 항목 점수 또는 {active:false}
        A->>A: LLM 관찰과 불일치 시 HELD(MODEL_DISAGREEMENT)
      end
      opt 풀이 단계(SOLUTION_STEPS) + M1 활성 범위
        A->>S: POST /internal/m1/checks
        S-->>A: 정답 여부·실수 위치·확신도
        A->>A: 확신도 0.8 미만이면 HELD(LOW_CONFIDENCE) (P15)
      end
      A-->>L: result·elements·heldReason·trial·versions
    end
    opt 되묻기 대상 (시도 내 되묻기 2회 미만, 고르기 CORRECT 아님, 마무리·완료 전, P04)
      L->>A: POST /internal/followups {timeline, judgment, rubric, mission, grade}
      A->>LLM: 되묻기 생성
      A->>A: LeakGuard 정답·금지어 검사
      opt 검사 실패
        A->>LLM: 1회 재생성 (source = LLM_RETRY)
      end
      A-->>L: type·question·source·leakCheck·versions
      opt 재생성도 검사 실패 (leakCheck.passed = false, question 없음)
        L->>DB: followup_bank_question에서 같은 type 활성 질문 선택 (source = BANK, P16)
      end
    end
    A--)A: llm.usage.recorded 발행 (best-effort)
    alt 위 처리 중 예외 (ai·LLM 실패, 타임아웃)
      L->>DB: judgment FAILED (failure_code, retry_count+1, 획득한 리스일 때만)
      L-->>C: 503 AI_UNAVAILABLE retryable
    else 정상
      rect rgba(128,128,128,0.12)
        L->>DB: attempt 행 잠금(FOR UPDATE)·마무리 여부 다시 확인 → judgment DONE + judgment_element + followup(마무리 전일 때만) + 버전 저장 (획득한 리스일 때만, 리스를 잃었으면 저장 없이 현재 상태)
      end
      L-->>C: 200 FeedbackResult
    end
  end
  alt status RUNNING 수신
    C-->>W: event status → done (클라이언트가 잠시 후 재요청)
  else 503 수신
    C-->>W: event error {AI_UNAVAILABLE, retryable:true} → done
  else 결과 수신 (저장 결과 포함)
    C-->>W: event result {judgment, followup, nextActions, versions} → done
  end
```

- 클라이언트가 끊겨도 core→learning 호출은 끝까지 진행·저장, 재요청 시 저장 결과 반환 (API 3.2)
- 타임아웃 예산: core→learning 80초 > learning→ai(judgments 35초 + followups 35초), 판정 리스 90초 (P12, 아키텍처 1.3)
- `nextActions`: 되묻기 생성 시 `[ANSWER_FOLLOWUP, FINISH]`(FINISH = "이대로 돌아보기"), 되묻기 2회 소진·고르기 CORRECT면 `[FINISH]` (P04)
- 판정 보류(`result = HELD`)는 정상 처리(`DONE`), 처리 실패(`process_status = FAILED`)와 구분 (NFR-REL-04)
- 보류 사유 결정은 모두 ai 담당, learning은 `judge_verified`·학년을 포함한 기준표 전달 (상태 다이어그램 3.3)

### 3.3 마무리·정답 공개·돌아보기

```mermaid
sequenceDiagram
  autonumber
  participant W as Web
  participant C as core
  participant L as learning
  participant DB as learning_db

  W->>C: POST /attempts/{id}/finish
  C->>L: POST /internal/attempts/{id}/finish
  L->>DB: attempt 행 잠금(FOR UPDATE)·본인 시도 확인 (이미 마무리했으면 기록 없이 같은 결과)
  L->>DB: 타임라인(답변·판정·되묻기) 조회
  L->>L: FinishPolicy.canFinish (판정 DONE 1회 이상, P04)
  alt 조건 미충족
    L-->>C: 409 REVEAL_CONDITION_UNMET
    C-->>W: 409 (정답·예시 답 비공개)
  else 충족
    L->>DB: attempt.finished_at 기록
    L-->>C: 정답(닫힌 문제)·예시 답(열린 문제)·verified 요소만 체크한 체크리스트
    C-->>W: 200
  end
  opt 자기 평가 (선택)
    W->>C: POST /attempts/{id}/self-assessment
    C->>L: POST /internal/attempts/{id}/self-assessment {checks}
    L-->>C: 자기 체크 저장 (판정·원본 불변), AI 확인 항목과 나란히 반환 (마무리 전·완료 뒤 409)
    C-->>W: 200
  end
  W->>C: POST /attempts/{id}/reflection {difficulty, text}
  C->>L: POST /internal/attempts/{id}/reflection
  L->>DB: attempt 행 잠금(FOR UPDATE)·본인 시도 확인
  alt finished_at 없음 (마무리 전) 또는 이미 완료
    L-->>C: 409 REVEAL_CONDITION_UNMET (완료 뒤면 ATTEMPT_CLOSED)
    C-->>W: 409
  else
    rect rgba(128,128,128,0.12)
      L->>DB: reflection 저장
      L->>DB: attempt IN_PROGRESS → COMPLETED, completed_at
    end
    L-->>C: 200
    C-->>W: 200 학습 완료
  end
```

---

## 4. 대시보드 조회
- 2.3 권한 확인 후 core가 learning `/internal/records/...`를 그대로 프록시 (서비스 간 추가 호출 없음)
- 응답의 `state`(`OK`·`NO_RECORD`·`INSUFFICIENT_SAMPLE`)와 조회 실패(5xx → `FAILED`)를 화면에서 구분 (FN-DSH-11)

---

## 5. 분석 대화 SSE

```mermaid
sequenceDiagram
  autonumber
  participant W as Web
  participant C as core
  participant CDB as core_db
  participant A as ai
  participant LLM as LLM
  participant L as learning

  W->>C: POST /conversations/{id}/messages {question, scope?} (SSE)
  C->>CDB: guardianship LINKED 확인 (scope 자녀)
  C->>C: Conversation.resolveScope (생략 시 확인된 자녀·기간 유지)
  C->>CDB: conversation_message 저장 (QUEUED → RUNNING)
  C->>A: POST /internal/analysis/stream {question, scope, history[]} (X-Student-Scope: childId)
  A->>A: classify
  A->>LLM: 질문 의도·대상·기간 분류
  A->>A: clarify_scope
  alt LLM 키 부재·호출 실패 (P16)
    A->>L: 확인된 범위의 기본 기록 조회 (summary·attempts)
    A->>A: compute + RuleResponder 템플릿 구성
    A-->>C: event result {answer, metrics, evidence, source: TEMPLATE, fallback: AI_UNAVAILABLE}
    C->>CDB: message COMPLETED (source = TEMPLATE) + message_evidence
    C-->>W: event result → done (실패 사실 표시)
  else 대상·기간 불명확 또는 현재 선택과 충돌
    A-->>C: event clarification {question, options[]}
    C->>CDB: message COMPLETED + clarification 저장
    C-->>W: event clarification → done
  else 범위 확정
    A->>A: plan (조회 도구 선택)
    loop 도구 호출마다
      A->>A: require_student(scope.studentId)
      A->>L: GET /internal/records/students/{id}/... (헤더 그대로 전달)
      L-->>A: 기록·Metric[]·state
    end
    A->>A: compute (calculators, 코드 계산)
    A-->>C: event status {기록 조회 완료}
    C-->>W: event status
    A->>LLM: answer (조회·계산 결과 기반 답변, 스트리밍)
    loop 답변 조각
      A-->>C: event delta {text}
      C-->>W: event delta (대조 전 임시 표시)
    end
    A->>A: verify (AnswerVerifier 숫자·인용 대조)
    alt 대조 실패 (P16)
      A->>A: RuleResponder: 계산된 metrics·evidence만 템플릿 문장으로 구성
      A-->>C: event result {answer, metrics, evidence, source: TEMPLATE, fallback: VERIFICATION_FAILED}
      C->>CDB: message COMPLETED (source = TEMPLATE) + message_evidence
      C-->>W: event result → done (delta 임시 텍스트 폐기, 실패 사실 표시)
    else 대조 통과
      A-->>C: event result {answer, metrics, evidence, verification, recordCount}
      rect rgba(128,128,128,0.12)
        C->>CDB: message COMPLETED + answer·metrics·verification·버전
        C->>CDB: message_evidence (attemptId·answerId·version만)
      end
      C-->>W: event result → done
    end
  end
  A--)A: llm.usage.recorded 발행
  opt 기록 조회 실패·ai 서비스 장애
    C->>CDB: message FAILED (AI_UNAVAILABLE, 재시도 가능)
    C-->>W: event error → done
  end
  opt 클라이언트 단절
    C->>A: 스트림 취소
    C->>CDB: message FAILED (CLIENT_DISCONNECTED, 재시도 가능)
  end
```

- 재시도(`/messages/{id}/retry`): 같은 행 `FAILED → RUNNING` 조건부 전이 후 같은 흐름 (ERD 3.2)
- 대조 실패·LLM 키 부재·호출 실패 시 규칙 응답 모드(`source = TEMPLATE`), 기록 조회 자체 실패는 `error` (FN-AGT-06·10, P16)
- 무료 플랜은 대화 생성 시 `429 USAGE_LIMIT_REACHED`, 프리미엄은 하루 30회 (P13)
- 근거 확인(`/evidence`): core가 `message_evidence` ID로 learning `/internal/records/evidence` 조회, 삭제된 기록은 `available: false`

---

## 6. 주간 리포트

### 6.1 자동 생성

```mermaid
sequenceDiagram
  autonumber
  participant SCH as core 스케줄러
  participant C as core
  participant CDB as core_db
  participant MQ as RabbitMQ
  participant RW as report-worker
  participant RDB as report_db
  participant L as learning
  participant A as ai
  participant S3 as S3

  SCH->>SCH: 매주 월 07:00 KST, @SchedulerLock 획득 (ShedLock, 1개 레플리카만) (P06)
  loop ACTIVE 학생마다 (기록 없어도 포함, 대상 주 = 직전 월~일 KST, P06)
    rect rgba(128,128,128,0.12)
      SCH->>CDB: report_job 저장 (SCHEDULE, QUEUED) — 부분 UK로 중복 방지
      SCH->>CDB: outbox_event (report.generate, narrativeEnabled = 프리미엄 여부 P13) 저장
    end
  end
  C->>CDB: OutboxRelay 미발행 행 조회
  C-)MQ: cmd.direct / report.generate (publisher confirm)
  C->>CDB: published_at 기록
  MQ-)RW: report.report.generate 소비 (수동 ACK)
  RW->>RW: bind_user_context(SYSTEM, scope = subject 학생)
  RW->>RDB: job_id로 weekly_report 조회
  alt 없음 (최초 소비)
    rect rgba(128,128,128,0.12)
      RW->>RDB: weekly_report 저장 (job_id UK, RUNNING)
      RW->>RDB: outbox_event (report.started)
    end
  else 기존 COMPLETED·FAILED (재전달)
    RW->>MQ: ACK 후 종료 (종료 이벤트는 같은 트랜잭션 outbox에 이미 저장)
  else 기존 RUNNING (이전 Pod 중단 후 재전달)
    Note over RW: 같은 행으로 아래 처리 처음부터 재실행
  end
  RW->>L: GET /internal/records/students/{id}/thinking-types·attempts·changes
  L-->>RW: 기간 내 기록
  RW->>RW: MetricsCalculator (기간 확정·수치·전후 변화·state)
  alt 기록 없음·표본 부족
    RW->>RW: state = NO_RECORD·INSUFFICIENT_SAMPLE (가능한 요약만)
  end
  alt NO_RECORD 또는 narrativeEnabled = false
    RW->>RW: 서술 생략 (NO_RECORD는 기록 없음 안내 문구, 무료는 narrative null) (P06, P13)
  else
    RW->>A: POST /internal/report-narratives {metrics, thinkingTypes, changes, reflections, quotes}
    A-->>RW: narrative·eveningQuestion·citedQuotes
    RW->>L: GET /internal/records/evidence?answerIds=
    RW->>RW: ReportVerifier 숫자·인용 대조
    opt 대조 실패 (P16)
      RW->>RW: 템플릿 요약으로 교체 (narrative.source = TEMPLATE)
    end
  end
  RW->>RW: ReportRenderer HTML·PDF·MD
  RW->>S3: 파일 업로드
  alt 처리 성공
    rect rgba(128,128,128,0.12)
      RW->>RDB: weekly_report COMPLETED + report_item·evidence·report_file
      RW->>RDB: outbox_event (report.completed)
    end
  else 처리 실패
    rect rgba(128,128,128,0.12)
      RW->>RDB: weekly_report FAILED (failure_reason)
      RW->>RDB: outbox_event (report.failed)
    end
  end
  RW->>MQ: ACK
  RW-)MQ: events.topic / report.started·completed·failed (OutboxRelay)
  MQ-)C: core.report.events 소비
  C->>CDB: processed_event 저장 (중복이면 무시)
  C->>CDB: report_job 조건부 전이 (started: QUEUED → RUNNING / completed·failed: QUEUED·RUNNING → COMPLETED·FAILED + report_id)
  opt report.completed
    C->>C: NotificationService.notify (REPORT_COMPLETED, source_event_id)
  end
```

- 소비 실패(예외)는 `report.report.generate.retry.1~3` 경유 지연 재시도 3회(1·5·15분, P12) → `report.report.generate.dlq` (아키텍처 1.6, `definitions.json`)
- `report.started`보다 `report.completed`가 먼저 도착해도 `QUEUED → COMPLETED` 허용 (상태 다이어그램 4.1)
- KEDA가 `report.report.generate` 큐 길이로 report-worker 0~N 확장

### 6.2 알림 전달 (SSE 다중 레플리카)

```mermaid
sequenceDiagram
  autonumber
  participant C1 as core (소비 레플리카)
  participant CDB as core_db
  participant R as Redis
  participant C2 as core (SSE 연결 레플리카)
  participant W as Web

  W->>C2: GET /notifications/stream (SSE 연결 유지)
  C2->>R: SUBSCRIBE notifications
  C1->>CDB: notification INSERT QUEUED (UK user_id·type·source_event_id, 중복 시 무시)
  alt 새로 생성됨
    C1->>CDB: QUEUED → RUNNING
    C1->>R: PUBLISH {userId, notificationId}
    alt 발행 성공
      C1->>CDB: RUNNING → COMPLETED
      R-->>C2: 메시지
      C2-->>W: event notification (제목·링크만, 원문·결제 정보 없음)
    else Redis 오류
      C1->>CDB: RUNNING → FAILED (failure_reason, 관리자 재처리 대상)
    end
  end
  Note over W,C2: 재연결 시 GET /notifications?unreadOnly=true 로 누락분 조회
```

### 6.3 조회·다운로드

```mermaid
sequenceDiagram
  autonumber
  participant W as Web
  participant C as core
  participant RA as report-api
  participant S3 as S3

  W->>C: GET /reports/{reportId}/download?format=pdf
  C->>C: GuardianshipService.authorizeLinkedChildren → X-Student-Scope = 연결 자녀 전체
  C->>RA: GET /internal/reports/{reportId}/files/pdf
  RA->>RA: weekly_report.student_id ∈ X-Student-Scope 검사
  alt 범위 밖
    RA-->>C: 403 FORBIDDEN
    C-->>W: 403 CHILD_NOT_LINKED
  else
    RA->>S3: presigned URL 발급 (단기)
    RA-->>C: {url, expiresAt}
    C-->>W: 200 {url, expiresAt}
    W->>S3: GET url
  end
```

- `reportId`처럼 경로에 자녀 ID가 없는 API는 core가 연결 자녀 전체를 범위로 전달하고, 소유 서비스(report-api)가 리소스의 학생 ID로 검사
- 상세 조회 시 core가 `report_view` 저장 (열람률 지표)
- 재생성(`/regenerate`): 새 `report_job(REGENERATE)` + outbox → 6.1과 같은 흐름, `weekly_report.revision` 증가 (기존 판 보존·최신판 기본 조회. 학부모는 리포트당 1회, 초과 시 409 REGENERATE_NOT_ALLOWED, 관리자 무제한, P06)

---

## 7. 결제·구독 (토스페이먼츠 테스트)

### 7.1 주문·승인

```mermaid
sequenceDiagram
  autonumber
  participant W as Web (결제위젯)
  participant C as core
  participant DB as core_db
  participant T as Toss

  W->>C: POST /orders {productId, childId} (Idempotency-Key)
  C->>DB: 연결 자녀 확인, 활성 구독(ACTIVE·RENEWAL_FAILED) 확인
  alt 중복 구독
    C-->>W: 409 SUBSCRIPTION_DUPLICATE
  else
    C->>DB: payment_order 저장 (INITIAL, amount)
    C-->>W: orderId·amount·위젯 파라미터
  end
  W->>T: 결제위젯 결제 요청
  T-->>W: successUrl (paymentKey, orderId, amount)
  W->>C: POST /payments/confirm (Idempotency-Key)
  C->>DB: order.amount·대상 자녀 대조
  alt 금액 불일치
    C-->>W: 422 PAYMENT_AMOUNT_MISMATCH
  else
    C->>T: POST 결제 승인 API (트랜잭션 밖)
    alt 승인 성공
      C->>DB: payment APPROVED 저장 (order_id UK)
      alt 구독 반영 성공
        rect rgba(128,128,128,0.12)
          C->>DB: subscription ACTIVE 생성·기간 설정
          C->>DB: payment_order.subscription_id 연결, entitlement APPLIED
        end
        C-->>W: 200 APPROVED + subscription
      else 구독 반영 실패
        C->>DB: payment APPROVED 유지, entitlement RECOVERY_REQUIRED
        C-->>W: 200 APPROVED (권한 반영 처리 중)
        Note over C: 추가 청구 없이 SubscriptionService.recoverEntitlement 재시도
      end
    else 응답 지연·불명확 (타임아웃)
      C->>DB: payment CONFIRMING
      C-->>W: 202 CONFIRMING (재결제 안내 금지)
    else 승인 실패
      C->>DB: payment FAILED (failure_code)
      C-->>W: 실패 안내
    end
  end
```

### 7.2 상태 확인·웹훅

```mermaid
sequenceDiagram
  autonumber
  participant T as Toss
  participant C as core
  participant DB as core_db
  participant SCH as core 스케줄러

  T->>C: POST /webhooks/tosspayments (transmission_id)
  C->>DB: pg_webhook_event INSERT (transmission_id UK, 충돌 시 기존 행 조회)
  alt 기존 행 result = APPLIED·IGNORED (처리 완료 통지)
    C-->>T: 200
  else 새 통지 또는 기존 FAILED·미처리
    C->>T: 결제 조회 API (본문 미신뢰)
    T-->>C: 실제 상태
    alt 상태 반영 대상
      C->>DB: payment 상태 갱신 (CONFIRMING → APPROVED·FAILED 등) + 구독 반영
      C->>DB: pg_webhook_event APPLIED·processed_at
    else 변경 없음
      C->>DB: pg_webhook_event IGNORED·processed_at
    end
    C-->>T: 200
  end
  opt 처리 중 오류
    C->>DB: pg_webhook_event FAILED
    C-->>T: 5xx (PG 재전송 시 위 분기로 재처리)
  end
  SCH->>DB: payment CONFIRMING 조회 (status, updated_at)
  SCH->>T: 결제 조회 API
  SCH->>DB: 상태 확정
```

### 7.3 정기 청구·해지

```mermaid
sequenceDiagram
  autonumber
  participant SCH as core 스케줄러
  participant DB as core_db
  participant T as Toss
  participant N as NotificationService

  SCH->>SCH: @SchedulerLock 획득
  Note over SCH: 매일 09:00 KST (P13)
  SCH->>DB: subscription 조회 (auto_renew, next_billing_date ≤ 오늘 / RENEWAL_FAILED 재청구 대상)
  loop 대상 구독마다
    SCH->>DB: payment_order 저장 (RENEWAL, billing_period_start) — 부분 UK로 이중 청구 방지
    alt UK 충돌 + 기존 결제 APPROVED·CONFIRMING
      SCH->>SCH: 건너뜀
    else 신규 주문 또는 UK 충돌 + 기존 결제 FAILED (재청구 매일 1회 최대 3회 P13, 11장 가정)
      SCH->>T: 빌링키 자동결제 API
      alt 성공
        SCH->>DB: payment APPROVED, subscription 기간 연장·next_billing_date 갱신
      else 실패
        SCH->>DB: payment FAILED, subscription RENEWAL_FAILED (retry_count + 1, grace_until = 최초 실패일 + 3일, P13)
        SCH->>N: SUBSCRIPTION_CHANGED 알림
      end
    end
  end
  SCH->>DB: auto_renew = false 이고 period_end 지난 구독 → CANCELED (P14)
  SCH->>DB: RENEWAL_FAILED 이고 재청구 3회 실패 또는 grace_until 지난 구독 → CANCELED (P13)
```

### 7.4 환불

```mermaid
sequenceDiagram
  autonumber
  participant W as Web (학부모)
  participant AW as Web (관리자)
  participant C as core
  participant DB as core_db
  participant T as Toss

  W->>C: POST /payments/{id}/refund-requests (Idempotency-Key)
  C->>DB: 결제 7일 이내 + 결제 후 해당 자녀의 피드백(learning 기록)·분석 대화·리포트 열람(report_view) 기록 없음 확인 (P14)
  alt 조건 불충족
    C-->>W: 409 REFUND_NOT_ALLOWED
  end
  C->>DB: refund_request REQUESTED (전액), payment REFUND_REVIEW
  alt 관리자 반려
    AW->>C: POST /admin/refund-requests/{id}/reject {reason}
    C->>DB: refund_request REJECTED (decided_by, reject_reason), payment REFUND_REVIEW → APPROVED
    C->>DB: audit_log 기록
    C-->>AW: 결과
  else 관리자 승인
    AW->>C: POST /admin/refund-requests/{id}/approve (PAYMENT_REFUND, Idempotency-Key)
    C->>DB: 승인 합계 + 요청 금액 ≤ payment.amount 확인
    alt 초과·중복
      C-->>AW: 409 REFUND_NOT_ALLOWED
    else
      C->>DB: refund_request APPROVED (decided_by)
      C->>T: 결제 취소 API (amount)
      alt PG 성공
        C->>DB: refund_request COMPLETED, payment REFUNDED, subscription 즉시 CANCELED (P14)
      else PG 실패
        C->>DB: refund_request FAILED (pg_status), payment REFUND_REVIEW → APPROVED
      end
      C->>DB: audit_log 기록
      C-->>AW: 결과
    end
  end
```

- PG 취소 응답이 불명확하면 PG 조회로 확정 후 반영 (재취소 요청 금지, FN-ADM-16)

---

## 8. 오류 신고·정정

```mermaid
sequenceDiagram
  autonumber
  participant W as Web (학생·학부모)
  participant AW as Web (관리자)
  participant C as core
  participant DB as core_db
  participant L as learning

  W->>C: POST /error-reports {targetType: JUDGMENT, targetId, comment} (Idempotency-Key)
  C->>DB: error_report RECEIVED
  AW->>C: PATCH /admin/error-reports/{id} {status: IN_REVIEW}
  C->>DB: RECEIVED → IN_REVIEW
  AW->>C: POST /admin/error-reports/{id}/corrections {reason, corrected}
  C->>L: POST /internal/judgments/{judgmentId}/corrections (Idempotency-Key)
  L->>L: judgment_correction 추가 (기존 판정·원본 답변 불변)
  L-->>C: 201
  rect rgba(128,128,128,0.12)
    C->>DB: correction 저장 (impact: 대화·집계·리포트 반영 여부)
    C->>DB: error_report RESOLVED + audit_log
  end
  C->>C: NotificationService.notify (ERROR_REPORT_RESOLVED)
```

- 접수만으로 판정을 바꾸지 않음 (FN-SUP-02). 정정 없이 종료하는 경우 `IN_REVIEW → RESOLVED`만 수행

---

## 9. 모델·프롬프트 버전 활성화

```mermaid
sequenceDiagram
  autonumber
  participant AW as Web (관리자)
  participant C as core
  participant DB as core_db
  participant MQ as RabbitMQ
  participant A1 as ai Pod 1
  participant A2 as ai Pod 2
  participant S as scoring Pod

  Note over A1,S: 기동 시
  A1->>MQ: exclusive·auto-delete 큐 선언 → events.topic model.version.* 바인딩
  A1->>C: GET /internal/model-versions/active
  alt core 조회 실패
    A1->>A1: readiness false 유지, 재시도 (프로세스 종료 안 함)
  else
    C-->>A1: 활성 버전 → ActiveVersions.replace → readiness true
  end

  AW->>C: POST /admin/model-versions/{id}/activate
  C->>C: 승인 조건 확인 (eval_result, NFR-AIQ-05)
  rect rgba(128,128,128,0.12)
    C->>DB: 기존 ACTIVE → INACTIVE, 대상 → ACTIVE (부분 UK)
    C->>DB: audit_log (MODEL_ACTIVATE)
    C->>DB: outbox_event (model.version.activated)
  end
  C-)MQ: events.topic / model.version.activated
  par 모든 레플리카 수신
    MQ-)A1: Pod별 큐
    A1->>A1: ActiveVersions 교체
  and
    MQ-)A2: Pod별 큐
    A2->>A2: ActiveVersions 교체
  and
    MQ-)S: Pod별 큐
    S->>S: ModelRegistry 가중치 로딩 (S3) → 교체
  end
```

- 롤백(`/rollback`): 이전 승인 버전 재활성화로 같은 흐름, 재분석 여부는 `audit_log.detail` 기록 (FN-ADM-18)
- 기준표(`kind = RUBRIC`) 행은 core 레지스트리의 승인·활성 기록만 담당. learning은 이 이벤트를 소비하지 않으며, `judge_verified`·현재 기준표 버전 반영은 관리자 미션 API(`/admin/missions/...`)로 별도 수행

---

## 10. 학생 삭제 전파·LLM 사용량

### 10.1 `student.deleted`

```mermaid
sequenceDiagram
  autonumber
  participant W as Web (학부모)
  participant C as core
  participant CDB as core_db
  participant MQ as RabbitMQ
  participant L as learning
  participant RW as report-worker

  W->>C: POST /children/{childId}/deletion-requests {scope}
  C->>CDB: deletion_request REQUESTED
  Note over C: X-Reauth-Token 재확인 후 (P09)
  rect rgba(128,128,128,0.12)
    C->>CDB: deletion_request CONFIRMED (scope = PROFILE면 student DELETION_REQUESTED)
    C->>CDB: outbox_event (student.deleted, subject = studentId)
  end
  C-)MQ: events.topic / student.deleted
  par
    MQ-)L: learning.student.deleted
    L->>L: processed_event 확인 → attempt 이하 삭제 + deleted_student 저장
    L->>C: POST /internal/deletion-requests/{id}/completions {service: learning}
  and
    MQ-)RW: report.student.deleted
    RW->>RW: processed_event 확인 → weekly_report·S3 파일 삭제
    RW->>C: POST /internal/deletion-requests/{id}/completions {service: report}
  end
  C->>CDB: core 소유 대화·메시지 근거 삭제
  Note over C: learning·report 보고가 모두 오면 deletion_request COMPLETED, student DELETED (P09)
```

### 10.2 `llm.usage.recorded`

```mermaid
sequenceDiagram
  autonumber
  participant A as ai·scoring
  participant MQ as RabbitMQ
  participant C as core
  participant DB as core_db

  A->>A: LLM 호출(ai LlmClient)·모델 추론(scoring) 완료 (토큰·지연·성공 여부)
  A-)MQ: events.topic / llm.usage.recorded (학생 ID·원문 없음, best-effort)
  MQ-)C: core.llm.usage.recorded
  C->>DB: llm_usage INSERT (event_id UK, 중복 무시), cost_usd = 설정 단가로 계산
```

---

## 11. 확인 필요 가정
- `student.deleted` 완료 확인: learning 이벤트 발행 없음 원칙에 따라 이벤트 대신 core 내부 API로 완료 보고(10.1). 보고 호출 실패 시 지연 재시도(1·5·15분)로 재전달 → 삭제는 멱등이라 다시 보고 (P09)
- `report.started`·`report.completed` 순서 역전 허용 (상태 다이어그램 4.1)
- 정기 청구 재시도(7.3): ERD 부분 UK `(subscription_id, billing_period_start) WHERE kind = 'RENEWAL'` 때문에 같은 기간 새 주문 불가. 가정은 "기존 주문의 결제가 `FAILED`면 같은 주문으로 재청구". PG 주문번호 재사용 가능 여부 확인 후 ERD 반영 필요
- 웹훅 처리 실패 시 5xx 응답으로 PG 재전송 유도(7.2): 토스페이먼츠 재전송 정책 확인 필요
