# AWS 데모 진입·저장소 구성

2026-11-03 실제 계정의 설정 보존이다. Terraform/CloudFormation 등 새 실행 계층을 도입하지 않았다. `demo-observed.json`은 RDS·S3 관측 결과이며 배포 명령 입력이 아니다.

## IaC: eksctl + AWS CLI 스크립트 (#185)

EKS는 [eksctl 설정](../eks/cluster.json), 나머지는 `demo-stack.json`(원하는 상태)과 `iam/`(trust·policy 원문)이 정의한다. `demo_stack.py`는 Python 표준 라이브러리와 aws CLI·kubectl만 쓴다. 저장소 루트에서 실행한다.

| 명령 | 동작 | AWS 변경 |
|---|---|---|
| `plan` | VPC·subnet·route·NAT·S3 endpoint, S3 4개, ECR 7개, Secret 이름 11개, RDS·SG·subnet group, IAM 역할 10개(trust·정책 원문, #211 Karpenter 컨트롤러 포함), EKS·노드그룹·add-on·Pod Identity를 실제와 비교. 차이가 있으면 exit 1 | 없음 |
| `apply --confirm-account 347161580747` | `plan`에서 MISSING인 자원만 생성. 기존 자원은 변경·삭제하지 않는다. Secret 값과 EKS는 만들지 않는다 | 생성만 |
| `render-eksctl --operator-cidr <IP>/32 --out <저장소 밖>` | 현재 subnet ID를 채운 eksctl 설정 출력 → `eksctl create cluster -f <파일>` (2026-11-04 eksctl 0.231.0 `--dry-run` 통과) | 없음 |
| `apply --after-eksctl ...` | 새 클러스터의 cluster SG에서 RDS 5432 허용 | 생성만 |
| `rds-bootstrap --kubeconfig <파일>` | 입력(ESO Secret 6개·`rds-ca`) 확인. `--execute`일 때 RDS 관리 master secret을 임시 Secret으로 넣고 `rds-bootstrap*.sql` Job 실행 후 삭제 | `--execute`일 때만 |
| `pause` / `resume --state <저장소 밖 파일>` | [EKS 중단·재개 절차](../eks/README.md#데모-종료축소재개-실행안-185) 자동화. 기본은 계획 출력 | `--execute --confirm-account`일 때만 |

```powershell
python infrastructure/aws/demo_stack.py --profile sagomungchi-provided plan
```

새 환경 순서: `apply` → 비밀 값 입력(Secrets Manager, 담당자) → `render-eksctl` → `eksctl create cluster` → `apply --after-eksctl` → [prod 초기 배포 절차](../gitops/environments/prod/README.md#초기-배포-재현-절차-185)(ESO·LB Controller·`rds-bootstrap`·migration·앱). CloudFront 배포·OAC·Function, ALB Ingress의 origin 헤더, 웹 업로드, Google OAuth 등록은 이 스크립트 범위 밖이며 아래 redacted 설정과 절차로 수동 구성한다. 계정 ID와 이름이 고정이므로 다른 계정에는 `demo-stack.json`·`iam/`·`cluster.json`을 먼저 바꾼다.

[`rds-bootstrap.sql`](../gitops/charts/platform-data/files/postgres/rds-bootstrap.sql)은 로컬 PostgreSQL init과 같은 파일(#230)이며 DB 3개, DB별 migration(DDL)·app(DML) 계정, PUBLIC CONNECT 회수, migration 계정 소유 객체의 default privileges를 멱등으로 만든다. learning_db에는 지식 저장소용 `vector` 확장도 만든다(#466). AWS 재가동 때 RDS 엔진의 pgvector 버전과 `rds.allowed_extensions` 허용 여부를 먼저 확인한다. 계정 이름·비밀번호는 ESO Secret에서 환경변수로만 받고, 이미 있는 계정의 비밀번호는 바꾸지 않는다. migration 후 한 번 더 실행하면 기존 테이블 권한을 맞추고 `flyway_schema_history`·`alembic_version`의 app 권한을 회수한다.

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
- VPC의 available NAT GW는 1개이며 JSON에 ID·subnet을 기록했다. AZ 장애 시 외부 호출 복구 검증은 하지 않았다. 2026-11-12 데모 정지 중 비용 축소로 NAT와 EIP, core ALB를 지웠다. 같은 날 EKS 클러스터도 지웠다(RDS·S3·ECR·Secret·IAM·VPC는 유지). 다시 켤 때는 [EKS 재생성 순서](../eks/README.md#재생성-순서-2026-11-12-eks-삭제-이후)를 따른다.
- RDS·S3·IAM 생성은 위 `demo_stack.py apply`로 정의했다. 웹 버킷 policy(CloudFront 배포 ID 필요)와 lifecycle은 정의하지 않았다. 관측 파일을 재생성 완료 근거로 사용하지 않는다.

## 배포·복구 유의 사항

초기 입력·설치 순서·미완료 선행 조건은 [prod 초기 배포 절차](../gitops/environments/prod/README.md#초기-배포-재현-절차-185), 단기 중단·데이터 보존·비용·재개 계획은 [EKS 데모 종료·축소안](../eks/README.md#데모-종료축소재개-실행안-185)을 따른다. 두 문서는 절차이며 신규 환경 재현이나 실제 축소 실행 결과가 아니다.

웹 배포는 assets를 먼저 업로드하고 index.html을 마지막에 교체한다. 현재는 no-cache 응답이며 API 캐시는 비활성이다. 이전 해시 assets는 즉시 삭제하지 않는다. 코드 SHA·빌드 설정·S3 버전 및 이미지 digest를 함께 기록한다. 현재 core와 웹의 이용권 수정은 미커밋 상태이므로 소스 재현성 후속 작업이 필요하다.

Google OAuth의 승인된 origin은 위 HTTPS 주소, redirect URI는 `/api/v1/auth/google/callback`, `/api/v1/auth/google/reauth/callback`이다. Client secret은 `sagomungchi/demo/app/google`에만 두고 Git에 넣지 않는다.

## 생성·관리 범위 추가 확인 (2026-11-03)

기존 프로필로 계정 347161580747을 확인한 뒤 AWS API를 읽기 전용으로 조회했다. 서울 리전 `cloudformation describe-stacks` 결과는 빈 목록이다. 이것만으로 모든 리소스가 수동 생성되었다고 단정하지 않는다. Terraform state·최초 생성 기록·담당자는 아직 확인하지 않았으며, 기존 자원의 IaC import나 재생성은 수행하지 않았다.

| 범위 | 추가 관측 | 재현·관리 시 남은 일 |
|---|---|---|
| VPC | `vpc-0f4d9134097830b4b`, 10.20.0.0/16. public 10.20.0.0/20(2a)·10.20.16.0/20(2b)는 IGW, private 10.20.128.0/20(2a)·10.20.144.0/20(2b)는 동일 NAT로 기본 경로 연결 | 생성 주체·SG·NACL·endpoint policy 전체 보존 및 관리 책임 확정 |
| S3 경로 | private route table 두 개에 S3 Gateway endpoint `vpce-0dab53d8da86d39c8` 연결, available | S3 통신을 모두 NAT 경유로 설명하지 않는다. 2026-11-04 #212에서 endpoint policy(기본 전체 허용 유지)·IAM·NAT 우회를 점검했다(아래 절) |
| RDS 네트워크 | 위 private subnet 두 개를 사용하는 `sagomungchi-demo-db-subnet-group`. SG `sg-022d3c9a8cf111b47`의 5432 ingress는 EKS SG `sg-086c7c83b3638da59`만 참조 | 복원 DB의 subnet group·SG를 원본과 대조. public 접근을 새로 허용하지 않음 |
| RDS 저장·설정 | gp3 20GiB, 최대 자동확장 1000GiB, `default.postgres17` in-sync, TagList 빈 목록 | 최대 용량·비용 한도 검토. KMS key 접근과 DB별 계정·migration·데이터 초기화 절차 확인 |
| S3 | 네 버킷 모두 기본 암호화 AES256, lifecycle 없음(`NoSuchLifecycleConfiguration`) | 현재/이전 버전 보존 기간과 삭제 정책 확정 후 lifecycle 검토. 버전 관리만으로 별도 백업·복구 성공을 주장하지 않음 |
| S3 policy | web은 CloudFront 서비스의 GetObject를 배포 `EW2QD9OAPEVRK` SourceArn으로 제한, IsPublic=false. 나머지 세 버킷은 bucket policy 없음(`NoSuchBucketPolicy`) | bucket policy 부재를 공개 접근이나 IAM 접근 불가로 해석하지 않는다. 기존 Public Access Block·IAM과 함께 평가 |

## S3 endpoint·NAT 점검 (#212, 2026-11-04)

읽기 전용 점검이며 AWS 자원은 바꾸지 않았다. 상세 근거·비용 비교는 [#185 보고서의 #212 절](../../docs/report/infra.md#5-s3-gateway-엔드포인트와-nat-점검-212).

- S3 Gateway endpoint와 private route 두 개의 `pl-78a54011` 경로가 active다. 정책은 기본 전체 허용을 유지한다. ECR layer 다운로드도 AWS 소유 버킷을 이 endpoint로 받으므로 우리 버킷만 허용하도록 좁히지 않는다.
- scoring 모델 약 844MiB 다운로드 구간에 NAT 바이트는 0.04MiB였다. Pod 안 S3 DNS 해석 IP는 모두 prefix list 대역이고, report·scoring Pod의 `ListObjectsV2`는 200이다. `demo-observed.json`에 endpoint·route table을 기록했다.
- NAT 지표(약 2일): 동시 연결 최대 126, 포트 할당 오류 0, 드롭 6(구성 직후). 병목은 없고 단일 AZ(2a) 가용성 위험만 남는다. AZ별 NAT는 결정 대기다.
- VPC Flow Logs는 없다. 만들려면 비용·보존 기간을 정한 뒤 별도 승인으로 진행한다.

## 관측·복구 우선순위

아래는 초기 점검 당시의 후속 후보 목록이며 #185의 완료 조건 전체를 뜻하지 않는다. 2026-11-03 제안(CloudWatch 경보 6개 + SNS→Lambda→Discord 중계, EKS 로그 14일 보존)은 채택하지 않았다. 경보 조건은 [미적용 경보 JSON](alarms.proposed.json)에 검토용으로만 남아 있고(`ActionsEnabled=false`, action 없음) AWS에 만들지 않았다. 당시 추정은 경보·secret 고정비 월 약 $1, 기존 EKS 로그 수집 약 1.2GiB/일(월 약 $28)이며 로그 그룹 보존 기간은 정하지 않았다. 이후 기존 설계의 Grafana→Discord 연결과 최소 경보를 배포했다. 전체 경보·추적은 #187, 자동 배포는 #186, 노드 자동확장은 #211에서 다룬다. 실제 완료 근거는 [#185 보고서](../../docs/report/infra.md#4-aws-데모-구성-185)의 후속 배포 절을 따른다.

1. **경보와 로그 보존:** 서울 리전 `cloudwatch describe-alarms`의 metric/composite 목록이 모두 비어 있다. EKS `/aws/eks/sagomungchi-demo-eks/cluster` 로그 그룹은 retentionInDays 미설정이다. RDS는 Enhanced Monitoring interval=0, Performance Insights=true, CloudWatch log export 없음이다. 먼저 ALB unhealthy target·5xx, RDS 여유 저장공간·연결·CPU, 앱 readiness 및 큐 적체의 수집 가능 지표와 알림 수신 담당을 정한다. 임계값은 실측 후 정하고 로그 보관 기간·알림 채널·비용을 정한 뒤 구성한다. 이번 조회는 CloudFront용 us-east-1 경보나 외부 알림 도구까지 조사한 것은 아니다.
2. **RDS 격리 복원:** 자동 스냅샷 두 개가 available이며, 자동 백업 API의 복원 범위는 2026-11-02 17:55:20.511~2026-11-03 19:32:50 KST였다. 백업 보존은 7일, backup window는 14:54–15:24 UTC(23:54–다음 날 00:24 KST), maintenance window는 금요일 13:31–14:01 UTC다. 이 범위는 조회 시점 값이므로 복원 직전에 다시 조회한다. 복원 대상 ID·시각·기간·비용·정리 담당을 확정한 뒤 별도 DB에 복원하고 TLS 접속, 서비스별 스키마·migration·건수·표본 정합성, 소요 시간을 기록한다. 원본 endpoint나 앱 Secret을 시험 DB로 변경하지 않는다. 복원 자원 생성·삭제는 이번에 실행하지 않았다.
3. **PVC·S3 복구:** 서울 리전 AWS Backup plan 목록은 비어 있다. 이것만으로 별도 EBS snapshot·DLM·외부 백업이 없다고 단정하지 않는다. RabbitMQ/Redis PVC의 volume ID·AZ·snapshot/일관성 확보 방법을 먼저 확인한다. gp3 reclaimPolicy가 Delete이므로 복구 근거 없이 PVC를 삭제하지 않는다. S3 복구 시험은 합성 객체의 version ID·내용 비교로 진행할 범위를 정하며 실제 보고서·학습 데이터의 삭제나 부모 재생성 한도 소비를 하지 않는다.
4. **확장·자동 배포:** 위 관측과 복구 기준을 정한 다음 노드그룹 분리·자동확장·Argo CD 도입 범위를 결정한다. 현재 인벤토리만으로 전체 환경 복원이 가능하다고 판단하지 않는다.

조회 근거: EC2 `describe-subnets`, `describe-route-tables`, `describe-vpc-endpoints`, `describe-security-groups`; RDS `describe-db-instances`, `describe-db-snapshots`, `describe-db-instance-automated-backups`; S3 `get-bucket-encryption`, `get-bucket-lifecycle-configuration`, `get-bucket-policy-status`, 웹 `get-bucket-policy`; CloudWatch `describe-alarms`; Logs `describe-log-groups`; Backup `list-backup-plans`. Secret 값·S3 객체 본문은 조회하지 않았다.

## #185 검증 도구

- `verify-viewer-ip.ps1`: 명시한 EKS context에서 Redis 카운터를 읽고 CloudFront 기기 등록 API에 유효하지 않은 코드로 두 번 요청한다. 직접 확인한 접속자 공인 IPv4를 `-ViewerIp`, 전용 kubeconfig를 `-Kubeconfig`로 전달한다. 두 번째 요청에는 위조 XFF를 넣는다. 실제 viewer 카운터 +2, 위조 IP 카운터 불변과 PAIRING_CODE_INVALID 응답을 모두 확인한다. 기기·페어링을 생성하지 않지만 IP별 10분 한도에서 2회를 사용한다. 동시 요청·카운터 TTL 만료·프록시 egress 차이가 있으면 실패로 보고 조사하며 카운터를 임의로 지우지 않는다.
- `audit-demo-data.sql`: read-only transaction에서 건수만 조회한다. core_db(core_app)는 계정·학생의 demo flag별 건수, 결제 건수, DB CONNECT 권한과 #624 시연 학생 준비 상태(프리미엄·추억의 벽·가구·지난 주 리포트)를 본다. learning_db(learning_app)는 진행 주 이전 액자 수·검색 문서 상태·지난 주 M2 점수 답변을, report_db(report_app)는 지난 주 주간 리포트의 설명 카드·최근 일일 리포트를 본다. 접속한 DB에 맞는 절만 실행되므로 같은 파일을 세 DB에 각각 돌린다(`demo-db-oneoff.k8s.yaml`의 `PGDATABASE`·Secret을 바꿔 실행). 개인정보를 출력하지 않는다. demo flag가 false라고 실제 사용자라고 단정하거나, 별도 DB라는 이유만으로 모든 데이터가 demo라고 단정하지 않는다. 실제 배포의 외부 키·접속 대상·데이터 생성 절차와 함께 해석한다.
- `mark-confirmed-demo-data.sql`: 사용자가 테스트용이라고 확인한 기존 학부모 1명·학생 2명의 flag를 보정한 일회성 SQL이다. 자동 초기화나 일반 운영 DB에서 실행하지 않는다. 새 가입자의 demo 여부를 자동 설정하는 기능이 아니다.
- `scan-repository-secrets.py`: Python 표준 라이브러리와 Gitleaks 8.30.1로 이력·현재 파일을 분리 검사한다. 예: `python infrastructure/aws/scan-repository-secrets.py --gitleaks <실행파일> --reports <저장소밖-보고서폴더>`. `.gitleaks.toml`의 예외는 검토한 합성 값과 비밀이 아닌 식별자에 한정한다. Git 무시 파일·원격의 미수신 이력은 검사 범위 밖이다.

## 시연 계정 데이터 준비 (#624)

12/7 시연에서 추억 앨범·추억 검색·추억의 벽·가구 스킨·지난 주 주간 리포트(설명 카드)·일일 리포트가 빈 화면이 되지 않도록, 가상 학생 2명(초3 무료·초5 프리미엄)에게 지난 3회차(11/16·11/23·11/30 주) 완료 기록을 만든다. 기록은 SQL INSERT 없이 실제 공개 API로 만든다. 지난 주(11/30 주)는 실제 시각으로, 그보다 앞선 2회차는 core·learning 시계를 그 주 토요일로 옮겨 만든다(결정·kind 확인: [docs/report/infra.md 9.7](../../docs/report/infra.md#97-시연-계정-데이터-준비-624-2026-11-13)). 가상 학생과 자체 미션만 쓴다(NFR-SEC-07).

| 파일 | 역할 |
|---|---|
| `demo_account_data.py` | `children`(가상 자녀 등록·학부모 동의) → `themes`(대상 주 게시 확인) → `solve`(서버 시계 기준 이번 주 5문제·정답 고르기) → `decorate`(앨범 확인·벽·가구) → `verify`(화면 내용 API 확인). 표준 라이브러리만 쓰고 비밀값·답변 원문·presigned URL을 출력하지 않는다 |
| `prepare-demo-account-students.sql` | 두 자녀와 학부모를 `is_demo`로 표시, 초5에 결제 없는 프리미엄 시험 구독(`product_snapshot.demoAccount = '624'`) |
| `demo-clock.Dockerfile` | core·learning 이미지에 libfaketime만 더한 시험 시계 이미지. 준비 동안만 쓴다 |
| `audit-demo-data.sql` | 준비 결과를 세 DB에서 건수로 점검 |

### 사전 조건

1. #601 재가동이 끝나고 12/1(화) 이전이다. 시연 학부모(ID·비밀번호 로그인)와 CONTENT 관리자 계정이 있다.
2. 11/16·11/23·11/30 주의 G3·G5 테마가 게시돼 있다(`python demo_account_data.py themes --weeks 2026-11-16,2026-11-23,2026-11-30`). 정답 후보가 있는 테마여야 엔딩·정답까지 보인다.
3. 추억의 벽에 걸 가구 look_item(DESK·WALL 등)이 판매 중이고, 한 회차 포인트(완주 기준 약 65~125)로 살 수 있는 값이다.
4. 설명 카드(FN-RPT-09)는 다음이 모두 갖춰져야 나온다. 하나라도 빠지면 리포트는 "설명 미포함"으로 발행된다.
   - 초5 테마의 서술 미션 기준표에 M2 핵심어(`keywords`), 논술은 `essayType`. 저장소 시드(`demo_missions.sql`)의 미션에는 없다
   - M2 `m2-klue-narrative` 활성(scope `judgment/grade-5/narrative`), 설명 모델 `report-explanation` 활성(scope `explanation/grade-5/narrative`)과 sLLM 서버(#476)
   - ai `M2_CROSS_CHECK_ENABLED=true`. 저장소 prod 값은 기본 false라 이대로면 M2를 부르지 않는다. 켜면 판정 보류(`HELD`)가 생길 수 있어 켤지는 따로 정한다
   - 학생 원문 공개(`solve`가 켬)·프리미엄 구독

### 순서

환경 변수는 스크립트 머리말을 따른다(`DEMO_API_BASE`, `DEMO_PARENT_*`, `DEMO_ADMIN_*`). 값은 출력하지 않는다.

1. 자녀 등록: `python demo_account_data.py children --child <초3 닉네임>:3 --child <초5 닉네임>:5`
2. 시연 표시·프리미엄: `demo-db-oneoff.k8s.yaml`로 `prepare-demo-account-students.sql` 실행(`psql -v g3=<초3> -v g5=<초5> -v product_code=PREMIUM`). Pod의 `command`에 `-v` 세 개를 더한다.
3. 앞선 2회차(시험 시계):
   - `docker build -f infrastructure/aws/demo-clock.Dockerfile --build-arg BASE=<배포 중인 core 이미지> -t <같은 ECR 저장소>:<태그>-demo-clock .`(learning도 같게) → ECR push
   - core·learning Deployment를 그 이미지로 바꾸고 `LD_PRELOAD=/usr/lib/x86_64-linux-gnu/faketime/libfaketime.so.1`, `FAKETIME=@2026-11-21 05:00:00`(UTC, 토요일 14:00 KST), `FAKETIME_FORCE_MONOTONIC_FIX=1`, `FAKETIME_DONT_RESET=1`을 넣는다. monotonic을 위조하지 않으면(`FAKETIME_DONT_FAKE_MONOTONIC=1`) JVM 대기 스레드가 CPU 1코어를 계속 쓴다
   - 롤아웃이 끝나면 `solve --child <초3>`, `solve --child <초5>`. 이어서 `FAKETIME=@2026-11-28 05:00:00`으로 바꿔 두 번 더 `solve`
   - 앞선 주의 주간 리포트까지 원하면 그 주 일요일 23:56 KST로 옮겨 월요일 00:00 스케줄을 기다린다(sLLM KEDA cron은 실제 시각 기준이라 이때만 1대로 직접 올린다). 시연에 필요한 것은 지난 주 리포트뿐이라 생략할 수 있다
   - 원래 이미지·환경 변수로 되돌리고(`kubectl set image`·`kubectl set env ...-`), Pod 시각이 실제 시각인지 확인한다. 이 동안 가짜 시각으로 서명한 S3 그림 URL은 403이고, 다른 사용자가 쓰지 않는 시간에만 한다
4. 지난 주(실제 시각): 12/4(금)~12/5(토)에 `solve` 두 번. 무료도 금·토에는 다섯 요일이 모두 열린다(#483). 12/6 00:00 일일, 12/7 00:00 주간 리포트가 정기 스케줄로 만들어진다
5. 12/7 00:00 이후: `decorate --child <닉네임> --min-frames 3 --keep-newest-unseen --furniture <DESK 코드>,<WALL 코드>`(가장 최근 회차는 "새 액자"로 남김) → `verify --child <닉네임> --query "<답변 소재 질문>"` → 세 DB에 `audit-demo-data.sql`

되돌리기: 시험 구독은 `prepare-demo-account-students.sql` 머리말의 UPDATE로 해지한다. 학습 기록은 자녀 프로필 삭제(학부모 설정)로 지운다.
