# 운영 경보 검증 (#187)

설계: [operational-alerts](../../../docs/design/architecture.md#47-운영-경보-구성-경계-187).
근거·요구사항별 공백·결정 목록: [보고서](../../../docs/report/infra.md#8-운영-경보와-trace-185187).

경보 provisioning은 #185의 observability chart(`grafana.alerting.*`, `templates/alerting.yaml`)를 그대로 쓴다.
#187은 그 위에 RabbitMQ DLQ 큐별 지표 수집, 규칙별 `noDataState`, 평가·알림 간격 values, core 월 LLM 비용 지표, 검증기를 더한다.

## prod 규칙 (#187 추가분, 초기 기준)

| uid | 조건 | 지속 | NoData |
|---|---|---|---|
| `rabbitmq-dlq-depth` | 큐별 `rabbitmq_detailed_queue_messages` > 0 | 5m | NoData |
| `llm-budget-80` | `max(llm_usage_month_to_date_priced_cost)` > 240 (월 300 USD의 80%) | 1m | NoData |
| `llm-unpriced-calls` | `max(delta(llm_usage_month_to_date_unpriced_calls[1h]))` > 0 (최근 1시간에 새로 생긴 미산정, #764) | 1m | NoData |
| `app-metrics-missing` | core 또는 learning HTTP 지표 부재 | 10m | NoData |
| `http-<영역>-errors` | 5xx 비율 > 5%, 5분 10건 이상 | 5m | OK |
| `http-<영역>-latency` | p95 > 인증 1s·학생 학습 2s·리포트 3s·결제 5s, 5분 10건 이상 | 5m | OK |
| `report-explanation-not-included` | 창 안 최근 30분 `NO_TARGET` 뺀 설명 결정 5건 이상 중 `NOT_INCLUDED` > 50% (#1031) | 5m | OK |
| `report-explanation-none-included` | 창 안 최근 30분 `NOT_INCLUDED` 3건 이상, `INCLUDED` 0건 (#1031) | 5m | OK |

영역은 core 공개 API의 `http_route`로 나눈다: 인증 `/api/v1/auth/.+`, 학생 학습 `/api/v1/(attempts/.+|missions/.+/(attempts|community-posts)|students/me/.+|community-posts/.+)`(풀이 저장·학생 본인 경로·커뮤니티, #504),
AI 처리 `/api/v1/(conversations.*|answers/.+/feedback)`, 리포트 `/api/v1/reports/.+`, 결제 `/api/v1/(payments.*|subscriptions.*|orders|webhooks/tosspayments)`.
AI 처리는 SSE 스트림이 섞여 지연 규칙을 두지 않는다. 비용 지표는 단가가 있는 호출만 합산하므로 미산정 호출이 있으면 합계는 하한값이고 별도 경고가 난다.
미산정 경보는 누적값이 아니라 1시간 증가분을 봐서 새 누락이 없으면 1시간 뒤 해제되고, 월초 누적 초기화(감소)에는 울리지 않는다(#764).
외부 비용이 없는 클러스터 안 모델은 core 단가 0, Veo·RunPod Gemma는 별도 청구로 저장되어 미산정에 들어가지 않는다.
core가 여러 replica면 같은 값을 각각 보고하므로 `max`로 본다. 값은 core의 metric export 주기(기본 60초)마다 DB에서 다시 읽는다.
리포트 설명 규칙은 report-worker 카운터 `report_explanation_state_total`(`state` 하나, #1031)을 보고, 창(일 23:30 ~ 월 02:00 KST = UTC 일 14:30~17:00) 밖에서는 `day_of_week()`·`hour()` 조건이 값을 비워 NoData(OK)가 된다.
엔드포인트 InService 여부는 보지 않으며 임계값은 30명 배치 실측 전 기준안이다.
Python 표준 라이브러리 검증기만 두며 운영에 Python 서비스를 추가하지 않는다.

## DLQ 경보 켜기

DLQ 규칙은 `prometheus.rabbitmqDlqMetrics.enabled=true`와 함께 `grafana.alerting.rules`에 넣는다.
수집이 꺼진 상태로 `job="rabbitmq-dlq"` 규칙을 넣으면 Helm 렌더가 실패한다.
임계값·지속시간은 운영 결정 전이다. 아래는 **시험 전용 값**이며 운영 values에 그대로 넣지 않는다.

```json
{
  "prometheus": {"rabbitmqDlqMetrics": {"enabled": true}},
  "grafana": {"alerting": {"rules": [
    {"uid": "rabbitmq-dlq-depth", "title": "RabbitMQ dead letter queue depth",
     "expr": "max by (vhost, queue) (rabbitmq_detailed_queue_messages{job=\"rabbitmq-dlq\"})",
     "operator": "gt", "threshold": 0, "for": "10s",
     "summary": "Dead-lettered messages wait for manual inspection or reprocessing; check the queue label."}
  ]}}
}
```

Helm은 `rules` 배열을 values 파일 사이에서 합치지 않고 통째로 바꾼다. 기존 규칙을 모두 함께 적은 목록으로 전달한다(prod `observability.json`은 #185 3개 + #187 13개 + #1028 4개 + #1031 2개).
수집을 켜고 끄면 Prometheus Pod가 다시 만들어진다(설정 reload 장치가 없음). `emptyDir`이면 수집 이력이 초기화된다.

`grafana.alerting.interval`·`groupWait`·`groupInterval`·`repeatInterval`의 기본값은 #185 운영값(1m·30s·5m·4h)과 같다.
검증기만 빠른 값으로 바꿔 렌더한다.

## 격리 검증

```powershell
python infrastructure/gitops/operational-alerts/verify_chart.py --helm <helm-실행파일>
python infrastructure/gitops/operational-alerts/verify_chart.py --helm <helm-실행파일> --baseline <반영한-develop-SHA>
git diff --check
```

`verify_chart.py`는 Helm과 검증용 PyYAML이 필요하다(운영 의존성 아님).

- default·local·prod values 렌더 결과가 `--baseline`(기본 #185 병합 develop `de8e225`)과 리소스 단위로 같은지, `helm lint --strict`가 통과하는지 본다.
  #984 대시보드는 기준·현재 chart 양쪽에서 끄고 비교하며, local·prod의 활성화·provisioning은 별도로 검사한다.
  #730 로컬 재학습 지표와 경보도 기준 비교 때만 끈다. 실제 로컬 값으로는 Prometheus 수집 주소, `app` Job·CronJob 조회 권한, 실패·일정 누락 규칙, Discord 비밀 참조와 발송 설정의 부재를 검사한다.
  prod 앱은 CI·ApplicationSet과 같은 순서로 `prod/<서비스>.json` 다음 `prod/images/<서비스>.json`을 함께 렌더한다.
- prod 규칙 22개를 지속 10초로 줄이고 적체 임계값을 10으로 낮춘 사본을 렌더한다.
  prod values가 #187 규칙을 포함하므로 기준 비교는 `--baseline` 시점의 prod values로 한다.
  provisioning ConfigMap·mount·webhook Secret 참조, DLQ 수집 job·relabel·Pod annotation을 검사한다.
- DLQ relabel이 저장소 `definitions.json`의 `<큐>.dlq`만 남기는지, 수집 없이 DLQ 규칙을 넣으면 실패하는지 본다.
- 이어 렌더된 provisioning·datasource를 `verify.py --chart-bundle`에 넘겨 Docker에서 실제로 평가한다.

`verify.py`는 Docker Linux engine과 고정 이미지 `grafana/grafana:13.3.0`, `prom/prometheus:v3.15.1`,
`rabbitmq:4.3.7-management-alpine`, `python:3.12-slim`이 필요하다. 이미지가 없으면 Docker가 pull한다.
고유 `issue187-<난수>` internal network와 container만 만들고 호스트 포트를 열지 않는다. 종료 시 본인 container/network만 제거한다.
기존 kind/Compose/Secret/볼륨에는 접근하지 않는다.

- 실제 RabbitMQ에 `definitions.json`을 import해 기본 집계 gauge의 큐 라벨 부재와 `/metrics/detailed`의 DLQ 큐 라벨을 확인한다.
- 이 실제 출력을 로컬 대역이 제공해 Prometheus relabel 결과가 DLQ 총 메시지 지표뿐인지 확인한다.
- Grafana rule engine에서 적체 정상→pending→발생→유지(반복 억제)→회복, 로컬 Discord protocol 대역의 발생·회복 수신을 확인한다.
- 한 DLQ만 값을 올려 그 큐만 발생·회복·수신하는지 확인한다.
- 대역 지표로 월 비용 80% 발생·회복, 미산정 호출 증가 발생·누적 유지 중 회복·월초 초기화 미발생(가속 사본은 `[1h]` 창을 `[1m]`로 줄임), 인증 5xx 비율·p95 지연 발생, HTTP 지표 부재 발생을 확인한다.
  5xx·지연 규칙은 5분 rate 창 때문에 회복을 기다리지 않는다.
- 리포트 설명 규칙(#1031)은 창 조건을 Prometheus `time` 지정 조회로 경계 시각마다 확인하고, 가속 사본은 창 조건을 빼고 `[30m]`을 `[1m]`로 줄여
  `NO_TARGET` 제외 비율 발생(`NO_TARGET`을 넣으면 울리지 않는 값), `INCLUDED` 0건 발생, 회복을 확인한다.
- NoData, 잘못된 query, 없는 datasource UID, 재provision 중복 방지, 수집 실패 발생을 확인한다.
  #185의 target 규칙은 `min(up)`이라 scrape job 자체가 사라지면 발생이 아니라 NoData가 된다.
- job 제거 시험은 Prometheus lookback을 시험 전용 10초로 줄인다. 기본 5분 lookback에서는 잔존 기간이 더해질 수 있다.

`--faults-only`는 발생·유지·회복 시험을 건너뛰고 NoData 이후만, `--scrape-only`는 수집 실패·job 제거만 다시 실행한다.
가속 시험값은 운영 정책이 아니다. 실제 팀 Discord 수신·AWS·Langfuse는 이 검사에 포함되지 않는다.

공식 근거: [Grafana provisioning](https://grafana.com/docs/grafana/latest/alerting/set-up/provision-alerting-resources/file-provisioning/),
[RabbitMQ 4.3 metrics](https://www.rabbitmq.com/docs/4.3/prometheus).
