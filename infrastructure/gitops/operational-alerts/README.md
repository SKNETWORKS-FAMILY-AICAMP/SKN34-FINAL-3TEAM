# 운영 경보 provisioning (#187, 아직 배포하지 않음)

설계: [operational-alerts](../../../docs/design/operational-alerts.md).
근거·요구사항별 공백·결정 목록: [보고서](../../../docs/report/issue-187-operational-alerts.md).
Python 표준 라이브러리만 사용하며 운영에 Python 서비스를 추가하지 않는다.

## 생성

운영 임계값·간격은 확정되지 않았다. 아래는 **시험 전용 입력**이다. 승인된 운영 값으로 바꾸기 전 배포하지 않는다.
실제 datasource UID는 Grafana `/api/datasources/name/Prometheus`의 `uid`를 조회해 입력한다.
#171은 고정 UID가 없으므로 임의 UID를 운영에 넣지 않는다.

```json
{
  "environment": "verification",
  "datasource_uid": "issue187-prometheus",
  "backlog_messages": 10,
  "pending_seconds": 10,
  "interval_seconds": 10,
  "group_wait_seconds": 1,
  "group_interval_seconds": 10,
  "repeat_interval_seconds": 300,
  "secret_name": "ops-discord",
  "secret_key": "DISCORD_WEBHOOK_URL"
}
```

```powershell
python infrastructure/gitops/operational-alerts/render.py <승인된-설정.json> <새-출력-폴더>
```

생성되는 `alerting.json`은 Grafana provisioning/alerting에 mount할 파일,
`configmap.json`은 이를 포함하는 ConfigMap, `deployment-patch.json`은 #171 Grafana Deployment용 strategic merge patch다.
같은 출력 폴더를 덮어쓰지 않는다. 출력 파일에 webhook 값은 없으며 `$OPS_DISCORD_WEBHOOK_URL` 참조만 있다.
Secret 미존재/키 누락은 Kubernetes optional=false로 차단하고 빈 값은 시작 guard에서 오류로 종료한다.
실제 webhook을 config·명령 인자·fixture·Git에 넣지 않는다.

#171 병합과 사용자가 허락한 기존 chart의 opt-in 연결을 반영했다.
생성한 `helm-values.json`을 `observability` chart의 추가 values로 전달하면
ConfigMap·mount·Secret env·시작 guard·datasource UID가 함께 연결된다.
기본 `grafana.alerting.enabled=false`이며 local/Argo values를 활성화하지 않았다.
기존 datasource를 사용하는 환경에서는 기존 UID를 그대로 입력한다. 다른 UID로 교체하지 않는다.

```powershell
helm lint infrastructure/gitops/charts/observability -f <출력-폴더>/helm-values.json
helm template observability infrastructure/gitops/charts/observability --namespace observability -f <출력-폴더>/helm-values.json
```

활성화 전에 실제 Secret·승인된 운영 임계값·담당·HTTPS egress를 준비해야 한다.
기존 정책의 Grafana→Prometheus 9090·DNS 허용은 보존하고 Discord HTTPS egress를 별도 검토한다.
실제 배포는 수행하지 않았다. 검토 없이 patch를 직접 적용하지 않는다.
UID는 환경당 단일 Grafana org 1에 `ops187-*`로 고정된다. 같은 org에 여러 환경의 파일을 동시에 올리지 않는다.
규칙별 direct routing을 쓰므로 조직 전체 notification policy tree를 덮어쓰지 않는다.
group_by는 서비스·환경·규칙, 발생과 회복을 전송하고 repeat interval 전 반복을 억제한다.
NoData/Error도 정상으로 숨기지 않는다. Grafana 자체가 중단되면 이 경로로 통보할 수 없다.

## 격리 검증

```powershell
python infrastructure/gitops/operational-alerts/verify.py
python infrastructure/gitops/operational-alerts/verify_chart.py --helm <helm-실행파일>
python infrastructure/gitops/operational-alerts/verify_chart.py --helm <helm-실행파일> --baseline <반영한-develop-SHA>
git diff --check
```

Docker Linux engine과 고정 이미지 `grafana/grafana:13.3.0`, `prom/prometheus:v3.15.1`,
`rabbitmq:4.3.7-management-alpine`, `python:3.12-slim`이 필요하다.
이미지가 없으면 Docker가 pull한다. 고유 `issue187-<난수>` internal network와 container만 생성한다.
호스트 포트를 열지 않으며 검증 클라이언트도 내부 네트워크에서 실행한다. 저장소는 임시 폴더이며 종료 시 본인 container/network만 제거한다.
기존 kind/Compose/Secret/볼륨에는 접근하지 않는다. 재시작·prune하지 않는다.
Prometheus 시험 데이터는 tmpfs이며 생성된 본인 익명 볼륨도 container 삭제 시 함께 제거한다.

실제 RabbitMQ 기본 gauge/type/큐 라벨 부재를 확인하고 실제 Prometheus→Grafana rule engine에서
정상→pending→발생→유지→회복, 로컬 Discord protocol 대역 수신·회복, NoData, 잘못된 query/UID,
재provision 중복 방지, Secret 환경 누락 시작 차단을 확인한다.
누락 지표는 명시적으로 없는 metric을 질의해 Prometheus lookback 잔존값과 구분한다.
job 제거 시험은 lookback을 시험 전용 10초로 단축한다. #171 기본 lookback에서는 탐지까지
최대 기본 5분의 잔존 기간과 pending/알림 대기가 더해질 수 있다.
가속 시험값은 운영 정책이 아니다. Kubernetes Secret 누락의 실제 Pod 상태와 chart 통합,
실제 Discord 수신·AWS·Langfuse는 이 검사에 포함되지 않는다.

실패한 fault 검증만 재개할 때는 `verify.py --faults-only`를 사용한다.
발생·유지·회복 시험을 생략하고 새 격리 환경에서 NoData 이후 분기만 실행한다.
`--scrape-only`는 수집 실패·job 제거 시험만 재개한다.

chart 검증에는 Helm과 검증용 PyYAML이 필요하다(운영 의존성 아님).
`--baseline`은 현재 HEAD에 반영된 commit만 허용하며, 생략하면 최초 #171 병합 SHA와 비교한다.
develop 갱신 후에는 반영한 SHA를 명시해 최신 기준의 비활성 동작 보존도 확인한다.
기본/local 비활성 렌더 결과를 병합 #171 SHA와 리소스 단위로 비교하고,
생성기 CLI 출력의 활성화 values·Secret/UID 오류를 검사한다.
이어 실제 렌더된 ConfigMap의 provisioning/datasource와 Grafana command를 격리 Docker 시험에 전달한다.
Kubernetes Deployment·NetworkPolicy 적용을 검증한 것으로 해석하지 않는다.

공식 근거: [Grafana provisioning](https://grafana.com/docs/grafana/latest/alerting/set-up/provision-alerting-resources/file-provisioning/),
[13.3.0 공식 provisioning 예시](https://github.com/grafana/grafana/blob/v13.3.0/conf/provisioning/alerting/sample.yaml),
[RabbitMQ 4.3 metrics](https://www.rabbitmq.com/docs/4.3/prometheus).
