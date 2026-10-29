# 아키텍처 설계 (참고: SKN34-4th-1Team)

## 배경
- 대주제: 대화형 데이터 기반 분석 에이전트 및 자동 리포팅 플랫폼 → **사고뭉치**(초~중학생 사고력 학습 플랫폼)에 적용. 분석 대상 데이터 = 학생 학습 기록
- 확정 사항: Spring + Python 혼합, RabbitMQ 하이브리드 EDA, PostgreSQL, kind 로컬 + AWS EKS 운영(자체 구축 K8s 미사용, 4.2 참고)
- 기획서(4.4) 대비 변경: FastAPI 단일 서버 → 서비스 5개 분리, EC2 → EKS
- 참고 레포에서 계승: `backend/<x>-service` 모노레포, 기능 중심 패키지, Outbox·DLQ·수동 ACK, Helm + Argo CD GitOps, kind/EKS, `evaluation/`, `infrastructure/stubs`
- 참고 레포 대비 보강: 작업 큐만 쓰던 구조 → **명령 큐 + 도메인 이벤트 fan-out** 구분, 이벤트 계약(`contracts/`), 큐 길이 기반 오토스케일링(KEDA)
- 기능 요구는 [기능명세서](functional-spec.md), 공개·내부 API는 [API 명세서](api-spec.md), 서비스별 DB는 [ERD](erd.md)

---

## 1. 시스템 아키텍처

### 1.1 서비스 경계 (5개)

| 서비스 | 언어 | 책임 | 소유 저장소 |
|---|---|---|---|
| core-service | Spring Boot (Kotlin) | **유일한 공개 API**. 계정·인증·동의, 학부모-자녀 연결(권한 기준), 분석 대화 세션·이력, 주간 리포트 작업·일정, 알림(SSE·인앱), 신고·문의·공지, 결제·구독(토스페이먼츠 테스트), 관리자 운영·모델 버전 레지스트리, LLM 사용량 집계 | core_db, Redis |
| learning-service | Spring Boot (Kotlin) | 미션·기준표·예시 답·생각 열기 질문(버전 관리), 학습 시도·답변 버전·초안·도움 이용·돌아보기·자기 평가, 규칙 판정(고르기·수학 동치), 판정·되묻기 저장, 학습 기록 조회 API(대시보드·에이전트 도구·리포트 소재) | learning_db, S3(미션 장면) |
| ai-service | FastAPI | 서술 근거 구절 추출(LLM) + 원문 대조 판정(코드), 되묻기 생성·정답/금지어 유출 검사, LangGraph 분석 에이전트, 리포트 서술·저녁 질문 생성, 프롬프트 버전 | 없음 (상태 없음) |
| scoring-service | FastAPI | M2 항목 점수(klue/roberta), M1 수학 풀이 점검(활성 범위만) 추론, CPU 추론 | 없음 (S3 가중치 읽기) |
| report-service | FastAPI | 주간 리포트 기간·포함 기록 확정, 수치·전후 변화 코드 계산, 숫자·인용 대조, 렌더링(HTML/PDF/Markdown)·저장 | report_db, S3 |

- 언어 분담 근거: 트랜잭션·권한·버전 관리·Outbox·스케줄·결제 = Spring 생태계(Spring AMQP, Flyway, ShedLock) 성숙 / LLM·모델 추론·렌더링 = Python 생태계
- scoring 분리 근거: PyTorch 이미지·메모리 요구가 ai-service와 달라 배포·확장 단위 분리, 모델 미활성 시 ai-service 영향 없음
- 다른 서비스 DB 직접 접근 금지, API 또는 이벤트로만 연동 (참고 레포 원칙 동일)
- 권한 기준: 학부모-자녀 연결은 core만 소유. core가 요청마다 권한 확인 후 내부 호출에 사용자 컨텍스트·허용 학생 범위 전달 (2.3)

### 1.2 전체 구성도

```
[React Web] ──HTTPS──▶ CloudFront ──▶ ALB(Ingress) ──▶ core-service ──SSE──▶ Web
                                                     │
                       ┌──────────── HTTP(동기) ──────┼──────────────────┐
                       ▼                              ▼                  ▼
               learning-service ──HTTP──▶ ai-service ──HTTP──▶ scoring-service
                       ▲                     │  ▲
                       └──── 기록 조회 ───────┘  │
      ┌─────────────────────────── RabbitMQ ──┼──────────────────────────────┐
      │ cmd.direct  : report.generate          │       (작업 큐, 소비자 1)      │
      │ events.topic: report.*, llm.*, model.*, student.*  (fan-out, 소비자 N) │
      └────────────────────────────────────────┼──────────────────────────────┘
               ▲ consume                       │ HTTP(서술 생성)
        report-service ────────────────────────┘
          └─ HTTP(기록 조회) ─▶ learning-service

저장소: RDS PostgreSQL(서비스별 DB) · S3(미션 장면·리포트 파일·모델 가중치) · Redis
외부: LLM API(ai) · 토스페이먼츠 테스트(core)
```

### 1.3 통신 원칙
| 구간 | 방식 | 근거 |
|---|---|---|
| 답변 제출 (Web→core→learning) | 동기 HTTP, `Idempotency-Key` | 저장 성공을 즉시 확정, 중복 제출 1회 반영 |
| 피드백: 판정·되묻기 (Web→core→learning→ai→scoring) | 동기 HTTP + core에서 SSE 전달 | 학생 실시간 대기. 답변 저장과 분리된 별도 요청이라 AI 실패 시 저장 결과 보존, 같은 요청 재호출로 재시도 |
| 분석 대화 (Web→core→ai, 도구→learning) | 동기 HTTP + SSE 스트리밍 | 학부모 실시간 대기 |
| 대시보드·리포트 조회 (Web→core→learning/report) | 동기 HTTP | 단순 조회 |
| 주간 리포트 생성 | **명령** → `cmd.direct` 작업 큐 | 일괄 처리, 재시도, 워커 단독 확장 |
| 상태 변화 전파 | **이벤트** → `events.topic` | 생산자가 소비자를 모름, 소비자 추가 시 생산자 무변경 |

- 동기 호출 장애 대응: 타임아웃 + 재시도 제한 + 서킷 브레이커(Spring Resilience4j / Python httpx 타임아웃·재시도). 값(P12): LLM 1회 15초·재시도 1회(1초 대기), learning→ai 판정·되묻기 각 35초, core→learning 피드백 80초, 분석 대화 core→ai 첫 응답 20초·전체 120초, 서킷 브레이커 최근 20건 중 실패 50% 이상 시 30초 차단, 리포트 작업 재시도 3회(1·5·15분) 후 DLQ. 실패 시 "처리 실패"로 기록·SSE 전달, 판정 보류·기록 없음과 구분
- 타임아웃 예산: 바깥 호출 타임아웃 > 안쪽 호출 합계 (예: core→learning > learning→ai judgments + followups). 전체 상한은 CloudFront·ALB 타임아웃(4.3) 이내. 이를 넘는 SSE(피드백 80초, 분석 대화 120초)는 15초 heartbeat가 유휴 타이머를 갱신하는 것을 전제로 함
- 재시도 계층: ai의 LLM 호출에서만 재시도, core·learning·report의 서비스 간 호출은 재시도 없음 (계층별 재시도 시 호출 수 곱셈 증폭)
- #38 일반 core→learning JSON 프록시는 연결 2초·응답 30초를 사용한다(피드백의 80초 예산은 #39). Resilience4j count window 20·최소 20건·실패율 50%·차단 30초·half-open 1건으로 복구를 확인한다. 전송 오류·5xx를 실패로 집계하고 4xx는 정상 HTTP 결과로 센다. 응답·오류 대역은 test 소스에만 둔다.
- SSE heartbeat: 모든 SSE는 15초마다 주석 줄(`: ping`) 전송. 피드백은 learning 동기 응답 대기 중 전송할 데이터가 없어 필수
- SSE 연결 종료
  - 피드백: 클라이언트가 끊겨도 learning 처리는 끝까지 진행·저장, 재요청 시 저장 결과 반환
  - 분석 대화: 클라이언트가 끊기면 core가 ai 스트림 취소, 메시지 `FAILED`(재시도 가능) 저장
  - 알림: 재연결 시 `/notifications`로 누락분 재조회
