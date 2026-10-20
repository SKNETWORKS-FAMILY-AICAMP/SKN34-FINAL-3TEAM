# 아키텍처 설계 (참고: SKN34-4th-1Team)

## 배경
- 대주제: 대화형 데이터 기반 분석 에이전트 및 자동 리포팅 플랫폼 (세부 주제 미정 → 공통 기능 기준 범용 설계)
- 확정 사항: Spring + Python 혼합, RabbitMQ 하이브리드 EDA, kind 로컬 + AWS EKS 운영
- 참고 레포에서 계승: `backend/<x>-service` 모노레포, 기능 중심 패키지, Outbox·DLQ·수동 ACK, Helm + Argo CD GitOps, kind/EKS, `evaluation/`, `infrastructure/stubs`
- 참고 레포 대비 보강: 작업 큐만 쓰던 구조 → **명령 큐 + 도메인 이벤트 fan-out** 구분, 이벤트 계약(`contracts/`), 큐 길이 기반 오토스케일링(KEDA), 코드 실행 격리

---

## 1. 시스템 아키텍처

### 1.1 서비스 경계 (5개)

| 서비스 | 언어 | 책임 | 소유 저장소 |
|---|---|---|---|
| core-service | Spring Boot (Kotlin) | **유일한 공개 API**. 계정·인증, 워크스페이스, 대화 세션·이력, 리포트 요청·정기 일정, 알림(이메일·SSE), 관리자 | core_db, Redis |
| data-service | Spring Boot (Kotlin) | 데이터 소스 등록·업로드(presigned URL), 메타데이터 카탈로그, 스키마 버전, 접근 권한 | data_db, S3 |
| ai-service | FastAPI | LangGraph 분석 에이전트(NL2SQL·분석 계획·차트 스펙), 리포트 서술 생성, 스키마 의미 색인 | Qdrant (상태 없음) |
| compute-service | FastAPI | 데이터 프로파일링, 읽기 전용 쿼리·생성 코드 **격리 실행** (DuckDB·pandas) | 없음 (S3 읽기만) |
| report-service | FastAPI | 리포트 조립·렌더링(HTML/PDF)·저장 | report_db, S3 |

- 언어 분담 근거: 트랜잭션·권한·Outbox·스케줄 = Spring 생태계(Spring AMQP, Flyway, ShedLock) 성숙 / 데이터 처리·LLM·렌더링 = Python 생태계
- 다른 서비스 DB 직접 접근 금지, API 또는 이벤트로만 연동 (참고 레포 원칙 동일)
- 세부 주제 확정 시: 도메인 특화 데이터 수집이 필요하면 참고 레포 `catalog-service`처럼 수집 서비스 1개 추가

### 1.2 전체 구성도

```
[React Web] ──HTTPS──▶ CloudFront ──▶ ALB(Ingress) ──▶ core-service ──SSE──▶ Web
                                                     │
                     ┌───────────── HTTP(동기) ───────┼─────────────────────┐
                     ▼                                ▼                     ▼
               data-service                      ai-service ──HTTP──▶ compute-service
                     │                                │ (Qdrant)            (격리 namespace)
                     ▼                                │
      ┌──────────────────────── RabbitMQ ───────────────────────────────────┐
      │ cmd.direct  : profiling.run, report.generate        (작업 큐, 소비자 1) │
      │ events.topic: dataset.*, analysis.*, report.*       (fan-out, 소비자 N) │
      └─────────────────────────────────────────────────────────────────────┘
               ▲ consume                ▲ consume              ▲ consume
        compute-service           report-service         core / data / ai

저장소: RDS MySQL(서비스별 스키마) · S3(원본 데이터·리포트) · Redis · Qdrant
```

