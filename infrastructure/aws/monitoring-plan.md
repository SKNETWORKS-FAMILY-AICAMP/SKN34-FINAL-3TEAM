# AWS 데모 경보·로그 보존 설정안 (#185)

> 2026-11-03 후속 결정: 아래 SNS→Lambda 중계와 CloudWatch 경보 직접 생성 제안은 **채택하지 않는다**. 기존 설계의 Prometheus·Grafana→Discord를 현재 EKS 노드에 먼저 배포한다. 실행 설정은 [prod 관측 values](../gitops/environments/prod/observability.json)와 [관측 chart](../gitops/charts/observability/README.md)를 따른다. 아래 단가·관측치는 조사 이력이며 적용 완료 상태가 아니다. CloudWatch Logs 14일 보존 역시 이번 관측 배포에 포함하지 않는다.

2026-11-03 작성. **미적용 제안**이다. 계정 347161580747 / ap-northeast-2의 실제 지표를 읽었으며 AWS 설정 변경·알림 발송은 하지 않았다. [경보 JSON](alarms.proposed.json)은 검토용 배열이며 AWS CLI 단일 요청 파일이 아니다. ActionsEnabled=false, action 목록은 비어 있다. 수신 SNS를 연결하고 검토하기 전 배포하지 않는다.

## 관측 근거

조회 범위는 2026-11-02 19:52:17~2026-11-03 19:52:17 KST, CloudWatch GetMetricStatistics period=300초다. RDS·로그는 288개 구간, ALB는 14개 구간만 반환했다. 전체 24시간의 ALB 가용성·실제 부하 성능 검증으로 해석하지 않는다.

| 지표 | 통계·관측 결과 |
|---|---|
| HealthyHostCount / UnHealthyHostCount | 5분 Minimum 정상 타깃 항상 1, Maximum 비정상 항상 0 (각 14개) |
| RequestCount | 5분 Sum 총 202건, 구간 최대 47건 |
| HTTPCode_ELB_5XX_Count / HTTPCode_Target_5XX_Count | 반환 데이터 포인트 0개. 누락을 측정된 0으로 기록하지 않음 |
| RDS CPUUtilization | 5분 Average의 평균 4.76%, 최대 5.63% |
| FreeStorageSpace | 5분 Minimum의 최소 18,297,618,432 bytes ≈ 17.04GiB |
| DatabaseConnections | 5분 Maximum의 최대 28, 마지막 25 |
| FreeableMemory | 5분 Minimum의 최소 1,003,008,000 bytes ≈ 0.934GiB |
| CPUCreditBalance | 5분 Minimum의 최소 35.20, 마지막 471.57 |
| EKS IncomingBytes | Sum 1,317,689,629 bytes/24h ≈ 1.227GiB/일 |

ALB `app/sagomungchi-demo-core/1eda1209ceafe116`, target group `targetgroup/k8s-app-coreserv-98f92e4f50/ea8f0fa098ea9200`, DB `sagomungchi-demo-db`를 지정했다. 서울 리전 경보는 현재 0개, EKS 로그 그룹 `/aws/eks/sagomungchi-demo-eks/cluster`의 보존 기간은 미설정이며 storedBytes=118,890,065였다.

## 경보 6개 제안

아래는 초기 데모 운영 기준이다. 짧고 저부하인 관측치만으로 최적 임계값을 계산한 것은 아니다. 실제 부하·배포·알림 빈도를 보고 조정한다.

| 이름 접미사 | 조건 | 평가 | 근거·누락 처리 |
|---|---|---|---|
| alb-no-healthy-target | HealthyHostCount Minimum < 1 | 1분 × 3/3 | 현재 정상 타깃 1개. missing은 INSUFFICIENT_DATA, 정상으로 간주하지 않음 |
| alb-5xx | HTTPCode_ELB_5XX_Count Sum ≥ 5 | 5분 × 1/1 | ALB 생성 오류. 적은 트래픽에서 비율보다 절대 건수로 시작, 누락 notBreaching |
| target-5xx | HTTPCode_Target_5XX_Count Sum ≥ 5 | 5분 × 1/1 | 앱 생성 오류를 별도로 구분, 누락 notBreaching |
| rds-cpu-high | CPUUtilization Average ≥ 80% | 5분 × 3/3 | 현재 최대 5.63%; 지속 고부하 경고, 누락 missing |
| rds-storage-low | FreeStorageSpace Minimum < 5GiB | 5분 × 2/2 | 현재 약 17GiB, 할당 20GiB. 자동확장만 믿지 않고 조사, 누락 missing |
| rds-connections-high | DatabaseConnections Maximum ≥ 60 | 5분 × 3/3 | 관측 최대 28 대비 증가 감지. DB max_connections 비율 경보는 아님, 누락 missing |

ALB는 유휴 상태나 등록 타깃 부재 시 지표가 누락될 수 있다. healthy count 경보만으로 외부 가용성 감시가 완성되지 않는다. 1분 해상도의 실제 상태 평가는 적용 후 확인해야 한다. DB max_connections 실제 값은 이번에 SQL로 조회하지 않았다. 앱 6개 readiness·RabbitMQ 큐 적체·PVC 용량의 수집기는 이번 범위에 추가하지 않는다.

## Discord 연결과 권한

