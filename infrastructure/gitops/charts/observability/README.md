# 로컬 관측 수집 기반 (#171)

이 chart는 검증 전용 kind 클러스터의 `observability` namespace에 OTel Collector, Prometheus, Grafana를 배치한다. Collector의 OTLP 수신(4317/4318)과 Prometheus exporter(8889), RabbitMQ 기존 metrics(15692) 수집, Grafana Prometheus datasource만 포함한다. Grafana는 `observability-credentials` Secret의 `GRAFANA_ADMIN_USER`·`GRAFANA_ADMIN_PASSWORD`를 참조한다. UI는 외부 Ingress 없이 필요한 동안만 port-forward로 조회한다.

Grafana 13.3.0의 저메모리 첫 기동은 60초를 넘어 startup probe를 300초로 두고, local `emptyDir` 데이터 특성에 맞춰 `Recreate` 전략을 사용한다. 실제 전용 kind에서는 세 Pod가 Ready였고 Collector→Prometheus 합성 gauge 값 7과 Grafana datasource 등록을 확인했다. [검증 범위와 실패 수정 기록](../../../../docs/report/issue-171-app-deployment.md)을 따른다.

로컬 Prometheus와 Grafana 데이터는 각각 `emptyDir`이어서 Pod 재생성 시 사라진다. 운영 장기 보관·EKS 자원과 Langfuse 자체 호스팅은 #185 환경에 맞춰 별도로 구성한다. Langfuse 공식 chart의 최소 자원 요구는 현재 Docker 메모리 한도보다 크므로 이 로컬 chart에 숨겨서 추가하지 않는다.

현재 Collector는 **metrics 수신만** 구성한다. 공통 앱 chart가 core·learning에 Java agent를 주입해 OTLP metrics를 보내도록 정의했지만 아직 Pod 실행·수집을 확인하지 않았다. AI·scoring·report에는 exporter가 없고, local trace export는 꺼져 있다. RabbitMQ는 기존 `rabbitmq_prometheus` plugin과 Service port를 사용한다. AI 포함 나머지 서비스 계측 연결 및 Langfuse trace 저장·조회는 후속 검증이 필요하다. 이 chart만 렌더링하거나 기동한 결과를 계측 완료로 취급하지 않는다.

EKS에서 Langfuse web과 프로젝트 키가 준비되면 `collector.traces.enabled`를 켜고 내부 `/api/public/otel` endpoint 및 기존 Secret의 Basic Authorization 헤더를 지정한다. 이때 Collector는 OTLP traces를 Langfuse v4 ingestion으로 보내며 `x-langfuse-ingestion-version: 4`를 붙인다. 현재 local values는 이 경로를 활성화하지 않는다. endpoint·Secret·Langfuse Pod label·NetworkPolicy를 실제 #185 배포 결과와 대조하고 저장·조회가 확인되기 전에는 trace 완료로 보지 않는다.

이미지 고정 근거: [OTel Collector v0.164.0](https://github.com/open-telemetry/opentelemetry-collector/releases/tag/v0.164.0), [Prometheus v3.15.1](https://github.com/prometheus/prometheus/releases/tag/v3.15.1), [Grafana v13.3.0](https://github.com/grafana/grafana/releases/tag/v13.3.0).

## 선택 경보 연결 (#187)

`grafana.alerting.enabled`는 기본 false다. [경보 생성기](../../operational-alerts/README.md)의
`helm-values.json`을 추가 values로 전달하면 기존 Grafana에 rule/contact provisioning ConfigMap을 mount하고
필수 Secret 환경 참조·빈 값 시작 차단과 명시적 Prometheus datasource UID를 연결한다.
기존 환경에서는 Grafana API로 확인한 기존 datasource UID를 사용하며 UID를 임의 변경하지 않는다.
규칙과 datasource UID가 다르거나 Secret 참조·provisioning이 누락되면 Helm 렌더가 실패한다.
알림은 규칙별 직접 라우팅을 사용하며 조직 전체 notification policy tree는 덮어쓰지 않는다.

local values/Argo 경보 활성화·실제 클러스터 적용·Discord 수신은 수행하지 않았다.
현재 Grafana NetworkPolicy에는 Discord HTTPS egress가 없으므로 이 값만 켜도 운영 발송이 되는 것은 아니다.
운영 임계값·Secret·담당·egress 승인과 실제 발송 허락 후 통합 검증한다.
전체 요청·오류율·DLQ별 경보·월 비용·trace 저장은 [#187 보고서](../../../../docs/report/issue-187-operational-alerts.md)의 후속 범위다.