### 1.3 통신 원칙
| 구간 | 방식 | 근거 |
|---|---|---|
| 채팅 분석 (Web→core→ai→compute) | 동기 HTTP + SSE 스트리밍 | 사용자 실시간 대기, 응답 지연 불가 |
| 오래 걸리는 단일 작업 (프로파일링, 리포트 생성) | **명령** → `cmd.direct` 작업 큐 | 타임아웃 회피, 재시도, 워커 단독 확장 |
| 상태 변화 전파 | **이벤트** → `events.topic` | 생산자가 소비자를 모름, 소비자 추가 시 생산자 무변경 |

### 1.4 메시지 목록

| 메시지 | 종류 | 생산 | 소비 | 소비 측 처리 |
|---|---|---|---|---|
| `profiling.run` | 명령 | data | compute | 통계·스키마 추출 |
| `dataset.registered` | 이벤트 | data | core | 화면 상태 갱신 |
| `dataset.profiled` | 이벤트 | compute | data / ai / core | 메타데이터 READY / Qdrant 스키마 색인(상태 사본 보유 → ai→data 동기 호출 제거) / 사용자 알림 |
| `analysis.completed` | 이벤트 | core | report / core(usage) | 리포트 소재 수집 / 토큰·비용 집계 |
| `report.generate` | 명령 | core (수동·정기) | report | 데이터 조회→서술→렌더링 |
| `report.completed` / `report.failed` | 이벤트 | report | core | 상태 갱신, 이메일·SSE 알림 |

### 1.5 핵심 흐름
1. **데이터 등록**: core → data(presigned URL 발급) → 브라우저가 S3 직접 업로드 → data가 dataset 저장 + Outbox(`dataset.registered`, `profiling.run`) → compute 프로파일링 → `dataset.profiled` → data·ai·core 각각 반영
2. **대화형 분석**: Web ─SSE→ core → ai(스트리밍) → LangGraph `classify → plan → retrieve_schema(Qdrant) → generate_sql → execute(compute) → chart → verify → answer` → core가 이력 저장 + Outbox(`analysis.completed`)
3. **자동 리포트**: core 스케줄러(ShedLock) 또는 사용자 요청 → report_job + Outbox → `report.generate` → report가 compute로 최신 데이터 조회, ai로 서술 생성, 렌더링·S3 저장 → `report.completed` → core 알림

### 1.6 메시징 신뢰성 규칙
- **Outbox**: DB 상태 변경 + 발행이 함께 필요한 서비스(core, data, report)만 적용. 같은 트랜잭션에 outbox 행 저장 → 릴레이 스케줄러가 publisher confirm 받은 후 발행 시각 기록 (참고 레포 `*OutboxScheduler` 패턴)
- **상태 없는 워커(compute)**: 처리 → 결과 이벤트 발행·confirm → 그 후 ACK. 중간 장애 시 명령 재전달로 재실행
- **멱등 소비**: 소비자별 `processed_event(event_id UK)` 테이블 또는 DB 상태 전이 조건(`QUEUED→RUNNING`)
- **DLQ**: 큐마다 dead-letter exchange, 관리자 화면에서 현황 조회 (참고 레포 `QueueOperations*` 계승)
- **이벤트 봉투**: CloudEvents 형식 `id, type, source, time, subject, traceparent, data` → `contracts/events/*.schema.json`
- **SSE 다중 레플리카**: core 레플리카 간 Redis Pub/Sub으로 알림 중계

---

## 2. 백엔드 아키텍처

### 2.1 구조 원칙: 기능 단위 패키지 + 기능 내부 레이어드 아키텍처
- 최상위는 기능(`report/`, `chat/` …) 기준, 각 기능 내부를 레이어로 분리 (참고 레포 core-service 동일 방식)
- 기능 우선 근거: 한 기능의 코드가 한 폴더에 모임, 기능을 별도 서비스로 분리하기 쉬움
- 헥사고날·클린 아키텍처 미적용: 서비스 규모 대비 포트·어댑터 비용 과다. 교체 가능성이 큰 LLM 제공자(`llm/`), 실행 환경(`sandbox`)만 래퍼로 분리

