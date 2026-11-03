# #187 독립 경보 provisioning 경계

기준: architecture 1.6·4.6, functional-spec NFR-OPS-04/05·FN-ADM-19·P10/P13.
기존 Grafana Alerting → Discord 경로를 사용한다. 새 운영 서비스·의존성·공개 API는 추가하지 않는다.
사용자 공지 FN-SUP-07과 별개이며 앱 알림을 변경하지 않는다.

#171 PR #204의 참조 head는 `4787b523828883c6cb2dd4c5732133cb94dd3952`다.
작업 중 `b35e381aa37cf22b5816d2750b46d18f2c11fa5c`로 develop에 병합되어 본인 브랜치에도 이력을 보존해 반영했다.
`infrastructure/gitops/operational-alerts/`에서 독립 파일을 준비했다.
사용자가 #171 병합 후 기존 chart의 opt-in 연결을 명시적으로 허락했다.
#171 chart를 복제하지 않고 기존 chart에 기본 비활성인 연결을 추가한다.
생성기는 배포 시 사용할 JSON provisioning, ConfigMap, Secret 참조 Deployment 패치를 만든다.
패치는 검토 산출물이며 자동 적용하지 않는다. 생성한 helm-values.json은 동일 provisioning·UID·Secret 참조를 chart에 전달한다.
기존 chart는 enabled=false일 때 기존 datasource·Deployment·NetworkPolicy 동작을 유지한다.
활성화 시 기존 datasource의 실제 UID를 명시적으로 받고 규칙의 datasource UID와 대조한다.
실제 클러스터 적용·Discord 발송·HTTPS egress 변경은 이번 허가 범위에서 제외한다.

Grafana datasource UID는 #171에 고정값이 없다. 실제 datasource 조회 결과를 필수 입력으로 받는다.
Grafana 13.3.0 file provisioning의 stable rule/contact UID와 규칙별 notification_settings를 사용한다.
전체 notification policy tree를 덮어쓰지 않고 각 규칙을 전용 contact point로 직접 라우팅한다.
service/environment label과 알림 묶음·지속·반복 간격은 설정 입력이다. 평가 주기는 Grafana 기본 base interval에 맞춘 10초 배수다.
인프라 담당 실명·멘션과 서비스별 담당은 결정 전까지 넣지 않는다.
조회 오류는 Error, 지표 부재는 NoData로 유지한다. 0 또는 정상으로 바꾸지 않는다.
scrape job 자체가 사라지면 absent로 장애 신호를 만들고, Grafana/Prometheus 전체 중단을 스스로 감지한다고 주장하지 않는다.

Secret은 observability namespace의 기존 Secret을 이름·키로만 참조한다.
optional=false로 누락 시 Pod 구성을 실패시킨다. 값은 파일에 저장하지 않는다.
Grafana의 Discord HTTPS egress는 #171 기본 거부 정책에 없어 운영 연결 때 별도 허가·검토가 필요하다.
현재 patch만으로 실제 발송이 가능하다고 간주하지 않는다.

현재 scrape는 RabbitMQ 기본 /metrics 집계이므로 전체 ready 메시지 gauge의 합계만 사용한다.
이는 DLQ·retry·일반 큐를 구분하지 못하고 메시지 나이·업무 지연도 의미하지 않는다.
DLQ 적재는 별도 opt-in scrape job `rabbitmq-dlq`로 본다. 같은 RabbitMQ 15692 포트의 `/metrics/detailed`에서
`queue_coarse_metrics` family만 요청하고, metric relabel로 `rabbitmq_detailed_queue_messages` 중 `<큐>.dlq`(architecture 1.6 명명)만 남긴다.
#171 기본 `rabbitmq` job과 전체 per-object 지표는 바꾸지 않는다. 시계열은 정의된 DLQ 수(현재 6개)만큼이다.
규칙은 `max by (vhost, queue)`로 큐마다 경보 인스턴스를 만들고 임계값 `dlq_messages`는 필수 입력이다(0 허용, 숨은 기본값 없음).
메시지 수는 ready+unacked 합계이며 메시지 나이·재처리 지연은 의미하지 않는다. scrape 실패나 지표 부재는 0이 아니라 NoData로 남는다.
업무 ID·메시지 내용은 label에 넣지 않으며 큐 이름만 쓴다.
업무별 오류율·지연, 월 비용, 동기·비동기 trace 저장 검증은 이 독립 기능의 완료 범위가 아니다.
