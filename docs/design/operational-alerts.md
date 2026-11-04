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
기본 `rabbitmq` job과 전체 per-object 지표는 바꾸지 않는다. 시계열은 정의된 DLQ 수(현재 6개)만큼이다.
규칙은 `max by (vhost, queue)`로 큐마다 경보 인스턴스를 만든다. 큐 이름은 시계열 라벨로 알림에 실린다.
메시지 수는 ready+unacked 합계이며 메시지 나이·재처리 지연은 의미하지 않는다. scrape 실패나 지표 부재는 0이 아니라 NoData로 남는다.
업무 ID·메시지 내용은 label에 넣지 않는다. 운영 임계값·지속시간은 결정 전이며 prod values에는 아직 넣지 않았다.

## 남은 경계

- #185 규칙의 target 감시는 `min(up{job=~...})`라 scrape job 자체가 사라지면 발생이 아니라 NoData로 보고된다.
- 조직 notification policy를 chart가 소유한다. 서비스별 담당이 정해지면 policy 하위 route로 나눈다.
- 업무별 오류율·지연, 월 비용, 동기·비동기 trace 저장 검증은 이 구성의 완료 범위가 아니다.