사용자가 지정한 Discord 서버는 `최종`(1557590050034684007)이다. 사용자가 새 알림 채널을 만들 예정이며 이름은 `aws-alerts`를 제안했다. **채널 ID·웹훅은 아직 미확정**이다. 현재 연결된 Discord Bridge는 조회 도구만 제공하므로 웹훅 생성·경보 전송에는 사용할 수 없다.

제안 흐름: CloudWatch ALARM/OK 전이 → 전용 SNS topic → Lambda 변환 → Discord webhook. SNS HTTP 알림과 Discord webhook의 payload 계약이 달라 직접 SNS HTTPS 구독으로 연결하지 않는다.

- 신규 자원: SNS topic·Lambda 구독, Lambda 함수·로그 그룹, 전용 IAM 실행 역할, Secrets Manager secret 1개. 아직 만들지 않았다.
- 실행 역할은 해당 secret의 GetSecretValue와 해당 함수 로그 스트림 작성만 허용한다. Lambda invoke 권한은 해당 SNS topic·계정으로 제한한다. 기존 EKS 앱 역할에 권한을 추가하지 않는다.
- Lambda는 VPC 밖에서 실행해 기존 NAT·EKS에 의존하지 않도록 제안한다. 새 NAT·API Gateway·서버는 필요하지 않다.
- 웹훅 URL은 secret으로 보관하고 Git·채팅·함수 로그에 남기지 않는다. 전달 내용은 경보명·상태·시각·리소스·지표 수준으로 제한하고 학생 데이터·로그 원문·토큰을 보내지 않는다. 멘션은 비활성화한다.
- 전송 실패를 성공으로 처리하지 않는다. HTTP timeout·비정상 상태·429를 명시적으로 실패 처리하고 재시도·실패 이벤트 보존을 구현 단계에서 확정한다. 중복 전달 가능성을 고려해 경보명·전이 시각을 표시한다.
- CloudWatch 경보는 자동 재시작·확장·DB 변경 action을 갖지 않는다. 수신 확인용 합성 ALARM/OK 시험 메시지를 운영 장애와 구분해 보낼 계획이다.

## 로그 보존과 비용

제안: 기존 EKS control-plane 로그와 신규 중계 Lambda 로그를 **14일 보존**한다. EKS 로그 수집 종류(audit/authenticator)는 유지한다. 보존 기간이 지난 로그는 삭제 대상이 되므로 적용 전에 이 보존 정책을 확정한다. 로그 보존 단축은 수집 요금 절감이 아니다.

2026-11-03 AWS Pricing API에서 regionCode=ap-northeast-2로 확인한 단가:

| 항목 | 단가·추정 |
|---|---|
| 표준 경보 | APN2-CW:AlarmMonitorUsage = $0.10/metric-month → 6개 월 $0.60 |
| 기존 EKS 로그 수집 | APN2-DataProcessing-Bytes = $0.76/GB. 관측 1.227GiB/일 × 30일 × $0.76 ≈ 월 $27.98. 기존 발생 비용이며 신규 경보 비용과 구분 |
| 로그 저장 | APN2-TimedStorage-ByteHrs = $0.0314/GB-month. 실제 과금 저장량·압축·수명에 따라 달라 일일 수집량으로 확정 계산하지 않음 |
| 웹훅 secret | 공개 요금 $0.40/secret-month + API 호출 비용 |
| 중계 | SNS·Lambda 요청/실행·로그 비용 별도. 이벤트 수·실행 시간이 미측정이므로 총액 상한으로 표현하지 않음 |

경보와 secret의 고정 단가 부분은 합계 약 $1.00/월이다. 무료 구간·계정 크레딧·세금·환율은 제외했다. 로그 수집 월 추정은 현재 속도 유지 가정이며 실제 청구액이 아니다. 신규 중계의 요청·실행·실패 보존 비용은 최종 구성 시 추가 산정한다.

## 적용·최종 검증 순서

1. 새 Discord 채널 ID·웹훅 생성 권한과 14일 보존, 신규 SNS/Lambda/IAM/Secret 범위·비용을 확정한다.
2. 중계 구현·실패 처리·최소 권한과 대상 SNS action을 연결한 경보 설정을 완성한다. 웹훅은 안전한 입력 경로로 저장한다.
3. 구현 완료 후 로컬 payload·오류 처리 테스트, AWS 설정 대조, 합성 ALARM/OK의 Discord 도착과 실패 처리 검증을 함께 수행한다. 실제 ALB/RDS 장애를 일으키지 않는다.
4. 로컬 테스트·실제 AWS 적용·Discord 수신 결과를 나눠 보고한다. 미확인 경로가 있으면 완료로 표시하지 않는다. 경보 제거로 과금은 중단할 수 있지만, 보존 만료로 삭제된 로그는 retention을 되돌려도 복구되지 않는다.

참고: [ALB 지표](https://docs.aws.amazon.com/elasticloadbalancing/latest/application/load-balancer-cloudwatch-metrics.html), [SNS payload](https://docs.aws.amazon.com/sns/latest/dg/http-notification-json.html), [Discord webhook](https://github.com/discord/discord-api-docs/blob/main/developers/resources/webhook.mdx), [CloudWatch 요금](https://aws.amazon.com/cloudwatch/pricing/), [Secrets Manager 요금](https://aws.amazon.com/secrets-manager/pricing/), [Lambda 요금](https://aws.amazon.com/lambda/pricing/).
