# #187 운영 경보 구성 경계

기준: architecture 1.6·4.6, functional-spec NFR-OPS-04/05·FN-ADM-19·P10/P13.
기존 Grafana Alerting → Discord 경로를 사용한다. 새 운영 서비스·의존성·공개 API는 추가하지 않는다.
사용자 공지 FN-SUP-07과 별개이며 앱 알림을 변경하지 않는다.

## 기준 구조

경보 provisioning은 #185(PR #333 병합, develop `de8e225`)의 observability chart를 기준으로 한다.
`grafana.alerting.enabled`일 때 `grafana-alerting` ConfigMap이 contact point `discord-aws-alerts`, 조직 notification policy,
values `rules`의 규칙을 Grafana에 provision하고, Discord webhook은 기존 Secret의 `DISCORD_WEBHOOK_URL` 키로 환경변수에 넣는다.
datasource UID는 chart가 `prometheus`로 고정한다. prod는 이 구조로 규칙 3개와 실제 Discord 수신을 확인했다(#185 보고서).

#187에서 따로 만들었던 생성기(`render.py`, `ops187-*` ConfigMap·contact point, 규칙별 직접 라우팅, datasource UID 필수 입력)는
같은 values 키와 provisioning 경로를 #185와 겹쳐 쓰므로 병합 시 제거했다. 같은 org에 두 provisioning 체계를 두지 않는다.
그 대신 #185 템플릿에 평가·알림 간격 values를 더했다. 기본값은 #185 운영값과 같아 기존 렌더 결과가 바뀌지 않는다.

## DLQ 적재

DLQ 적재는 별도 opt-in scrape job `rabbitmq-dlq`로 본다. 같은 RabbitMQ 15692 포트의 `/metrics/detailed`에서
`queue_coarse_metrics` family만 요청하고, metric relabel로 `rabbitmq_detailed_queue_messages` 중 `<큐>.dlq`(architecture 1.6 명명)만 남긴다.
기본 `rabbitmq` job과 전체 per-object 지표는 바꾸지 않는다. 시계열은 정의된 DLQ 수(현재 7개, #370 `core.model.loading.reported.dlq` 포함)만큼이다.
규칙은 `max by (vhost, queue)`로 큐마다 경보 인스턴스를 만든다. 큐 이름은 시계열 라벨로 알림에 실린다.
메시지 수는 ready+unacked 합계이며 메시지 나이·재처리 지연은 의미하지 않는다. scrape 실패나 지표 부재는 0이 아니라 NoData로 남는다.
업무 ID·메시지 내용은 label에 넣지 않는다. prod values는 수집(`prometheus.rabbitmqDlqMetrics.enabled`)을 켜고 `rabbitmq-dlq-depth`(> 0, 5m)를 초기 기준으로 넣었다. 운영 임계값·지속시간은 실측 뒤 조정한다.
일일 리포트(P24, #390·#391)는 같은 `report.generate` 큐를 써 DLQ 수(현재 7개)는 늘지 않는다. 월요일 00:00에는 주간·일일 작업이 함께 쌓이므로 임계값·지속시간을 정할 때 이 시각의 적체를 실측해 반영한다([아키텍처 4.4](architecture.md#44-확장)).

## 월 LLM 비용

core `LlmCostMetrics`가 OTel API gauge 두 개(`llm.usage.month_to_date.priced_cost`, `...unpriced_calls`)를 낸다.
OTel Java agent가 켜진 경우에만 export되고 없으면 no-op이다. export 주기마다 `llm_usage`에서 KST 달력 월 1일 00:00부터 현재까지를 한 번 조회한다.
단가가 있는 호출만 합산하고 미산정 호출 수는 따로 낸다(0으로 치환하지 않음). 조회 실패 주기에는 값을 내지 않아 경보는 NoData가 된다.
예산 300 USD와 80%(240 USD) 판정은 Grafana 규칙 임계값이다. 새 exporter·주기 실행 계층·DB 계정은 추가하지 않았다.
이벤트 발행 유실(best-effort)은 반영되지 않으므로 실제 비용보다 작을 수 있다.
일일 리포트는 템플릿만 써 `llm_usage`가 늘지 않고, 일일 리포트 대화는 기존 분석 대화 호출 종류로 집계되어 예산 규칙에 포함된다.
리포트 설명(FN-RPT-09, #473)은 클러스터 안 sLLM이라 토큰 단가가 없어 미산정 호출로 집계되고 예산 합산에는 들어가지 않는다. 비용은 sLLM 서버 노드 시간(EC2)으로 나타난다.

## 업무별 오류율·지연

core·learning Java agent의 `http_server_request_duration_seconds`(`http_route`·`http_response_status_code`)를 쓴다.
core 공개 API 경로로 인증·학생 학습·AI 처리·리포트·결제를 나누고 5xx 비율과 p95 지연을 본다(AI 처리는 SSE 스트림이 섞여 p95 지연 규칙 없이 5xx 비율만). 요청이 없으면 `noDataState: OK`로 정상 처리하고,
지표 수집 자체가 사라지면 `app-metrics-missing`이 알린다. 4xx는 사용자 입력 오류로 보고 제외한다. Python 서비스(ai·report)의 자체 HTTP 지표는 아직 없다.
prod는 core·learning의 Java agent와 Collector egress를 켜야 이 규칙들이 값을 갖는다. app-service chart는 env의 `JAVA_TOOL_OPTIONS`를 agent 옵션 뒤에 합친다.
커뮤니티·포인트·꾸미기·주간 테마는 core 공개 API 경로라 새 지표 없이 경로 분류(학생 학습 묶음)만 추가한다.
학생 학습 묶음(`http-learning-*`)의 경로는 `/api/v1/(attempts/.+|missions/.+/(attempts|community-posts)|students/me/.+|community-posts/.+)`이다.
풀이 저장과 학생 본인 경로(`/students/me/*`: 홈·풀이 목록·커뮤니티 공유·포인트·꾸미기·주간 테마), 커뮤니티 반응·미션별 공유물 조회를 함께 본다(#504).
미션 목록·상세(`/missions`, `/missions/{missionId}`)와 보호자 자녀 경로(`/children/*`)는 이 묶음에 넣지 않는다.

## 실패 요청 trace

저장소는 Tempo(observability chart 선택 구성)다. 아키텍처의 "HTTP 헤더와 이벤트 봉투 양쪽 전파"를 다음처럼 잇는다.

- core: `OutboxWriter`가 저장 시점 활성 span(없으면 요청 헤더 값)을 봉투 `traceparent`에 넣는다. `OutboxRelay`는 스케줄러 스레드에서
  그 값을 부모 context로 열고 발행해, Java agent가 PRODUCER span과 AMQP `traceparent` 헤더를 만든다.
- core·learning 소비자와 HTTP 서버/클라이언트는 Java agent가 AMQP·HTTP 헤더로 잇는다.
- report-worker: 봉투 `traceparent`를 부모로 CONSUMER span을 열고, 하위 HTTP 호출(UserContext 헤더)과 결과 이벤트 봉투에 이 span을 넘긴다.
  결과 이벤트 발행 시 AMQP `traceparent` 헤더도 붙인다. 실패는 `messaging.outcome`(retry/dlq)·`error.type`만 남기고 예외 메시지는 저장하지 않는다.
- 업무 ID·학생 ID·메시지 내용(커뮤니티 공유물 내용 포함)은 span attribute에 넣지 않는다(메시지 ID와 큐 이름만). 다만 Java agent의 HTTP span에는 경로 템플릿만 남는다.
- OTel exporter가 꺼져 있으면 core는 요청 헤더 값만 전달하고 report-worker는 받은 값을 그대로 넘긴다(기존 동작).

## 남은 경계

- #185 규칙의 target 감시는 `min(up{job=~...})`라 scrape job 자체가 사라지면 발생이 아니라 NoData로 보고된다.
- 조직 notification policy를 chart가 소유한다. 서비스별 담당이 정해지면 policy 하위 route로 나눈다.
- ai·scoring·report-api는 자체 span이 없다. ai 호출 구간은 호출한 쪽 span으로만 보인다.
- local values는 Tempo·trace를 켜지 않는다. 검증 시 opt-in으로 켠다.
- 임계값은 초기 기준이다. 실측 부하 기반 조정과 서비스별 담당 라우팅은 후속이다.
- 리포트 설명(#476·#479): 배치 시간대 설명 sLLM 서버 기동 실패와 설명 `NOT_INCLUDED` 비율 경보는 아직 없다. 설명이 빠져도 리포트는 `COMPLETED`로 끝나 기존 DLQ·오류율 규칙에 잡히지 않으므로 #479에서 지표를 정하고 임계값은 실측 뒤 정한다.
