# 로컬 관측 수집 기반 (#171)

## EKS 최소 관측 구성 (#185)

`environments/prod/observability.json`은 `platform-observability` 노드그룹(`scheduling`의 nodeSelector·toleration)에서 Collector·Prometheus·Grafana를 실행하기 위한 설정이다. SNS·Lambda·Langfuse는 추가하지 않는다. `scheduling` 기본값은 비어 있어 local 배치는 바뀌지 않는다. 기본 local values의 emptyDir 동작은 유지하며 prod만 Prometheus gp3 4Gi·Grafana gp3 1Gi PVC를 사용한다. PVC에 Helm keep을 적용해 uninstall 시 보존한다. 직접 PVC를 삭제하면 StorageClass Delete 정책으로 EBS가 삭제될 수 있다. 보존 PVC를 재사용할 때는 Helm 소유권을 확인한다.

prod 예약량은 CPU 250m·메모리 544Mi, limit 합계 CPU 1250m·메모리 1152Mi다. Prometheus는 3일·2GB 보존 제한을 함께 사용한다. 보존 한도는 WAL·head의 전체 디스크 사용 상한이 아니며 여유 공간을 따로 확인한다. Grafana와 Prometheus는 PVC의 RWO 사용을 위해 Recreate로 갱신한다. 이 구성은 단일 replica여서 재시작·AZ 장애 시 관측 중단이 가능하다.

호출 흐름: 앱 OTLP(활성화된 경우) → Collector:4317/4318 → Prometheus:8889 scrape, RabbitMQ:15692 → Prometheus → Grafana 경보 평가 → Discord HTTPS 웹훅. `observability-platform-network.json`을 platform에 적용해 Prometheus 라벨의 15692 접근만 추가한다. Grafana alerting 활성화 시 DNS·Prometheus 외 공인 IPv4 TCP 443을 허용한다. 기본 NetworkPolicy는 FQDN 필터가 아니므로 Discord 전용 도메인 제한은 아니다. 외부 Ingress는 만들지 않고 운영자는 명시적 kubeconfig의 port-forward로 접근한다.

`observability-credentials` Secret에는 GRAFANA_ADMIN_USER·GRAFANA_ADMIN_PASSWORD를, prod의 discord-alert-webhook Secret에는 DISCORD_WEBHOOK_URL을 안전하게 입력한다. 비밀 값은 Helm values·ConfigMap·Git에 넣지 않는다. admin Secret은 PVC에 저장된 Grafana 사용자의 비밀번호를 자동 회전하지 않는다. 기존 PVC 재사용 시 최초 로그인 정보를 확인한다.

Grafana contact point·notification policy·경보 3개를 파일로 provision한다. target down(3분), RabbitMQ ready messages >100(10분), memory watermark >80%(5분)은 초기 기준이다. no-data/error는 별도 상태로 보고하며 정상으로 숨기지 않는다. 실측 부하 기반 임계값 확정이나 서비스 SLA 검증은 아니다. 등록한 경보와 datasource는 파일에서 수정한다.