| 레이어 | Spring 위치 | Python 위치 | 책임 | 금지 |
|---|---|---|---|---|
| Presentation | `controller`, `consumer`, `scheduler` | `router.py`, `consumer.py` | HTTP·메시지·스케줄 수신, DTO 검증·변환, 인증 정보 추출, ACK | 업무 로직, DB 접근 |
| Application | `service`, `facade` | `service.py`, `graph.py`·`nodes/`(ai) | 업무 흐름, 트랜잭션 경계, Outbox 기록 | HTTP 요청·AMQP 채널 객체 직접 사용 |
| Domain | `domain` | `models.py`, `state.py` | 엔티티·값 객체, 상태 전이 규칙(`QUEUED→RUNNING` 등) | 프레임워크·외부 라이브러리 의존 |
| Infrastructure | `repository`, `client`, `messaging` | `repository.py`, `clients/`, `messaging/`, `llm/`, `sandbox.py` | DB, 외부 API, 브로커, LLM, S3 연동 | 업무 판단 |

### 2.2 의존 규칙
- `Presentation → Application → Infrastructure` 단방향, 계층 건너뛰기 금지 (controller → repository 직접 호출 금지)
- Domain은 모든 레이어가 참조 가능, Domain은 다른 레이어를 참조하지 않음
- 기능 간 호출은 상대 기능의 service로만 (다른 기능의 repository 직접 참조 금지)
- 여러 기능에 걸친 흐름은 `facade`로 조합 (참고 레포 `applicationpreparation/facade` 패턴)
- 공통 코드: Spring `_common/`, Python `app/` 루트의 `config.py`·`messaging/`
- DB 트랜잭션은 Application 레이어에서만 시작, 트랜잭션 안에서 외부 HTTP·AMQP 호출 금지
- 서비스 간 내부 호출: 내부 토큰 헤더 필터(참고 레포 `CatalogInternalAuthFilter` 패턴) + NetworkPolicy

### 2.3 서비스별 적용 강도
| 서비스 | 적용 레이어 | 비고 |
|---|---|---|
| core, data | 4개 전부 | 업무 규칙·DB 소유 → 표준 적용 |
| report | 4개 전부 | 작업 상태 전이·Outbox 보유 |
| ai | Presentation · Application · Infrastructure | DB 없음. LangGraph 그래프·노드가 Application, Qdrant·LLM이 Infrastructure |
| compute | Presentation · Application · Infrastructure | 상태 없음. `sandbox`·`sql_guard`가 Infrastructure |

### 2.4 요청 처리 예시 (core 리포트 요청)
```
ReportController (Presentation)      요청 검증 → DTO 변환
  → ReportService (Application)      권한 확인, @Transactional: report_job 저장 + outbox 기록
    → ReportJob (Domain)             QUEUED 상태 생성 규칙
    → ReportRepository (Infra)       MyBatis → MySQL
OutboxRelay (_common/messaging, Infra)  미발행 outbox 조회 → ReportCommandPublisher → RabbitMQ (업무 로직 없음)
ReportEventConsumer (Presentation)   report.completed 수신 → ReportService.complete() → ACK
```

### 2.5 서비스 폴더 예시

Spring (core)
```
backend/core-service/src/main/kotlin/<base>/core/
├─ _common/{config, exception, security, messaging}   # 이벤트 봉투, OutboxRelay
├─ account/{controller, service, domain, repository}
├─ workspace/
├─ chat/{controller(SSE), service, domain, repository, client(AiServiceClient)}
├─ report/{controller, consumer(ReportEventConsumer), scheduler, service, domain, repository, messaging(ReportCommandPublisher)}
├─ notification/{service, client(Mail), sse}
└─ admin/{controller, service}                         # 큐·DLQ 현황
src/main/resources/{db/migration (Flyway), mybatis/}
```

