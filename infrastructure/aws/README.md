# AWS 데모 진입·저장소 구성

2026-11-03 실제 계정의 설정 보존이다. Terraform/CloudFormation 등 새 실행 계층을 도입하지 않았다. `demo-observed.json`은 RDS·S3 관측 결과이며 배포 명령 입력이 아니다.

## 외부 요청 흐름

`https://d3jf0rnm6vhd9v.cloudfront.net` → 정적 경로는 비공개 S3 웹 버킷(OAC), `/api/*`는 ALB → app/core-service:8080.

- CloudFront ID: `EW2QD9OAPEVRK`. 웹과 API가 같은 origin을 사용하므로 Secure 인증 쿠키를 사용한다.
- API는 CachingDisabled, AllViewerExceptHostHeader, 압축 false, origin read timeout 60초. ALB idle timeout 120초, XFF preserve.
- ALB inbound는 CloudFront origin-facing prefix list `pl-22a6434b`로 제한한다. 추가로 CloudFront와 ALB rule의 `X-Sagomungchi-Origin` 값이 일치해야 한다.
- CloudFront→ALB는 현재 HTTP이며 전 구간 TLS는 아니다. 사용자→CloudFront는 HTTPS. custom domain·ALB 인증서 적용은 별도 결정이다.
- `spa-router.js`는 배포 때 사용한 CloudFront Function 소스다. extensionless 웹 경로를 index.html로 연결하고 `/internal`, `/actuator` 직접 접근을 막는다. API behavior에는 이 함수를 연결하지 않는다.

## redacted 파일 취급

`cloudfront-config.redacted.json`, `core-ingress.redacted.json`은 **직접 적용 금지**인 검토용 설정이다. origin header 실제 값은 `__SET_ORIGIN_HEADER_OUTSIDE_GIT__`로 치환했다. Git 게시 전 실제 AWS endpoint·리소스 이름·subnet/prefix list/OAC/policy 식별값도 placeholder로 바꿨다. 계정 ID와 기능 연결에 필요한 논리 이름·설정값은 유지한다. placeholder 자체를 배포하면 안 된다.

재구성 시 실제 리소스 식별값을 대상 계정에서 조회하고, 기존 비밀 값을 출력하지 않고 안전한 별도 작업 파일에서 양쪽 동일 값으로 주입한다. CloudFront update는 최신 ETag를 먼저 조회해야 한다. 실제 값이 들어 있는 임시 파일·CLI 출력·Ingress 전체 YAML을 커밋하지 않는다. 별도 demo-observed.json과 prod values는 해당 계정의 비밀이 아닌 배포 인벤토리이며 이 두 redacted 예제와 용도가 다르다.

## RDS·S3

- RDS `sagomungchi-demo-db`: PostgreSQL 17.11, db.t4g.small, Single-AZ, 비공개, 암호화, 백업 7일. 삭제 보호 false. PITR 복원 시각은 JSON에 기록했지만 실제 복원 시간·RPO/RTO 달성은 미검증이다.
- `sagomungchi-demo-347161580747-{web,missions,reports,models}`: 버전 관리·Public Access Block 상태는 JSON 참고. 웹만 CloudFront OAC로 제공하며 reports/models는 앱 IAM 및 서비스 권한 검사를 통한다.
- VPC의 available NAT GW는 1개이며 JSON에 ID·subnet을 기록했다. AZ 장애 시 외부 호출 복구 검증은 하지 않았다.
- S3 bucket policy, lifecycle, IAM policy 전체와 RDS 생성 절차의 IaC는 아직 미완료다. 관측 파일을 재생성 완료 근거로 사용하지 않는다.

## 배포·복구 유의 사항