2026-11-03 revision 1은 웹훅 권한 대기로 경보가 비활성이었으나, 웹훅 제공 후 revision 2에서 alerting을 활성화했다. Discord URL은 admin Secret과 분리된 discord-alert-webhook의 DISCORD_WEBHOOK_URL 키로 저장한다. 실제 웹훅의 서버·채널 ID를 확인하고 URL을 출력하지 않았다. 경보 3개는 Grafana에서 health=ok·inactive로 평가됐다. 통지·복구 검증 결과는 [#185 보고서](../../../../docs/report/issue-185-aws.md)를 따른다.

현재 AWS 앱의 Java agent는 비활성이며 이 최소 배포에서는 앱을 재시작하지 않는다. Collector scrape 성공만으로 실제 JVM·HTTP 지표 수집을 주장하지 않는다. core·learning agent의 기존 JAVA_TOOL_OPTIONS 병합과 rolling update 여유 자원은 후속으로 다룬다. ALB/RDS CloudWatch datasource·조회 IAM, 전체 앱 계측, 노드 exporter·metrics-server·Langfuse는 이번 chart에 추가하지 않는다.

적용 순서: 관측 Secret 준비 → chart lint/template 및 정책 검토 → namespace·platform 수집 정책 → Helm 배포 → PVC/Ready·Prometheus target/query·Grafana 경보·Discord 수신·기존 앱 및 노드 자원 확인. 자원 압박이나 기존 앱 장애가 발생하면 관측 Deployment를 0으로 축소해 부하를 제거하고 PVC는 보존한다. 앱 자원 예약량을 낮추지 않는다.

## DLQ 큐별 적재 경보 (#187)

`prometheus.rabbitmqDlqMetrics.enabled`(기본 false)를 켜면 기존 `rabbitmq` job은 그대로 두고 같은 15692 포트의
`/metrics/detailed?family=queue_coarse_metrics`를 `rabbitmq-dlq` job으로 수집한다. metric relabel로
`rabbitmq_detailed_queue_messages` 중 `<큐>.dlq`만 남겨 시계열은 정의된 DLQ 수만큼이다. Prometheus→RabbitMQ 15692 허용 범위 안이다.
`grafana.alerting.rules`에 `job="rabbitmq-dlq"` 규칙이 있는데 이 값이 꺼져 있으면 Helm 렌더가 실패한다.
Prometheus는 ConfigMap 변경을 다시 읽지 않으므로 이 값이 켜질 때만 Pod template annotation을 붙여 켜고 끌 때 Pod를 다시 만든다.

`grafana.alerting.interval`·`groupWait`·`groupInterval`·`repeatInterval`은 기본값이 위 운영값(1m·30s·5m·4h)과 같아 기존 렌더를 바꾸지 않는다.
DLQ 규칙 예시·검증 절차는 [경보 검증](../../operational-alerts/README.md)을 따른다. prod values에는 아직 DLQ 수집·규칙을 넣지 않았다.

## 기존 로컬 구성과 검증 이력

이 chart는 검증 전용 kind 클러스터의 `observability` namespace에 OTel Collector, Prometheus, Grafana를 배치한다. Collector의 OTLP 수신(4317/4318)과 Prometheus exporter(8889), RabbitMQ 기존 metrics(15692) 수집, Grafana Prometheus datasource만 포함한다. Grafana는 `observability-credentials` Secret의 `GRAFANA_ADMIN_USER`·`GRAFANA_ADMIN_PASSWORD`를 참조한다. UI는 외부 Ingress 없이 필요한 동안만 port-forward로 조회한다.

Grafana 13.3.0의 저메모리 첫 기동은 60초를 넘어 startup probe를 300초로 두고, local `emptyDir` 데이터 특성에 맞춰 `Recreate` 전략을 사용한다. 실제 전용 kind에서는 세 Pod가 Ready였고 Collector→Prometheus 합성 gauge 값 7과 Grafana datasource 등록을 확인했다. [검증 범위와 실패 수정 기록](../../../../docs/report/local-platform.md#9-관측-171)을 따른다.

로컬 Prometheus와 Grafana 데이터는 각각 `emptyDir`이어서 Pod 재생성 시 사라진다. 운영 장기 보관·EKS 자원과 Langfuse 자체 호스팅은 #185 환경에 맞춰 별도로 구성한다. Langfuse 공식 chart의 최소 자원 요구는 현재 Docker 메모리 한도보다 크므로 이 로컬 chart에 숨겨서 추가하지 않는다.

현재 Collector는 **metrics 수신만** 구성한다. 공통 앱 chart가 core·learning에 Java agent를 주입해 OTLP metrics를 보내도록 정의했지만 아직 Pod 실행·수집을 확인하지 않았다. AI·scoring·report에는 exporter가 없고, local trace export는 꺼져 있다. RabbitMQ는 기존 `rabbitmq_prometheus` plugin과 Service port를 사용한다. AI 포함 나머지 서비스 계측 연결 및 Langfuse trace 저장·조회는 후속 검증이 필요하다. 이 chart만 렌더링하거나 기동한 결과를 계측 완료로 취급하지 않는다.

EKS에서 Langfuse web과 프로젝트 키가 준비되면 `collector.traces.enabled`를 켜고 내부 `/api/public/otel` endpoint 및 기존 Secret의 Basic Authorization 헤더를 지정한다. 이때 Collector는 OTLP traces를 Langfuse v4 ingestion으로 보내며 `x-langfuse-ingestion-version: 4`를 붙인다. 현재 local values는 이 경로를 활성화하지 않는다. endpoint·Secret·Langfuse Pod label·NetworkPolicy를 실제 #185 배포 결과와 대조하고 저장·조회가 확인되기 전에는 trace 완료로 보지 않는다.

이미지 고정 근거: [OTel Collector v0.164.0](https://github.com/open-telemetry/opentelemetry-collector/releases/tag/v0.164.0), [Prometheus v3.15.1](https://github.com/prometheus/prometheus/releases/tag/v3.15.1), [Grafana v13.3.0](https://github.com/grafana/grafana/releases/tag/v13.3.0).

Discord 알림의 Source/Silence 링크는 외부 Grafana Ingress를 만들지 않아 localhost:3000을 가리킨다. 수신자가 바로 공개 웹으로 접근할 수 있는 링크가 아니다. 운영자는 명시적 EKS kubeconfig로 observability의 svc/grafana를 로컬 3000:3000에 port-forward한 뒤 접근한다. Grafana를 공개하기 위해 임의 Ingress나 인증 우회를 추가하지 않는다.