Python (ai)
```
backend/ai-service/app/
├─ main.py, bootstrap.py, config.py
├─ analysis_agent/{router.py, service.py, graph.py, nodes/, state.py, models.py, tools.py, prompts.py}
├─ schema_index/{consumer.py, service.py}      # dataset.profiled → Qdrant
├─ report_narrative/{router.py, service.py, prompt.py}
├─ clients/compute_client.py                  # compute-service 호출
├─ llm/                                       # LLM 클라이언트 래퍼 (제공자 교체 지점)
├─ messaging/{envelope.py, connection.py, consumer.py}
└─ health/router.py
```
- compute: `profiling/{consumer.py, service.py, models.py}`, `execution/{router.py, service.py, sandbox.py, sql_guard.py}` (sqlglot으로 SELECT만 허용, 실행 시간·행 수 제한)
- report: `generation/{consumer.py, service.py, models.py, repository.py}`, `rendering/{templates/, renderer.py}`, `outbox/`

---

## 3. 인프라 아키텍처

### 3.1 환경 구분
| 구분 | 로컬 개발 | 로컬 K8s 검증 | 운영 (AWS) |
|---|---|---|---|
| 실행 | Docker Compose | kind 단일 노드 | EKS (eksctl) |
| 상태 저장소 | 컨테이너 | `platform-data` Helm chart (StatefulSet) | RDS MySQL, S3 / RabbitMQ·Redis·Qdrant는 StatefulSet + EBS gp3 |
| 이미지 | 로컬 빌드 | GHCR | ECR |
| 배포 | `docker compose up` | Argo CD (local env) | Argo CD (prod env) |

### 3.2 운영 네트워크·배치
- VPC: Public Subnet(ALB, NAT GW) / Private Subnet(EKS 노드, RDS)
- 진입: CloudFront → S3(웹 정적 파일) / CloudFront → ALB(AWS Load Balancer Controller Ingress) → core-service
- 외부 호출(LLM API): Pod → NAT GW → Internet GW
- Namespace: `app`(core·data·ai·report), `sandbox`(compute), `platform`(RabbitMQ·Redis·Qdrant), `observability`, `argocd`
- 노드그룹: `application`, `platform-observability` 분리 (참고 레포 2그룹 구성 계승)

### 3.3 확장·격리
- HPA(CPU): core, ai — 최소 2, PDB `minAvailable: 1`
- **KEDA(RabbitMQ 큐 길이)**: compute, report 워커 — 0~N 확장, EDA와 K8s 연계 지점
- Cluster Autoscaler: Pending Pod 발생 시 application 노드 증설
- sandbox 격리: egress 전면 차단 NetworkPolicy, 리소스 limit, non-root, readOnlyRootFilesystem, ServiceAccount 토큰 미주입

### 3.4 CI/CD
- GitHub Actions: 경로 필터로 변경 서비스만 테스트·빌드 → GHCR/ECR 푸시(OIDC로 AWS 인증)
- `infrastructure/gitops/environments/<env>/` 이미지 태그 갱신 커밋 → Argo CD 자동 동기화
- Secret: 운영 AWS Secrets Manager + External Secrets Operator / 로컬 `.env` → K8s Secret

### 3.5 관측
- Langfuse: LLM 호출·토큰·비용·trace
- OpenTelemetry → Prometheus + Grafana: 서비스 지표, 큐 길이·DLQ 적재량
- `traceparent`를 HTTP 헤더와 이벤트 봉투 양쪽에 전파 → 동기·비동기 구간 단일 trace

---

