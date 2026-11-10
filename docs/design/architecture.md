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
| core-service | Spring Boot (Kotlin) | **유일한 공개 API**. 계정·인증·동의, 학부모-자녀 연결(권한 기준), 분석 대화 세션·이력, 주간·일일 리포트 작업·일정, 알림(SSE·인앱), 신고·문의·공지, 결제·구독(토스페이먼츠 테스트), 관리자 운영·모델 버전 레지스트리, LLM 사용량 집계 | core_db, Redis |
| learning-service | Spring Boot (Kotlin) | 미션·기준표·예시 답·생각 열기 질문(버전 관리), 학습 시도·답변 버전·초안·도움 이용·돌아보기·자기 평가, 규칙 판정(고르기·수학 동치), 판정·되묻기 저장, 학습 기록 조회 API(대시보드·에이전트 도구·리포트 소재) | learning_db (미션 장면 이미지는 웹 정적 파일과 함께 CloudFront→S3로 서빙, learning은 S3를 쓰지 않음) |
| ai-service | FastAPI | 서술 근거 구절 추출(LLM) + 원문 대조 판정(코드), 되묻기 생성·정답/금지어 유출 검사, LangGraph 분석 에이전트, 리포트 서술·저녁 질문 생성, 리포트 설명 생성 요청·검사(설명 sLLM 호출, #477), 프롬프트 버전 | 없음 (상태 없음) |
| scoring-service | FastAPI | M2 항목 점수(klue/roberta, 국어 우선), M1 수학 풀이 점검(후순위, 활성 범위만) 추론, CPU 추론, 관리자 모델 파일 사전 검사(#368), Pod별 모델 로딩 상태 보고(#370) | 없음 (S3 가중치 읽기) |
| report-service | FastAPI | 주간·일일 리포트 기간·포함 기록 확정, 수치·전후 변화 코드 계산, 숫자·인용 대조, 렌더링(HTML/PDF/Markdown)·저장 | report_db, S3 |

- 언어 분담 근거: 트랜잭션·권한·버전 관리·Outbox·스케줄·결제 = Spring 생태계(Spring AMQP, Flyway, ShedLock) 성숙 / LLM·모델 추론·렌더링 = Python 생태계
- scoring 분리 근거: PyTorch 이미지·메모리 요구가 ai-service와 달라 배포·확장 단위 분리, 모델 미활성 시 ai-service 영향 없음
- 설명 sLLM 서버(FN-RPT-09, #476): 업무 서비스가 아니라 ai만 호출하는 OpenAI 호환 내부 추론 서버(llama.cpp 등). 상태·DB 없음, S3의 승인된 양자화 모델을 CPU로 추론하며 평소 0대이고 주간 리포트 생성 시간대만 켬(4.4). 학생 글은 클러스터 밖으로 나가지 않음
- 다른 서비스 DB 직접 접근 금지, API 또는 이벤트로만 연동 (참고 레포 원칙 동일)
- DB 권한으로 강제(#230): 인스턴스 1개(로컬 PostgreSQL·운영 RDS)에 DB별 migrate(DDL)·app(DML) 계정을 두고 각 DB의 PUBLIC CONNECT 회수 → 다른 서비스 DB 접속 불가. 로컬·운영 모두 `charts/platform-data/files/postgres/rds-bootstrap.sql`로 생성, 관리자 계정은 초기화 전용 ([결정](../report/db-dev-guide.md#8-서비스별-db-계정-230))
- 권한 기준: 학부모-자녀 연결은 core만 소유. core가 요청마다 권한 확인 후 내부 호출에 사용자 컨텍스트·허용 학생 범위 전달 (2.3)


#### 1.1.1 2026-11-06 결정 추가 책임

커뮤니티·포인트·꾸미기·주간 테마·일일 리포트([기능명세 1.4](functional-spec.md#14-확정-정책) P20~P25). 서비스 수·경계와 1.3 통신 원칙은 그대로 둔다. API는 [API 명세](api-spec.md) 2.9~2.11, 저장은 [ERD](erd.md) 3.6·4.4·5.2.

| 서비스 | 추가 책임 | 기능 패키지 |
|---|---|---|
| core-service | 커뮤니티 공개 설정·보호자 선택 동의·공유물 신고 연결, 작성자 별명·꾸미기 표시 변환, 포인트 규칙·원장·잔액, 테마·캐릭터·아이템 해금·착용, 꾸미기 아이템 관리, 무료 하루 미션 1개 집계, 일일 리포트 일정(매일 자정, 다음 날 00:00)·작업, 리포트 고정 대화 생성 | `community`(설정·learning 프록시·신고 연결), `reward`(포인트·해금·아이템). 무료 미션 한도는 기존 `usage`(`MissionUsageService`), 일일 일정은 기존 `report`, 리포트 고정 대화는 기존 `conversation`, 동의 문서 종류는 기존 `consent` |
| learning-service | 주간 테마·요일별 미션 배치·게시 검사, 시도 `context`(당일·되돌아보기·추가 문제) 검사, 되돌아보기 열람 기록·완주 판정 소재, 커뮤니티 공유물·반응·열람 검사(같은 미션 마무리 여부)·숨김 상태 | `theme`, `community` |
| report-service | 일일 리포트(템플릿, LLM 미호출) 기간 확정·계산·대조·렌더링, 주간 리포트 테마 요약 | 기존 리포트 생성 흐름에 기간 종류 분기 |
| ai-service | 리포트 고정 대화의 범위(그날)와 core가 넣어 주는 리포트 요약 입력 처리(report 직접 호출 없음). 일일 리포트 서술은 없음 | 기존 분석 에이전트 |
| scoring-service | 변경 없음 | - |

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

- core→scoring 동기 HTTP는 관리자 모델 파일 사전 검사 중계 `POST /internal/models/preflight`(#368, 20초·재시도 없음)뿐이다. 판정 교차 확인(M2·M1)은 ai→scoring이다
- `model.*`는 `model.version.activated`(core→ai·scoring)와 `model.loading.reported`(scoring→core, #370) 두 메시지다(1.4)

### 1.3 통신 원칙
| 구간 | 방식 | 근거 |
|---|---|---|
| 답변 제출 (Web→core→learning) | 동기 HTTP, `Idempotency-Key` | 저장 성공을 즉시 확정, 중복 제출 1회 반영 |
| 피드백: 판정·되묻기 (Web→core→learning→ai→scoring) | 동기 HTTP + core에서 SSE 전달 | 학생 실시간 대기. 답변 저장과 분리된 별도 요청이라 AI 실패 시 저장 결과 보존, 같은 요청 재호출로 재시도 |
| 분석 대화 (Web→core→ai, 도구→learning) | 동기 HTTP + SSE 스트리밍 | 학부모 실시간 대기 |
| 대시보드·리포트 조회 (Web→core→learning/report) | 동기 HTTP | 단순 조회 |
| 주간·일일 리포트 생성 | **명령** → `cmd.direct` 작업 큐 | 일괄 처리, 재시도, 워커 단독 확장 |
| 상태 변화 전파 | **이벤트** → `events.topic` | 생산자가 소비자를 모름, 소비자 추가 시 생산자 무변경 |

- 동기 호출 장애 대응: 타임아웃 + 재시도 제한 + 서킷 브레이커(Spring Resilience4j / Python httpx 타임아웃·재시도). 값(P12): LLM 1회 15초·재시도 1회(1초 대기), learning→ai 판정·되묻기 각 35초(예외: 미션 초안은 주기 작업이라 ai LLM 60초 1회·마감 63초, learning→ai 70초, #353), core→learning 피드백 80초, 분석 대화 core→ai 첫 응답 20초·전체 120초, 서킷 브레이커 최근 20건 중 실패 50% 이상 시 30초 차단, 리포트 작업 재시도 3회(1·5·15분) 후 DLQ. 실패 시 "처리 실패"로 기록·SSE 전달, 판정 보류·기록 없음과 구분
  - 서킷 브레이커 적용 구간은 core→learning(`learning-json`·`learning-feedback`), learning→ai, core→ai(`ai-analysis`), core→report(`report-query`·`report-recovery`), core→토스 조회(`toss-lookup`·`toss-transactions`)다(#167). 각 core 인스턴스 안에서 구간별 상태를 공유하며 구간 사이는 독립이다. 최근/최소 20건·실패율 50%·30초 차단·half-open 1건을 사용한다. HTTP 4xx는 실패로 세지 않고 전송 오류·시간 초과·5xx는 실패로 센다. report 2xx 복구 결과 FAILED/BUSY는 정상 통신 결과다. 토스 쓰기(승인·청구·취소·빌링키 발급)는 예외로 기존 타임아웃만 유지한다. 준비 상태 저장 후 전송을 차단하면 PG 거래가 없어 조회만으로 복구할 수 없으므로, 전송 전 차단 상태/복구 설계를 별도로 확정하기 전에는 적용하지 않는다. 서비스 간 재시도는 추가하지 않는다.
- #305 learning→ai 판정·되묻기는 서킷 `ai` 하나를 함께 쓰므로, 그 뒤 ai→scoring 실패가 이 서킷으로 번지지 않게 ai에서 끊는다. ai→scoring(M2·M1)은 교차 확인 플래그(`M2_CROSS_CHECK_ENABLED`·`M1_CHECK_ENABLED`, 기본 꺼짐)가 켜진 경우에만 부르고, scoring 장애·시간 초과·5xx·4xx(입력 한도 초과 등)·계약 밖 응답은 503으로 바꾸지 않는다. ai는 교차 확인을 생략한 LLM 판정을 200으로 돌려주고 `modelScores.skipped`(`SCORING_UNAVAILABLE`·`SCORING_REJECTED`)에 사유를 남긴다(api-spec 4.2.2). 따라서 scoring 장애는 learning `ai` 서킷의 실패로 집계되지 않고 scoring과 무관한 판정·되묻기를 막지 않는다. 대신 교차 확인 없이 확정된 판정은 다시 판정하지 않는다. ai→scoring에는 서킷·재시도를 따로 두지 않는다(요청마다 남은 판정 시간 안의 timeout만).
- #280 core→ai 리포트 설정 제안(`AiClient.reportTemplate`, 25초)은 분석 스트림과 분리한 작은 서킷 `ai-report-template`(최근/최소 10건·실패율 50%·30초 차단·half-open 1건)을 쓴다. 설정 제안 실패가 분석 대화 스트림을 차단하지 않게 하기 위해서다. HTTP 4xx는 성공으로, 전송 오류·시간 초과·5xx(ai `AI_UNAVAILABLE`·`AI_PROMPT_VERSION_UNAVAILABLE` 포함)·빈 본문은 실패로 센다. OPEN은 기존 502 `AI_UNAVAILABLE`로 실패하며 이미 차감한 분석 사용량은 그대로 둔다. 재시도는 추가하지 않는다.
- #167 분석 서킷은 헤더/첫 이벤트가 아닌 스트림 종료 결과를 집계한다. 중간 EOF·잘못된 스트림·시간 초과·error 이벤트는 실패, 정상 done/clarification 및 기존 TEMPLATE 결과는 성공이다. 사용자 취소·core 권한/저장/전송 처리 오류는 AI 실패 집계에서 제외하고 half-open 허가를 반환한다. OPEN은 기존 AI_UNAVAILABLE로 실패하며, 이미 접수한 분석 시도의 한도/사용 이력 차감은 보존한다. HTTP/1.1과 기존 body 종료·timer 취소를 유지한다.
- 타임아웃 예산: 바깥 호출 타임아웃 > 안쪽 호출 합계 (예: core→learning > learning→ai judgments + followups). 전체 상한은 CloudFront·ALB 타임아웃(4.3) 이내. 이를 넘는 SSE(피드백 80초, 분석 대화 120초)는 15초 heartbeat가 유휴 타이머를 갱신하는 것을 전제로 함
- 재시도 계층: ai의 LLM 호출에서만 재시도, core·learning·report의 서비스 간 호출은 재시도 없음 (계층별 재시도 시 호출 수 곱셈 증폭)
- #38 일반 core→learning JSON 프록시는 연결 2초·응답 30초를 사용한다(피드백의 80초 예산은 #39). Resilience4j count window 20·최소 20건·실패율 50%·차단 30초·half-open 1건으로 복구를 확인한다. 전송 오류·5xx를 실패로 집계하고 4xx는 정상 HTTP 결과로 센다.
- SSE heartbeat: 모든 SSE는 15초마다 주석 줄(`: ping`) 전송. 피드백은 learning 동기 응답 대기 중 전송할 데이터가 없어 필수
- SSE 연결 종료
  - 피드백: 클라이언트가 끊겨도 learning 처리는 끝까지 진행·저장, 재요청 시 저장 결과 반환
  - 분석 대화: 클라이언트가 끊기면 core가 ai 스트림 취소, 메시지 `FAILED`(재시도 가능) 저장
  - 알림: 재연결 시 `/notifications`로 누락분 재조회
- core 피드백: `FeedbackService` → `LearningProxyService` → `LearningClient`(read timeout 80초, 일반 JSON 경로의 30초·멱등성은 유지). `_common/web/SseEmitters`는 연결 시간(피드백 90초 `open`, 알림 5분 `subscribe`, 분석 대화 125초 `open`·120초 취소 hook, #41)·15초 heartbeat·종료만 소유하고 판정 상태는 저장하지 않음. 요청 컨텍스트를 작업 virtual thread에 설정·정리. 연결 종료는 heartbeat만 취소하며 learning 작업은 취소하지 않음
- 피드백의 별도 서킷 이름은 `learning-feedback`이다. 전송 오류·시간 초과·계약된 Problem Details가 아닌 5xx를 실패로 센다. Content-Type `application/problem+json`의 JSON 객체에 비어 있지 않은 문자열 code가 있으면 정상 HTTP 전달로 집계하되 업무 결과는 error로 유지한다. 따라서 learning이 보낸 AI_UNAVAILABLE·INTERNAL_ERROR를 core 서킷이 다시 차단하지 않고 같은 답변 재요청은 learning으로 전달할 수 있다. AI 서킷은 learning이 소유하며 일반 `learning-json`의 기존 5xx 집계는 바꾸지 않는다.
- JDK 21 SSE 전송·종료의 상호 배제는 `ReentrantLock`을 사용한다. 블로킹 소켓 전송을 synchronized monitor 안에서 실행해 virtual thread의 carrier가 고정되지 않게 한다.

### 1.3.1 분석 대화 수명 (#41)

분석 전용 SseEmitters.open의 연결 시간·취소 hook을 사용한다. 피드백과 알림 수명은 유지한다. AI HTTP body는 취소 시 닫는다. 계정→학생→대화 잠금과 시도 fencing으로 삭제/중복 재시도를 직렬화한다. 상세 계약은 [#41 보고서](../report/core-gateway.md#5-분석-대화-계약-41167).

### 1.4 메시지 목록

| 메시지 | 종류 | 생산 | 소비 | 소비 측 처리 |
|---|---|---|---|---|
| `report.generate` | 명령 | core (정기 스케줄·재생성·관리자 재처리) | report | 기간 확정 → learning 기록 조회 → 계산 → ai 서술(주간만) → 대조 → 렌더링·저장 |
| `report.started` | 이벤트 | report | core | 작업 상태 처리 중 |
| `report.completed` / `report.failed` | 이벤트 | report | core | 작업 상태 갱신, 학부모 알림 |
| `llm.usage.recorded` | 이벤트 | ai, scoring | core | 호출 종류별 토큰·지연·실패·버전 집계 (학생 ID·원문 미포함) |
| `model.version.activated` | 이벤트 | core | ai, scoring (Pod별 수신) | 모든 레플리카가 승인 scope의 활성 모델·프롬프트 버전 교체 (기동 시 core 내부 API로 현재 버전 조회) |
| `model.loading.reported` | 이벤트 | scoring (Pod마다 기동·상태 변화 즉시, 이후 30초 주기로 전체 상태 재보고) | core | Pod·인스턴스별 최신 로딩 상태를 `model_loading_report`에 저장(같은 인스턴스는 더 큰 `sequence`만 반영, 1일 넘은 이벤트 무시), 관리자 `GET /admin/model-loading` 조회 (#370) |
| `student.deleted` | 이벤트 | core | learning, report | 삭제 확정 학생의 학습 기록·리포트 물리 삭제, 처리 후 core 내부 API로 완료 보고. 페이로드에 `deletionRequestId`·`scope` 포함 (P09) |

- 위 메시지는 모두 core 감사 큐 `core.event.audit`에도 바인딩되어 `event_log`에 기록된다(#208). 바인딩은 routing key별로 두며 `#` 와일드카드는 쓰지 않는다(report 발행자의 unroutable 감지 유지). 메시지를 추가하면 감사 바인딩도 함께 추가하고 `RabbitDefinitionsTest`가 누락을 검사한다.
- P24(#390·#391): `report.generate` 페이로드에 `periodType`(`DAILY`·`WEEKLY`, 생략 시 `WEEKLY`) 추가, 새 메시지·큐 없음. 일일은 ai를 호출하지 않음. 감사 바인딩(#208) 변경 없음

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
   - LangGraph 흐름: `classify → clarify_scope → plan → tool(learning 조회, 실행마다 허용 범위 검사) → compute(코드 계산) → answer → verify(숫자·인용 대조)`. 구현 노드는 `classify`(범위 확인 포함) → `retrieve`(도구 선택·조회) → `compute` → `answer` → `check`(대조), 실패 분기 `fallback`·`insufficient`·`unsupported` ([ai 보고서 2장](../report/ai.md#2-분석-대화-에이전트-langgraph))
   - core가 질문·답변·참조 기록 저장
5. **자동 리포트**
   - core 스케줄러(ShedLock)가 자녀별 report_job + Outbox → `report.generate`
   - report가 learning 기록 조회 → 코드 계산 → ai 서술·저녁 질문 → 숫자·인용 대조 → 렌더링·S3 저장
   - 주간 리포트의 프리미엄·원문 공개 자녀는 서술 뒤 M2 점수가 있는 대표 답변 최대 3개를 ai에 설명 요청(ai → 설명 sLLM 서버, 검사 통과분만 `EXPLANATION` 항목). 실패·시간 초과·모델 미활성은 설명 없이 진행 (FN-RPT-09, P16, #479)
   - `report.completed` → core 알림

2026-11-06 결정(6~9 구현):

6. **주간 테마**: core가 학생 학년으로 학년군을 정해 learning에 이번 주 테마 조회 → learning이 KST 요일로 문제 상태 계산. 시도 시작 시 learning이 `context` 검사, core가 무료 한도(`THEME_DAY`·`EXTRA` 신규 `201`, 합쳐 하루 1개) 집계(#387)
7. **학습 완료 후**: 돌아보기 저장 성공 → core가 포인트 적립(미션당 최초 1회) → 커뮤니티 공개가 켜져 있고 그 미션 공유물이 없으면 learning에 공유 요청(학생·미션당 1개) → 공유 성공 시 포인트 적립. 공유 요청(#388)과 두 포인트 적립 연결(#389) 구현
8. **일일 리포트**: core 스케줄러(ShedLock)가 매일 자정(다음 날 00:00 KST) 보호자가 연결된 자녀별 `report_job(period_type = DAILY)` + Outbox → `report.generate` → report가 learning 기록 조회 → 코드 계산·템플릿 구성 → 인용 대조 → 렌더링·S3 저장(ai 호출 없음) → `report.completed` → core 일일 알림
9. **리포트 대화**: 학부모가 일일 리포트에서 대화 생성 → core가 리포트 소유·자녀 연결 확인 후 대화에 리포트 ID·판을 저장하고 범위를 그날로 고정 → 메시지마다 core가 report에서 그 판을 읽어 ai 요청에 넣음 → 이후는 4번 분석 대화 흐름 그대로

### 1.6 메시징 신뢰성 규칙
- **Outbox**: DB 상태 변경 + 발행이 함께 필요한 서비스(core, report)만 적용 (learning은 발행 없음, 멱등 소비만). 같은 트랜잭션에 outbox 행 저장 → 릴레이 스케줄러가 publisher confirm 받은 후 발행 시각 기록 (참고 레포 `*OutboxScheduler` 패턴). core 릴레이는 ShedLock 단일 실행, 발행·confirm 대기는 DB 트랜잭션 밖, 발행 시각만 짧은 트랜잭션으로 기록
- **core 발행 복구(#243)**: report #131과 같은 기준으로 subject별 선두만 1건씩 발행·confirm한다. 실패는 안전 오류 코드·횟수를 기록하고 1·5·15분 재시도 후 격리하며 다른 subject는 계속 처리한다. 브로커 연결 실패·confirm timeout은 그 주기를 중단한다. 격리 선두와 그 뒤 이벤트는 운영 SQL로 재처리할 때까지 대기한다. [정책·운영 SQL](../report/core-gateway.md#11-core-outbox-실패-격리-243)
- **report 발행 복구(#131)**: 학생별 선두만 발행한다. 실패한 학생은 1·5·15분 재시도 후 격리하고 다른 학생은 계속 처리한다. 격리된 선두와 그 뒤 이벤트는 운영 CLI로 원래 이벤트 id를 재처리할 때까지 대기한다. 소비 재시도 큐/DLQ와 별개로 Outbox DB에 실패·격리 상태를 저장한다. [정책·운영 명령](../report/report.md#11-outbox-실패-격리와-학생별-발행-순서-131)
- #389 구현: 포인트 적립은 core가 learning 응답을 동기 프록시하는 경로(돌아보기 저장 성공 = 학습 완료, 공유·반응 성공, 되돌아보기 열람)에서 core 자체 트랜잭션(`RewardService.earn`, `REQUIRES_NEW`)으로 원장에 기록한다(실패해도 프록시 응답은 그대로). learning은 계속 발행 없음(1.6 Outbox 원칙 유지). 프록시 응답 후 core 저장이 실패하면 사건 키(`student_id, event_type, source_key`)로 다음 같은 사건·조회 때 다시 적립할 수 있게 둔다(사건 키 멱등, 같은 사건 재요청·주간 테마 조회 때 보충)
- 공유물 생성(#388)도 돌아보기 저장 성공 직후 core → learning 내부 호출(학생·미션당 1개 멱등, 다시 풀기는 공유 안 함). 공개 설정 변경·동의 철회·이관 수락은 core → learning `community-visibility` 호출
- 학생 삭제는 기존 `student.deleted` 소비 범위에 테마 열람 기록(learning #385 구현)·공유물·반응(learning #386 구현) 추가, core는 포인트·해금·착용 정보를 함께 삭제(`mission_daily_usage`는 #387에서 삭제 확정 트랜잭션에 포함)
- **상태 없는 서비스(ai, scoring)**: 이벤트 발행은 처리 결과 반환 후 best-effort (사용량 집계용, scoring의 모델 로딩 상태 보고 #370 포함), 유실 시 Langfuse trace로 보정(Langfuse는 예정, 저장소 미구성)
- **멱등 소비**: 소비자별 `processed_event(event_id UK)` 테이블 또는 DB 상태 전이 조건(`QUEUED→RUNNING`)
- **이벤트 기록·보존(#208)**: core가 감사 큐로 모든 업무 메시지의 id·type·source·subject·봉투 시각·수신 시각을 `event_log`에 저장한다(payload 제외). 발행은 각 서비스 `outbox_event`, 소비는 `processed_event`·`llm_usage`·작업 상태와 `event_id`로 조인한다. ai·scoring은 DB 없이 유지하며, 브로커에 도달하지 못한 발행 실패는 `event_log`에 없고 서비스 로그로만 확인한다. `model.version.activated`의 Pod별 적용은 기록하지 않는다(readiness·snapshot 재조회로 보장). 발행 완료 outbox·processed_event·event_log는 90일 후 삭제하고 미발행·격리 행은 남긴다. [결정 근거](../report/core-gateway.md#9-rabbitmq-발행소비-기록-208)
- **재시도**: 소비 실패 시 지연 재시도 3회(1·5·15분, P12) 후 DLQ 이동. `report.generate` 확정값을 모든 큐에 동일 적용
- **명시적 관리자 재처리(#152/#47)**: 위 메시지 전송 재시도와 구분한다. core가 새 jobId·ADMIN_RETRY로 기존 명령을 발행하고 원작업 연결을 보관한다. report는 기존 생성·revision·Outbox를 재사용한다. 같은 jobId의 종료 상태 재전달은 ACK 후 종료하며, 새 관리자 HTTP API·큐·스키마를 report에 추가하지 않는다. core 관리자 접수(`POST /admin/jobs/{jobId}/retry`)는 #47에서 구현했다.
  - 큐마다 `<큐>.retry.1`(1분)·`.retry.2`(5분)·`.retry.3`(15분)을 `definitions.json`에 선언 (`x-message-ttl` = 지연, 만료 시 기본 exchange로 원래 큐 복귀)
  - 처리 실패: 소비자가 `x-retry-count` 헤더 +1 후 `<큐>.retry.<회차>`로 재발행하고 ACK. 3회 초과 시 `reject(requeue=false)` → `dlx` → `<큐>.dlq`
  - 횟수는 자체 헤더로 셈 (클라이언트 재발행 시 `x-death`가 승계되지 않음). 지연은 `definitions.json`, 최대 횟수는 서비스 설정(3)으로 단계 큐 개수와 일치
  - 메시지 변환 실패(형식 오류)는 재시도해도 복구되지 않으므로 재시도 없이 바로 reject → DLQ
  - core는 전역 수동 ACK(`acknowledge-mode: manual`, learning도 동일 설정, #128): 모든 `@RabbitListener`는 `RetryingConsumer.handle`로 처리. ACK 누락 시 메시지가 unacked로 남아 소비 정지
  - 큐 미존재 시 기동 실패 대신 경고 후 재확인(`missing-queues-fatal: false`), 큐 생성 시 소비 자동 시작
- **DLQ**: 큐마다 dead-letter exchange, 관리자 화면에서 현황 조회 (참고 레포 `QueueOperations*` 계승)
- **브로드캐스트 이벤트**: 모든 레플리카가 받아야 하는 이벤트(`model.version.activated`)는 Pod별 exclusive·auto-delete 큐를 서비스가 기동 시 선언·바인딩 (exchange는 `definitions.json`). 공유 큐는 경쟁 소비라 1개 Pod만 수신
  - 기동 순서: 큐 바인딩 → core 활성 버전 조회 (반대 순서면 그 사이 이벤트 유실)
  - #43 계약: 내부 조회와 이벤트는 같은 kind·name별 revision·적용 scopes를 제공한다. 소비자는 초기 조회 중 이벤트를 보존·조정하고 더 높은 revision만 적용하며 승인 scope 밖에는 적용하지 않는다. core는 Pod 공유 소비 큐를 추가하지 않는다. scoring 소비·readiness는 #86에서 구현하며 ai는 #68 범위다.
  - scoring #86: 큐 바인딩·소비 시작 후 snapshot을 조회한다. 조회·로딩 중 이벤트는 이름별 최신 revision을 보존하고 readiness 전에 조정한다. 재연결 때 새 exclusive 큐를 바인딩하고 snapshot을 다시 조회하여 연결 중단 중 변경도 복구한다.
  - scoring 교체·롤백은 #85와 동일하게 S3/MinIO에서 재다운로드 → 메모리 로딩 → 임시 파일 정리 방식이다. 성공 후 참조를 교체하며 로딩 실패 시 기존 모델과 새 승인 범위의 교집합만 사용한다. 정상 기동 후 교체 실패는 기존 모델을 유지하고 재시도한다. 최초 조회·로딩 실패 또는 재연결 조정 중에는 readiness false다.
  - ai #68: `PROMPT`의 `name`은 `judgment`·`followup`·`analysis`·`reportNarrative`·`reportTemplate`(#280 리포트 설정 제안)·`missionDraft`(#354 미션 초안) 6개, 각 승인 scope는 `ai/judgment`·`ai/followup`·`ai/analysis`·`ai/report-narrative`·`ai/report-template`·`ai/mission-draft`다. 해당 scope가 없는 항목은 적용하지 않는다. 각 버전의 실제 system/user 프롬프트 본문은 ai 이미지의 코드에 함께 보관한다. core에 활성 항목이 없으면 현재 내장 버전을 사용한다. 활성 버전 본문이 이미지에 없으면 다른 본문에 그 버전명을 붙이지 않고 해당 기능의 새 요청을 503으로 거부하며 readiness는 false다. 요청마다 선택한 본문과 버전을 고정해 응답·사용량에 같은 버전을 기록한다.
  - ai도 큐 바인딩·소비 시작 후 snapshot을 조회하고 그사이 이벤트를 revision으로 조정한다. 재연결마다 새 큐를 먼저 바인딩하고 snapshot으로 유실 구간을 복구한다. readiness는 이 백그라운드 상태만 읽으며 probe가 core를 호출하지 않는다.
  - core 조회 실패 시 프로세스 종료 없이 readiness false 유지·재시도 (core 장애가 ai·scoring 기동 실패로 번지지 않게)
- **이벤트 봉투**: CloudEvents 형식 `id, specversion, type, source, time, subject, dataschema, traceparent, data` → `contracts/events/*.schema.json`
- **스키마 버전**: 파일 `<message>.v<N>.schema.json`, `dataschema`에 버전 표기. 하위 호환 변경(선택 필드 추가)만 같은 버전, 그 외는 새 버전 병행 발행 후 소비자 전환
- **SSE 다중 레플리카**: 알림은 리포트 종료 전이 트랜잭션에서 저장 → AFTER_COMMIT에 `NotificationDispatchService`가 Redis 채널 `core:notifications:v1` 발행 후 `COMPLETED`·`FAILED` 기록(관리자 재처리도 같은 경로, 발행기 `NotificationRedisPublisher`는 Redis 발행만, #250) → 구독 레플리카가 SSE 전달(5분·15초 heartbeat). 유실은 `ready` 후 목록 재조회로 보완 (api-spec 2.7)

### 1.6.1 리포트 종료 유실 복구 (#132)

core report의 `ReportRecoveryScheduler`(ShedLock) → `ReportRecoveryService` → `ReportClient`가 상태를 대조한다. report generation의 router → `ReconciliationService` → 기존 `ReportRepository`/`JobLocks`를 재사용한다. HTTP 동안 core 트랜잭션은 없고 report는 session 잠금 아래 짧은 DB 트랜잭션만 사용한다. 새 production 의존성은 없다.

core의 생성은 guardianship `StudentAccessService`를 통해 ACTIVE 학생 행을 먼저 잠근 뒤 주 단위 잠금·작업 저장을 수행한다. lifecycle/복구 반영도 학생 → job 순서다. 삭제는 기존 parent → student 순서를 유지하며 `ReportLifecycleService.failForDeletion`을 호출해 같은 트랜잭션에서 미종료 작업과 실행 이력을 FAILED로 만든다. 상대 기능 repository 직접 접근 없이 service 경계로 연결한다. 삭제 종료와 reportId 없는 실패는 알림을 발행하지 않는다.

### 1.6.2 관리자 대화 재처리 실행 경계 (#47)

CONVERSATION은 DB의 conversation_job_retry를 core 작업자가 선점하고 기존 AnalysisStreamService의 공통 실행을 호출한다. 학부모 SSE와 같은 검증·근거 확인·저장을 사용하며 관리자에게 원문 이벤트를 전달하지 않는다. RabbitMQ 큐나 외부 실행 서비스를 추가하지 않는다. 요청·종료 감사는 BEFORE_COMMIT이며 외부 AI 호출은 DB 트랜잭션 밖이다. 사용량은 영속 요청 ID를 결제 사용 이력 source ID로 써서 실행 선점 트랜잭션 안에서 한 번만 차감한다(#225). 중단 실행은 세대를 확인해 실패로 종료하고 자동 AI 재실행하지 않는다.

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

- 공통 메시징 인프라 예외(#278): `_common/messaging`의 이벤트 감사 기록·보존 정리(core `EventAuditConsumer`·`EventRetentionCleanup`)는 `_common`이 소유한 메시징 테이블(`event_log`·`outbox_event`·`processed_event`)만 다루고 업무 판단이 없어 service 없이 같은 패키지의 `_common` repository를 직접 호출한다. 같은 패키지의 `OutboxRelay`·`ProcessedEventRepository` 멱등 소비와 같은 공통 인프라로 보며, `_common`에 service 계층을 새로 두지 않는다. 이 예외는 `_common/messaging` 안에만 적용한다. `_common`의 다른 주기 작업은 `_common/scheduler`에 두고 service를 호출한다(`IdempotencyCleanupScheduler` → `IdempotencyService.deleteExpired`, #314). 기능 패키지의 controller·consumer·scheduler는 항상 자기 기능 service만 호출한다(learning `record/scheduler/ProcessedEventCleanupScheduler` → `ProcessedEventCleanupService`, report `worker.py` → `deletion/service.py` `prune_event_records`)
- Domain 오류(Spring): domain은 HTTP 상태가 없는 `_common/exception`의 `DomainException(ErrorKind, code, title, detail)`만 던진다. `ErrorKind` → HTTP 상태 변환은 `_common/exception` 한 곳에서 하고(2.3), HTTP 상태를 직접 받는 `BusinessException`은 application·presentation에서만 쓴다. 예외의 상태·code를 읽는 곳은 두 예외를 함께 처리하는 공통 함수(`httpStatusOf`·`errorCodeOf`)를 쓴다 (#249)

### 2.2 의존 규칙
- `Presentation → Application → Infrastructure` 단방향, 계층 건너뛰기 금지 (controller → repository 직접 호출 금지)
- Domain은 모든 레이어가 참조 가능, Domain은 다른 레이어를 참조하지 않음
- 기능 간 호출은 상대 기능의 service로만 (다른 기능의 repository 직접 참조 금지)
- 기능 간 호출 예: 자녀 기록 존재 조회는 `GuardianshipService` → `LearningRecordService` → `LearningRecordClient` → `LearningClient`(학생 전용 `LearningProxyService` 권한과 분리, 서킷·타임아웃 공유, 최대 3명 병렬). 학생 학년·시연 여부는 `StudentLearningContextService`로 조회. 전체 구현 경로는 class-diagram 3장
- 여러 기능에 걸친 흐름은 주도 기능의 service가 상대 기능 service를 호출해 조합한다(core 현행: `LearningProxyService`·`GuardianTransferService`·`SupportService` 등). `facade`는 조합 대상이 많아 service 책임이 흐려질 때만 둔다(선례: learning `judgment/facade/FeedbackFacade`, 참고 레포 `applicationpreparation/facade` 패턴). core는 facade 없이 service 조합이 기준이며 실제 구조에 맞춰 문구를 고쳤다(#422)
- 공통 코드: Spring `_common/`, Python `app/` 루트의 `config.py`·`errors.py`·`security.py`·`messaging/`·`clients/base.py`
  - `_common`은 기능 패키지를 참조하지 않는다. 기능에 의존하는 공통 처리는 그 기능에 둔다(예: `PublicAuthFilter` → account, #251)
  - 여러 기능 client가 같은 하위 서비스 연결을 쓰면 전송은 `_common/client`에 둔다(core `LearningClient`: learning 내부 API, 서킷·타임아웃 공유). 기능별 요청·응답 해석은 각 기능 `client`(learning `LearningRecordClient`, community `CommunityClient`, support `LearningSupportClient`)가 맡고, 다른 기능의 client를 참조하지 않는다(#422)
  - 여러 기능 controller가 쓰는 기능 타입 없는 요청 검사는 `_common/web`(예: 관리자 목록 페이지 범위 `operationPage`, #422)
  - 응답 DTO(Spring): 여러 기능 응답이 같은 OpenAPI component를 공유하면 `_common/web`(예: learning `MissionResponse`·`MissionListItemResponse`·`AnswerItem`), 스키마가 다르면 기능별 controller DTO. `_common/web` DTO는 기능 타입 없이 열거값은 이름 문자열, 값 객체는 같은 모양의 DTO, 기능 타입이 필요한 칸은 타입 인자로 두고, domain → DTO 변환은 쓰는 기능의 controller에 둔다(데이터 표현이라 매핑 중복 허용, 업무 로직은 service 재사용) (#251)
- DB 트랜잭션은 Application 레이어에서만 시작, 트랜잭션 안에서 외부 HTTP·AMQP 호출 금지
- 멱등성: `_common/web/IdempotencyService`가 `idempotency_record`와 PostgreSQL 세션 잠금을 관리. HTTP 동안 auto-commit 연결 1개만 보유하고 트랜잭션·행 잠금은 보유하지 않음 (api-spec 1.4)
- 서비스 간 내부 호출: 내부 토큰 헤더 필터(참고 레포 `CatalogInternalAuthFilter` 패턴) + NetworkPolicy

### 2.3 공통 규칙

- #119 내부 별명 조회는 `guardianship/controller/InternalStudentProfileController` → `guardianship/service/InternalStudentProfileService` → 기존 `ChildManagementRepository.profile` 순서다. `InternalAuthFilter`가 토큰·요청 컨텍스트를 관리하고 서비스가 SYSTEM·학생 scope를 검사한다. 응답 전용 DTO는 UUID·별명만 제공하며 ACTIVE만 조회한다. #56 기본 report-worker의 `CoreClient.lookup`·`NamedGenerator`가 조회 결과를 렌더링에 전달하고 최종 AI 요청에서 별명을 가린다([#119](../report/core-gateway.md#8-리포트용-학생-별명-내부-조회-119), [#56 검증](../report/report.md#10-기본-worker-연결-56130)).
- 오류 응답: 전 서비스 공통 형식(RFC 9457 Problem Details), 예외 → 응답 변환은 Presentation(Spring `_common/exception`, FastAPI exception handler)
- 사용자 컨텍스트 전파: JWT 검증은 core만, 내부 호출은 내부 토큰 + `X-User-Id`·`X-User-Role`·`X-Student-Scope`(허용 학생 ID 목록) 헤더, 이벤트는 봉투 `subject`·`data`에 포함
  - #135 report 조회용 HTTP·S3 연결은 앱 lifespan에서 생성·정리한다. HTTP 연결을 재사용하되 사용자 헤더를 클라이언트 기본값으로 저장하지 않고 요청 훅의 ContextVar에서 읽는다.
  - 중간 서비스(ai)는 받은 컨텍스트 헤더를 하위 호출(learning)에 그대로 전달
  - 사용자 요청 없는 호출(report-worker 등 이벤트 소비): `X-User-Role: SYSTEM`, `X-Student-Scope` = 이벤트 `subject` 학생
- 스레드 모델
  - Spring core: JDK 21 virtual threads 사용 (LLM 대기·SSE 연결). learning: JDK 21에서는 Tomcat의 제한된 플랫폼 스레드 풀을 사용한다. Kotlin reflection/Jackson의 초기 직렬화 잠금 대기로 모든 virtual carrier가 고정되는 콜드 스타트 무응답이 재현됐기 때문이다. core 설정·공개 API·DB 계약은 유지하며, carrier 수 증가나 순차 예열을 해결책으로 삼지 않는다. 근거·재현·재검증은 [learning 콜드 스타트](../report/learning.md#19-실행-모델-가상-스레드-비활성-201).
  - FastAPI: 외부 호출은 async httpx. scoring CPU 추론은 동기 함수(스레드풀)로 실행해 이벤트 루프 차단 방지
- 범위 검사: learning은 조회 대상 학생이 `X-Student-Scope`에 없으면 403. ai 에이전트 도구도 실행 전 같은 검사 (FN-AGT-02)
- 대화 상태: ai-service는 상태 없음, core가 요청마다 대화 이력·허용 범위 전달
- 버전 연결: 판정·되묻기·분석·리포트 결과에 미션·기준표·모델·프롬프트 버전 저장 (NFR-DAT-02)
- 개인정보: LLM 요청에 학생 이름·식별정보 미포함, 운영 로그에 학생 원문·비밀 키·결제 정보 미기록 (NFR-SEC-03, 05)
- 테스트: Domain 단위 테스트, Application은 Infrastructure 대역, Repository는 Testcontainers(PostgreSQL), core 메시징 통합은 Testcontainers(PostgreSQL·RabbitMQ·Redis), 메시지는 `contracts/events` 스키마 계약 테스트
  - 테스트 베이스(`PostgresRepositoryTest`·`IntegrationTestSupport`)는 [DB 개발 가이드](../report/db-dev-guide.md) 5장

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
│  ├─ client/                    # LearningClient·LearningHttpProperties: learning 내부 API 공용 전송·서킷 (#422)
│  ├─ config/
│  ├─ exception/
│  ├─ security/
│  ├─ messaging/                 # 이벤트 봉투, OutboxRelay, 멱등 소비, 이벤트 감사 기록·보존 정리(EventAuditConsumer·EventRetentionCleanup, #208, repository 직접 호출은 2.1 공통 인프라 예외 #278)
│  ├─ json/                      # JsonObject: domain이 드는 jsonb 객체 값 (#168)
│  ├─ persistence/               # MyBatis 설정·PostgreSQL 타입 핸들러
│  ├─ scheduler/                 # IdempotencyCleanupScheduler: 만료 멱등 키 정리 주기 실행 (#314)
│  └─ web/                       # IdempotencyService, SseEmitters, 관리자 목록 페이지 범위 검사 PageQuery (core만)
│     └─ repository/             # IdempotencyRepository
├─ account/                      # Google 로그인·세션·탈퇴
│  ├─ controller/                # PublicAuthFilter(공개 API 인증, #251) 포함
│  ├─ service/                   # GuardianPasswordService: 학생 화면 → 학부모 복귀용 보호자 비밀번호 (V24)
│  │  └─ dto/
│  ├─ domain/
│  ├─ repository/
│  ├─ config/                    # AuthProperties·StudentDeviceProperties
│  └─ client/
│     └─ GoogleOAuthClient.kt
├─ consent/
│  ├─ controller/
│  ├─ service/
│  ├─ domain/
│  └─ repository/
├─ guardianship/                 # 자녀 등록·연결·권한 확인, 삭제 요청 → student.deleted, 학부모 간 자녀 이관(#289)
│  ├─ controller/                # GuardianTransferController: 받는 학부모 확인·이관 요청·수락·거절·취소
│  ├─ service/                   # GuardianTransferService(이관 실행), GuardianTransferAccessService(대기 중 탈퇴·삭제 차단)
│  │  └─ dto/
│  ├─ domain/
│  └─ repository/
├─ learning/                     # learning 프록시 (미션·시도·대시보드)
│  ├─ controller/                # LearningController, FeedbackController(SSE)
│  ├─ service/                   # LearningProxyService, FeedbackService, LearningRecordService
│  ├─ config/                    # FeedbackConfiguration (피드백 전용 클라이언트·서킷)
│  └─ client/
│     └─ LearningRecordClient.kt # 전송은 _common/client/LearningClient
├─ conversation/                 # 분석 대화, 예시 질문
│  ├─ controller/                # SSE
│  ├─ scheduler/                 # ConversationRetryWorker: 관리자 재처리 대기 요청 DB 선점·실행 (#47)
│  ├─ service/                   # ConversationTransferService: 이관 시 진행 중 분석 확인·대화 이전, 탈퇴 시 남은 대화 삭제 (#289)
│  ├─ domain/
│  ├─ repository/
│  └─ client/
│     └─ AiClient.kt
├─ report/
│  ├─ controller/
│  ├─ consumer/                  # report.started·completed·failed
│  ├─ scheduler/                 # 주간·일일 생성·종료 유실 복구 (ShedLock)
│  ├─ service/
│  ├─ domain/
│  ├─ repository/
│  ├─ messaging/                 # report.generate 발행
│  └─ client/
│     └─ ReportClient.kt
├─ notification/
│  ├─ controller/                # SSE
│  ├─ consumer/                  # Redis 구독(다른 레플리카 알림 수신, #168)
│  ├─ config/                    # Redis 구독 연결·채널 이름
│  ├─ service/                   # NotificationDispatchService: 커밋 후 발행·결과 기록 (#250)
│  ├─ domain/
│  ├─ repository/
│  └─ messaging/                 # Redis 발행만 (#250)
├─ support/                      # 신고·문의·공지·도움말·정정
│  ├─ controller/
│  ├─ service/
│  ├─ domain/
│  ├─ repository/
│  └─ client/
│     └─ LearningSupportClient.kt  # 대상 확인·원문·판정 정정
├─ payment/
│  ├─ controller/
│  ├─ service/
│  ├─ domain/
│  ├─ repository/
│  ├─ client/
│  │  ├─ TossClient.kt
│  │  └─ PremiumUsageClient.kt   # learning 프리미엄 사용 증빙 조회
│  └─ scheduler/                 # 정기 청구
├─ usage/                        # LLM 사용량 집계, 무료 미션 하루 한도(#387 `MissionUsageService`, `mission_daily_usage`)
│  ├─ controller/                # AiUsageController: 관리자 AI 사용량 조회 (#422)
│  ├─ consumer/
│  ├─ service/
│  ├─ domain/                    # LlmUsageRecorded·UsageSummary
│  └─ repository/
├─ community/                    # (P20, #388) 커뮤니티 공개 설정·learning 프록시·작성자 표시 변환·신고 연결
│  ├─ controller/
│  ├─ service/
│  ├─ domain/
│  ├─ repository/
│  └─ client/
├─ reward/                       # (P21·P22, #389) 포인트 규칙·원장·잔액, 해금·착용, 꾸미기 아이템
│  ├─ controller/
│  ├─ service/
│  ├─ domain/
│  └─ repository/
└─ admin/                        # 운영 현황·재처리·모델 버전 레지스트리·감사 이력·큐/DLQ
   ├─ controller/
   ├─ consumer/                  # 재처리 감사 리스너(BEFORE_COMMIT 내부 이벤트, AMQP 아님), ModelLoadingConsumer(model.loading.reported AMQP 소비, 큐 core.model.loading.reported, #370)
   ├─ service/
   ├─ domain/
   ├─ repository/
   └─ client/
      └─ QueueManagementClient.kt  # RabbitMQ 관리 API 큐 현황
```

Spring (learning)
```
backend/learning-service/src/main/kotlin/com/sagomungchi/learning/
├─ _common/
│  ├─ config/
│  ├─ exception/
│  ├─ security/
│  ├─ messaging/                 # 멱등 소비 (발행 없음)
│  ├─ persistence/               # MyBatis 설정·PostgreSQL 타입 핸들러
│  └─ web/                       # 공유 응답 DTO: MissionResponse·MissionListItemResponse·AnswerItem (#251)
├─ mission/                      # 미션·기준표·예시 답·생각 열기 질문 버전, 관리자 작성·검토·공개, 성취기준·미션 초안(#353)
│  ├─ controller/
│  ├─ service/
│  ├─ domain/
│  ├─ repository/
│  ├─ client/
│  │  └─ MissionDraftAiClient.kt # ai 미션 초안 요청 POST /internal/mission-drafts
│  └─ scheduler/
│     └─ MissionDraftScheduler.kt # 미션 초안 주기 생성 (처리는 MissionDraftService)
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
│  ├─ scheduler/                 # StuckJudgmentScheduler: 고착 RUNNING 판정 1분 주기 탐지 (#241)
│  ├─ service/
│  ├─ domain/
│  ├─ repository/
│  ├─ rule/                      # 고르기·수학 동치
│  ├─ client/
│  │  ├─ AiClient.kt
│  │  ├─ AiModels.kt
│  │  └─ PaymentUsageClient.kt   # core 프리미엄 사용 예약·확정 (#48)
│  └─ facade/
│     └─ FeedbackFacade.kt
├─ theme/                        # (P23, #385) 주간 테마·요일별 미션·게시 검사, 되돌아보기 열람·완주·주간 요약
│  ├─ controller/
│  ├─ service/
│  ├─ domain/
│  └─ repository/
├─ community/                    # (P20, #386) 공유물·반응·열람 검사·숨김 상태
│  ├─ controller/
│  ├─ service/
│  ├─ domain/
│  └─ repository/
└─ record/                       # 대시보드·에이전트 도구·리포트용 조회 API, student.deleted 소비(#128)
   ├─ controller/                # 기록 조회·존재 확인·결제 사용 증빙
   ├─ consumer/                  # StudentDeletedConsumer
   ├─ scheduler/                 # ProcessedEventCleanupScheduler: processed_event 보존 정리 주기 실행 (#208, #278)
   ├─ service/                   # RecordService, StudentDeletionService, ProcessedEventCleanupService 등
   ├─ domain/
   ├─ repository/
   └─ client/
      └─ CoreClient.kt           # 삭제 완료 보고
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
│  ├─ judgment/
│  │  ├─ router.py
│  │  ├─ service.py
│  │  ├─ models.py               # 요청·응답 스키마
│  │  ├─ extractor.py            # LLM 근거 추출
│  │  ├─ verifier.py             # 코드 원문 대조
│  │  ├─ cross_check.py          # M2·M1 교차 확인 요청 본문·불일치 판단 (#69)
│  │  └─ prompts.py
│  ├─ followup/
│  │  ├─ router.py
│  │  ├─ service.py
│  │  ├─ models.py               # 요청·응답 스키마
│  │  ├─ leak_guard.py
│  │  └─ prompts.py
│  ├─ analysis_agent/
│  │  ├─ router.py               # SSE 형식 변환만
│  │  ├─ service.py              # AnalysisService: 범위·기한·프롬프트 선택, 그래프 실행·최종 상태 → 이벤트, 템플릿 제안 역할 확인 (#253)
│  │  ├─ models.py
│  │  ├─ graph.py
│  │  ├─ nodes/                  # understand·retrieve·respond·events
│  │  ├─ state.py                # 그래프 상태 (models·calculators만 참조)
│  │  ├─ context.py              # AgentContext: LLM·기록 도구·기한·프롬프트
│  │  ├─ tools.py
│  │  ├─ calculators.py
│  │  ├─ verification.py         # 답변 숫자·인용 ↔ 조회·계산 결과 대조
│  │  ├─ templates.py            # 규칙 응답
│  │  ├─ template_settings.py    # 리포트 표시 설정 제안 (#209)
│  │  ├─ template_prompts.py     # 설정 제안 프롬프트 본문·버전 (#280 reportTemplate)
│  │  └─ prompts.py
│  ├─ report_narrative/
│  │  ├─ router.py
│  │  ├─ service.py
│  │  ├─ models.py               # 요청·응답 스키마
│  │  └─ prompts.py
│  ├─ mission_draft/             # 미션 초안 1회 생성·검사 (#354)
│  │  ├─ router.py               # POST /internal/mission-drafts
│  │  ├─ service.py
│  │  ├─ models.py
│  │  ├─ checks.py               # REQUIRED·QUESTION_LENGTH·LEAK 검사
│  │  └─ prompts.py              # missionDraft 프롬프트 본문·버전
│  ├─ prompt_versions/           # 활성 프롬프트 버전 (#68, #254 분리)
│  │  ├─ router.py               # GET /internal/versions
│  │  ├─ service.py              # PromptSync: core snapshot·대기 이벤트 조정
│  │  ├─ registry.py             # ActiveVersions: 이미지 본문·이름별 revision 상태
│  │  └─ models.py               # 활성 버전 계약·PromptChoice
│  ├─ clients/
│  │  ├─ base.py                 # 내부 토큰·컨텍스트 헤더 전달 httpx 클라이언트
│  │  ├─ learning_client.py
│  │  ├─ scoring_client.py       # ScoringClient: M2 점수·M1 점검 호출 (#69)
│  │  └─ core_client.py          # 기동·재연결 시 core 활성 버전 조회 (#68)
│  ├─ llm/                       # LLM 클라이언트 래퍼 (제공자 교체 지점)
│  │  ├─ base.py                 # 공통 인터페이스·재시도·타임아웃·사용량 기록
│  │  └─ providers.py            # Claude·OpenAI·OpenAI 호환 sLLM, LLM_PROVIDER로 선택
│  ├─ messaging/
│  │  ├─ envelope.py
│  │  ├─ connection.py
│  │  ├─ publisher.py            # llm.usage.recorded
│  │  ├─ usage_recorder.py       # LlmClient 사용량 → 백그라운드 발행
│  │  └─ consumer.py             # model.version.activated, Pod별 exclusive 큐 (#68), 검증·ACK 후 PromptSync.offer
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
│  │  ├─ service.py
│  │  ├─ models.py
│  │  ├─ metadata.py             # 학습 산출물 입력·출력·경계 검증 (로딩·추론 공통)
│  │  └─ content3_rule.py        # 서술 핵심어 포함 비율 결합 보정 규칙
│  ├─ m1/
│  │  ├─ router.py
│  │  ├─ service.py
│  │  └─ models.py
│  ├─ model_registry.py          # 모델별 revision·승인 범위·로딩 완료 후 교체
│  ├─ model_versions.py          # core snapshot·이벤트의 scoring 대상 계약
│  ├─ model_startup.py           # 기동 시 snapshot 조회·최초 로딩 재시도
│  ├─ model_loader.py            # CPU 모델 로딩
│  ├─ model_loading_reporter.py  # Pod별 로딩 상태 model.loading.reported 발행 (즉시·30초 주기, #370)
│  ├─ preflight.py               # POST /internal/models/preflight 모델 파일 사전 검사 (core 중계, #368)
│  ├─ versions.py                # 로딩 완료한 모델 버전 조회
│  ├─ clients/
│  │  ├─ base.py
│  │  ├─ core_client.py          # 기동 시 활성 버전 조회
│  │  └─ model_artifacts.py      # S3 가중치 임시 경로 다운로드
│  ├─ messaging/
│  │  ├─ envelope.py
│  │  ├─ connection.py
│  │  ├─ publisher.py            # llm.usage.recorded·model.loading.reported
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
│  ├─ worker.py                  # report-worker 진입점 (report.generate·student.deleted 소비, 발행·처리 기록 보존 정리 주기 호출 #208)
│  ├─ bootstrap.py
│  ├─ config.py
│  ├─ errors.py
│  ├─ security.py
│  ├─ database.py                # 공통 DB 연결 (트랜잭션 범위는 서비스 소유)
│  ├─ concurrency.py             # 취소 전 블로킹 작업 완료 후 잠금 해제
│  ├─ tracing.py                 # OTLP trace 내보내기·traceparent 전파 (#187)
│  ├─ generation/
│  │  ├─ consumer.py
│  │  ├─ service.py
│  │  ├─ pipeline.py             # 기록 조회·계산·서술·렌더링 단계 조립 (#56)
│  │  ├─ record_generator.py     # 기록 조회·계산 단계
│  │  ├─ narrative_generator.py  # ai 서술·대조, 대조 실패 시 템플릿
│  │  ├─ records.py              # P06·P08 정규화 기록
│  │  ├─ metrics.py
│  │  ├─ daily.py                # 일일 리포트 사실 구성 (P24, LLM 미호출)
│  │  ├─ theme_summary.py        # 주간 리포트 테마 요약 (learning #385 사실 검증)
│  │  ├─ verifier.py
│  │  ├─ presentation.py         # 조회·파일 렌더링 공통 조립
│  │  ├─ template_settings.py    # 리포트 표시 설정 검증·적용 (#209)
│  │  ├─ reconciliation.py       # core 상태 복구 대조 (#132)
│  │  ├─ router.py               # 복구 대조 내부 API (#132)
│  │  ├─ locking.py              # 작업별 session 잠금
│  │  ├─ codec.py                # v1 이벤트 변환
│  │  ├─ ports.py
│  │  ├─ unconfigured.py         # 생성기 미설정 시 FAILED
│  │  ├─ models.py
│  │  └─ repository.py
│  ├─ rendering/
│  │  ├─ templates/
│  │  ├─ renderer.py
│  │  └─ generator.py            # 파일 렌더링·저장
│  ├─ query/
│  │  ├─ router.py
│  │  ├─ service.py              # 학생 범위 검사·조회
│  │  └─ schemas.py
│  ├─ deletion/
│  │  ├─ consumer.py
│  │  ├─ service.py              # 삭제 조합·생성/조회 허용 검사·발행·처리 기록 보존 정리(prune_event_records, #278)
│  │  ├─ repository.py           # 삭제 장벽·processed_event DB 작업 (#252)
│  │  └─ state.py                # DeleteStudent·순수 삭제/생성 허용 규칙
│  ├─ outbox/                    # report.started·completed·failed
│  │  ├─ service.py              # 동일 트랜잭션의 subject별 삭제·발행 완료 보존 정리 진입점 (#252, #278)
│  │  ├─ repository.py
│  │  ├─ relay.py                # 학생별 선두 발행·재시도·격리 (#131)
│  │  └─ manage.py               # 격리 이벤트 운영 CLI (#131)
│  ├─ clients/
│  │  ├─ base.py
│  │  ├─ learning_client.py
│  │  ├─ ai_client.py
│  │  ├─ core_client.py          # 학생 별명(#119)·리포트 표시 설정(#209) 조회, 삭제 완료 보고
│  │  └─ storage.py              # S3·로컬 MinIO
│  ├─ messaging/
│  │  ├─ envelope.py
│  │  ├─ contracts.py            # 수신 이벤트 엄격 검증
│  │  ├─ connection.py
│  │  ├─ publisher.py
│  │  └─ consumer.py
│  └─ health/
│     └─ router.py
├─ migrations/                   # Alembic
├─ alembic.ini
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
| 배포 | `docker compose up` | Argo CD (local env) | 현재 데모: 수동 Helm / 목표: Argo CD (prod env) |
| Ingress | - | ingress-nginx | AWS LB Controller (ALB) |
| CNI (NetworkPolicy) | - | Calico (기본 CNI 정책 지원 버전별 상이) | VPC CNI `enableNetworkPolicy: "true"` |
| 외부 연동 | stub (LLM·토스·Google OAuth, E2E 오버레이) | stub 또는 테스트 키 | LLM API, 토스페이먼츠 테스트 키 |

- stub(`infrastructure/stubs`)은 실서버 E2E 오버레이 `compose.e2e.yaml`에서만 연결한다(google·llm·toss-stub, 합성 값 `infrastructure/stubs/e2e.env`). 기본 Docker Compose의 ai-service는 그대로 `.env`의 `LLM_PROVIDER`·API 키로 실제 LLM을 호출하고, 키가 없으면 판정·되묻기가 `AI_UNAVAILABLE`로 실패한다(6장 LLM 제공자). kind의 `<target>-stub` Service는 미구성이다. [이슈 #246 보고서](../report/testing-ci.md#2-실서버-브라우저-e2e와-외부-스텁-246)

- 로컬 kind 클러스터(`sagomungchi-local`)·Calico·ingress-nginx·MinIO의 버전·CIDR·버킷·자원 예산·초기화는 [로컬 플랫폼](../report/local-platform.md) 1~6장, 설치 절차는 [kind](../../infrastructure/kind/README.md)·[platform-data](../../infrastructure/gitops/charts/platform-data/README.md). API·HTTP·HTTPS는 loopback에서만 노출

### 4.2 운영 클러스터: EKS
- 선정 근거 (자체 구축 K8s(kubeadm·k3s) 대비)
  - 설계 구성 요소(ALB LB Controller, EKS Pod Identity, EBS CSI, Karpenter, ECR, Secrets Manager) AWS 기본 연동
  - control plane HA·etcd 백업·업그레이드를 AWS가 관리 → 12/7 일정 내 운영 부담 제거
  - 자체 구축도 control plane EC2 필요 → 비용 차이 작음 (EKS 수수료 $0.10/시간)
- 목표 구성: eksctl, 관리형 노드그룹 2개(4.3), EKS add-on(VPC CNI·CoreDNS·kube-proxy·EBS CSI·Pod Identity Agent), LB Controller·Karpenter의 Argo CD prod 관리.
- AWS 데모: EKS 1.35, 노드그룹 2개(4.3, 전부 On-Demand), Pod Identity, EBS CSI·LB Controller·ESO, RDS·S3·CloudFront·ALB를 구성했다. 앱 6개는 수동 Helm으로 배포했으며 prod Argo CD는 미구성이다. 2026-11-05 metrics-server add-on, core·learning·ai HPA(1~3, CPU 70%), Karpenter 1.15.1(NodePool `application-burst`)을 구성했다(#211·#372, 4.4). 이후 같은 노드에 최소 Collector·Prometheus·Grafana와 관측 PVC를 배포하고 RabbitMQ 수집을 확인했다. Grafana→Discord 경보를 연결했으며 전체 운영 관측 완료를 뜻하지 않는다. [현재 설정과 설계 차이](../report/aws-deploy.md), [EKS 인벤토리](../../infrastructure/eks/README.md)를 따른다. 생성 정의는 `infrastructure/eks/cluster.json`(eksctl)과 `infrastructure/aws/demo_stack.py`(AWS CLI)이며 기존 자원은 대조만 한다.
- 비용 절감
  - 데모 외 기간: 워크로드 정상 종료 후 노드그룹 0대 + RDS 정지(2026-11-03 결정, `demo_stack.py pause`/`resume`). 클러스터 삭제 후 재생성은 채택하지 않음
  - Spot은 무상태 앱 노드에만, 서비스별 replica 2개 이상·PDB를 갖춘 뒤 Karpenter 앱 NodePool에서 On-Demand와 혼합 적용(2026-11-05 #211은 On-Demand만, 앱이 replica 1·PDB 없음). `platform-observability`는 On-Demand 고정(2026-11-04 결정: 상태 저장 서비스가 replica 1개이고 EBS가 AZ에 묶여 Spot 회수 시 다른 AZ로 옮길 수 없음)
  - NAT GW 단일 AZ 1개(2a). 2026-11-04 #212 점검에서 연결·포트·드롭·대역폭 병목이 없어 데모 기간은 유지한다. AZ별 NAT(월 약 +$47)는 가용성 개선안으로 결정 대기([점검 근거](../report/aws-deploy.md#s3-gateway-엔드포인트와-nat-병목-점검-212-2026-11-04))

### 4.3 운영 네트워크·배치
- VPC: Public Subnet(ALB, NAT GW) / Private Subnet(EKS 노드, RDS)
- 진입: CloudFront → S3(웹 정적 파일·미션 장면) / CloudFront → ALB(AWS Load Balancer Controller Ingress) → core-service
- CloudFront: 웹과 API를 한 배포·한 도메인에서 경로로 분기 (refresh 쿠키 `SameSite=Strict` 전제)
  - `/api/*` 동작: 캐시 비활성, `Authorization`·`Idempotency-Key`·`If-Match`·`X-Reauth-Token`·`Origin`·`X-Requested-With`(쿠키 API 검사, API 5.1) 헤더와 쿠키 전달, 압축 비활성(SSE 버퍼링 방지)
  - 타임아웃: CloudFront origin 응답 60초, ALB idle 120초 (SSE heartbeat 15초, 1.3)
  - 클라이언트 IP(기기 등록 IP별 한도, API 3.11): CloudFront가 X-Forwarded-For 끝에 viewer IP를 붙이고, ALB는 `routing.http.xff_header_processing.mode=preserve`(Ingress annotation `alb.ingress.kubernetes.io/load-balancer-attributes`)로 CloudFront 엣지 IP를 덧붙이지 않음. ALB 보안그룹 inbound는 `com.amazonaws.global.cloudfront.origin-facing` prefix list만 허용해 XFF 위조 경로 차단. core는 `server.forward-headers-strategy: native`로 사설 대역 직전 연결만 신뢰(Tomcat 기본 internal-proxies). 운영 적용은 #185
- 외부 호출(LLM API·토스페이먼츠): Pod → NAT GW → Internet GW. Secrets Manager·STS·ECR API·공개 레지스트리 이미지도 NAT 경유(Interface endpoint 없음)
- S3: private 라우팅 테이블 2개에 S3 Gateway 엔드포인트(prefix list 경로)를 연결해 Pod의 S3 읽기·쓰기와 ECR layer 다운로드는 NAT를 거치지 않는다. 엔드포인트 정책은 기본 전체 허용, 버킷 접근은 Pod Identity 역할 정책으로 제한(#212)
- Namespace: `app`(core·learning·ai·scoring·report), `platform`(RabbitMQ·Redis), `observability`, `argocd`
- 노드그룹: `application`, `platform-observability` 분리 (참고 레포 2그룹 구성 계승)
  - `application`: t3.medium 2대(최대 3), 앱·ESO·LB Controller·CoreDNS·Karpenter 컨트롤러·metrics-server 등. 관리형 노드그룹은 자동 확장하지 않는다
  - Karpenter NodePool `application-burst`: 평소 0대. 기존 노드에 자리가 없는 Pending Pod가 생길 때만 t3.medium·t3.large On-Demand(2a·2b)를 만들고 비면 정리한다(4.4). taint가 없어 platform Pod는 배치되지 않는다
  - `platform-observability`: t3.medium 2대(2a·2b 1대씩, EBS PVC가 AZ별로 있음), label·taint `workload=platform:NoSchedule`. `platform-data`·`observability` chart의 `scheduling` 값으로 RabbitMQ·Redis·Prometheus·Grafana·Collector만 배치
- Pod AWS 권한: EKS Pod Identity(서비스별 IAM 역할, trust는 클러스터·namespace·ServiceAccount 조건). IRSA(OIDC provider·SA annotation)는 쓰지 않음
- NetworkPolicy: 기본 거부 + 아래 허용만 (호출 관계는 [API 명세서](api-spec.md) 4장). 공통 앱 chart·local Ingress·app/platform/observability NetworkPolicy 정의는 #171, 검증 범위는 [로컬 플랫폼](../report/local-platform.md#10-171-검증-결과와-교훈) 10장

| 대상 | ingress 허용 | egress 허용 |
|---|---|---|
| core | ALB(서브넷 ipBlock), ai, scoring, learning, report-worker, Prometheus | learning, ai, scoring(모델 사전 검사 #368), report-api, RabbitMQ(5672·15672), Redis, RDS, 토스(NAT) |
| learning | core, ai, report-api, report-worker, Prometheus | core, ai, RabbitMQ, RDS |
| ai | core, learning, report-worker, Prometheus | learning, scoring, core, RabbitMQ, LLM API(NAT), 설명 sLLM 서버(#476) |
| scoring | ai, core(모델 사전 검사 #368), Prometheus | core, RabbitMQ, S3 |
| report-api | core, Prometheus | learning(근거 조회), RDS, S3 |
| report-worker | Prometheus | core, learning, ai, RabbitMQ, RDS, S3 |
| 설명 sLLM 서버(#476) | ai, Prometheus | S3(모델 로딩) |
| RabbitMQ·Redis | `app` 전체, KEDA(RabbitMQ), Prometheus | - |

  - 전 Pod 공통 egress: kube-dns(53), OTel Collector·Langfuse(`observability`)
  - report-api·report-worker는 라벨이 달라 허용 대상에 각각 명시
  - core 내부 API 호출(위 core ingress 허용의 근거, 경로는 [API 명세서](api-spec.md) 4장)

    | 호출 서비스 | 클라이언트 | core 경로 |
    |---|---|---|
    | learning | `record/client/CoreClient.kt` | 삭제 완료 보고 `POST /internal/deletion-requests/{id}/completions` (P09) |
    | learning | `judgment/client/PaymentUsageClient.kt` | 피드백 프리미엄 사용 예약·확정 `POST /internal/payment-usage/reservations`·`/completions` (#48) |
    | report-worker | `app/clients/core_client.py` | 학생 별명 `GET /internal/students/{id}/profile`(#119)·리포트 표시 설정 `GET /internal/students/{id}/report-template`(#209) 조회, 삭제 완료 보고 |
    | ai·scoring | `app/clients/core_client.py` | 기동·재연결 시 활성 버전 snapshot `GET /internal/model-versions/active` (ai #68, scoring #85) |
  - migration-job: RDS egress / local: LLM API·토스 stub는 compose E2E 전용이며 kind에는 없음(4.1)

### 4.4 확장
- #171로 HPA·KEDA·PDB 템플릿과 local report-worker KEDA 0–1 설정. local 상시 값의 HPA·PDB는 자원 한도로 비활성화한다. 아래는 제품 설계 기준이고, 2026-11-05 AWS 데모 적용 값은 이 절 끝의 "AWS 데모 적용"을 따른다
- HPA(CPU): core, learning, ai, scoring, report-api — 최소 2(scoring은 메모리 고려해 최소 1, report-api 최소 1), PDB `minAvailable: 1`
- **KEDA(RabbitMQ 큐 길이)**: report-worker — 0~N 확장, EDA와 K8s 연계 지점
  - report 조회 API는 core가 동기 호출하므로 0으로 줄지 않는 `report-api`로 분리 (같은 이미지, 진입점만 다름). core `ReportClient` 대상 Service = report-api
  - `maxReplicaCount` × consumer prefetch = learning·ai·LLM API 동시 호출 상한 → LLM rate limit 이내로 설정 (값은 실측 후 결정)
- ai HPA: LLM 대기 위주라 CPU가 낮게 유지됨 → 실측 후 동시 요청 수 기준 지표 검토
- 노드 확장(Karpenter, #211): Pending Pod 발생 시 Karpenter가 EC2 노드를 직접 추가하고, 비거나 덜 쓰이는 노드를 정리(consolidation). Karpenter는 트래픽을 보지 않으므로 앞단 HPA/KEDA가 Pod를 늘려야 노드가 는다(#372)
- AWS 데모 적용(2026-11-05, #211·#372)
  - metrics-server(EKS add-on, replica 1). HPA는 core·learning·ai만 `minReplicas 1`·`maxReplicas 3`·CPU 70%. scoring(모델 로딩·메모리 1Gi)·report-api는 replica 1 고정, report-worker KEDA는 KEDA 미설치로 후속. 앱 PDB 없음
  - 축소 시 끊김 방지(D안): replica 1에서는 노드 정리가 Pod를 먼저 지운 뒤 새로 만들어 공백이 생긴다. core·learning·ai에 `eks.amazonaws.com/nodegroup=application` preferred nodeAffinity를 두어 기본 Pod를 관리형 노드에 놓고, HPA 축소 때 ReplicaSet이 최근 Pod부터 지우는 기본 순서로 Karpenter 노드가 먼저 비게 한다. 부하 중 재배포·관리형 노드 장애로 순서가 바뀌면 축소 때 한 번 끊길 수 있다(A안: 최소 2 + PDB는 상시 노드 1대 비용으로 보류)
  - NodePool `application-burst`: t3.medium·t3.large On-Demand, 2a·2b, 상한 CPU 4·메모리 16Gi(최대 약 2대), `WhenEmptyOrUnderutilized`·`consolidateAfter 5m`·한 번에 1노드, `expireAfter 720h`. EC2NodeClass `application`은 기존 노드 역할·AMI(`al2023@v20261031`)·private subnet·cluster SG를 ID로 지정
  - 부하 시 노드 확장·축소 실측은 이번에 하지 않았다([근거와 한계](../report/aws-deploy.md#eks-노드-자동-확장-karpenter와-앱-hpa-211372-2026-11-05))
- 일일 리포트 부하(P24, #390)
  - 월요일 00:00에 주간·일일 리포트 작업이 함께 생긴다(자녀당 2건). 일일은 LLM을 부르지 않아 비용 경보(P13 80%)에는 영향이 없고, report-worker(KEDA) 적체·DLQ 경보는 기존 기준으로 함께 본다([운영 경보](operational-alerts.md))
  - 자녀 수만큼 매일 작업이 생겨 report_db·S3 파일이 주간 대비 약 7배로 늘어난다. 보관 기간은 기존(P09 이용 중 보관)과 같음
- 설명 sLLM 서버(FN-RPT-09·NFR-PRF-03, #476)
  - 평소 replica 0. 주간 리포트 생성 시간대(월 00:00 전후)만 KEDA cron 트리거로 1대. AWS 데모는 KEDA 미설치 상태라 #476에서 KEDA 설치 또는 같은 시각의 replica 조정 방식 중 선택
  - 3B급 양자화 모델 CPU 추론은 t3 계열에 맞지 않아 Karpenter에 설명 전용 CPU NodePool(연산형 On-Demand, taint로 다른 Pod 배치 차단)을 두고 비면 정리
  - 생성 시간은 건당 20~30초 가정(30명 × 3건 약 40분), #475 실측 후 시간대·대기 상한 조정
- 종료 처리: core는 preStop 지연 + terminationGracePeriod로 SSE 정리 시간 확보 (롤링 배포·축소 시 단절은 클라이언트 재연결로 처리)
  - 피드백 executor 종료 대기는 최대 85초, heartbeat timer 종료 대기는 최대 5초다. 배포 시 `terminationGracePeriodSeconds`는 preStop 지연 + Spring/Tomcat 종료 단계의 예산 + 이 최대 90초 + 안전 여유보다 길게 설정하고 실제 롤링 종료로 검증한다. local chart 시작값은 preStop 15초·grace 180초([로컬 플랫폼](../report/local-platform.md) 8장). SIGKILL·프로세스 강제 종료 후에도 진행 중 호출이 보존된다는 의미는 아니다.
- probe: readiness는 자기 연결과 백그라운드 초기화 상태만 확인, 요청마다 하위 서비스 호출 금지. ai는 RabbitMQ 구독·core 활성 버전 snapshot 조정·사용 가능한 프롬프트 본문을 완료해야 Ready이며 core 조회 실패·재연결 조정·미보유 활성 본문은 NotReady다(#68).
- 공통 보안: 리소스 limit, non-root, readOnlyRootFilesystem

### 4.5 CI/CD
- GitHub Actions: 경로 필터로 변경 서비스만 테스트·빌드 → GHCR/ECR 푸시(OIDC로 AWS 인증). 현재는 테스트·빌드까지, 푸시·태그 갱신은 예정
- `infrastructure/gitops/environments/<env>/` 이미지 태그 갱신 커밋 → Argo CD 자동 동기화
- #171로 local 앱·KEDA·NetworkPolicy·관측 Application 등록 정의. 이미지 게시·승인 흐름은 #186 범위다
- #186 운영 배포: `cd-release.yml`(main에서 수동 실행)이 계획 검증 → main SHA 이미지 ECR 게시(GitHub OIDC) → GitHub Environment `prod` 승인(김동섭·김태윤) → 작업자 PC self-hosted runner에서 Helm 적용(`redeploy-app.ps1 -ImageDigest`) → 로그인·학습 제출·리포트 조회 확인 → 배포 이력 artifact 순으로 진행한다. prod는 Argo CD 없이 수동 Helm이다(#185). 자동 롤백은 없고 롤백도 같은 승인을 거친다. 운영 설정(AWS OIDC 역할·`prod` Environment·runner) 적용 후 실행 스위치를 켰다(2026-11-04). [설정·절차](../../infrastructure/cd/README.md), [결정 근거](../report/cd-release.md)
- Secret: 운영 AWS Secrets Manager + External Secrets Operator / 로컬 `.env` → K8s Secret (LLM·토스 키는 저장소에 미포함, NFR-SEC-04). DB는 서비스별 app·migrate 계정 Secret만 앱·migration-job에 주입하고 관리자 계정은 넣지 않음(#230)

### 4.6 관측
- #171 local 관측 chart: Collector·Prometheus·Grafana, 공통 앱 chart Java agent로 core·learning JVM/HTTP metrics. AI는 기본 비활성 Langfuse v4 LLM 계측. scoring·report exporter와 Langfuse backend·trace 저장은 아직 없음. `traceparent` 헤더와 AI 사용량 이벤트 봉투는 연결
- Langfuse: LLM 호출·토큰·비용·trace
- OpenTelemetry → Prometheus + Grafana: 서비스 지표, 큐 길이·DLQ 적재량(큐별 `<큐>.dlq`, #187), 판정·피드백·리포트 처리 지연
- 경보(#185·#187): Grafana Alerting → 팀 디스코드 웹훅(`aws-alerts`). 수집 장애·작업 적체·DLQ 적재·RabbitMQ 메모리, core 공개 API 영역별(인증·학습 저장·AI 처리·리포트·결제) 5xx 비율·p95 지연, 월 LLM 비용 300 USD의 80%와 미산정 호출. 담당은 인프라 1명(동섭)이 전체를 받는다 (P10, P13). 임계값은 초기 기준이며 [경보 검증](../../infrastructure/gitops/operational-alerts/README.md)을 따른다
- trace 저장(#187): Collector → Tempo(observability chart 선택 구성) → Grafana. core·learning은 Java agent trace, report-worker는 OTel SDK 소비 span. ai·scoring·report-api의 자체 span은 아직 없음
- 백업: RDS 자동 백업(일 1회) + PITR, 보관 7일, RPO 5분·RTO 4시간 (P12)
- `traceparent`를 HTTP 헤더와 이벤트 봉투 양쪽에 전파 → 동기·비동기 구간 단일 trace. core outbox는 저장 시점 span을 봉투에 담고 relay가 그 context 아래에서 발행해 AMQP 헤더로 잇는다. report-worker는 봉투 값을 부모로 소비 span을 열고 결과 이벤트에 AMQP 헤더를 붙인다 (#187, kind 검증)

---

## 5. 디렉토리 구조

목표 구조다. `(예정)` 표시는 아직 저장소에 없는 항목이며 해당 기능 착수 시 만든다.

```
SKN34-FINAL-3TEAM/
├─ frontend/
│  └─ web/                       # React 웹
│     ├─ src/                    # 3장 참고
│     ├─ scripts/                # 시연용 Vite 플러그인·QR 기기 시연·결제 테스트 서버
│     ├─ tests/
│     │  ├─ e2e/                 # 실서버 Playwright 대표 시나리오 (NFR-QA-01, playwright.e2e.config.ts·seed/, #246)
│     │  ├─ transfer-local/      # #289 이관 격리 로컬 실서버 시나리오 (playwright.transfer-local.config.ts)
│     │  └─ transfer-mock/       # #289 이관 MSW 시나리오 (playwright.transfer-mock.config.ts)
│     ├─ playwright.config.ts    # 목업 API(VITE_API_MOCK) 브라우저 시나리오 tests/browser 기본 설정
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
│  │  ├─ report-messages.md      # 리포트 메시지 계약 설명
│  │  ├─ <message>.v1.schema.json  # 메시지 1개·버전 1개 = 파일 1개, 1.4 메시지 이름 그대로
│  │  └─ asyncapi.yaml           # (예정) exchange·routing key·생산/소비 매핑
│  ├─ examples/
│  │  └─ report-admin-retry/     # 관리자 리포트 재처리 계약 예시
│  └─ openapi/
│     ├─ <service>.yaml          # api-spec.md 기준 생성. core-service(공개 API), 나머지(내부 API)
│     └─ support-learning-required.yaml  # support↔learning 협의용 계약 (현재 learning 구현 명세와 구분)
├─ ml/                           # 모델 학습 (클러스터 밖 실행, 이미지 빌드·배포 대상 아님)
│  ├─ m2/
│  ├─ m1/                        # 수학 풀이 점검 학습·평가 코드(#263, 기준선까지·본 학습 전)
│  └─ sllm/                      # 설명 sLLM 학습·평가·양자화 (#475)
├─ evaluation/                   # 판정 일치도(QWK, #199)·(예정) 되묻기 유출·에이전트 숫자/인용 대조 평가
│  ├─ datasets/                  # 평가셋별 cases.jsonl·fixtures (자체 작성 예시 답안, AI Hub 원문 미포함)
│  ├─ runners/                   # 서비스 호출·채점 스크립트 (judgment_eval.py, 테스트는 ai-service tests)
│  └─ results/                   # (예정) 실행 결과 요약
├─ infrastructure/
│  ├─ cd/                        # #186 운영 배포 계획·정책 예시와 절차 (cd-release.yml)
│  ├─ gitops/
│  │  ├─ charts/
│  │  │  ├─ app-service/         # 공통 서비스 chart (#171)
│  │  │  │  ├─ templates/
│  │  │  │  │  ├─ _helpers.tpl
│  │  │  │  │  ├─ deployment.yaml
│  │  │  │  │  ├─ service.yaml
│  │  │  │  │  ├─ serviceaccount.yaml          # Pod Identity 연결 대상 SA (S3 접근 서비스)
│  │  │  │  │  ├─ hpa.yaml
│  │  │  │  │  ├─ scaledobject.yaml
│  │  │  │  │  ├─ triggerauthentication.yaml   # KEDA RabbitMQ 인증
│  │  │  │  │  ├─ pdb.yaml
│  │  │  │  │  ├─ networkpolicy.yaml
│  │  │  │  │  ├─ namespace-default-deny.yaml
│  │  │  │  │  ├─ migration-networkpolicy.yaml
│  │  │  │  │  ├─ ingress.yaml
│  │  │  │  │  ├─ migration-job.yaml           # Argo CD PreSync hook (이름에 values `migration.revision` 포함)
│  │  │  │  │  └─ externalsecret.yaml          # (예정) 운영 Secrets Manager 연동
│  │  │  │  ├─ values.yaml
│  │  │  │  └─ values.schema.json
│  │  │  ├─ platform-data/       # RabbitMQ·Redis (+ 로컬 전용 PostgreSQL·MinIO)
│  │  │  │  ├─ templates/
│  │  │  │  ├─ files/
│  │  │  │  │  ├─ rabbitmq/
│  │  │  │  │  │  └─ definitions.json      # exchange·queue·DLX 단일 기준
│  │  │  │  │  ├─ minio/                  # 로컬 버킷 생성
│  │  │  │  │  └─ postgres/
│  │  │  │  │     ├─ init.sql              # 로컬 init 진입점 (rds-bootstrap.sql 포함)
│  │  │  │  │     └─ rds-bootstrap*.sql    # DB·서비스별 migrate/app 계정 생성, 로컬 init·운영 RDS 공용 (#230)
│  │  │  │  └─ values.yaml
│  │  │  └─ observability/       # local OTel metrics·Prometheus·Grafana (#171), Langfuse는 운영 준비 대기
│  │  │     ├─ templates/
│  │  │     └─ values.yaml
│  │  ├─ environments/           # 앱별 values·이미지 태그
│  │  │  ├─ local/
│  │  │  │  ├─ core-service.yaml     # local 앱별 values (#171). 마이그레이션 추가 시 `migration.revision` 갱신(scripts/tests 검사)
│  │  │  │  ├─ learning-service.yaml
│  │  │  │  ├─ ai-service.yaml
│  │  │  │  ├─ scoring-service.yaml
│  │  │  │  ├─ report-api.yaml
│  │  │  │  ├─ report-worker.yaml
│  │  │  │  ├─ platform-data.yaml
│  │  │  │  └─ observability.yaml     # local metrics 기반, Langfuse 제외
│  │  │  └─ prod/                # AWS 데모 Helm values·ExternalSecret 참조·NetworkPolicy
│  │  ├─ migrations/             # core·learning Flyway PreSync 이미지 Dockerfile
│  │  ├─ operational-alerts/     # #187 경보 규칙 검증 스크립트·절차
│  │  ├─ policies/
│  │  │  └─ local/platform.yaml  # platform namespace NetworkPolicy
│  │  └─ argocd/
│  │     ├─ local/
│  │     │  ├─ root-app.yaml     # kind Argo CD 진입점
│  │     │  └─ apps/
│  │     │     ├─ applicationset.yaml  # environments/local/* Application 생성
│  │     │     ├─ keda.yaml
│  │     │     ├─ metrics-server.yaml
│  │     │     ├─ observability.yaml
│  │     │     └─ platform-network.yaml
│  │     └─ prod/                # (예정) EKS Argo CD 진입점, External Secrets·AWS LB Controller·Karpenter
│  ├─ kind/
│  │  ├─ README.md               # 클러스터 기준·설치 절차
│  │  ├─ local.yaml              # kind 클러스터 설정
│  │  ├─ calico-installation.yaml  # Calico CNI·IP pool
│  │  ├─ ingress-nginx-values.yaml # ingress-nginx chart values
│  │  ├─ create-platform-secret.ps1  # .env → platform namespace Secret
│  │  ├─ create-app-secrets.ps1  # .env → app·observability namespace Secret
│  │  └─ hpa-check-values.yaml   # #171 HPA 검증 전용 values
│  ├─ eks/                       # eksctl ClusterConfig(cluster.json)·관측 인벤토리·gp3
│  ├─ aws/                       # AWS CLI IaC(demo_stack.py·demo-stack.json·iam/), RDS bootstrap 실행(SQL은 platform-data chart 공용), CloudFront·ALB redacted 설정
│  └─ stubs/                     # compose.e2e.yaml 전용 대역, e2e.env(합성 값)
│     └─ <target>-stub/          # google·llm·toss-stub: Google OAuth·LLM·토스페이먼츠 대역 (로컬·CI E2E)
│        └─ Dockerfile
├─ .github/
│  └─ workflows/
│     ├─ _spring.yml             # 재사용 워크플로: 테스트→빌드 (푸시·태그 갱신은 예정)
│     ├─ _python.yml
│     ├─ _web.yml
│     ├─ ci-<service>.yml        # 서비스별 경로 필터 → 재사용 워크플로 호출 (감시 경로는 아래 목록)
│     ├─ ci-db-schema.yml        # 마이그레이션 적용·ERD 대조 (scripts/check_db_migrations.py)
│     ├─ ci-contracts.yml        # 저장소 계약 회귀·core 실제 테스트 산출물 대조 (#143·#237); asyncapi 검사는 미구현
│     ├─ ci-gitops.yml           # chart lint·렌더·스키마 검증, migration 이미지 빌드 (#238)
│     ├─ ci-ml-m1.yml · ci-ml-m2.yml  # ml/m1·ml/m2 ruff·pytest
│     ├─ cd-candidate.yml        # #186 CD 도구 검사(계획 검증·실행기 테스트, 배포 없음)
│     ├─ cd-release.yml          # #186 운영 배포(main 수동 실행, 4.5)
│     └─ e2e.yml                 # 실서버 E2E: 수동·E2E 구성 변경 PR (#246). 야간 schedule은 기본 브랜치(main)에 병합된 뒤부터 동작
├─ docs/
│  ├─ README.md                  # 개발 규칙
│  ├─ design/                    # 아키텍처·기능명세·API 명세 등 설계 문서
│  ├─ report/                    # 영역별 구현·결정·검증 보고서
│  ├─ screen-design/             # 화면 설계서 원본·빌드 스크립트
│  ├─ outputs/                   # 기획·설계 산출물(PDF·XLSX·HTML)
│  └─ adr/                       # (예정) NNNN-<제목>.md
├─ compose.yaml                  # 로컬 통합 실행 진입점
├─ compose.minio.yaml            # 로컬 MinIO 선택 실행 (기본 파일과 함께 지정)
├─ compose.e2e.yaml              # 실서버 E2E: stub·시드 연결 (compose.yaml·compose.minio.yaml과 함께 지정)
├─ compose.transfer-local.yaml   # #289 이관 격리 로컬 실행: 포트 재지정 (compose.e2e.yaml 위에 지정, scripts/start_transfer_local.ps1)
├─ scripts/                      # 저장소 계약·스키마 검사(check_db_migrations.py 등)·연동 검증·CD 도구, tests/는 ci-contracts 회귀 테스트
├─ .env.example
└─ README.md
```

- CI 경로 필터(각 `ci-<service>.yml`은 자기 workflow 파일과 재사용 워크플로도 감시)
  - `ci-ai-service`: `backend/ai-service/**`·`contracts/**` 전체·`evaluation/**`
  - `ci-core-service`: `backend/core-service/**`·`contracts/**` 전체·`definitions.json`
  - `ci-report-service`: `backend/report-service/**`·`contracts/events/**`·`contracts/openapi/report-service.yaml`·`contracts/examples/report-admin-retry/**`·`definitions.json`
  - `ci-scoring-service`: `backend/scoring-service/**`·`contracts/openapi/scoring-service.yaml`·이벤트 스키마 3개(`envelope`·`model.version.activated`·`llm.usage.recorded`)
  - `ci-learning-service`·`ci-web`·`ci-ml-m1`·`ci-ml-m2`: 자기 경로만
  - `ci-contracts`·`ci-db-schema`·`ci-gitops`·`e2e`·`cd-candidate`는 각 workflow의 `paths` 기준
- DB 마이그레이션: 서비스별 Flyway(core·learning)·Alembic(report), 앱 기동이 아닌 `migration-job`(Argo CD PreSync hook)으로 1회 실행. 로컬 compose는 일회성 컨테이너로 동일 실행. 마이그레이션은 DB별 migrate 계정, 앱은 app 계정 사용(#230)
- 서비스 추가: `app-service` chart 재사용 + `environments/<env>/<service>.yaml` (ApplicationSet이 자동 생성, 서비스별 chart 미작성)
- 한 서비스의 다중 Deployment(report-api·report-worker): 같은 이미지, values의 실행 명령·확장 방식만 다름
- API 변경: `api-spec.md` 먼저 수정 → `contracts/openapi` → 구현
- 메시지 변경: `contracts/events` 먼저 수정 → 생산·소비 서비스 반영
- 큐 선언: `definitions.json`만 선언, 서비스 코드는 선언 없이 존재 확인만. 예외: 브로드캐스트 이벤트의 Pod별 exclusive 큐 (1.6)
- `definitions.json`은 Helm `.Files` 접근 범위인 `platform-data` chart 안에 두고, compose도 같은 파일 마운트
- 공통 코드: 공통 라이브러리 없이 서비스별 보유(이벤트 봉투·Outbox·AMQP 연결), `contracts/events` 스키마로 계약 테스트. 중복이 문제 될 때 `libs/` 검토
- Docker 빌드 컨텍스트는 서비스 폴더, `contracts/` 계약 테스트는 CI에서만 실행
- 모델 학습 코드(M2·M1·sLLM)는 `ml/`에서 관리, scoring·설명 sLLM 서버는 승인된 가중치(S3)만 로딩
- 참고 레포 대비 추가: `contracts/`, `ml/`, `infrastructure/aws/` / 제외: `mobile/`, `ops-service`(LLMOps는 Langfuse + `evaluation/`로 시작, 필요 시 추가)

---

## 6. 사용 기술

| 영역 | 기술 | 선정 근거 |
|---|---|---|
| 프론트엔드 | React, Vite, TypeScript, Tailwind CSS, TanStack Query, 토스페이먼츠 결제위젯 SDK | 참고 레포 동일 계열, 기획서 4.4 |
| 업무 API | Spring Boot 3, Kotlin, JDK 21, Spring Security JOSE(JWT HS256·Google JWKS), MyBatis, Flyway, Spring AMQP, ShedLock, Resilience4j | 참고 레포 구현 패턴 재사용, 다중 레플리카 스케줄 중복 방지 |
| AI API | Python 3.12, FastAPI, Pydantic, uv, LangGraph, LangChain, OpenAI API(기본 `gpt-6.1-terra`)·Claude API(`LLM_PROVIDER`로 교체), aio-pika, httpx | 에이전트 그래프·도구 호출, 비동기 AMQP |
| 모델 추론 | PyTorch, Hugging Face Transformers (M2 klue/roberta, M1) | 기획서 5장 모델 |
| 리포트 | SQLAlchemy, Alembic, Jinja2, Playwright(Chromium PDF) | HTML 템플릿 → PDF·Markdown |
| 저장소 | PostgreSQL(RDS), S3(로컬 MinIO), Redis(core 알림 중계·학생 기기 페어링·기기 등록 rate limit) | 서비스별 DB 분리, 판정 근거·기준표 JSONB, 파일 분리. Redis는 SSE 중계와 짧은 TTL 값만 담당하고 조회 캐시로 쓰지 않음, 분석 대화 사용량은 PostgreSQL 결제 사용 이력 집계로 이전(#210 결정, #225 구현) |
| 메시징 | RabbitMQ (quorum queue, topic/direct exchange, DLX) | 작업 큐 + fan-out 동시 지원, Kafka 대비 운영 부담 작음 |
| 결제 | 토스페이먼츠 테스트 환경 (결제위젯·자동결제·웹훅) | 실결제 미연동 |
| 컨테이너·오케스트레이션 | Docker, Compose, kind, Kubernetes, Helm | 로컬 → 운영 동일 chart |
| 확장 | HPA, KEDA, Karpenter, PDB | CPU 기반 API 확장 + 큐 기반 워커 확장 + Pending Pod 기반 노드 확장 |
| AWS | EKS(eksctl), EC2, VPC, ALB(LB Controller), CloudFront, S3, RDS, ECR, EBS gp3, Secrets Manager | 관리형 control plane(자체 구축 대비 운영 부담 제거)·AWS 연동 기본 지원, 참고 레포 EKS 구성 계승 + 관리형 DB |
| GitOps·CI | GitHub Actions(OIDC), GHCR, Argo CD, External Secrets | 변경 서비스만 빌드, Git 기준 배포 |
| 테스트 | JUnit5, Testcontainers, pytest, Playwright(MSW 화면 회귀·실서버 E2E) | 기획서 4.4 |
| 관측·LLMOps | Langfuse, OpenTelemetry, Prometheus, Grafana | LLM trace + 서비스·큐 지표 |

---

## 7. 확인 필요 가정
- 학습(M2·M1·설명 sLLM)은 클러스터 밖 RunPod GPU에서 AI Hub 데이터만으로 수행하고 결과(가중치)만 S3로 반입. 설명 문장 생성은 클러스터 안 CPU sLLM 서버에서 수행해 학생 글이 AWS 밖으로 나가지 않음 (2026-11-10 결정, #473)
- AWS 계정 EKS 생성 권한·예산 한도: 권한 없으면 EC2 1대 + k3s로 대체 (HA·Cluster Autoscaler·Pod Identity 제외)

### 7.1 구현 결정 요약

클래스 수준 결정(인증·주간 리포트·삭제·결제·신고 연결 경계)은 [클래스 다이어그램](class-diagram.md) 3장과 보고서([auth-account](../report/auth-account.md)·[report](../report/report.md)·[payment](../report/payment.md)·[support-admin](../report/support-admin.md))를 따른다. Redis 사용 범위는 6장 저장소 행과 [core-gateway #210](../report/core-gateway.md#6-redis-사용-필요성과-postgresql-대체-비교-210). 무료 플랜 미션 일일 한도(P13, 하루 1개)는 #210 결정에 따라 core `usage`의 `mission_daily_usage`(PostgreSQL)로 구현(#387, [core-gateway 13절](../report/core-gateway.md#13-주간-테마-프록시무료-하루-1개추가-문제-프리미엄-387))
