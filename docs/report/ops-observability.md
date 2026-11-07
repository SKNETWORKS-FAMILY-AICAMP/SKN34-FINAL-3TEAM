# 운영 경보와 요청·오류 추적 (#185·#187)

경보 규칙·경계는 [설계: 운영 경보](../design/operational-alerts.md)가 소유한다. 이 문서는 결정·구현 경과·검증 근거를 남긴다. AWS 배포 전반은 [aws-deploy](aws-deploy.md).

## 결정

| 항목 | 결정 | 시점 |
|---|---|---|
| 경보 경로 | Grafana Alerting → 팀 디스코드 `aws-alerts`(webhook은 Secret `discord-alert-webhook`). SNS→Lambda 중계안은 보류 | 11-03 (#185) |
| 경보 chart 구조 | #185가 prod에 넣은 observability chart 구조(values `rules`, 조직 notification policy, datasource UID `prometheus`)를 기준으로 하고 #187 생성기(`render.py`·`ops187`)는 제거 | 11-04 |
| DLQ 수집 | 기본 `rabbitmq` job은 두고 opt-in `rabbitmq-dlq` job(`/metrics/detailed`의 `<큐>.dlq`만). DLQ 규칙이 있는데 수집이 꺼져 있으면 렌더 실패. 켜고 끌 때 Prometheus Pod 재생성 annotation | 11-03 |
| 월 LLM 비용 | 예산 300 USD, 80%(240 USD) 경보, KST 달력 월. core `LlmCostMetrics` gauge(단가 있는 비용·미산정 호출 수 분리) | 11-04 |
| 담당 | 동섭 1명, `aws-alerts` 한 채널. 서비스별 라우팅은 담당 확정 후 하위 route | 11-04 |
| trace 저장소 | Tempo(observability chart 선택 구성, 72h). Langfuse는 LLM 계측용으로 별도 | 11-04 |

## 경과

- 11-01: #187 독립 경보 생성기·검증기 작성(수집 장애·적체 규칙)
- 11-03: DLQ 수집 job과 규칙 추가, kind에서 실제 RabbitMQ DLQ 적재 → 발생·회복 확인. kind에서 Prometheus가 ConfigMap 변경을 다시 읽지 않는 문제를 발견해 재생성 annotation 추가
- 11-03 (#185): prod에 Collector·Prometheus·Grafana 최소 관측 배포와 Discord 연결(아래)
- 11-04: #185 병합으로 chart 구조 통합(아래), 월 LLM 비용·업무별 오류율·지연 규칙 추가, Tempo trace, kind 디스코드 실수신 확인

## prod 최소 관측 배포와 Discord 연결 (#185, 2026-11-03)

- 기존 노드에 Collector·Prometheus·Grafana를 observability release로 배포(CPU 250m·메모리 544Mi 예약, gp3 4Gi+1Gi). platform에는 Prometheus→RabbitMQ:15692만 허용하는 정책 추가
- RabbitMQ·Collector scrape up, 합성 gauge로 OTLP→Prometheus 수신 확인, Pod 재생성 뒤 이력 유지(PVC). 앱 JVM/HTTP 계측 검증은 아님
- Discord webhook은 Secret에만 저장하고 prod alerting 활성화. 임시 규칙(vector(1)→vector(0))으로 Firing·Resolved 메시지 실수신(20:36·20:41 KST) 후 임시 규칙 삭제, 운영 규칙 3개 유지. 실제 자원 임계값의 자연 회복 시나리오는 아님

## #185 병합 반영과 경보 구조 통합 (2026-11-04)

#185(PR #333) 병합 때 observability chart 5개 파일이 충돌했다.
#185는 같은 chart에 다른 방식의 Discord 경보를 이미 넣었고 prod에서 동작 중이었다.

| 항목 | #185 | 기존 #187 |
|---|---|---|
| 스위치·마운트 | `grafana.alerting.enabled`, `/etc/grafana/provisioning/alerting`, ConfigMap `grafana-alerting` | 같은 키·경로, ConfigMap `ops187-alerting` |
| 규칙 | values `rules`를 템플릿이 그림 | 생성기 출력 전체를 values로 받음 |
| webhook | `DISCORD_WEBHOOK_URL`, Secret `discord-alert-webhook` | `OPS_DISCORD_WEBHOOK_URL`, 빈 값 시작 차단 |
| 라우팅 | 조직 notification policy 소유 | 규칙별 직접 라우팅 |
| datasource UID | `prometheus` 고정 | 필수 입력 |

사용자 결정으로 #185 구조를 기준으로 삼았다. #187 생성기를 지우고 #185 chart 위에 DLQ 수집 job·수집 없는 DLQ 규칙 렌더 실패·Prometheus 재생성 annotation과 경보 간격 values(기본값은 #185 운영값)를 더했다.

#185 구조에서 달라지는 의미는 다음과 같다.

- target 규칙은 `min(up{job=~"otel-collector|rabbitmq"})`다. job 자체가 사라지면 발생이 아니라 NoData로 보고된다(NoData 알림은 전송됨).
- 빈 webhook 값의 시작 차단은 없다. Secret·키 누락은 `secretKeyRef` 기본 동작으로 Pod 구성이 실패한다.
- 조직 notification policy를 chart가 덮어쓴다. 담당별 라우팅은 담당 확정 후 하위 route로 나눈다.

### 통합 구조 재검증 (2026-11-04)

| 범위 | 결과 |
|---|---|
| Helm 4.3.1 | default·local·prod 렌더가 `de8e225`과 바이트 단위로 동일, 세 values 모두 `helm lint --strict` 통과 |
| `verify_chart.py`(기본 기준 `de8e225`) | 29개 확인 exit 0. prod 규칙 3개 가속 사본+DLQ 규칙 렌더, DLQ relabel·annotation·Secret 참조, 수집 없는 DLQ 규칙 렌더 실패, 실제 RabbitMQ 4.3.7 출력→Prometheus→Grafana 13.3.0 평가(적체·DLQ 발생·회복·로컬 수신, NoData·조회 오류·UID 오류·재적용·수집 실패, job 제거 NoData) |
| 계약 테스트 | `-O -m unittest discover -s scripts/tests` 112개 통과 |
| kind `sagomungchi-local` | 같은 가속 사본(적체 임계값 1)으로 revision 5 적용 → 규칙 4개 Normal, DLQ 큐 6개 인스턴스 → `report.report.generate.dlq`에 표식 2건 → 약 30초 안에 그 큐만 Alerting·적체 Alerting → `discord-aws-alerts` 전송 시도(시험 주소 DNS 실패, 실제 발송 없음) → 표식 2건 확인 후 제거, DLQ 합계 0 → 약 30초 안에 모두 Normal → local values로 revision 6 복구, 시험 Secret 삭제 |

kind에서 직접 확인한 것은 실제 수집·평가·발생·회복과 contact point 전송 시도까지다. 수신 메시지 형식·회복 알림·NoData/오류 알림은 격리 Docker 대역으로만 확인했다.
실제 팀 Discord 수신은 #185가 prod에서 임시 규칙으로 확인한 결과이며, #187의 DLQ 규칙으로 prod Discord에 보낸 적은 없다.

## 월 LLM 비용·업무별 오류율·지연 경보 (2026-11-04)

사용자 결정: 월 LLM 예산 300 USD(80% = 240 USD), 담당은 동섭 1명·`aws-alerts` 한 채널. 월 경계는 KST 달력 월 1일 00:00(api-spec 4.6의 KST 기준과 같음).

### 구현

- core: `LlmUsageRepository.monthToDate`·`LlmUsageService.monthToDate`·`LlmCostMetrics`. 기존 `summarize`는 미산정 호출이 섞인 call type의 비용 전체를 null로 내므로
  예산용으로는 단가 있는 비용 합계와 미산정 호출 수를 따로 구한다. `io.opentelemetry:opentelemetry-api`(Boot BOM)와 테스트용 `opentelemetry-sdk-testing`을 추가했다.
- observability chart: 규칙별 `noDataState`(기본 NoData). prod values에 규칙 13개와 DLQ 수집 활성화를 추가해 총 16개.
- app-service chart: env의 `JAVA_TOOL_OPTIONS`를 agent 옵션 뒤에 합친다. 이전에는 prod의 `-XX:MaxRAMPercentage=60.0`이 agent 플래그를 덮어써
  agent를 켜도 실제로는 빠지는 상태였다(#185 README의 후속 항목).
- prod `core-service.json`·`learning-service.json`: `javaAgent.enabled`·`networkPolicy.egressToCollector`를 켰다.
- 모든 환경 파일 25개의 렌더를 develop과 비교해 prod observability(규칙 추가)·core·learning(agent 활성화) 외에는 리소스가 같음을 확인했다.

### 검증

| 범위 | 방식 | 결과 |
|---|---|---|
| core 단위·저장소 테스트 | JDK 21 Gradle 컨테이너, Testcontainers PostgreSQL | 새 테스트 2개 통과(KST 월 경계·미산정 분리, OTel SDK 메모리 reader로 gauge 값). 전체 506개 중 179개 실패는 develop 원본도 같은 환경에서 504개 중 179개 실패(`IntegrationTestSupport`가 core 밖 파일을 읽는 `NoSuchFileException`)로 실행 환경 문제이며 새 실패 없음 |
| kind 실제 core | `:issue187` 이미지를 kind에 로드해 core Deployment 이미지를 잠시 교체 | agent 2.33.1 → Collector → Prometheus에 `llm_usage_month_to_date_priced_cost`=0, `..._unpriced_calls`=5 수집. kind의 LLM stub 모델에 단가가 없어 미산정 경고가 실제로 발생 |
| kind 규칙 16개 | prod 규칙 가속 사본(지속 10초) | 모두 health ok. 미산정 호출 Alerting, 비용 Normal. ingress로 인증·리포트 요청을 보내자 해당 영역 5xx 비율·p95 규칙이 NoData→실제 값으로 Normal |
| kind 복구 | | observability local values(revision 8), core 이미지 `:local` 복구, 시험 Secret·kind의 `:issue187` 이미지 삭제 |
| 격리 Docker | `verify_chart.py` | 37개 확인 exit 0. 기존 항목에 더해 비용 80% 발생·회복, 미산정 발생·회복, 인증 5xx 비율·p95 지연 발생, HTTP 지표 부재 발생 |
| 계약 테스트 | `scripts/tests` | 112개 통과 |

kind에서 5xx·지연 초과를 실제로 일으키지는 않았다(대역으로만 발생 확인). `app-metrics-missing`은 처음에 `absent() or absent()`로 작성해 정상일 때 NoData가 되는 문제를 kind에서 발견했고,
`max(... or vector(0))`로 고쳐 정상일 때 0이 되게 했다.

### prod 적용

- prod values에 규칙 16개·DLQ 수집, core·learning `javaAgent.enabled`·Collector egress가 반영돼 있다(main). 실제 prod 적용 시각과 `app-metrics-missing`·비용 규칙 정상화는 기록이 없어 확인 필요
- 적용 순서: core 이미지(비용 지표 포함) 배포 → core·learning agent 활성화 → observability values 적용(Prometheus 재생성, PVC 보존)
- 남은 것: ai·report(Python) 자체 HTTP 지표, 임계값 실측 조정

## 실패 요청 단일 trace (Tempo, 2026-11-04)


### 구현

| 위치 | 내용 |
|---|---|
| observability chart | 선택 구성 `tempo.enabled`: Tempo 2.10.10 단일 바이너리, Collector `otlp/tempo` traces pipeline, Grafana datasource `Tempo`(uid `tempo`), NetworkPolicy(Collector→4317, Grafana→3200), 선택 PVC. Collector·Grafana는 Tempo를 켜고 끌 때 annotation으로 재생성(설정을 시작 시에만 읽음, kind에서 Grafana datasource 누락으로 발견) |
| app-service chart | `tracing.enabled`: Java agent는 `OTEL_TRACES_EXPORTER=otlp`, agent 없는 서비스는 같은 `OTEL_*` 값을 받아 자체 SDK에서 사용 |
| core | `TraceContexts`(OTel API): `OutboxWriter`가 저장 시점 활성 span(없으면 요청 헤더 값)을 봉투 `traceparent`에 넣고, `OutboxRelay`가 그 context 아래에서 발행해 agent가 AMQP 헤더를 만든다 |
| report-service | `app/tracing.py`(OTel SDK, `OTEL_TRACES_EXPORTER=otlp`일 때만 export). 소비 span의 부모를 봉투 `traceparent`로 두고 하위 HTTP·결과 이벤트에 소비 span을 넘긴다. 결과 이벤트에 AMQP `traceparent` 헤더. 실패는 `messaging.outcome`·`error.type`만 기록. 의존성 `opentelemetry-sdk`·`opentelemetry-exporter-otlp-proto-http` 1.45.2(ai-service와 같은 버전) |
| prod values | observability `tempo`(72h, gp3 2Gi), core·learning·report-worker `tracing.enabled`, report-worker Collector egress |

### 검증

| 범위 | 결과 |
|---|---|
| core 테스트(JDK 21 Gradle 컨테이너, platform-data definitions·contracts 포함) | 전체 502개 실패 0. `TraceContextsTest` 3개, 비용 지표 2개, relay를 포함한 `MessagingIntegrationTest` 실행 확인. 앞 절의 179건 실패는 컨테이너에 core 밖 파일을 넣지 않아 생긴 것이었고 이번 실행에서 해소 |
| report-service 테스트(로컬 uv) | 새 `test_tracing.py` 7개 포함 consumer 테스트 통과, ruff 통과. 전체 344개 중 PDF 렌더 10건은 이 PC에 Playwright Chromium이 없어 실패(develop 원본도 같은 원인으로 실패) |
| Helm | 모든 환경 파일 25개 렌더를 develop과 비교해 의도한 prod 4개(observability·core·learning·report-worker) 외 동일. `verify_chart.py` 38개 확인 exit 0(Tempo·trace 렌더 검사 추가) |
| kind 단일 trace | 아래 |

kind 시나리오(2026-11-04 14:25~14:46 KST): Tempo와 core·learning(agent trace)·report-worker(새 이미지·OTLP env, 임시 NetworkPolicy)를 켠 뒤,
존재하지 않는 학생·작업 ID로 `report.generate`를 `cmd.direct`에 1건 발행했다. 봉투와 AMQP 헤더에 같은 `traceparent`를 넣어 core outbox relay가 발행하는 형태를 흉내 냈다.
trace `e08ac021…` 하나에 span 67개가 모였다.

1. core 감사 소비자와 report-worker 소비 span(비동기)
2. worker → core `GET /internal/students/{studentId}/profile`(동기, core SERVER span이 worker span의 자식)
3. worker가 발행한 `report.started`·`report.failed`를 core가 소비(비동기, AMQP 헤더로 연결)
4. core가 "Unknown report job"으로 처리 실패 → 재시도 큐 발행 → 1·5·15분 뒤 재소비 3회 → 마지막에 `core.report.events.dlq`로 이동(2건)

첫 발행만 core relay 대신 직접 했다. relay가 저장된 trace 아래에서 발행하는 부분은 단위·통합 테스트로 확인했고 kind에서는 실행하지 않았다.
로그인한 사용자의 HTTP 요청에서 시작하는 경로(리포트 재생성 등)는 kind에 리포트·관리자 계정이 없어 실행하지 못했다.
span 상태는 core 재시도 처리기·worker 업무 실패가 예외를 밖으로 내지 않아 ERROR가 아니라 재시도 발행·DLQ 이동으로 드러난다.

정리: DLQ 2건(제 학생·작업 ID 확인 후 제거), report DB의 해당 학생 `weekly_report` 1행·발행 완료 `outbox_event` 2행 삭제,
core·learning `OTEL_TRACES_EXPORTER=none`·report-worker 원래 이미지와 env 복구, 임시 NetworkPolicy·kind 시험 이미지 삭제, observability local values(revision 11).
core `event_log`에는 이 시험 이벤트의 감사 메타데이터 3행이 남아 있다(감사 기록이라 지우지 않음). 학생·작업 ID는 실제 데이터와 무관한 임의 UUID다.

## kind 경보 디스코드 수신 (2026-11-04)

사용자 결정으로 #187은 kind 근거로 마무리한다. 사용자가 루트 `.env`에 `DISCORD_WEBHOOK_URL`(`aws-alerts` 채널)을 넣고 시험 발송을 허락했다.
값은 형식만 확인했고(Discord webhook URL 형식, 출력 없음) stdin으로 시험 Secret `observability/issue187-discord`에만 넣었다. `.env.example`에 항목을 추가했다.

| 시각(KST) | 내용 |
|---|---|
| 15:18 | 경보 활성화(revision 12): 규칙은 DLQ 1개, 제목 `[kind test #187] RabbitMQ dead letter queue depth`, 요약에 로컬 시험·운영 장애 아님을 명시. 지속 10초·평가 10초·묶음 1초/10초 |
| 15:18:03 | 실제 kind DLQ 6개마다 Normal 인스턴스 |
| 15:18:15 | `report.report.generate.dlq`에 표식 메시지 1건 적재 |
| 15:18:41 | 해당 큐 인스턴스만 Alerting |
| 15:18:54 | contact point `discord-aws-alerts` 전송, Grafana 기록 오류 없음(Discord 응답 성공) |
| 15:20:00 | 표식 메시지 확인 후 제거, DLQ 합계 0 |
| 15:20:24 | 회복(Resolved) 전송, 오류 없음 |
| 15:21 | local values(revision 13, 경보 꺼짐)로 복구, 시험 Secret 삭제 |

Grafana NetworkPolicy는 경보 활성화 시 공인 IPv4 443만 추가로 열며 kind Calico에서 실제 Discord로 나갔다.
템플릿의 `environment: demo` 라벨은 #185 고정값이라 kind 메시지에도 그대로 붙는다.

## 완료 조건 상태

- 경보 발생·디스코드 수신: kind에서 실제 DLQ 적재 → 규칙 발생 → `aws-alerts` Firing·Resolved 수신(11-04), prod는 #185 임시 규칙으로 수신 경로 확인(11-03)
- 실패 요청 단일 trace: kind에서 명령 소비 → 동기 HTTP → 결과 이벤트 → 실패·재시도·DLQ가 한 trace. 로그인 사용자 요청 시작점은 kind 데이터 부재로 미실행
- prod trace: Tempo·`tracing.enabled`는 prod values에 있으나 실제 적용 여부와 core OTLP span 전송 404 경고([cd-release](cd-release.md)·[load-test](load-test.md))의 해소 여부는 확인 필요