## 4. 디렉토리 구조
```
SKN34-FINAL-3TEAM/
├─ frontend/web/                 React 웹 (presentation / domain / data 구조)
├─ backend/
│  ├─ core-service/              Spring Boot — 공개 API·사용자 업무·리포트 일정·알림
│  ├─ data-service/              Spring Boot — 데이터 소스·업로드·메타데이터
│  ├─ ai-service/                FastAPI — 분석 에이전트·리포트 서술·스키마 색인
│  ├─ compute-service/           FastAPI — 프로파일링·격리 실행
│  └─ report-service/            FastAPI — 리포트 생성·렌더링
├─ contracts/
│  ├─ events/                    이벤트 JSON Schema, asyncapi.yaml
│  └─ openapi/                   서비스별 OpenAPI
├─ evaluation/                   NL2SQL·분석 정확도 평가셋, 실행 결과
├─ infrastructure/
│  ├─ gitops/
│  │  ├─ charts/{app-service, platform-data, observability}/   공통 서비스 chart + 저장소 + 관측
│  │  ├─ environments/{local, prod}/                           환경별 values·이미지 태그
│  │  ├─ argocd/
│  │  └─ kind/local.yaml
│  ├─ eks/                       eksctl 클러스터·노드그룹·Ingress·오토스케일링·StorageClass
│  ├─ messaging/                 RabbitMQ exchange·queue·DLX 정의 (definitions.json)
│  └─ stubs/                     LLM·외부 API 대역 (테스트·무료 시연용)
├─ .github/workflows/            서비스별 CI, 이미지 발행, 배포
├─ docs/{architecture/, adr/}
├─ compose.yaml                  로컬 통합 실행 진입점
├─ .env.example
└─ README.md
```
- 템플릿(`project_template`) 대비: `Backend/LLM/Vision/DB` → `backend/<x>-service`로 대체, `Vision` 제거, `DB/` 제거(마이그레이션은 서비스별 Flyway·Alembic)
- 참고 레포 대비 추가: `contracts/`, `infrastructure/messaging/` / 제외: `mobile/`, `ops-service`(LLMOps는 Langfuse + `evaluation/`로 시작, 필요 시 추가)

---

## 5. 사용 기술

| 영역 | 기술 | 선정 근거 |
|---|---|---|
| 프론트엔드 | React, Vite, TypeScript, Tailwind CSS, TanStack Query, Plotly.js | 참고 레포 동일 계열, 차트 스펙을 백엔드 렌더링과 공유 |
| 업무 API | Spring Boot 3, Kotlin, JDK 21, Spring Security(JWT), MyBatis, Flyway, Spring AMQP, ShedLock | 참고 레포 구현 패턴 재사용, 다중 레플리카 스케줄 중복 방지 |
| AI·분석 API | Python 3.12, FastAPI, uv, LangGraph, LangChain, LLM API, aio-pika | 에이전트 그래프·도구 호출, 비동기 AMQP |
| 데이터 처리 | DuckDB, pandas, sqlglot | 파일 기반 데이터 직접 SQL, SQL 검증·읽기 전용 강제 |
| 리포트 | Jinja2, Playwright(Chromium PDF), Plotly + kaleido | HTML 템플릿 → PDF, 웹과 동일 차트 |
| 저장소 | MySQL 8.4(RDS), S3(로컬 MinIO), Redis, Qdrant | 서비스별 스키마 분리, 대용량 파일 분리, SSE 중계·캐시, 스키마 의미 검색 |
| 메시징 | RabbitMQ (quorum queue, topic/direct exchange, DLX) | 작업 큐 + fan-out 동시 지원, Kafka 대비 운영 부담 작음 |
| 컨테이너·오케스트레이션 | Docker, Compose, kind, Kubernetes, Helm | 로컬 → 운영 동일 chart |
| 확장 | HPA, KEDA, Cluster Autoscaler, PDB | CPU 기반 API 확장 + 큐 기반 워커 확장 |
| AWS | EKS(eksctl), EC2, VPC, ALB(LB Controller), CloudFront, S3, RDS, ECR, EBS gp3, Secrets Manager | 참고 레포 EKS 구성 계승 + 관리형 DB |
| GitOps·CI | GitHub Actions(OIDC), GHCR, Argo CD, External Secrets | 변경 서비스만 빌드, Git 기준 배포 |
| 관측·LLMOps | Langfuse, OpenTelemetry, Prometheus, Grafana | LLM trace + 서비스·큐 지표 |

---

## 6. 확인 필요 가정
- LLM 제공자: 미정 (ai-service `llm/` 래퍼로 교체 가능하게 설계)