초기 입력·설치 순서·미완료 선행 조건은 [prod 초기 배포 절차](../gitops/environments/prod/README.md#초기-배포-재현-절차-185), 단기 중단·데이터 보존·비용·재개 계획은 [EKS 데모 종료·축소안](../eks/README.md#데모-종료축소재개-실행안-185)을 따른다. 두 문서는 절차이며 신규 환경 재현이나 실제 축소 실행 결과가 아니다.

웹 배포는 assets를 먼저 업로드하고 index.html을 마지막에 교체한다. 현재는 no-cache 응답이며 API 캐시는 비활성이다. 이전 해시 assets는 즉시 삭제하지 않는다. 코드 SHA·빌드 설정·S3 버전 및 이미지 digest를 함께 기록한다. 현재 core와 웹의 이용권 수정은 미커밋 상태이므로 소스 재현성 후속 작업이 필요하다.

Google OAuth의 승인된 origin은 위 HTTPS 주소, redirect URI는 `/api/v1/auth/google/callback`, `/api/v1/auth/google/reauth/callback`이다. Client secret은 `sagomungchi/demo/app/google`에만 두고 Git에 넣지 않는다.

## 생성·관리 범위 추가 확인 (2026-11-03)

기존 프로필로 계정 347161580747을 확인한 뒤 AWS API를 읽기 전용으로 조회했다. 서울 리전 `cloudformation describe-stacks` 결과는 빈 목록이다. 이것만으로 모든 리소스가 수동 생성되었다고 단정하지 않는다. Terraform state·최초 생성 기록·담당자는 아직 확인하지 않았으며, 기존 자원의 IaC import나 재생성은 수행하지 않았다.

| 범위 | 추가 관측 | 재현·관리 시 남은 일 |
|---|---|---|
| VPC | `vpc-0f4d9134097830b4b`, 10.20.0.0/16. public 10.20.0.0/20(2a)·10.20.16.0/20(2b)는 IGW, private 10.20.128.0/20(2a)·10.20.144.0/20(2b)는 동일 NAT로 기본 경로 연결 | 생성 주체·SG·NACL·endpoint policy 전체 보존 및 관리 책임 확정 |
| S3 경로 | private route table 두 개에 S3 Gateway endpoint `vpce-0dab53d8da86d39c8` 연결, available | S3 통신을 모두 NAT 경유로 설명하지 않는다. endpoint policy와 IAM을 함께 검토 |
| RDS 네트워크 | 위 private subnet 두 개를 사용하는 `sagomungchi-demo-db-subnet-group`. SG `sg-022d3c9a8cf111b47`의 5432 ingress는 EKS SG `sg-086c7c83b3638da59`만 참조 | 복원 DB의 subnet group·SG를 원본과 대조. public 접근을 새로 허용하지 않음 |
| RDS 저장·설정 | gp3 20GiB, 최대 자동확장 1000GiB, `default.postgres17` in-sync, TagList 빈 목록 | 최대 용량·비용 한도 검토. KMS key 접근과 DB별 계정·migration·데이터 초기화 절차 확인 |
| S3 | 네 버킷 모두 기본 암호화 AES256, lifecycle 없음(`NoSuchLifecycleConfiguration`) | 현재/이전 버전 보존 기간과 삭제 정책 확정 후 lifecycle 검토. 버전 관리만으로 별도 백업·복구 성공을 주장하지 않음 |
| S3 policy | web은 CloudFront 서비스의 GetObject를 배포 `EW2QD9OAPEVRK` SourceArn으로 제한, IsPublic=false. 나머지 세 버킷은 bucket policy 없음(`NoSuchBucketPolicy`) | bucket policy 부재를 공개 접근이나 IAM 접근 불가로 해석하지 않는다. 기존 Public Access Block·IAM과 함께 평가 |

## 관측·복구 우선순위

아래는 초기 점검 당시의 후속 후보 목록이며 #185의 완료 조건 전체를 뜻하지 않는다. [경보·로그 보존 설정안](monitoring-plan.md)과 [미적용 경보 JSON](alarms.proposed.json)의 SNS/Lambda 방안은 보류했다. 이후 기존 설계의 Grafana→Discord 연결과 최소 경보를 배포했다. 전체 경보·추적은 #187, 자동 배포는 #186, 노드 자동확장은 #211에서 다룬다. 실제 완료 근거는 [#185 보고서](../../docs/report/issue-185-aws.md)의 후속 배포 절을 따른다.

1. **경보와 로그 보존:** 서울 리전 `cloudwatch describe-alarms`의 metric/composite 목록이 모두 비어 있다. EKS `/aws/eks/sagomungchi-demo-eks/cluster` 로그 그룹은 retentionInDays 미설정이다. RDS는 Enhanced Monitoring interval=0, Performance Insights=true, CloudWatch log export 없음이다. 먼저 ALB unhealthy target·5xx, RDS 여유 저장공간·연결·CPU, 앱 readiness 및 큐 적체의 수집 가능 지표와 알림 수신 담당을 정한다. 임계값은 실측 후 정하고 로그 보관 기간·알림 채널·비용을 정한 뒤 구성한다. 이번 조회는 CloudFront용 us-east-1 경보나 외부 알림 도구까지 조사한 것은 아니다.
2. **RDS 격리 복원:** 자동 스냅샷 두 개가 available이며, 자동 백업 API의 복원 범위는 2026-11-02 17:55:20.511~2026-11-03 19:32:50 KST였다. 백업 보존은 7일, backup window는 14:54–15:24 UTC(23:54–다음 날 00:24 KST), maintenance window는 금요일 13:31–14:01 UTC다. 이 범위는 조회 시점 값이므로 복원 직전에 다시 조회한다. 복원 대상 ID·시각·기간·비용·정리 담당을 확정한 뒤 별도 DB에 복원하고 TLS 접속, 서비스별 스키마·migration·건수·표본 정합성, 소요 시간을 기록한다. 원본 endpoint나 앱 Secret을 시험 DB로 변경하지 않는다. 복원 자원 생성·삭제는 이번에 실행하지 않았다.
3. **PVC·S3 복구:** 서울 리전 AWS Backup plan 목록은 비어 있다. 이것만으로 별도 EBS snapshot·DLM·외부 백업이 없다고 단정하지 않는다. RabbitMQ/Redis PVC의 volume ID·AZ·snapshot/일관성 확보 방법을 먼저 확인한다. gp3 reclaimPolicy가 Delete이므로 복구 근거 없이 PVC를 삭제하지 않는다. S3 복구 시험은 합성 객체의 version ID·내용 비교로 진행할 범위를 정하며 실제 보고서·학습 데이터의 삭제나 부모 재생성 한도 소비를 하지 않는다.
4. **확장·자동 배포:** 위 관측과 복구 기준을 정한 다음 노드그룹 분리·자동확장·Argo CD 도입 범위를 결정한다. 현재 인벤토리만으로 전체 환경 복원이 가능하다고 판단하지 않는다.

조회 근거: EC2 `describe-subnets`, `describe-route-tables`, `describe-vpc-endpoints`, `describe-security-groups`; RDS `describe-db-instances`, `describe-db-snapshots`, `describe-db-instance-automated-backups`; S3 `get-bucket-encryption`, `get-bucket-lifecycle-configuration`, `get-bucket-policy-status`, 웹 `get-bucket-policy`; CloudWatch `describe-alarms`; Logs `describe-log-groups`; Backup `list-backup-plans`. Secret 값·S3 객체 본문은 조회하지 않았다.

## #185 검증 도구

- `verify-viewer-ip.ps1`: 명시한 EKS context에서 Redis 카운터를 읽고 CloudFront 기기 등록 API에 유효하지 않은 코드로 두 번 요청한다. 직접 확인한 접속자 공인 IPv4를 `-ViewerIp`, 전용 kubeconfig를 `-Kubeconfig`로 전달한다. 두 번째 요청에는 위조 XFF를 넣는다. 실제 viewer 카운터 +2, 위조 IP 카운터 불변과 PAIRING_CODE_INVALID 응답을 모두 확인한다. 기기·페어링을 생성하지 않지만 IP별 10분 한도에서 2회를 사용한다. 동시 요청·카운터 TTL 만료·프록시 egress 차이가 있으면 실패로 보고 조사하며 카운터를 임의로 지우지 않는다.
- `audit-demo-data.sql`: demo의 core_app 계정으로 read-only transaction에서 계정·학생의 demo flag별 건수, 결제 건수와 DB CONNECT 권한만 조회한다. 개인정보를 출력하지 않는다. demo flag가 false라고 실제 사용자라고 단정하거나, 별도 DB라는 이유만으로 모든 데이터가 demo라고 단정하지 않는다. 실제 배포의 외부 키·접속 대상·데이터 생성 절차와 함께 해석한다.
- `mark-confirmed-demo-data.sql`: 사용자가 테스트용이라고 확인한 기존 학부모 1명·학생 2명의 flag를 보정한 일회성 SQL이다. 자동 초기화나 일반 운영 DB에서 실행하지 않는다. 새 가입자의 demo 여부를 자동 설정하는 기능이 아니다.
- `scan-repository-secrets.py`: Python 표준 라이브러리와 Gitleaks 8.30.1로 이력·현재 파일을 분리 검사한다. 예: `python infrastructure/aws/scan-repository-secrets.py --gitleaks <실행파일> --reports <저장소밖-보고서폴더>`. `.gitleaks.toml`의 예외는 검토한 합성 값과 비밀이 아닌 식별자에 한정한다. Git 무시 파일·원격의 미수신 이력은 검사 범위 밖이다.