- core 피드백(#39): `learning/controller` → `learning/service/FeedbackService` → #38 `LearningProxyService` → `LearningClient` → 기존 `InternalRestClientFactory`. 피드백 전용 조합은 같은 client/service 구현에 80초 read timeout을 적용하며 일반 JSON 경로의 30초 설정·멱등성은 유지한다. `_common/web/SseEmitters`는 연결 시간·15초 heartbeat·전송 종료만 소유하고(연결 시간은 용도별 설정: 현재 피드백 90초 고정, 분석 대화(#41)는 P12 전체 120초 + 여유로 호출 측이 지정하도록 확장) 판정 상태를 저장하지 않는다. 컨텍스트는 요청에서 복사해 작업 virtual thread에 설정·정리한다. 연결 종료는 heartbeat만 취소하며 learning 작업을 취소하지 않는다.
- 피드백의 별도 서킷 이름은 `learning-feedback`이다. 전송 오류·시간 초과·계약된 Problem Details가 아닌 5xx를 실패로 센다. Content-Type `application/problem+json`의 JSON 객체에 비어 있지 않은 문자열 code가 있으면 정상 HTTP 전달로 집계하되 업무 결과는 error로 유지한다. 따라서 learning이 보낸 AI_UNAVAILABLE·INTERNAL_ERROR를 core 서킷이 다시 차단하지 않고 같은 답변 재요청은 learning으로 전달할 수 있다. AI 서킷은 learning이 소유하며 일반 `learning-json`의 기존 5xx 집계는 바꾸지 않는다.
- JDK 21 SSE 전송·종료의 상호 배제는 `ReentrantLock`을 사용한다. 블로킹 소켓 전송을 synchronized monitor 안에서 실행해 virtual thread의 carrier가 고정되지 않게 한다.

### 1.4 메시지 목록

| 메시지 | 종류 | 생산 | 소비 | 소비 측 처리 |
|---|---|---|---|---|
| `report.generate` | 명령 | core (정기 스케줄·재생성·관리자 재처리) | report | 기간 확정 → learning 기록 조회 → 계산 → ai 서술 → 대조 → 렌더링·저장 |
| `report.started` | 이벤트 | report | core | 작업 상태 처리 중 |
| `report.completed` / `report.failed` | 이벤트 | report | core | 작업 상태 갱신, 학부모 알림 |
| `llm.usage.recorded` | 이벤트 | ai, scoring | core | 호출 종류별 토큰·지연·실패·버전 집계 (학생 ID·원문 미포함) |
| `model.version.activated` | 이벤트 | core | ai, scoring (Pod별 수신) | 모든 레플리카가 활성 모델·프롬프트 버전 교체 (기동 시 core 내부 API로 현재 버전 조회) |
| `student.deleted` | 이벤트 | core | learning, report | 삭제 확정 학생의 학습 기록·리포트 물리 삭제, 처리 후 core 내부 API로 완료 보고. 페이로드에 `deletionRequestId`·`scope` 포함 (P09) |

### 1.5 핵심 흐름
1. **미션 학습**
   - 학생이 미션 시작 → learning이 학습 시도 생성 (진행 중 시도가 있으면 반환)
   - 초안 저장 시 `If-Match` 버전 확인, 충돌하면 409
   - 답변 제출 → learning이 답변 버전 저장 → 201
2. **피드백**
   - Web ─SSE→ core → learning
   - learning 처리 순서
     - 고르기·수학 최종 답: 규칙 판정
     - 서술·논술: ai `judgments` 호출 (LLM 근거 추출 → 코드 원문 대조 → M2 활성 시 scoring 교차 확인)
     - 이후 ai `followups`로 되묻기 생성·유출 검사
   - 판정·되묻기를 기준표·모델·프롬프트 버전과 함께 저장
   - 실패 시 판정 상태 `FAILED` 저장, 같은 피드백 요청 재호출로 재시도
3. **마무리**: learning이 마무리 조건(판정 `DONE` 1회 이상, P04)을 확인한 뒤에만 정답·예시 답·근거 확인된 체크리스트 반환 → 돌아보기 저장 시 완료 처리
4. **분석 대화**
   - Web ─SSE→ core: 자녀 연결 확인 후 허용 학생·기간·대화 이력 전달 → ai(스트리밍)
   - LangGraph 흐름: `classify → clarify_scope → plan → tool(learning 조회, 실행마다 허용 범위 검사) → compute(코드 계산) → answer → verify(숫자·인용 대조)`
   - core가 질문·답변·참조 기록 저장
5. **자동 리포트**
   - core 스케줄러(ShedLock)가 자녀별 report_job + Outbox → `report.generate`
   - report가 learning 기록 조회 → 코드 계산 → ai 서술·저녁 질문 → 숫자·인용 대조 → 렌더링·S3 저장
   - `report.completed` → core 알림

### 1.6 메시징 신뢰성 규칙
- **Outbox**: DB 상태 변경 + 발행이 함께 필요한 서비스(core, report)만 적용 (learning은 발행 없음, 멱등 소비만). 같은 트랜잭션에 outbox 행 저장 → 릴레이 스케줄러가 publisher confirm 받은 후 발행 시각 기록 (참고 레포 `*OutboxScheduler` 패턴)
- **상태 없는 서비스(ai, scoring)**: 이벤트 발행은 처리 결과 반환 후 best-effort (사용량 집계용), 유실 시 Langfuse trace로 보정
- **멱등 소비**: 소비자별 `processed_event(event_id UK)` 테이블 또는 DB 상태 전이 조건(`QUEUED→RUNNING`)
- **재시도**: 소비 실패 시 지연 재시도 3회(1·5·15분, P12) 후 DLQ 이동. `report.generate` 확정값을 모든 큐에 동일 적용
  - 큐마다 `<큐>.retry.1`(1분)·`.retry.2`(5분)·`.retry.3`(15분)을 `definitions.json`에 선언 (`x-message-ttl` = 지연, 만료 시 기본 exchange로 원래 큐 복귀)
  - 처리 실패: 소비자가 `x-retry-count` 헤더 +1 후 `<큐>.retry.<회차>`로 재발행하고 ACK. 3회 초과 시 `reject(requeue=false)` → `dlx` → `<큐>.dlq`
  - 횟수는 자체 헤더로 셈 (클라이언트 재발행 시 `x-death`가 승계되지 않음). 지연은 `definitions.json`, 최대 횟수는 서비스 설정(3)으로 단계 큐 개수와 일치
  - 메시지 변환 실패(형식 오류)는 재시도해도 복구되지 않으므로 재시도 없이 바로 reject → DLQ
  - core는 전역 수동 ACK(`acknowledge-mode: manual`, learning은 소비자 구현 시 동일 설정): 모든 `@RabbitListener`는 `RetryingConsumer.handle`로 처리. ACK 누락 시 메시지가 unacked로 남아 소비 정지
  - 큐 미존재 시 기동 실패 대신 경고 후 재확인(`missing-queues-fatal: false`), 큐 생성 시 소비 자동 시작
- **DLQ**: 큐마다 dead-letter exchange, 관리자 화면에서 현황 조회 (참고 레포 `QueueOperations*` 계승)
- **브로드캐스트 이벤트**: 모든 레플리카가 받아야 하는 이벤트(`model.version.activated`)는 Pod별 exclusive·auto-delete 큐를 서비스가 기동 시 선언·바인딩 (exchange는 `definitions.json`). 공유 큐는 경쟁 소비라 1개 Pod만 수신
  - 기동 순서: 큐 바인딩 → core 활성 버전 조회 (반대 순서면 그 사이 이벤트 유실)
  - #43 계약: 내부 조회와 이벤트는 같은 kind·name별 revision·적용 scopes를 제공한다. 소비자는 초기 조회 중 이벤트를 보존·조정하고 더 높은 revision만 적용하며 승인 scope 밖에는 적용하지 않는다. core는 Pod 공유 소비 큐를 추가하지 않는다. 실제 ai·scoring 소비·readiness 구현은 해당 서비스의 후속 작업이다.
  - core 조회 실패 시 프로세스 종료 없이 readiness false 유지·재시도 (core 장애가 ai·scoring 기동 실패로 번지지 않게)
- **이벤트 봉투**: CloudEvents 형식 `id, specversion, type, source, time, subject, dataschema, traceparent, data` → `contracts/events/*.schema.json`
- **스키마 버전**: 파일 `<message>.v<N>.schema.json`, `dataschema`에 버전 표기. 하위 호환 변경(선택 필드 추가)만 같은 버전, 그 외는 새 버전 병행 발행 후 소비자 전환
- **SSE 다중 레플리카**: core 레플리카 간 Redis Pub/Sub으로 알림 중계. #44는 리포트 상태 전이의 동기 ApplicationEvent를 같은 트랜잭션에서 알림으로 저장하고 AFTER_COMMIT에서 발행한다. report.service의 알림 연결부 → guardianship.service로 수신 보호자를 결정한 뒤 notification.service로 저장한다. Redis 채널 `core:notifications:v1`은 #58 페어링 키와 분리하며 같은 spring.data.redis 연결을 사용한다. 알림 전용 구독은 SseEmitters의 heartbeat/종료 정리를 재사용하되 작업 완료 후 종료하는 피드백 API는 유지한다. 알림 구독 5분·15초 heartbeat, 종료 시 사용자별 구독 제거, 재연결 ready 후 목록 재조회로 유실을 보완한다.

---

## 2. 백엔드 아키텍처

### 2.1 구조 원칙: 기능 단위 패키지 + 기능 내부 레이어드 아키텍처
- 최상위는 기능(`attempt/`, `conversation/` …) 기준, 각 기능 내부를 레이어로 분리 (참고 레포 core-service 동일 방식)
- 기능 우선 근거: 한 기능의 코드가 한 폴더에 모임, 기능을 별도 서비스로 분리하기 쉬움
- 헥사고날·클린 아키텍처 미적용: 서비스 규모 대비 포트·어댑터 비용 과다. 교체 가능성이 큰 LLM 제공자(`llm/`), PG(`payment/client`)만 래퍼로 분리

| 레이어 | Spring 위치 | Python 위치 | 책임 | 금지 |
|---|---|---|---|---|
| Presentation | `controller`, `consumer`, `scheduler` | `router.py`, `consumer.py` | HTTP·메시지·스케줄 수신, DTO 검증·변환, 인증 정보 추출, ACK | 업무 로직, DB 접근 |
| Application | `service`, `facade` | `service.py`, `graph.py`·`nodes/`(ai) | 업무 흐름, 트랜잭션 경계, Outbox 기록 | HTTP 요청·AMQP 채널 객체 직접 사용 |
| Domain | `domain` | `models.py`, `state.py` | 엔티티·값 객체, 상태 전이 규칙(`QUEUED→RUNNING`, 판정 상태 등) | 프레임워크·외부 라이브러리 의존 |
| Infrastructure | `repository`, `client`, `messaging` | `repository.py`, `clients/`, `messaging/`, `llm/` | DB, 외부 API, 브로커, LLM, PG, S3 연동 | 업무 판단 |

### 2.2 의존 규칙
- `Presentation → Application → Infrastructure` 단방향, 계층 건너뛰기 금지 (controller → repository 직접 호출 금지)
- Domain은 모든 레이어가 참조 가능, Domain은 다른 레이어를 참조하지 않음
- 기능 간 호출은 상대 기능의 service로만 (다른 기능의 repository 직접 참조 금지)
- #37 자녀 기록 존재 조회는 guardianship service → learning의 LearningRecordService → LearningRecordClient → 기존 LearningClient 순서로 호출한다. 학생 전용 LearningProxyService 권한은 유지하며 learning-json 서킷·타임아웃·내부 컨텍스트 전달을 공유한다. 최대 3명 조회는 요청 단위의 최대 3개 virtual-thread 작업으로 병렬 수행하고, 검증된 UserContext를 전달·finally 정리한다. HTTP를 DB 트랜잭션 안에서 호출하지 않는다.
- 여러 기능에 걸친 흐름은 `facade`로 조합 (참고 레포 `applicationpreparation/facade` 패턴)
- 공통 코드: Spring `_common/`, Python `app/` 루트의 `config.py`·`errors.py`·`security.py`·`messaging/`·`clients/base.py`
- DB 트랜잭션은 Application 레이어에서만 시작, 트랜잭션 안에서 외부 HTTP·AMQP 호출 금지
- #38 공통 멱등성은 `_common/web/IdempotencyService`가 조합하고 `web/repository`가 기존 idempotency_record와 PostgreSQL 세션 잠금을 관리한다. HTTP 동안 auto-commit 연결 1개를 보유하며 트랜잭션·행 잠금은 보유하지 않는다. 잠금과 레코드 작업을 동일 연결에서 수행하는 JDBC Repository만 사용해 추가 연결 대기로 인한 풀 교착을 피한다. 일반 기능 Repository의 MyBatis 패턴은 유지한다.
- #62 미션 조회와 #23 시도 시작의 학생 메타데이터는 core `guardianship/StudentLearningContextService` → 전용 Repository/Mapper로 core의 연결된 활성 학생 `grade`·`is_demo`만 조회한다. 기존 #36/#37 service 인터페이스는 유지한다. `learning`은 이 service를 통해 검증된 학생의 내부 요청 조건을 만들고, 문항 노출·신규 시도 제공 범위·기존 시도 당시 버전 유지의 업무 판단·learning DB 접근은 수행하지 않는다.
- #23 시도 시작의 일일 한도는 core Redis 카운터 책임이며 learning은 관여하지 않는다. learning의 신규 생성 `201`·기존 진행 시도 반환 `200`을 core가 그대로 전달한다. 후속 Redis 연계에서는 `201`만 집계하고 `200`은 집계하지 않으며, 한도 도달 시에도 이어하기를 허용하고 신규 생성만 차단하는 처리 순서를 검증한다. #38의 이번 프록시 보완에는 Redis 한도 기능을 구현하지 않는다.
- 서비스 간 내부 호출: 내부 토큰 헤더 필터(참고 레포 `CatalogInternalAuthFilter` 패턴) + NetworkPolicy

### 2.3 공통 규칙

- #119 내부 별명 조회는 `guardianship/controller/InternalStudentProfileController` → `guardianship/service/InternalStudentProfileService` → 기존 `ChildManagementRepository.profile` 순서다. `InternalAuthFilter`가 토큰·요청 컨텍스트를 관리하고 서비스가 SYSTEM·학생 scope를 검사한다. 응답 전용 DTO는 UUID·별명만 제공하며 ACTIVE만 조회한다. report 담당자는 조회 결과를 렌더링에 전달하고 최종 AI 요청에서 별명을 가린다. core 공급자 구현과 아직 미연결인 report-worker를 구분한다([#119](../report/issue-119-student-profile.md)).
- 오류 응답: 전 서비스 공통 형식(RFC 9457 Problem Details), 예외 → 응답 변환은 Presentation(Spring `_common/exception`, FastAPI exception handler)
- 사용자 컨텍스트 전파: JWT 검증은 core만, 내부 호출은 내부 토큰 + `X-User-Id`·`X-User-Role`·`X-Student-Scope`(허용 학생 ID 목록) 헤더, 이벤트는 봉투 `subject`·`data`에 포함
  - 중간 서비스(ai)는 받은 컨텍스트 헤더를 하위 호출(learning)에 그대로 전달
  - 사용자 요청 없는 호출(report-worker 등 이벤트 소비): `X-User-Role: SYSTEM`, `X-Student-Scope` = 이벤트 `subject` 학생
- 스레드 모델
  - Spring(core·learning): JDK 21 virtual threads 사용 (LLM 대기·SSE 연결 동안 스레드 점유)
  - FastAPI: 외부 호출은 async httpx. scoring CPU 추론은 동기 함수(스레드풀)로 실행해 이벤트 루프 차단 방지
- 범위 검사: learning은 조회 대상 학생이 `X-Student-Scope`에 없으면 403. ai 에이전트 도구도 실행 전 같은 검사 (FN-AGT-02)
- 대화 상태: ai-service는 상태 없음, core가 요청마다 대화 이력·허용 범위 전달
- 버전 연결: 판정·되묻기·분석·리포트 결과에 미션·기준표·모델·프롬프트 버전 저장 (NFR-DAT-02)
- 개인정보: LLM 요청에 학생 이름·식별정보 미포함, 운영 로그에 학생 원문·비밀 키·결제 정보 미기록 (NFR-SEC-03, 05)
- 테스트: Domain 단위 테스트, Application은 Infrastructure 대역, Repository는 Testcontainers(PostgreSQL), core 메시징 통합은 Testcontainers(PostgreSQL·RabbitMQ·Redis), 메시지는 `contracts/events` 스키마 계약 테스트
  - core·learning Repository 테스트는 각 서비스의 `PostgresRepositoryTest` 상속 (PostgreSQL 컨테이너 JVM당 1회 기동, 테스트별 트랜잭션 롤백). core는 RabbitMQ listener를 시작하지 않고 `OutboxRelay`를 Mockito 대역으로 교체한다.
  - core 메시징 통합 테스트는 `IntegrationTestSupport` 상속 (PostgreSQL·RabbitMQ·Redis 컨테이너 JVM당 1회 기동, `definitions.json` 반영, 실제 발행기·소비자 사용).
  - 두 베이스 모두 테스트 준비 단계에서 명시적으로 Flyway 전체 스키마를 적용하며, 앱 기동 시 자동 마이그레이션은 비활성화한다. core의 두 베이스는 별도 DB를 사용해 메시징의 비동기 커밋과 Repository 테스트의 롤백이 간섭하지 않도록 한다.

### 2.4 서비스별 적용 강도
| 서비스 | 적용 레이어 | 비고 |
|---|---|---|
| core, learning | 4개 전부 | 업무 규칙·DB 소유 → 표준 적용 |
| report | 4개 전부 | 작업 상태 전이·Outbox 보유 |
| ai | Presentation · Application · Infrastructure | DB 없음. LangGraph 그래프·노드, 판정 대조 로직이 Application, LLM·서비스 클라이언트가 Infrastructure |
| scoring | Presentation · Application · Infrastructure | 상태 없음. 모델 로딩·추론이 Infrastructure |

### 2.5 요청 처리 예시 (learning 답변 제출)
```
AnswerController (Presentation)      요청 검증 → DTO 변환, Idempotency-Key 확인
  → AnswerService (Application)      시도 상태·학생 범위 확인, @Transactional: answer 버전 저장
    → Answer (Domain)                버전 번호 증가 규칙, 이전 버전 덮어쓰기 금지
    → AnswerRepository (Infra)       MyBatis → PostgreSQL
FeedbackFacade (Application)         판정 상태 PENDING→RUNNING → 규칙 판정 또는 AiClient 호출(트랜잭션 밖)
                                     → @Transactional: judgment·followup 저장, 상태 DONE/HELD/FAILED
```

### 2.6 서비스 폴더 예시
- Spring 루트 패키지: `com.sagomungchi.<service>`, 디렉토리는 패키지와 1:1 (루트 패키지 생략 안 함)

Spring (core)
```
backend/core-service/src/main/kotlin/com/sagomungchi/core/
├─ _common/
│  ├─ config/
│  ├─ exception/
│  ├─ security/
│  ├─ messaging/                 # 이벤트 봉투, OutboxRelay, 멱등 소비
│  └─ web/                       # IdempotencyService, SseEmitters (core만)
├─ account/                      # Google 로그인·세션·탈퇴
│  ├─ controller/
│  ├─ service/
│  ├─ domain/
│  └─ repository/
├─ consent/
│  ├─ controller/
│  ├─ service/
│  ├─ domain/
│  └─ repository/
├─ guardianship/                 # 자녀 등록·연결·권한 확인, 삭제 요청 → student.deleted
│  ├─ controller/
│  ├─ service/
│  ├─ domain/
│  └─ repository/
├─ learning/                     # learning 프록시 (미션·시도·대시보드)
│  ├─ controller/                # LearningController, FeedbackController(SSE)
│  ├─ service/                   # LearningProxyService, FeedbackService, LearningRecordService
│  ├─ config/                    # FeedbackConfiguration (피드백 전용 클라이언트·서킷)
│  └─ client/
│     ├─ LearningClient.kt
│     └─ LearningRecordClient.kt
├─ conversation/                 # 분석 대화, 예시 질문
│  ├─ controller/                # SSE
│  ├─ service/
│  ├─ domain/
│  ├─ repository/
│  └─ client/
│     └─ AiClient.kt
├─ report/
│  ├─ controller/
│  ├─ consumer/                  # report.started·completed·failed
│  ├─ scheduler/                 # ShedLock
│  ├─ service/
│  ├─ domain/
│  ├─ repository/
│  ├─ messaging/                 # report.generate 발행
│  └─ client/
│     └─ ReportClient.kt
├─ notification/
│  ├─ controller/                # SSE
│  ├─ service/
│  └─ repository/
├─ support/                      # 신고·문의·공지·도움말·정정
│  ├─ controller/
│  ├─ service/
│  ├─ domain/
│  ├─ repository/
│  └─ client/
│     └─ LearningClient.kt       # 판정 정정
├─ payment/
│  ├─ controller/
│  ├─ service/
│  ├─ domain/
│  ├─ repository/
│  ├─ client/
│  │  └─ TossClient.kt
│  └─ scheduler/                 # 정기 청구
├─ usage/                        # LLM 사용량 집계
│  ├─ consumer/
│  ├─ service/
│  └─ repository/
└─ admin/                        # 운영 현황·재처리·모델 버전 레지스트리·감사 이력·큐/DLQ
   ├─ controller/
   ├─ service/
   ├─ domain/
   └─ repository/

backend/core-service/src/main/resources/
├─ application.yml               # 현재 단일 파일, 환경별 application-<env>.yml은 예정
├─ db/
│  └─ migration/                 # Flyway
└─ mybatis/
```

Spring (learning)
```
backend/learning-service/src/main/kotlin/com/sagomungchi/learning/
├─ _common/
│  ├─ config/
│  ├─ exception/
│  ├─ security/
│  └─ messaging/                 # 멱등 소비 (발행 없음)
├─ mission/                      # 미션·기준표·예시 답·생각 열기 질문 버전, 관리자 작성·검토·공개
│  ├─ controller/
│  ├─ service/
│  ├─ domain/
│  └─ repository/
├─ attempt/                      # 학습 시도·초안·도움 이용·마무리·돌아보기·자기 평가
│  ├─ controller/
│  ├─ service/
│  ├─ domain/
│  └─ repository/
├─ answer/                       # 답변 버전
│  ├─ controller/
│  ├─ service/
│  ├─ domain/
│  └─ repository/
├─ judgment/
│  ├─ controller/                # 피드백·정정 내부 API
│  ├─ service/
│  ├─ domain/
│  ├─ repository/
│  ├─ rule/                      # 고르기·수학 동치
│  ├─ client/
│  │  └─ AiClient.kt
│  └─ facade/
│     └─ FeedbackFacade.kt
├─ record/                       # 대시보드·에이전트 도구·리포트용 조회 API
│  ├─ controller/
│  ├─ service/
│  └─ repository/
└─ deletion/                     # student.deleted 소비
   ├─ consumer/
   └─ service/
```

Python (ai)
```
backend/ai-service/
├─ app/
│  ├─ main.py
│  ├─ bootstrap.py
│  ├─ config.py
│  ├─ errors.py                 # Problem Details 예외 핸들러
│  ├─ security.py               # 내부 토큰·사용자 컨텍스트·학생 범위 검사
│  ├─ versions.py               # 활성 프롬프트 버전, model.version.activated 수신 시 교체
│  ├─ judgment/
│  │  ├─ router.py
│  │  ├─ service.py
│  │  ├─ models.py               # 요청·응답 스키마
│  │  ├─ extractor.py            # LLM 근거 추출
│  │  ├─ verifier.py             # 코드 원문 대조
│  │  └─ prompts.py
│  ├─ followup/
│  │  ├─ router.py
│  │  ├─ service.py
│  │  ├─ models.py               # 요청·응답 스키마
│  │  ├─ leak_guard.py
│  │  └─ prompts.py
│  ├─ analysis_agent/
│  │  ├─ router.py
│  │  ├─ service.py
│  │  ├─ graph.py
│  │  ├─ nodes/
│  │  ├─ state.py
│  │  ├─ tools.py
│  │  ├─ calculators.py
│  │  ├─ verifier.py             # 답변 숫자·인용 ↔ 조회·계산 결과 대조
│  │  └─ prompts.py
│  ├─ report_narrative/
│  │  ├─ router.py
│  │  ├─ service.py
│  │  └─ prompts.py
│  ├─ clients/
│  │  ├─ base.py                 # 내부 토큰·컨텍스트 헤더 전달 httpx 클라이언트
│  │  ├─ learning_client.py
│  │  ├─ scoring_client.py
│  │  └─ core_client.py          # 기동 시 활성 버전 조회
│  ├─ llm/                       # LLM 클라이언트 래퍼 (제공자 교체 지점)
│  │  ├─ base.py                 # 공통 인터페이스·재시도·타임아웃·사용량 기록
│  │  └─ providers.py            # Claude·OpenAI·OpenAI 호환 sLLM, LLM_PROVIDER로 선택
│  ├─ messaging/
│  │  ├─ envelope.py
│  │  ├─ connection.py
│  │  ├─ publisher.py            # llm.usage.recorded
│  │  ├─ usage_recorder.py       # LlmClient 사용량 → 백그라운드 발행
│  │  └─ consumer.py             # model.version.activated, Pod별 exclusive 큐
│  └─ health/
│     └─ router.py
├─ tests/                        # app과 동일 기능 폴더 구조
├─ pyproject.toml
├─ uv.lock
└─ Dockerfile
```

Python (scoring)
```
backend/scoring-service/
├─ app/
│  ├─ main.py
│  ├─ bootstrap.py
│  ├─ config.py
│  ├─ errors.py
│  ├─ security.py
│  ├─ m2/
│  │  ├─ router.py
│  │  └─ service.py
│  ├─ m1/
│  │  ├─ router.py
│  │  └─ service.py
│  ├─ model_registry.py          # 활성 버전·가중치 로딩
│  ├─ clients/
│  │  ├─ base.py
│  │  └─ core_client.py          # 기동 시 활성 버전 조회
│  ├─ messaging/
│  │  ├─ envelope.py
│  │  ├─ connection.py
│  │  ├─ publisher.py            # llm.usage.recorded
│  │  └─ consumer.py             # model.version.activated, Pod별 exclusive 큐
│  └─ health/
│     └─ router.py
├─ tests/
├─ pyproject.toml
├─ uv.lock
└─ Dockerfile
```

Python (report)
```
backend/report-service/
├─ app/
│  ├─ main.py                    # report-api 진입점 (조회 API)
│  ├─ worker.py                  # report-worker 진입점 (report.generate·student.deleted 소비)
│  ├─ bootstrap.py
│  ├─ config.py
│  ├─ errors.py
│  ├─ security.py
│  ├─ generation/
│  │  ├─ consumer.py
│  │  ├─ service.py
│  │  ├─ metrics.py
│  │  ├─ verifier.py
│  │  ├─ models.py
│  │  └─ repository.py
│  ├─ rendering/
│  │  ├─ templates/
│  │  └─ renderer.py
│  ├─ query/
│  │  ├─ router.py
│  │  └─ service.py              # 학생 범위 검사·조회
│  ├─ deletion/
│  │  ├─ consumer.py
│  │  └─ service.py
│  ├─ outbox/                    # report.started·completed·failed
│  ├─ clients/
│  │  ├─ base.py
│  │  ├─ learning_client.py
│  │  ├─ ai_client.py
│  │  └─ storage.py              # S3·로컬 MinIO
│  ├─ messaging/
│  │  ├─ envelope.py
│  │  ├─ connection.py
│  │  ├─ publisher.py
│  │  └─ consumer.py
│  └─ health/
│     └─ router.py
├─ migrations/                   # Alembic
├─ tests/
├─ pyproject.toml
├─ uv.lock
└─ Dockerfile
```
- report는 같은 이미지로 `report-api`(`main.py`)·`report-worker`(`worker.py`) 2개 Deployment 배포 (4.4)

---

## 3. 프론트엔드 아키텍처
- 구조: `presentation`(페이지·컴포넌트) / `domain`(타입·화면 규칙) / `data`(API 클라이언트·SSE·쿼리 훅), 레이어 안은 기능 폴더
- 역할별 화면: `student`(홈·미션·되묻기·돌아보기), `parent`(대시보드·분석 대화·리포트·구독), `admin`(운영·미션·신고·결제·모델)
- 의존: `presentation → data`, `domain`은 공통 참조, 컴포넌트에서 API 직접 호출 금지
- 상태: 서버 상태 TanStack Query, UI 상태는 React state, 전역 상태 라이브러리 미도입
- API: core-service만 호출, [API 명세서](api-spec.md) 기준
- 스트리밍: 피드백·분석 대화·알림 SSE를 fetch 스트림으로 수신(인증 헤더 필요), 수신 결과로 쿼리 캐시 갱신
- 인증: access token 메모리 보관, refresh token httpOnly 쿠키
- 결제: 토스페이먼츠 결제위젯 SDK (테스트 키)
- 접근성: 움직임 줄이기 설정 시 정적 장면, 상태를 색상 외 글로 표시 (NFR-UX-02)

---

## 4. 인프라 아키텍처

### 4.1 환경 구분
| 구분 | 로컬 개발 | 로컬 K8s 검증 | 운영 (AWS) |
|---|---|---|---|
| 실행 | Docker Compose | kind 단일 노드 | EKS (eksctl) |
| 상태 저장소 | 컨테이너 | `platform-data` Helm chart (StatefulSet) | RDS PostgreSQL, S3 / RabbitMQ·Redis는 StatefulSet + EBS gp3 |
| 이미지 | 로컬 빌드 | GHCR | ECR |
| 배포 | `docker compose up` | Argo CD (local env) | Argo CD (prod env) |
| Ingress | - | ingress-nginx | AWS LB Controller (ALB) |
| CNI (NetworkPolicy) | - | Calico (기본 CNI 정책 지원 버전별 상이) | VPC CNI `enableNetworkPolicy: "true"` |
| 외부 연동 | stub (LLM·토스) | stub 또는 테스트 키 | LLM API, 토스페이먼츠 테스트 키 |

- 현재 stub(`infrastructure/stubs`)은 미구성이다. Docker Compose의 ai-service는 `.env`의 `LLM_PROVIDER`·API 키로 실제 LLM을 호출하고, 키가 없으면 판정·되묻기가 `AI_UNAVAILABLE`로 실패한다(6장 LLM 제공자).

- 로컬 자원 시작 기준: i5-1135G7(4코어·8스레드)·16GB급 PC, WSL 2 Docker 메모리 상한 약 7.62GiB. 저장소·Ingress·초기화 작업과 기반 구성에 약 6GiB를 계획하며, 앱·관측·모델 추론의 동시 실행 보장은 아니다. [이슈 #17 자원 설계](../report/local-platform-resource-plan.md)의 제안값을 구현·실측 후 조정한다.
- 로컬 MinIO는 `sagomungchi-local-missions`·`sagomungchi-local-reports`·`sagomungchi-local-models` 버킷 세 개를 단일 MinIO 저장 공간 안에 구성한다. 운영 S3 이름은 AWS 자원 작업에서 별도 확정한다.
- Compose의 MinIO는 선택 실행용 `compose.minio.yaml`에 서비스 세 개와 전용 볼륨을 둔다. 기본 `compose.yaml`은 MinIO 계정 없이 기존 앱·DB 실행과 스키마 검증에 사용하고, MinIO가 필요할 때만 두 파일을 함께 지정한다. kind의 MinIO는 로컬 values에서 계속 활성화한다.
- 로컬 MinIO 서버는 Chainguard 공개 배포본의 linux/amd64 digest로 고정하고, 버킷 초기화는 기존 curl 이미지의 고정 버전과 S3 서명 요청으로 수행한다. 이미지 참조는 `platform-data` 공통 values에서 관리한다. 로컬 계정은 `platform` namespace의 기존 `platform-data-credentials` Secret에 두고 chart는 키 이름만 참조한다. [platform-data 설정](../../infrastructure/gitops/charts/platform-data/README.md)을 따른다.
- 버전·CNI·이미지 배포·초기화·자격 증명·데이터 보존을 구체화한 내용과 근거는 [이슈 #17 설계 변경 근거](../report/local-platform-design-decisions.md)에 기록한다.
- 로컬 클러스터는 `sagomungchi-local`(kind v0.33.0, Kubernetes v1.35.8), Pod `10.244.0.0/16`, Service `10.96.0.0/12`, IPv4·iptables를 기준으로 한다. Calico v3.33.0과 ingress-nginx chart 4.15.1(controller v1.15.1)을 사용하며 API·HTTP·HTTPS를 loopback에서만 노출한다. 다른 PC·Wi-Fi·VPN 환경에서는 기존 경로·Docker subnet·포트 중복 여부를 확인한다. [kind 설정·설치 절차](../../infrastructure/kind/README.md)를 따른다.

### 4.2 운영 클러스터: EKS
- 선정 근거 (자체 구축 K8s(kubeadm·k3s) 대비)
  - 설계 구성 요소(ALB LB Controller, IRSA, EBS CSI, Cluster Autoscaler, ECR, Secrets Manager) AWS 기본 연동
  - control plane HA·etcd 백업·업그레이드를 AWS가 관리 → 12/7 일정 내 운영 부담 제거
  - 자체 구축도 control plane EC2 필요 → 비용 차이 작음 (EKS 수수료 $0.10/시간)
- 구성: eksctl(`infrastructure/eks/`), 관리형 노드그룹 2개(4.3), EKS add-on(VPC CNI·CoreDNS·kube-proxy·EBS CSI), IRSA, LB Controller·Cluster Autoscaler는 Argo CD `addons/prod/`
- 비용 절감
  - 데모 외 기간: 노드그룹 최소값 축소 또는 클러스터 삭제 후 eksctl 재생성
  - `platform-observability` 노드그룹 Spot 적용
  - NAT GW 단일 AZ 1개

### 4.3 운영 네트워크·배치
- VPC: Public Subnet(ALB, NAT GW) / Private Subnet(EKS 노드, RDS)
- 진입: CloudFront → S3(웹 정적 파일·미션 장면) / CloudFront → ALB(AWS Load Balancer Controller Ingress) → core-service
- CloudFront: 웹과 API를 한 배포·한 도메인에서 경로로 분기 (refresh 쿠키 `SameSite=Strict` 전제)
  - `/api/*` 동작: 캐시 비활성, `Authorization`·`Idempotency-Key`·`If-Match`·`X-Reauth-Token`·`Origin`·`X-Requested-With`(쿠키 API 검사, API 5.1) 헤더와 쿠키 전달, 압축 비활성(SSE 버퍼링 방지)
  - 타임아웃: CloudFront origin 응답 60초, ALB idle 120초 (SSE heartbeat 15초, 1.3)
- 외부 호출(LLM API·토스페이먼츠): Pod → NAT GW → Internet GW
- Namespace: `app`(core·learning·ai·scoring·report), `platform`(RabbitMQ·Redis), `observability`, `argocd`
- 노드그룹: `application`, `platform-observability` 분리 (참고 레포 2그룹 구성 계승)
- NetworkPolicy: 기본 거부 + 아래 허용만 (호출 관계는 [API 명세서](api-spec.md) 4장)

| 대상 | ingress 허용 | egress 허용 |
|---|---|---|
| core | ALB(서브넷 ipBlock), ai, scoring, learning, report-worker, Prometheus | learning, ai, report-api, RabbitMQ(5672·15672), Redis, RDS, 토스(NAT) |
| learning | core, ai, report-worker, Prometheus | core, ai, RabbitMQ, RDS, S3 |
| ai | core, learning, report-worker, Prometheus | learning, scoring, core, RabbitMQ, LLM API(NAT) |
| scoring | ai, Prometheus | core, RabbitMQ, S3 |
| report-api | core, Prometheus | RDS, S3 |
| report-worker | Prometheus | core, learning, ai, RabbitMQ, RDS, S3 |
| RabbitMQ·Redis | `app` 전체, KEDA(RabbitMQ), Prometheus | - |

  - 전 Pod 공통 egress: kube-dns(53), OTel Collector·Langfuse(`observability`)
  - report-api·report-worker는 라벨이 달라 허용 대상에 각각 명시
  - learning·report-worker → core는 삭제 완료 보고(`/internal/deletion-requests/.../completions`)만 사용 (P09)
  - migration-job: RDS egress / local: LLM API·토스 대신 `<target>-stub` Service로 egress

### 4.4 확장
- HPA(CPU): core, learning, ai, scoring, report-api — 최소 2(scoring은 메모리 고려해 최소 1, report-api 최소 1), PDB `minAvailable: 1`
- **KEDA(RabbitMQ 큐 길이)**: report-worker — 0~N 확장, EDA와 K8s 연계 지점
  - report 조회 API는 core가 동기 호출하므로 0으로 줄지 않는 `report-api`로 분리 (같은 이미지, 진입점만 다름). core `ReportClient` 대상 Service = report-api
  - `maxReplicaCount` × consumer prefetch = learning·ai·LLM API 동시 호출 상한 → LLM rate limit 이내로 설정 (값은 실측 후 결정)
- ai HPA: LLM 대기 위주라 CPU가 낮게 유지됨 → 실측 후 동시 요청 수 기준 지표 검토
- Cluster Autoscaler: Pending Pod 발생 시 application 노드 증설
- 종료 처리: core는 preStop 지연 + terminationGracePeriod로 SSE 정리 시간 확보 (롤링 배포·축소 시 단절은 클라이언트 재연결로 처리)
  - 피드백 executor 종료 대기는 최대 85초, heartbeat timer 종료 대기는 최대 5초다. 배포 시 `terminationGracePeriodSeconds`는 preStop 지연 + Spring/Tomcat 종료 단계의 예산 + 이 최대 90초 + 안전 여유보다 길게 설정하고 실제 롤링 종료로 검증한다. 현재 앱 Deployment의 수치가 저장소에 확정돼 있지 않아 이 작업에서 임의의 배포 설정은 추가하지 않는다. SIGKILL·프로세스 강제 종료 후에도 진행 중 호출이 보존된다는 의미는 아니다.
- probe: readiness는 자기 상태(DB·브로커 연결)만 확인, 하위 서비스 호출 금지 (연쇄 NotReady 방지)
- 공통 보안: 리소스 limit, non-root, readOnlyRootFilesystem

### 4.5 CI/CD
- GitHub Actions: 경로 필터로 변경 서비스만 테스트·빌드 → GHCR/ECR 푸시(OIDC로 AWS 인증). 현재는 테스트·빌드까지, 푸시·태그 갱신은 예정
- `infrastructure/gitops/environments/<env>/` 이미지 태그 갱신 커밋 → Argo CD 자동 동기화
- Secret: 운영 AWS Secrets Manager + External Secrets Operator / 로컬 `.env` → K8s Secret (LLM·토스 키는 저장소에 미포함, NFR-SEC-04)

### 4.6 관측
- Langfuse: LLM 호출·토큰·비용·trace
- OpenTelemetry → Prometheus + Grafana: 서비스 지표, 큐 길이·DLQ 적재량, 판정·피드백·리포트 처리 지연
- 경보: Grafana Alerting → 팀 디스코드 웹훅. 오류율·지연·작업 적체·월 LLM 비용 예산 80% 도달, 담당은 인프라 1명 + 서비스별 담당 (P10, P13)
- 백업: RDS 자동 백업(일 1회) + PITR, 보관 7일, RPO 5분·RTO 4시간 (P12)
- `traceparent`를 HTTP 헤더와 이벤트 봉투 양쪽에 전파 → 동기·비동기 구간 단일 trace

---

## 5. 디렉토리 구조

목표 구조다. `(예정)` 표시는 아직 저장소에 없는 항목이며 해당 기능 착수 시 만든다.

```
SKN34-FINAL-3TEAM/
├─ frontend/
│  └─ web/                       # React 웹
│     ├─ src/                    # 3장 참고
│     ├─ tests/
│     │  └─ e2e/                 # (예정) Playwright 대표 시나리오 (NFR-QA-01). 현재 빈 폴더
│     ├─ package.json
│     ├─ vite.config.ts
│     └─ tsconfig.json
├─ backend/                      # 서비스별 내부 구조는 2.6 참고
│  ├─ core-service/              # Spring Boot — 공개 API·계정·대화·리포트 작업·알림·결제·관리자
│  │  ├─ src/
│  │  │  ├─ main/
│  │  │  │  ├─ kotlin/           # 기능 패키지
│  │  │  │  └─ resources/        # application.yml(환경별 application-<env>.yml은 예정), Flyway, MyBatis
│  │  │  └─ test/
│  │  │     └─ kotlin/
│  │  └─ Dockerfile
│  ├─ learning-service/          # Spring Boot — 미션·학습 시도·답변·규칙 판정·기록 조회 (core-service와 동일 구성)
│  ├─ ai-service/                # FastAPI — 판정 근거·되묻기·분석 에이전트·리포트 서술
│  ├─ scoring-service/           # FastAPI — M2·M1 추론
│  └─ report-service/            # FastAPI — 리포트 생성·렌더링·조회 (report-api·report-worker)
├─ contracts/
│  ├─ events/
│  │  ├─ envelope.schema.json    # CloudEvents 공통 봉투
│  │  ├─ <message>.v1.schema.json  # 메시지 1개·버전 1개 = 파일 1개, 1.4 메시지 이름 그대로
│  │  └─ asyncapi.yaml           # (예정) exchange·routing key·생산/소비 매핑
│  └─ openapi/
│     └─ <service>.yaml          # api-spec.md 기준 생성. core-service(공개 API), 나머지(내부 API)
├─ ml/                           # 모델 학습 (클러스터 밖 실행, 이미지 빌드·배포 대상 아님)
│  ├─ m2/
│  ├─ m1/                        # (예정)
│  └─ sllm/                      # (예정)
├─ evaluation/                   # (예정) 판정 일치도(QWK)·되묻기 유출·에이전트 숫자/인용 대조 평가
│  ├─ datasets/                  # 평가셋별 cases.jsonl·fixtures (자체 작성 예시 답안, AI Hub 원문 미포함)
│  ├─ runners/                   # 서비스 호출·채점 스크립트
│  └─ results/                   # 실행 결과 요약
├─ infrastructure/
│  ├─ gitops/
│  │  ├─ charts/
│  │  │  ├─ app-service/         # (예정) 공통 서비스 chart
│  │  │  │  ├─ templates/
│  │  │  │  │  ├─ deployment.yaml
│  │  │  │  │  ├─ service.yaml
│  │  │  │  │  ├─ serviceaccount.yaml          # IRSA (S3 접근 서비스)
│  │  │  │  │  ├─ hpa.yaml
│  │  │  │  │  ├─ scaledobject.yaml
│  │  │  │  │  ├─ triggerauthentication.yaml   # KEDA RabbitMQ 인증
│  │  │  │  │  ├─ pdb.yaml
│  │  │  │  │  ├─ networkpolicy.yaml
│  │  │  │  │  ├─ externalsecret.yaml
│  │  │  │  │  ├─ ingress.yaml
│  │  │  │  │  └─ migration-job.yaml           # Argo CD PreSync hook
│  │  │  │  └─ values.yaml
│  │  │  ├─ platform-data/       # RabbitMQ·Redis (+ 로컬 전용 PostgreSQL·MinIO)
│  │  │  │  ├─ templates/
│  │  │  │  ├─ files/
│  │  │  │  │  ├─ rabbitmq/
│  │  │  │  │  │  └─ definitions.json      # exchange·queue·DLX 단일 기준
│  │  │  │  │  └─ postgres/
│  │  │  │  │     └─ init.sql              # 로컬 전용 서비스별 DB 생성
│  │  │  │  └─ values.yaml
│  │  │  └─ observability/       # (예정) OTel Collector·Prometheus·Grafana·Langfuse
│  │  │     ├─ templates/
│  │  │     └─ values.yaml
│  │  ├─ environments/           # 앱별 values·이미지 태그
│  │  │  ├─ local/
│  │  │  │  ├─ core-service.yaml     # (예정) 앱별 파일 전부 예정, 현재 platform-data.yaml만 존재
│  │  │  │  ├─ learning-service.yaml
│  │  │  │  ├─ ai-service.yaml
│  │  │  │  ├─ scoring-service.yaml
│  │  │  │  ├─ report-api.yaml
│  │  │  │  ├─ report-worker.yaml
│  │  │  │  ├─ <target>-stub.yaml
│  │  │  │  ├─ platform-data.yaml
│  │  │  │  └─ observability.yaml
│  │  │  └─ prod/                # (예정) local과 동일 구성, stub 제외
│  │  └─ argocd/                 # (예정)
│  │     ├─ local/
│  │     │  └─ root-app.yaml     # kind Argo CD 진입점
│  │     ├─ prod/
│  │     │  └─ root-app.yaml     # EKS Argo CD 진입점
│  │     ├─ apps/
│  │     │  └─ applicationset.yaml  # env 파라미터로 environments/<env>/* Application 생성
│  │     └─ addons/              # 외부 Helm chart
│  │        ├─ common/           # KEDA
│  │        └─ prod/             # External Secrets·AWS LB Controller·Cluster Autoscaler
│  ├─ kind/
│  │  └─ local.yaml              # kind 클러스터 설정
│  ├─ eks/                       # (예정) eksctl 클러스터·노드그룹·IRSA·StorageClass
│  ├─ aws/                       # (예정) eksctl 범위 밖 자원: RDS·S3·CloudFront·ECR·Secrets Manager·GitHub OIDC IAM (도구 미정)
│  └─ stubs/                     # (예정)
│     └─ <target>-stub/          # LLM·토스페이먼츠 대역 (테스트·무료 시연용)
│        └─ Dockerfile
├─ .github/
│  └─ workflows/
│     ├─ _spring.yml             # 재사용 워크플로: 테스트→빌드 (푸시·태그 갱신은 예정)
│     ├─ _python.yml
│     ├─ _web.yml
│     ├─ ci-<service>.yml        # 서비스·stub별 경로 필터(<경로>/**, contracts/**) → 재사용 워크플로 호출
│     ├─ ci-db-schema.yml        # 마이그레이션 적용·ERD 대조 (scripts/check_db_migrations.py)
│     └─ ci-contracts.yml        # (예정) 스키마 검증, asyncapi ↔ definitions.json exchange·routing key 일치 검사
├─ docs/
│  ├─ README.md                  # 개발 규칙
│  ├─ design/                    # 아키텍처·기능명세·API 명세 등 설계 문서
│  └─ adr/                       # (예정) NNNN-<제목>.md
├─ compose.yaml                  # 로컬 통합 실행 진입점
├─ compose.minio.yaml            # 로컬 MinIO 선택 실행 (기본 파일과 함께 지정)
├─ .env.example
└─ README.md
```

- DB 마이그레이션: 서비스별 Flyway(core·learning)·Alembic(report), 앱 기동이 아닌 `migration-job`(Argo CD PreSync hook)으로 1회 실행. 로컬 compose는 일회성 컨테이너로 동일 실행
- 서비스 추가: `app-service` chart 재사용 + `environments/<env>/<service>.yaml` (ApplicationSet이 자동 생성, 서비스별 chart 미작성)
- 한 서비스의 다중 Deployment(report-api·report-worker): 같은 이미지, values의 실행 명령·확장 방식만 다름
- API 변경: `api-spec.md` 먼저 수정 → `contracts/openapi` → 구현
- 메시지 변경: `contracts/events` 먼저 수정 → 생산·소비 서비스 반영
- 큐 선언: `definitions.json`만 선언, 서비스 코드는 선언 없이 존재 확인만. 예외: 브로드캐스트 이벤트의 Pod별 exclusive 큐 (1.6)
- `definitions.json`은 Helm `.Files` 접근 범위인 `platform-data` chart 안에 두고, compose도 같은 파일 마운트
- 공통 코드: 공통 라이브러리 없이 서비스별 보유(이벤트 봉투·Outbox·AMQP 연결), `contracts/events` 스키마로 계약 테스트. 중복이 문제 될 때 `libs/` 검토
- Docker 빌드 컨텍스트는 서비스 폴더, `contracts/` 계약 테스트는 CI에서만 실행
- 모델 학습 코드(M2·M1·sLLM)는 `ml/`에서 관리, scoring은 승인된 가중치(S3)만 로딩
- 참고 레포 대비 추가: `contracts/`, `ml/`, `infrastructure/aws/` / 제외: `mobile/`, `ops-service`(LLMOps는 Langfuse + `evaluation/`로 시작, 필요 시 추가)

---

## 6. 사용 기술

| 영역 | 기술 | 선정 근거 |
|---|---|---|
| 프론트엔드 | React, Vite, TypeScript, Tailwind CSS, TanStack Query, 토스페이먼츠 결제위젯 SDK | 참고 레포 동일 계열, 기획서 4.4 |
| 업무 API | Spring Boot 3, Kotlin, JDK 21, Spring Security JOSE(JWT HS256·Google JWKS), MyBatis, Flyway, Spring AMQP, ShedLock(예정), Resilience4j | 참고 레포 구현 패턴 재사용, 다중 레플리카 스케줄 중복 방지 |
| AI API | Python 3.12, FastAPI, Pydantic, uv, LangGraph, LangChain, OpenAI API(기본 `gpt-6.1-terra`)·Claude API(`LLM_PROVIDER`로 교체), aio-pika, httpx | 에이전트 그래프·도구 호출, 비동기 AMQP |
| 모델 추론 | PyTorch, Hugging Face Transformers (M2 klue/roberta, M1) | 기획서 5장 모델 |
| 리포트 | SQLAlchemy, Alembic, Jinja2, Playwright(Chromium PDF) | HTML 템플릿 → PDF·Markdown |
| 저장소 | PostgreSQL(RDS), S3(로컬 MinIO), Redis(core 연동은 예정, 현재 Compose 기동만) | 서비스별 DB 분리, 판정 근거·기준표 JSONB, 파일 분리, SSE 중계·캐시 |
| 메시징 | RabbitMQ (quorum queue, topic/direct exchange, DLX) | 작업 큐 + fan-out 동시 지원, Kafka 대비 운영 부담 작음 |
| 결제 | 토스페이먼츠 테스트 환경 (결제위젯·자동결제·웹훅) | 실결제 미연동 |
| 컨테이너·오케스트레이션 | Docker, Compose, kind, Kubernetes, Helm | 로컬 → 운영 동일 chart |
| 확장 | HPA, KEDA, Cluster Autoscaler, PDB | CPU 기반 API 확장 + 큐 기반 워커 확장 |
| AWS | EKS(eksctl), EC2, VPC, ALB(LB Controller), CloudFront, S3, RDS, ECR, EBS gp3, Secrets Manager | 관리형 control plane(자체 구축 대비 운영 부담 제거)·AWS 연동 기본 지원, 참고 레포 EKS 구성 계승 + 관리형 DB |
| GitOps·CI | GitHub Actions(OIDC), GHCR, Argo CD, External Secrets | 변경 서비스만 빌드, Git 기준 배포 |
| 테스트 | JUnit5, Testcontainers, pytest, Playwright(E2E, 예정) | 기획서 4.4 |
| 관측·LLMOps | Langfuse, OpenTelemetry, Prometheus, Grafana | LLM trace + 서비스·큐 지표 |

---

## 7. 확인 필요 가정
- 정책 값은 [기능명세서 1.4 확정 정책](functional-spec.md#14-확정-정책) 기준
- LLM 제공자: 기본 OpenAI `gpt-6.1-terra`(`LLM_PROVIDER=openai`), `LLM_PROVIDER=anthropic`으로 Claude 교체 가능. ai-service `llm/` 래퍼(제공자별 클래스)로 교체 가능하게 설계. 기획서 4.4의 Claude API에서 바꾼 근거는 [ai 판정·되묻기 보고서](../report/ai-judgment-followup.md) "OpenAI 실제 호출 확인"
- 학습·일괄 생성(RunPod GPU, sLLM 설명)은 클러스터 밖에서 수행, 결과(가중치·주간 설명 문장)만 S3로 반입
- AWS 계정 EKS 생성 권한·예산 한도: 권한 없으면 EC2 1대 + k3s로 대체 (HA·Cluster Autoscaler·IRSA 제외)


### #36 인증 구현 결정
core의 공개 JWT 필터(`PublicAuthFilter`) → account service(`AuthService`) → Repository/Mapper → core_db로 로그인 세션·현재 권한을 확인한다. JWT는 Spring Security JOSE HS256, Google은 client에서 HTTP 코드 교환·JWKS 검증 후 내부 프로필로 변환한다. OAuth 외부 호출은 DB 트랜잭션 밖, 계정·세션·refresh 회전만 트랜잭션 안에서 처리한다. 상태 있는 access/refresh이며 브라우저 인증을 세션 쿠키 하나로 바꾸지 않는다. 세부 계약·키 관리·#37/#45 경계는 [#36 보고서](../report/issue-36-google-auth.md)를 따른다.


### #42 주간 리포트 연결 경계

#50 report-worker는 공유 v1 규격을 `ReportV1Codec`으로 검증하고 기본 진입점에서 생성 큐·Outbox 릴레이를 시작한다. report Outbox는 이벤트별 session advisory lock과 AUTOCOMMIT 연결로 발행을 선점하고, publisher confirm 이후 짧은 트랜잭션에서 발행 시각을 기록한다. HTTP·AMQP 대기 동안 DB 트랜잭션을 유지하지 않는다. #50 기반 단독 실행에서 계산/렌더링 생성기가 미연결이면 `GENERATOR_NOT_CONFIGURED`로 실패를 명시한다. 실제 생성기는 #51~#53에서 조립하며 이 기반만으로 전체 리포트 E2E 완료를 의미하지 않는다. 상세 검증은 [#50 보고서](../report/report-generation-foundation.md)를 따른다.

#48은 ReportEntitlementService를 payment 소유 ProductEntitlementService에 연결한다. 외부 PG 호출과 learning 사용 증빙 조회는 DB 트랜잭션 밖, 주문/구독/환불·프리미엄 사용 예약은 공통 parent 계정 행 잠금 안이다. payment repository는 payment 패키지만 사용한다. 신규 의존성 없이 기존 HTTP·MyBatis·ShedLock·IdempotencyService·NotificationService를 사용한다. [결제 경계·복구](../report/issue-48-payments.md).


report/scheduler → ReportScheduleService → ReportJobService의 자녀별 트랜잭션 → ReportJobRepository + 기존 OutboxWriter를 사용한다. report/consumer는 기존 RetryingConsumer → ReportLifecycleService(트랜잭션) → processed_event·report_job·job_execution을 사용한다. ReportQueryService의 내부 HTTP와 열람 저장 트랜잭션은 분리한다. ReportEntitlementService는 payment 소유 ProductEntitlementService에 위임하며 상품·구독 repository를 직접 참조하지 않는다. 기존 StudentAccessService·ConsentAccessService를 재사용하고 #37 구현을 복사하지 않는다. ShedLock Spring/JDBC 6.10.0만 production 의존성으로 추가하며 기존 shedlock 테이블을 사용한다. 상세 결정과 기존 OutboxRelay의 트랜잭션 제한은 [#42 보고서](../report/issue-42-weekly-reports.md)를 따른다.

## #45 삭제·재인증 보완

`student.deleted.v1` data는 `{studentId,deletionRequestId,scope:PROFILE|RECORDS}`다. 요청 CONFIRMED와 OutboxWriter.append는 한 트랜잭션이다. learning/report는 실제 삭제가 끝난 후 요청 ID와 service로 완료 보고한다. core는 서비스별 UNIQUE 완료 행을 기록하고 둘 다 확인할 때만 COMPLETED로 전이한다. core 분석 대화 정리는 conversation service를 통해 같은 DB 트랜잭션으로 처리한다. payment의 탈퇴 조건 조회도 payment service를 통해 호출한다. account/guardianship에서 다른 기능 repository를 직접 참조하지 않는다. Google 네트워크 교환은 DB 트랜잭션 밖에서 수행한다.

#58 학생 단독 인증: account/controller → account/service/StudentAuthService → account/repository(StudentDeviceRepository, PairingRepository). PIN·자녀 잠금은 guardianship/service/StudentPinService → guardianship/repository/StudentPinRepository. 기능 간 repository 참조 없이 service로 연결한다. PIN 변경의 재인증 DB 소비·PIN 갱신·audit는 같은 트랜잭션이다. Redis 페어링은 DB 등록 전 단회 소비하며 실패 시 코드 재발급이 필요하다.


### #46 신고·지원 연결 경계

support/controller → SupportService → support/repository를 사용한다. 대상 검증은 상대 기능 service(StudentAccessService·ConversationSupportService·ReportSupportService)를 호출하며 다른 기능 repository를 직접 참조하지 않는다. support/client는 기존 learning LearningClient·InternalRestClientFactory를 재사용한다. 정정 의도 저장·완료 저장 사이 HTTP는 트랜잭션 밖이며, core 영속 correction UUID가 공급자 요청 식별자다. 원문 응답 전 감사 저장이 실패하면 원문을 반환하지 않는다. 알림은 NotificationService.support로 저장·수신 설정·중복 방지·NotificationStored·커밋 후 Redis 전달을 재사용한다. 자세한 범위와 공급자 미구현은 [#46 보고서](../report/issue-46-support.md)에 기록한다.
