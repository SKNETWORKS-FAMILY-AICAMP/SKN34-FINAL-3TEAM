# 신고·문의·공지·관리자 운영 (#46·#47·#163·#242)

계약은 [API 명세](../design/api-spec.md) 2.7·2.8·5.7·5.12·5.14, 원문 보기·정정 흐름은 [사용자 흐름](../design/user-flow.md) 6장.

## 1. 신고·문의·공지·도움말 (#46)

- 기존 신고 `student_id`는 대상 학생이며 요청 역할을 구분하지 못하고 문의는 `user_id`만 있어 V16(구 V14)에 요청 역할·학생 주체를 분리. 기존 이력에 역할을 추정하지 않음
- 학생 결과는 본인 목록/상세에서 확인하며 보호자 계정 알림에 보내지 않음. 보호자 결과만 #44 알림(NotificationStored/커밋 후 Redis) 재사용
- 호출 경계: SupportController → SupportService → SupportRepository/SupportMapper → core_db. 대상 검증은 StudentAccessService(연결·동의), ConversationSupportService(본인 완료 메시지), ReportSupportService(완료 리포트), LearningSupportClient → 기존 LearningClient → InternalRestClientFactory(내부 토큰·검증된 컨텍스트·타임아웃·서킷)
- 원문: 저장된 attemptId/studentId → learning HTTP → 학생/시도 일치 검사·draft/memo 제외 → audit_log 별도 트랜잭션 성공 → 응답. 다른 attemptId query는 원문 대상을 바꾸지 않음
- 정정: 신고 행 잠금으로 단일 의도 저장 → 잠금/트랜잭션 종료 → 고정 correction UUID를 learning `Idempotency-Key`로 호출 → 신고 행 재잠금 → 공급자 결과·이전 결과·영향·완료·감사·알림 저장. HTTP 오류는 FAILED, core finalize 실패는 이전 의도 유지. 관리자 정정 요청은 신고 UUID를 공개 Idempotency-Key로 사용해 새로고침·재진입 후에도 같은 요청으로 재개
- 알림: support → `NotificationService.support` → 기존 insert(수신 설정·유일성) → 커밋 후 Redis. 비활성 계정·철회 동의·해제 자녀는 생성하지 않음. sourceEventId는 신고/문의 ID, 원문 없는 완료 안내만
- 공지: 등록/수정/종료 전후를 audit_log에 보존하며 DELETE는 `ended_at`만 기록. help/notices는 인증 필요(PublicAuthFilter 공개 예외에서 제거)
- ANALYSIS/REPORT 대상 정정은 공급자 계약이 없어 422 `CORRECTION_TARGET_UNSUPPORTED`
- 대상 `COMMUNITY_POST`(P20·P10, #388): 접수 즉시 숨김, 처리 결과로 다시 공개 또는 계속 숨김, 원문 열람 감사. 결정은 3장
- 구현 예정(FN-ADM-22·23): 관리자 주간 테마(learning 프록시, 미션과 같은 작성→검토→게시)·꾸미기 아이템(core 소유) 관리, CONTENT 권한·`audit_log`

### 정정 impact 의미

- `impact.aggregation`은 학습 수치 집계 반영 여부. 개별 기록 상세의 판정 표시는 조회 시 최신 정정 적용 규칙
- APPLIED=반영 확인, NOT_APPLIED=반영하지 않았음을 확인(집계가 판정 결과를 쓰지 않아 변경 대상이 없는 경우 포함, 오류 아님), UNKNOWN=확인하지 못함. conversation/report UNKNOWN 허용
- 모든 impact가 UNKNOWN이어도 공급자 정정이 성공이면 core는 RESOLVED 저장 가능. 파생 결과까지 반영됐다고 표시하지 않음
- 공급자(learning #80) 계약: 내부 토큰·ADMIN·단일 대상 학생 scope·X-User-Id 검사. DONE 이전 409, 같은 reportId의 다른 키 409, 같은 키의 다른 본문 422, 같은 키·본문은 최초 응답 재현. 원판정·원본 답변 불변
- 관리자 화면은 raw impact JSON 대신 분석 대화·학습 수치 집계·리포트별 확인 상태를 구분 표시

### learning 공급자 오류의 공개 표시 (#46·#163)

| 경로 | learning 응답 | core 공개 응답 |
|---|---|---|
| 정정 POST | 409 / 422 | 409 `SUPPORT_CORRECTION_CONFLICT` / 422 `SUPPORT_CORRECTION_REJECTED` |
| 지원 target·original GET | 정상 Problem Details 403 / 404 | 같은 상태·공통 코드(`FORBIDDEN`·`NOT_FOUND`)와 고정 문구 |
| 관리자 미션 | 정상 404 `NOT_FOUND` | 고정 문구 404. 불명확한 404·405·501은 503 `ADMIN_MISSIONS_UNAVAILABLE`, 409·422 allowlist와 정제한 `missingFields` 유지 |
| 그 밖의 비-2xx / 잘못된 2xx / 전송 실패 | — | 503 `SUPPORT_DEPENDENCY_UNAVAILABLE` / 502 `SUPPORT_INVALID_RESPONSE` / 기존 `LEARNING_*` |

- "정상 Problem Details"는 `application/problem+json` JSON 객체·HTTP와 일치하는 정수 status·허용 문자열 code. 오류 원문·내부 URI·공급자 trace·임의 code는 공개하지 않음. 신규 공개 코드 없음
- 최초 정정 POST도 대상 GET으로 사전 확인하므로 403/404가 공개될 수 있고, 이때 정정 의도·공급자 호출·완료 알림을 만들지 않음. 공급자 실패 시 정정 FAILED·신고 IN_REVIEW·완료 알림 없음
- `FORBIDDEN`은 learning의 학생 범위·역할·scope 형식 거부를 구별하지 못하고 `NOT_FOUND`는 경로 부재와 리소스 부재를 완전히 구별하지 못함(존재 여부 정보 차이 포함해 승인)

### 관리자 공지 전체 목록 (#242)

- `GET /api/v1/admin/notices?status&role&page&size`. 권한은 쓰기 API와 같은 `SupportAccessService.admin`(ADMIN + SERVICE_OPS). 권한 검사가 입력 검사보다 먼저라 권한 없는 요청은 값이 잘못돼도 403(#277)
- 응답은 `GET /notices` 항목과 공통 목록 봉투 `{items,page,size,totalElements}`(OpenAPI `SupportNoticePage`), 상태 필드 추가 없음
- 상태는 조회 시각으로 계산: `SCHEDULED` 종료 기록 없음·공개 시작 전, `ACTIVE` 사용자 GET 공개 조건(`ended_at IS NULL`·`visible_from <= now < visible_to`), `ENDED` 종료 기록 있음 또는 기간 지남(구분은 `endedAt`). 웹 `domain/admin/service.ts`의 `noticeStatus`도 같은 규칙
- 역할 필터는 `target_roles` 포함, 정렬 `visible_from DESC, id DESC`. 원문·개인정보가 없어 조회 감사 없음, 마이그레이션 없음

## 2. 관리자 운영 (#47)

- 설계: controller → admin service → 기능별 operations service → 각 소유 테이블 repository. execution/audit은 admin repository가 조회. learning 통계/미션은 learning 기능 service → 기존 LearningClient. 다른 서비스 DB를 조회하지 않음. 큐는 읽기 전용 RabbitMQ 관리 HTTP(별도 환경 변수)
- PublicAuthFilter는 overview/audit GET 두 경로만 ADMIN 역할로 개방. 관리자 응답은 프론트 목업의 `updatedAt`·`errorDetail` 등을 만들어 채우지 않음
- 알림 재처리(NOTIFICATION)는 기존 publisher/DeliveryService 호출, Redis 발행은 트랜잭션 밖. 200 결과 계약. Redis 발행 확인까지이며 브라우저 수신 보장 아님. 프로세스 중단으로 RUNNING 이력이 남으면 자동 재실행하지 않음. 공통 IdempotencyService의 24시간 응답 저장 재사용(5xx 미저장)

### REPORT 재처리 (#47·#152)

- 같은 jobId로 Outbox만 다시 넣어도 report job 멱등성과 core 종료 상태 때문에 실행되지 않으므로 새 jobId·ADMIN_RETRY로 접수. report 쪽 처리는 [report](report.md) 12장
- 원작업당 직접 자식 1개, 재실패 시 그 자식에서 다음 재처리. 관계는 V17
- 응답 202 `{originalJobId,jobId,type:REPORT,status:QUEUED,acceptedAt}`, Location은 새 작업 조회 URL. 화면은 '접수'로 표시하고 새 jobId GET으로 진행/완료/실패 확인. 원작업 상세의 `retryJobId`, 새 작업의 `retryOfJobId`를 이동 링크로. 이미 연결된 원작업은 `REPORT_ALREADY_RETRIED`
- 종료 감사: `ReportJobOutcomeRecorded` 내부 이벤트를 정상 종료·#132 복구·삭제의 조건부 전이가 실제 반영된 때에만 발행(reportId 없는 실패 포함). 감사는 BEFORE_COMMIT으로 소비하며, 삭제 결과 감사가 실패하면 학생 차단·삭제 요청·작업 종료·실행 이력도 함께 롤백. 중복·지연 결과는 감사를 추가하지 않음
- 접수 후 학생 삭제로 report 소비자가 생성을 막은 queued 작업의 정리 정책은 후속 검토

### CONVERSATION 재처리 (#47·#67·#162)

- 관리자 백그라운드 실행, 공통 분석 경로·권한/한도·감사/복구, 새 요청 테이블 V19. 기존 jobId의 Location
- 사용량 차감과 DB가 단일 원자 트랜잭션이 아니므로 요청 ID 표식으로 중복 차감 방지, 접수/실제 실행 이력 구분. 최초 202도 DB 저장값으로 반환(재접수 응답과 timestamp 정밀도 일치)
- 202 후 core 강제 종료 시 새 프로세스에서 1회 실행, 실행 중 종료는 대기 시각 경과 후 FAILED 이력/감사 1회로 복구
- `OperationRetryService`가 인증된 관리자 identity를 두 접수 서비스에 전달. 202 OpenAPI는 REPORT/CONVERSATION oneOf

### 관리자 미션 프록시 감사 (#47)

- learning 관리자 미션 10종 프록시. 실제 404 전달, 필터와 무관한 전체 상태 counts(`missionCounts`·`missionInclusionRule`)
- HTTP 전 REQUESTED를 짧은 독립 트랜잭션으로 남기고 응답 후 SUCCEEDED/REJECTED/UNKNOWN 기록. 프로세스 중단·결과 감사 저장 실패에는 REQUESTED만 남을 수 있어 변경 성공 여부는 learning에서 대조. 요청·오류 원문 미저장, 자동 재요청 없음
- 감사 저장 실패 시 503 `MISSION_AUDIT_UNAVAILABLE`(learning 변경은 이미 반영됐을 수 있음)

### 검증 범위

core 통합 테스트(실제 JWT/MVC/PostgreSQL·Redis·RabbitMQ)로 권한·기간·목록·민감 문자열 제거, 같은 키 응답 재현·다른 키 동시 실행 방지, 실행/감사 원자 저장, 트랜잭션 밖 발행, REPORT·CONVERSATION 재처리 경합·복구를 확인. 관리자 운영 응답 5종은 [testing-ci](testing-ci.md) 1장 계약 CI에서 공개 스키마와 대조. 실제 report-worker를 포함한 관리자 POST → 생성 파이프라인 E2E와 실제 외부 LLM 호출은 미검증.

## 3. 커뮤니티 공유물 신고 연결 (#388, P20·P10)

- 접수: 기존 `POST /error-reports`에 `targetType: COMMUNITY_POST`, `targetId: postId`(유형 5종 그대로). 학생 세션만 받고 학부모는 400. learning `GET /internal/community/posts/{postId}`로 대상을 확인해 본인 글 409 `COMMUNITY_OWN_POST`, 없거나 볼 수 없는 글(설정·검토 숨김, 작성자 비공개) 404 `COMMUNITY_POST_NOT_FOUND`
- 신고 행: `student_id`·`requester_student_id`는 신고한 학생, `attempt_id`는 NULL. 작성자 학생 ID를 core 신고 행에 남기지 않아 기존 본인 목록·상세 권한 검사(`student_id ∈ scope`)를 그대로 쓰고, 작성자 삭제로 신고 이력이 깨지지 않음
- 숨김: 신고 행 저장 뒤 트랜잭션 밖에서 learning `moderation {status: HIDDEN_REPORT, errorReportId}`. 실패해도 접수는 201로 두고 기록만 남김. 같은 멱등 키 재전송·검토 처리 때 다시 보냄. 그 사이에도 core 목록·반응은 신고 행(접수·처리 중, 또는 처리 결과가 `VISIBLE`이 아님)으로 그 공유물을 바로 숨김
- 처리: 기존 `PATCH /admin/error-reports/{id}`(SERVICE_OPS). `RESOLVED`로 바꿀 때 `reviewResult`는 `VISIBLE`(다시 공개)·`REMOVED`(계속 숨김)만, 생략하면 `REMOVED`(현재 관리자 화면 #395는 결과를 보내지 않아 계속 숨김이 기본). 같은 공유물에 신고가 여럿이면 계속 숨김이 하나라도 있으면 `REMOVED`, 처리 중이 있으면 `HIDDEN_REPORT`, 모두 다시 공개일 때만 `VISIBLE`을 보냄. 정정(`corrections`)은 판정만이라 422 그대로
- 원문 열람: 관리자 상세에 `linkedPost {postId, available, missionId, status, answer, authorStudentId}`. 열람마다 `SUPPORT_ORIGINAL_VIEW`(`ERROR_REPORT`, detail `postId`·`available`) 감사. 파기된 공유물은 `available: false`만
- 학생 결과 알림은 기존처럼 보호자 계정에 보내지 않음(학생 본인 목록에서 확인)
- 검증: core `CommunityIntegrationTest`(실제 JWT·MVC·PostgreSQL, learning만 내부 계약 가짜 서버)로 접수 즉시 숨김·같은 키 재전송·learning 반영 지연 중 core 숨김·다시 공개·계속 숨김·복수 신고·원문 열람 감사를 확인. 실제 learning #386과의 연동은 미검증
- 후속: 관리자 화면(#395)에 다시 공개·계속 숨김 선택과 `linkedPost` 표시 추가 필요. learning #386 `moderation`·`GET posts/{id}` 구현과 응답 모양 대조 필요
