# AWS 데모 진입·저장소 구성

2026-11-03 실제 계정의 설정 보존이다. Terraform/CloudFormation 등 새 실행 계층을 도입하지 않았다. `demo-observed.json`은 RDS·S3 관측 결과이며 배포 명령 입력이 아니다.

## IaC: eksctl + AWS CLI 스크립트 (#185)

EKS는 [eksctl 설정](../eks/cluster.json), 나머지는 `demo-stack.json`(원하는 상태)과 `iam/`(trust·policy 원문)이 정의한다. `demo_stack.py`는 Python 표준 라이브러리와 aws CLI·kubectl만 쓴다. 저장소 루트에서 실행한다.

| 명령 | 동작 | AWS 변경 |
|---|---|---|
| `plan` | VPC·subnet·route·NAT·S3 endpoint, S3 4개, ECR 7개, Secret 이름 11개, RDS·SG·subnet group, IAM 역할 12개(trust·정책 원문, #211 Karpenter 컨트롤러, #652 테마 자산 ai·learning 포함), EKS·노드그룹·add-on·Pod Identity를 실제와 비교. 차이가 있으면 exit 1 | 없음 |
| `apply --confirm-account 347161580747` | `plan`에서 MISSING인 자원만 생성. 기존 자원은 변경·삭제하지 않는다. Secret 값과 EKS는 만들지 않는다. `--without-rds`면 RDS 인스턴스만 만들지 않는다(SG·서브넷 그룹은 만듦, 스냅샷 복원용 #809) | 생성만 |
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

- RDS `sagomungchi-demo-db`: PostgreSQL 17.11, db.t4g.small, Single-AZ, 비공개, 암호화, 백업 7일. 삭제 보호 false. PITR 복구 시험은 2026-11-18에 실행해 RPO·RTO를 확인했다([infra 9.12](../../docs/report/infra.md#912-rds-pitr-복구-시험-629-2026-11-18)).
- `sagomungchi-demo-347161580747-{web,missions,reports,models}`: 버전 관리·Public Access Block 상태는 JSON 참고. 웹만 CloudFront OAC로 제공하며 reports/models는 앱 IAM 및 서비스 권한 검사를 통한다.
- VPC의 available NAT GW는 1개이며 JSON에 ID·subnet을 기록했다. AZ 장애 시 외부 호출 복구 검증은 하지 않았다. 2026-11-12 데모 정지 중 비용 축소로 NAT와 EIP, core ALB를 지웠다. 같은 날 EKS 클러스터도 지웠다(RDS·S3·ECR·Secret·IAM·VPC는 유지). 다시 켤 때는 [EKS 재생성 순서](../eks/README.md#재생성-순서-2026-11-12-eks-삭제-이후)를 따른다.
- RDS·S3·IAM 생성은 위 `demo_stack.py apply`로 정의했다. 웹 버킷 policy(CloudFront 배포 ID 필요)와 lifecycle은 정의하지 않았다. 관측 파일을 재생성 완료 근거로 사용하지 않는다.

## 테마 자산 버킷 권한 (#652, 2026-11-16 정의, 2026-11-17 적용)

ai는 테마 초안 그림·영상을 `missions` 버킷의 `theme-drafts/{실행 ID}/{장면}`에 올리고, learning은 같은 키를 1시간짜리 presigned GET URL로 바꿔 학생 화면에 준다(#437·#438). 지금까지 prod 값에는 두 서비스의 `ASSET_S3_BUCKET`도 S3 권한 역할도 없어서, 그림·영상 단계와 자산 URL이 오류 없이 꺼져 있었다. 저장소에만 아래를 정의했고 AWS에는 만들지 않았다(조회도 하지 않음).

| 역할 | Pod Identity 연결 | 권한(inline) |
|---|---|---|
| `sagomungchi-demo-ai-asset-s3-role` | `app/ai-service` | `s3:PutObject`·`s3:GetObject` — `missions` 버킷 `theme-drafts/*`(읽기는 테마 초안 부분 다시 생성 재료, #537. 정책 이름 `ai-asset-s3-write`는 그대로) |
| `sagomungchi-demo-learning-asset-s3-role` | `app/learning-service` | `s3:GetObject` — 같은 경로(presigned URL 서명자 권한. 서명 자체는 S3를 부르지 않음) |

- trust는 report·scoring 역할과 같은 형식(`pods.eks.amazonaws.com`, 클러스터 ARN·`app`·ServiceAccount 조건)이다. 두 앱 chart는 `serviceAccount.create` 기본값(true)으로 `ai-service`·`learning-service` ServiceAccount를 만든다.
- 버킷은 기본 암호화 SSE-S3(AES256)라 KMS 권한은 필요 없다. 그림은 `<img>`·`<video>`가 presigned URL을 직접 열므로 CORS 설정도 필요 없다.
- 두 앱의 NetworkPolicy egress에 Pod Identity agent `169.254.170.23/32:80`을 더했다(report·scoring·sLLM과 같음). 이것이 없으면 역할을 연결해도 자격 증명을 못 받는다. ai의 S3 업로드는 기존 공인 443 허용(S3 Gateway endpoint 대역 포함)으로 나간다.

재가동 때 순서(A 계정, #601):

1. `demo_stack.py plan` → 두 역할이 `MISSING`인지 확인 → `apply --confirm-account <계정>`이 역할·inline 정책을 만든다(기존 자원은 안 바꿈).
2. 클러스터를 새로 만들면 `cluster.json`의 Pod Identity 10개에 두 연결이 들어 있다. 클러스터가 이미 있으면 `aws eks create-pod-identity-association --cluster-name sagomungchi-demo-eks --namespace app --service-account ai-service --role-arn <ai 역할 ARN>`(learning도 같게)로 만든다. 연결 뒤 Pod를 다시 띄워야 자격 증명이 주입된다.
3. prod `ai-service.json`·`learning-service.json`으로 두 앱을 재배포한다(`ASSET_S3_BUCKET`·`S3_REGION`·`AWS_REGION`·agent egress 포함).
4. 확인: 관리자 화면에서 테마 초안 1건 생성 → ai 로그에 그림 단계 경고(`skipped`)가 없고 `theme-drafts/` 객체가 생겼는지 → 학생 테마 화면 응답의 장면 URL이 null이 아니고 브라우저에서 열리는지. 결과는 [infra 보고서 9.8](../../docs/report/infra.md#98-prod-테마-자산-버킷과-네임스페이스-기본-거부-준비-652657-2026-11-16)에 적는다.

B 계정(시연, 11/30 무렵)으로 옮길 때 바꿀 항목: 버킷 이름의 계정 번호(`prod/ai-service.json`·`learning-service.json`의 `ASSET_S3_BUCKET`), `iam/ai-asset-s3-role.*`·`iam/learning-asset-s3-role.*`의 버킷·클러스터 ARN, `eks/cluster.json`의 두 연결 role ARN. 다른 계정 번호 항목과 함께 바꾼다(#601 11/14 메모). 전체 순서와 교체 목록은 아래 [B 계정 전환 런북](#b-계정-전환-런북-809)이다.

## 리포트 Gemma SageMaker 엔드포인트 (#746, 2026-11-18)

리포트 상세 설명 Gemma는 같은 계정·VPC의 SageMaker 실시간 엔드포인트에서 돈다. 검증 결과와 결정은 [infra 보고서 9.13.9](../../docs/report/infra.md#9139-sagemaker-검증과-엔드포인트-구성-746-2026-11-18)에 있다.

| 파일 | 내용 |
|---|---|
| `sagemaker/explanation-endpoint.json` | 원하는 상태: 이미지, S3 경로, 인스턴스, 메모리 예약, vLLM 환경 변수, LoRA 사용 여부, 예약 창 |
| `sagemaker_explanation.py` | `status`·`manifest`·`verify`·`apply`·`schedule`·`copies`·`invoke`·`delete`. aws CLI만 쓴다 |
| `iam/sagemaker-explanation-role.*` | SageMaker 실행 역할(S3 `explanation/*` 읽기, DLC 이미지 받기, 로그·지표, VPC ENI) |
| `iam/ai-asset-s3-role.inline.ai-sagemaker-explanation-invoke.json` | ai Pod Identity 역할의 `sagemaker:InvokeEndpoint`(엔드포인트와 IC ARN 모두 필요) |

새 계정 순서:

1. `demo_stack.py apply --confirm-account <계정>`으로 실행 역할을 만든다. 역할이 이미 있으면 inline 정책은 `aws iam put-role-policy`로 넣는다(ai 역할 추가분 포함). Pod 재시작은 필요 없다.
2. 보안 그룹 `sagomungchi-demo-sagemaker-explanation-sg`를 VPC에 만든다. ingress는 없고 egress는 tcp 443만 둔다.
3. `sagemaker_explanation.py manifest --upload`로 승인 목록을 한 번만 올린다. 이때 LoRA 사용 여부(`useAdapter`)를 먼저 정한다.
4. `apply --confirm-account <계정>`을 실행한다. manifest 대조 → 모델 → 설정 → 엔드포인트 → IC(어댑터 포함) → Auto Scaling 대상 순서다. 인스턴스가 이미 떠 있어도 IC가 InService가 되기까지 약 9분 걸린다.
5. `schedule`로 주간 창(일 23:30·월 02:00 KST, 0대에서 켜지는 데 약 21분)을 건다. 시험은 `--test-start/--test-end`(UTC)로 시각을 당겨 확인한다.

- 계정 번호가 들어간 곳: `iam/sagemaker-explanation-role.*`, `iam/ai-asset-s3-role.inline.ai-sagemaker-explanation-invoke.json`. 버킷 이름은 스크립트가 sts로 채운다.
- 지울 때: `delete --confirm-account <계정>`(예약·Auto Scaling 대상·IC·엔드포인트·설정·모델). IAM·SG·S3 모델 파일은 남는다.

## 배포·복구 유의 사항

초기 입력·설치 순서·미완료 선행 조건은 [prod 초기 배포 절차](../gitops/environments/prod/README.md#초기-배포-재현-절차-185), 단기 중단·데이터 보존·비용·재개 계획은 [EKS 데모 종료·축소안](../eks/README.md#데모-종료축소재개-실행안-185)을 따른다. 두 문서는 절차이며 신규 환경 재현이나 실제 축소 실행 결과가 아니다.

웹 배포는 assets를 먼저 업로드하고 index.html을 마지막에 교체한다. 현재는 no-cache 응답이며 API 캐시는 비활성이다. 이전 해시 assets는 즉시 삭제하지 않는다. 코드 SHA·빌드 설정·S3 버전 및 이미지 digest를 함께 기록한다. 현재 core와 웹의 이용권 수정은 미커밋 상태이므로 소스 재현성 후속 작업이 필요하다.

Google OAuth의 승인된 origin은 위 HTTPS 주소, redirect URI는 `/api/v1/auth/google/callback`, `/api/v1/auth/google/reauth/callback`이다. Client secret은 `sagomungchi/demo/app/google`에만 두고 Git에 넣지 않는다.

## 생성·관리 범위 추가 확인 (2026-11-03)

초기 읽기 전용 조회로 VPC·S3 Gateway endpoint·RDS 네트워크·S3 암호화·bucket policy를 확인했다(CloudFormation stack 없음). 이후 생성은 위 `demo_stack.py apply`로 정의했고, 조회 결과 원문은 `demo-observed.json`과 git 이력에 있다. S3 lifecycle·bucket policy(web 외)는 정의하지 않았다.

## S3 endpoint·NAT 점검 (#212, 2026-11-04)

읽기 전용 점검이며 AWS 자원은 바꾸지 않았다. 상세 근거·비용 비교는 [#185 보고서의 #212 절](../../docs/report/infra.md#5-s3-gateway-엔드포인트와-nat-점검-212).

- S3 Gateway endpoint와 private route 두 개의 `pl-78a54011` 경로가 active다. 정책은 기본 전체 허용을 유지한다. ECR layer 다운로드도 AWS 소유 버킷을 이 endpoint로 받으므로 우리 버킷만 허용하도록 좁히지 않는다.
- scoring 모델 약 844MiB 다운로드 구간에 NAT 바이트는 0.04MiB였다. Pod 안 S3 DNS 해석 IP는 모두 prefix list 대역이고, report·scoring Pod의 `ListObjectsV2`는 200이다. `demo-observed.json`에 endpoint·route table을 기록했다.
- NAT 지표(약 2일): 동시 연결 최대 126, 포트 할당 오류 0, 드롭 6(구성 직후). 병목은 없고 단일 AZ(2a) 가용성 위험만 남는다. AZ별 NAT는 결정 대기다.
- VPC Flow Logs는 없다. 만들려면 비용·보존 기간을 정한 뒤 별도 승인으로 진행한다.

## 관측·복구 우선순위

2026-11-03 초기 점검의 후속 후보(경보·로그 보존, RDS 격리 복원, PVC·S3 복구, 확장·자동 배포)는 각각 Grafana → Discord 경보(#185·#187, [infra 8장](../../docs/report/infra.md#8-운영-경보와-trace-185187)), PITR 복구 시험(infra 9.12), Karpenter·HPA(infra 6장·9.14)로 진행했다. CloudWatch 경보 + SNS→Lambda 중계안은 채택하지 않았다. 점검 당시 AWS Backup plan은 없었고, EKS 제어 평면 로그 보존 기간·PVC 스냅샷 방법은 따로 기록된 결정이 없다.

## #185 검증 도구

- `verify-viewer-ip.ps1`: 명시한 EKS context에서 Redis 카운터를 읽고 CloudFront 기기 등록 API에 유효하지 않은 코드로 두 번 요청한다. 직접 확인한 접속자 공인 IPv4를 `-ViewerIp`, 전용 kubeconfig를 `-Kubeconfig`로 전달한다. 두 번째 요청에는 위조 XFF를 넣는다. 실제 viewer 카운터 +2, 위조 IP 카운터 불변과 PAIRING_CODE_INVALID 응답을 모두 확인한다. 기기·페어링을 생성하지 않지만 IP별 10분 한도에서 2회를 사용한다. 동시 요청·카운터 TTL 만료·프록시 egress 차이가 있으면 실패로 보고 조사하며 카운터를 임의로 지우지 않는다.
- `audit-demo-data.sql`: read-only transaction에서 건수만 조회한다. core_db(core_app)는 계정·학생의 demo flag별 건수, 결제 건수, DB CONNECT 권한과 #624 시연 학생 준비 상태(프리미엄·추억의 벽·가구·지난 주 리포트)를 본다. learning_db(learning_app)는 진행 주 이전 액자 수·검색 문서 상태·지난 주 M2 점수 답변, 최근 3주 판정 결과·보류 사유별 건수(`MODEL_DISAGREEMENT` 포함)와 M2 입력이 있는 공개 기준표 수(#668)를, report_db(report_app)는 지난 주 주간 리포트의 설명 카드·최근 일일 리포트를 본다. 접속한 DB에 맞는 절만 실행되므로 같은 파일을 세 DB에 각각 돌린다(`demo-db-oneoff.k8s.yaml`의 `PGDATABASE`·Secret을 바꿔 실행). 개인정보를 출력하지 않는다. demo flag가 false라고 실제 사용자라고 단정하거나, 별도 DB라는 이유만으로 모든 데이터가 demo라고 단정하지 않는다. 실제 배포의 외부 키·접속 대상·데이터 생성 절차와 함께 해석한다.
- `mark-confirmed-demo-data.sql`: 사용자가 테스트용이라고 확인한 기존 학부모 1명·학생 2명의 flag를 보정한 일회성 SQL이다. 자동 초기화나 일반 운영 DB에서 실행하지 않는다. 새 가입자의 demo 여부를 자동 설정하는 기능이 아니다.
- `scan-repository-secrets.py`: Python 표준 라이브러리와 Gitleaks 8.30.1로 이력·현재 파일을 분리 검사한다. 예: `python infrastructure/aws/scan-repository-secrets.py --gitleaks <실행파일> --reports <저장소밖-보고서폴더>`. `.gitleaks.toml`의 예외는 검토한 합성 값과 비밀이 아닌 식별자에 한정한다. Git 무시 파일·원격의 미수신 이력은 검사 범위 밖이다.

## 시연 계정 데이터 준비 (#624)

12/7 시연에서 추억 앨범·추억 검색·추억의 벽·가구 스킨·지난 주 주간 리포트(설명 카드)·일일 리포트가 빈 화면이 되지 않도록, 가상 학생 2명(초3 무료·초5 프리미엄)에게 지난 3회차(11/16·11/23·11/30 주) 완료 기록을 만든다. 기록은 SQL INSERT 없이 실제 공개 API로 만든다. 지난 주(11/30 주)는 실제 시각으로, 그보다 앞선 2회차는 core·learning 시계를 그 주 토요일로 옮겨 만든다(결정·kind 확인: [docs/report/infra.md 9.7](../../docs/report/infra.md#97-시연-계정-데이터-준비-624-2026-11-13)). 가상 학생과 자체 미션만 쓴다(NFR-SEC-07).

| 파일 | 역할 |
|---|---|
| `demo_account_data.py` | `children`(가상 자녀 등록·학부모 동의) → `themes`(대상 주 게시 확인) → `m2-rubric`(초5 테마 기준표 M2 입력 보강, #668) → `solve`(서버 시계 기준 이번 주 5문제·정답 고르기) → `decorate`(앨범 확인·벽·가구) → `verify`(화면 내용 API 확인). 표준 라이브러리만 쓰고 비밀값·답변 원문·presigned URL을 출력하지 않는다 |
| `prepare-demo-account-students.sql` | 두 자녀와 학부모를 `is_demo`로 표시, 초5에 결제 없는 프리미엄 시험 구독(`product_snapshot.demoAccount = '624'`) |
| `demo-clock.Dockerfile` | core·learning 이미지에 libfaketime만 더한 시험 시계 이미지. 준비 동안만 쓴다 |
| `audit-demo-data.sql` | 준비 결과를 세 DB에서 건수로 점검 |

### 사전 조건

1. #601 재가동이 끝나고 12/1(화) 이전이다. 시연 학부모(ID·비밀번호 로그인)와 CONTENT 관리자 계정이 있다.
2. 11/16·11/23·11/30 주의 G3·G5 테마가 게시돼 있다(`python demo_account_data.py themes --weeks 2026-11-16,2026-11-23,2026-11-30`). 정답 후보가 있는 테마여야 엔딩·정답까지 보인다.
3. 추억의 벽에 걸 가구 look_item(DESK·WALL 등)이 판매 중이고, 한 회차 포인트(완주 기준 약 65~125)로 살 수 있는 값이다.
4. 설명 카드(FN-RPT-09)는 다음이 모두 갖춰져야 나온다. 하나라도 빠지면 리포트는 "설명 미포함"으로 발행된다.
   - 초5 테마의 서술 미션 기준표에 M2 핵심어(`keywords`), 논술은 `essayType`. 저장소 시드(`demo_missions.sql`)에는 넣지 않고 순서 3의 `m2-rubric`이 채운다(#668). 관리자 화면·초안으로 만든 테마 미션은 `--m2-input` JSON으로 핵심어를 준다. 설명은 생각 유형이 겹치지 않는 답변 최대 3개이고 초5 M2 활성 범위는 서술이라, 주마다 생각 유형이 다른 서술 미션 3개에 핵심어가 있어야 카드 3개가 나온다
   - M2 `m2-klue-narrative` 활성(scope `judgment/grade-5/narrative`), 설명 모델 `report-explanation` 활성(scope `explanation/grade-5/narrative`)과 sLLM 서버(#476)
   - ai `M2_CROSS_CHECK_ENABLED=true`. prod 값(`gitops/environments/prod/ai-service.json`)에 켜 두었다(#668, 앱 기본값은 false). 재배포가 이 파일로 helm upgrade를 하므로 `kubectl set env`로 켜면 다음 ai 재배포 때 꺼진다. M2는 기준표에 M2 입력이 있는 미션에서만 불리므로 영향은 `m2-rubric`으로 보강한 미션뿐이다. 켜 두면 LLM이 `CORRECT`인데 M2 평균이 낮거나 `RETHINK`인데 높으면 판정 보류 `HELD(MODEL_DISAGREEMENT)`가 생길 수 있다(api-spec 4.2.2, 글자 수 하한 미만은 제외). 보류 답변에는 M2 점수가 남아 설명 후보는 되지만 학생 화면에는 보류로 보이므로, `solve` 뒤 `audit-demo-data.sql`의 `demo668_recent_judgments`로 보류 건수를 확인한다
   - 학생 원문 공개(`solve`가 켬)·프리미엄 구독

### 순서

환경 변수는 스크립트 머리말을 따른다(`DEMO_API_BASE`, `DEMO_PARENT_*`, `DEMO_ADMIN_*`). 값은 출력하지 않는다.

1. 자녀 등록: `python demo_account_data.py children --child <초3 닉네임>:3 --child <초5 닉네임>:5`
2. 시연 표시·프리미엄: `demo-db-oneoff.k8s.yaml`로 `prepare-demo-account-students.sql` 실행(`psql -v g3=<초3> -v g5=<초5> -v product_code=PREMIUM`). Pod의 `command`에 `-v` 세 개를 더한다.
3. 설명 카드용 기준표(첫 `solve` 전에): `python demo_account_data.py m2-rubric --weeks 2026-11-16,2026-11-23,2026-11-30 [--m2-input <JSON>]`. 먼저 `--dry-run`으로 채울 미션을 본다. 공개 기준표를 복사해 M2 입력만 더한 새 기준표 버전을 저장·검토 승인·재게시하고, 이미 있으면 그대로 둔다. 주마다 "M2 입력 서술 3유형"이 나와야 한다. 입력이 없는 미션이나 공개 안 된 수정본이 걸린 미션이 있으면 실패하고 이름을 알려 준다. 판정은 답변 때의 공개 기준표로 하므로 보강 전에 푼 답변에는 M2 점수가 생기지 않는다
4. 앞선 2회차(시험 시계):
   - `docker build -f infrastructure/aws/demo-clock.Dockerfile --build-arg BASE=<배포 중인 core 이미지> -t <같은 ECR 저장소>:<태그>-demo-clock .`(learning도 같게) → ECR push
   - core·learning Deployment를 그 이미지로 바꾸고 `LD_PRELOAD=/usr/lib/x86_64-linux-gnu/faketime/libfaketime.so.1`, `FAKETIME=@2026-11-21 05:00:00`(UTC, 토요일 14:00 KST), `FAKETIME_FORCE_MONOTONIC_FIX=1`, `FAKETIME_DONT_RESET=1`을 넣는다. monotonic을 위조하지 않으면(`FAKETIME_DONT_FAKE_MONOTONIC=1`) JVM 대기 스레드가 CPU 1코어를 계속 쓴다
   - 롤아웃이 끝나면 `solve --child <초3>`, `solve --child <초5>`. 이어서 `FAKETIME=@2026-11-28 05:00:00`으로 바꿔 두 번 더 `solve`
   - 앞선 주의 주간 리포트까지 원하면 그 주 일요일 23:56 KST로 옮겨 월요일 00:00 스케줄을 기다린다(sLLM KEDA cron은 실제 시각 기준이라 이때만 1대로 직접 올린다). 시연에 필요한 것은 지난 주 리포트뿐이라 생략할 수 있다
   - 원래 이미지·환경 변수로 되돌리고(`kubectl set image`·`kubectl set env ...-`), Pod 시각이 실제 시각인지 확인한다. 이 동안 가짜 시각으로 서명한 S3 그림 URL은 403이고, 다른 사용자가 쓰지 않는 시간에만 한다
5. 지난 주(실제 시각): 12/4(금)~12/5(토)에 `solve` 두 번. 무료도 금·토에는 다섯 요일이 모두 열린다(#483). 12/6 00:00 일일, 12/7 00:00 주간 리포트가 정기 스케줄로 만들어진다
6. 12/7 00:00 이후: `decorate --child <닉네임> --min-frames 3 --keep-newest-unseen --furniture <DESK 코드>,<WALL 코드>`(가장 최근 회차는 "새 액자"로 남김) → `verify --child <닉네임> --query "<답변 소재 질문>"` → 세 DB에 `audit-demo-data.sql`

되돌리기: 시험 구독은 `prepare-demo-account-students.sql` 머리말의 UPDATE로 해지한다. 학습 기록은 자녀 프로필 삭제(학부모 설정)로 지운다.

## B 계정 전환 런북 (#809)

2026-11-19 작성, **아직 실행하지 않은 절차**다. 시연용 B 계정을 11/26~27에 부트스트랩하고 11/28에 배포한다(#783). B의 DB는 A 최종 RDS 스냅샷을 복원한다(2026-11-18 결정). 이 문서 작업에서 AWS는 조회도 변경도 하지 않았다.

- 위치: 실행 절차는 쓰는 스크립트(`demo_stack.py`·`sagemaker_explanation.py`) 옆인 이 README에 둔다. `docs/report/infra.md`는 A에서 한 일의 기록이라 계정 번호를 바꿀 때도 A 값을 그대로 둔다. 또 9.15가 develop(#784 Tempo)과 #760 브랜치(빈 클러스터 첫 배포·스냅샷 복원 A-1~B-3)에서 겹쳐 있어 새 절을 더하지 않았다. #760의 9.15.2 표는 이 런북의 5·8~10·15단계와 같은 내용이다. 실행 결과와 실제 걸린 시간은 끝난 뒤 infra 보고서에 절로 남긴다.
- 배포 방식: 지금 방식(cd-release가 앱 5종을 배포하고 나머지는 손으로 적용)을 기준으로 썼다. 팀이 B에 Argo CD 도입을 검토 중이며(미결정), 도입하면 달라지는 단계를 표의 "Argo CD면" 열에 적었다.
- ★는 실행 전 동섭 승인 지점이다. 예상 시간은 11/17·11/19 A 실측(infra 9.11, #601 기록)을 바탕으로 한 추정이다. 명령의 `<B>`는 B 프로필, `<B 계정>`은 12자리 번호다.

### 확인 필요

값을 받으면 채운다. 질문은 #809 댓글에 남겼다.

| 항목 | 값 | 영향 |
|---|---|---|
| B 계정 번호 | (미정) | 아래 "A 계정 값 교체", CD 변수 |
| 리전 | (미정. A와 같은 `ap-northeast-2`로 가정) | `demo-stack.json` `region`·서브넷 AZ(2a·2b), CloudFront origin-facing prefix list `pl-22a6434b`(리전별 값), ECR 주소, `CD_AWS_REGION`. 다르면 계정 번호와 별도로 바꾼다 |
| 도메인 | (미정. 새 CloudFront 기본 주소인지 custom domain인지) | core `AUTH_WEB_ORIGIN`, Google OAuth origin·callback, `CD_BASE_URL`, 쿠키(도메인별) |
| A 최종 스냅샷·KMS 키 공유 | (미정. 11/19 종료 때 완료 여부) | 5단계 |
| A Secrets Manager 값 보존 | (미정. DB 계정 6개·결제 암호화 키를 B 입력 때까지 저장소 밖에 보관했는지) | 3단계 |
| A S3 객체 | (미정. A 버킷을 B 복사가 끝날 때까지 남기고 B 작업자가 읽게 하는지) | 2단계 |
| B AWS CLI 프로필 이름 | (미정) | 명령의 `--profile`, `redeploy-app.ps1` 기본값 `sagomungchi-provided`, runner의 `CD_AWS_PROFILE` |
| scoring 모델 경로 전환 | (결정 필요) | 8단계. 정하지 않으면 첫 배포가 scoring에서 멈춘다 |
| #777 적재 때 검사 이미지 | 미정 | 13단계 |

### 선행 (저장소, 11/26 전)

1. #760(계획 `currentRelease: "none"`, `redeploy-app.ps1 -AllowInstall`, scoring·report SA를 chart가 만듦)이 develop에 병합돼 있다. 없으면 11/17처럼 첫 배포가 `release: not found`로 멈춘다.
2. 계정 번호 교체 PR(아래 "A 계정 값 교체")을 develop에 병합한다. cd-release는 main SHA만 배포하고 `redeploy-app.ps1`이 계정 번호를 확인하므로, 이 교체와 6a단계 값 교체가 main에 들어가야 B에 배포된다(develop → main 릴리스, #623 시연 고정 버전).
3. GitHub 변수(손으로, A 종료 뒤): Repository `CD_AWS_ROLE_ARN`·`CD_ECR_REGISTRY`·`CD_AWS_REGION`, Environment `prod` `CD_BASE_URL`([CD README](../cd/README.md)). OIDC subject 설정은 저장소 단위라 바꾸지 않는다.

### 순서

| # | 단계 | 명령·방법 | 확인 | 예상 | Argo CD면 |
|---|---|---|---|---|---|
| 0 | 도구·로그인 | AWS CLI v2, eksctl 0.231.0(공식 릴리스, 체크섬 확인), kubectl 1.35, Helm 4.3.1, PowerShell 7, Python 3.12, Node.js·npm, gh. `aws sts get-caller-identity --profile <B>` | 계정이 B. 선행 1·2가 들어간 main SHA | 30분 | argocd CLI 추가 |
| 1★ | IAM·OIDC·ECR·S3·VPC | GitHub OIDC 제공자를 먼저 만든다([CD README A](../cd/README.md#a-aws-github-oidc-게시-역할-aws-변경), `demo_stack.py`가 관리하지 않음) → `python infrastructure/aws/demo_stack.py --profile <B> plan` → `apply --confirm-account <B 계정> --without-rds`. VPC·NAT·S3 endpoint, S3 4개, ECR 7개, IAM 역할 13개(SageMaker 실행 역할·ai invoke 정책 포함), RDS SG·서브넷 그룹을 만들고 RDS 인스턴스만 만들지 않는다 | `plan`에서 `eks`·`secret`·`rds`만 MISSING | 20분 | 같음 |
| 2★ | S3 데이터 | 아래 "S3 복사" | `sagemaker_explanation.py --profile <B> verify` 13개 일치, scoring 객체 `FULL_OBJECT` SHA-256 | 서버 간 30분, 로컬 경유 1~2시간 | 같음 |
| 3★ | Secrets Manager 12개 | 이름은 `demo-stack.json` `secrets`. 값은 저장소 밖 파일로 `create-secret --secret-string file://…`(출력하지 않음). **A와 같아야 하는 값**: DB 계정 6개(복원 DB의 계정이 A 비밀번호를 그대로 갖고 `rds-bootstrap`은 비밀번호를 바꾸지 않음), `app/payment`의 `PAYMENT_BILLING_ENCRYPTION_KEY`(DB에 암호화해 둔 값을 읽는 키). **새 값 가능**: `app/internal` 6개·`platform/rabbitmq`(RabbitMQ는 새 PVC), `app/auth` JWT(새 도메인이라 어차피 다시 로그인). `app/ai`는 `OPENAI_API_KEY`·`THEME_VIDEO_CREDENTIALS_JSON`·`VIDEO_PROJECT`만 넣고 RunPod 키 `SAGOMUNGCHI_SLLM_SERVERLESS_GEMMA`·`SAGOMUNGCHI_SLLM_SERVERLESS_KEY_GEMMA`는 넣지 않는다(11/19 결정, ExternalSecret도 `OPENAI_API_KEY`만 읽음) | `plan`의 secret OK. 값은 보지 않고 `describe-secret`로 이름만 본다 | 30분 | 같음(ESO) |
| 4★ | CloudFront 먼저 | 아래 "손으로 하는 단계"의 CloudFront를 웹 origin만으로 먼저 만든다(OAC·`spa-router.js`·웹 버킷 policy). 도메인이 이때 정해져야 6a 값 교체 PR을 낼 수 있다. `/api/*`의 ALB origin은 12단계에서 붙인다 | 배포 Deployed, 도메인 기록 | 20분 | 같음 |
| 5★ | RDS 스냅샷 복원 | 아래 "RDS 복원" | `plan`의 rds OK, `rds.force_ssl`, 새 endpoint 기록 | 40~60분 | 같음 |
| 6★ | EKS | `render-eksctl --operator-cidr <작업자 IP>/32 --out <저장소 밖>` → `eksctl create cluster -f <파일>` → `apply --confirm-account <B 계정> --after-eksctl`(RDS SG에 클러스터 SG 5432) → `plan` | 노드그룹 2개 OK, add-on 7개, Pod Identity 10개 | 30~40분(11/17 실측 17분) | 같음 |
| 6a | 자원 값 교체 PR | 아래 "B 자원을 만든 뒤 바꿀 값"(RDS endpoint·VPC·서브넷·클러스터 SG·CloudFront 도메인) → develop → main | main SHA에 B 값 | 1시간(리뷰 포함) | Argo CD가 읽을 브랜치에 같은 값 |
| 7 | 플랫폼 | [prod README 2절](../gitops/environments/prod/README.md#2-기반-자원--secret--저장소): gp3·namespace → ESO 2.14.0 → LB Controller 1.14.1(B `vpcId`) → `app/rds-ca` → `kubectl apply -f external-secret-resources.json` → `platform-network.json`·platform-data → Karpenter 1.15.1 → `karpenter-nodepool.json`(B 서브넷·SG) → `app-oneoff-db-network.json`·`app-check-pods-network.json` | ESO Ready 12개, `ai-provider-credentials`에 `OPENAI_API_KEY`만, RabbitMQ 서비스별 계정 5개, NodePool limits CPU 4·16Gi | 30분(11/17 실측 3분) | 외부 chart·ExternalSecret·NetworkPolicy를 Application으로. ESO·CRD 순서는 sync wave |
| 7a | 관측(#784) | 관측 Secret 2개(Grafana admin·Discord webhook, 값은 담당자) → `observability-platform-network.json` → `helm upgrade --install observability infrastructure/gitops/charts/observability -n observability -f infrastructure/gitops/environments/prod/observability.json`(Tempo 1Gi·Collector 지표 격리 포함) | Grafana 로그인·datasource, Tempo `/ready` 200, Prometheus `up`. 앱이 뜨기 전에는 LLM 비용 경보가 NoData로 Discord에 온다(11/17) | 15분 | Application(Secret은 손으로) |
| 8★ | DB 확인·모델 경로 | `demo_stack.py rds-bootstrap --kubeconfig <파일> --execute`(복원 DB라 DB·계정·`vector` 확장은 확인만, 멱등) → demo-db-oneoff로 `model_version` 활성 행과 `artifactUri` 조회 → **scoring 모델 경로 전환**(아래) | 활성 scoring 모델의 경로가 B 버킷에서 읽힘 | 30분 | 같음 |
| 9★ | 첫 배포 | cd-release, 계획 `currentRelease: "none"`, `services` 5개, 승인 1명 | 미리보기 `install`, migration 3개 complete(A 마지막 배포 뒤 새 migration만), release 6개 "첫 설치→r1". 경로 확인은 fixture 쿠키 때문에 실패할 수 있다(15단계) | 30~40분 | Application 동기화. migration은 PreSync 훅이 되고 승인·이력 방식은 다시 정한다 |
| 10 | 권한 정리 | `rds-bootstrap --execute` 한 번 더 | 새 테이블 app 권한, 이력 테이블 app 권한 회수 | 5분 | PostSync 훅 후보 |
| 11 | 웹 | 9단계와 같은 main SHA로 `frontend/web`에서 `npm ci && npm run build`(11/19처럼 env 없음) → `aws s3 cp dist/assets s3://<web 버킷>/assets --recursive` → 그 밖 정적 파일 → `index.html`을 `--cache-control no-cache`로 마지막 → `aws cloudfront create-invalidation --distribution-id <ID> --paths "/*"`(Git Bash면 `MSYS_NO_PATHCONV=1`) | CloudFront index의 해시 파일이 로컬 빌드와 같은 sha256, 콘솔 오류 0 | 15분 | 같음(Argo CD는 S3를 다루지 않음) |
| 12★ | ALB·API origin | `core-alb-network.json` + 검토한 Ingress(origin 헤더 실제 값은 Git 밖) → 새 ALB DNS로 CloudFront `/api/*` origin·behavior 추가 → Google OAuth에 새 origin·callback 2개 | prefix list만 허용, idle 120·XFF preserve, `/api/*` 응답 | 20분(11/17 실측 4분) | Ingress·NetworkPolicy는 Application, CloudFront·OAuth는 같음 |
| 13★ | SageMaker | [위 절](#리포트-gemma-sagemaker-엔드포인트-746-2026-11-18)의 새 계정 순서: SG `sagomungchi-demo-sagemaker-explanation-sg`(ingress 없음, egress 443) → `sagemaker_explanation.py --profile <B> verify` → `apply --confirm-account <B 계정>` → `schedule` → 확인 뒤 `copies 0`. `manifest.json`은 2단계에서 같은 sha256으로 복사했으므로 `manifest --upload`는 하지 않는다(같은 키면 `PreconditionFailed`). #777 검사 이미지는 미정: 쓰기로 하면 ECR 저장소 추가·이미지 게시 뒤 apply, 아니면 지금처럼 AWS DLC | 엔드포인트 InService, ai Pod에서 호출 200(infra 9.13.9), IC 0대로 내림 | 40분(IC 9분 + 인스턴스) | 같음 |
| 14 | 운영 데이터 | 스냅샷에 관리자·동의 문서·FREE 상품·모델 버전·성취기준 표·시연 학부모가 있다. 관리자 로그인, 모델 활성 상태·로딩(관리자 화면), 테마 그림 URL(learning presigned, B 버킷), 리포트 다운로드 | 모두 B 버킷에서 열림 | 20분 | 같음 |
| 15 | fixture·테마 | B 도메인에서 fixture 학부모 Google 로그인(refresh 쿠키 7일)·학생 기기 등록(`student_device`, 도메인별)으로 fixture 파일 갱신. 시연 주차 테마 초안 생성 → 채택 → 미션 검토·게시(11/17 A에서 READY까지 14분). 11/30~12/8은 두 주라 주마다 | 학생 로그인이 `CHILD_NOT_LINKED`가 아님, 학생 주간 테마에 시연 주차 문제 | 1시간 | 같음 |
| 16 | 확인 | 같은 계획을 다시 승인받아 실행(migration `already-complete`, 앱 `upgrade`) 또는 `python scripts/verify_cd_deployment.py --base-url <B 도메인> --fixture <파일> --output <파일>` → 리포트 설명(SageMaker 창 안에서만) → #624 시연 데이터·#668 M2 입력은 각 절차대로 | 6단계 통과, 결과를 #783에 기록 | 30분 | 동기화 상태 Healthy를 함께 본다 |

0~16은 합쳐 약 8~10시간이다. 11/26에 0~8(6a PR 포함), 11/27~28에 9~16을 하면 #783 일정과 맞는다.

#### S3 복사

| 버킷 | 대상 | 방법 |
|---|---|---|
| models | 활성·되돌리기 scoring 경로(`models/<이름>/<버전>/`, 8단계 조회 결과), `backup/2026-11-17/models/`(선택), 리포트 Gemma `explanation/gemma4-26b-a4b-lora-20261118/`의 `base-awq/`(11개)·`adapter/`(2개)·`manifest.json`. **`base-gguf/`·`adapter-gguf/`는 복사하지 않는다**(CPU용, 쓰지 않음) | 객체마다 `aws s3api copy-object --copy-source <A models 버킷>/<키> --bucket <B models 버킷> --key <키> --checksum-algorithm SHA256 --expected-bucket-owner <B 계정>`. 모든 객체가 5GB 이하로 나뉘어 있어(infra 9.13.6) 단일 복사가 되고 `FULL_OBJECT` SHA-256이 새로 계산된다. `aws s3 cp`·`sync`는 8MB를 넘으면 multipart라 COMPOSITE가 되므로 모델에는 쓰지 않는다(#368·#493 원칙) |
| missions | `theme-drafts/` 등 전체 | `aws s3 sync s3://<A missions> s3://<B missions>`. DB에는 키만 있고 버킷은 learning·ai `ASSET_S3_BUCKET` 값에서 읽는다 |
| reports | 전체 | `aws s3 sync`. report는 `S3_BUCKET` 값에서 버킷을 읽는다 |
| web | 복사하지 않음 | 11단계에서 새로 빌드해 올린다 |

권한: A 버킷 정책에 B 작업자 주체의 `s3:ListBucket`·`s3:GetObject`를 임시로 허용하고(A 변경, 확인 필요), 복사가 끝나면 지운다. A 버킷을 쓸 수 없으면 A에서 받아 둔 로컬 사본을 [`upload.py`](../../ml/sllm/scripts/serving/upload.py)(설명 가중치)와 [scoring 6.3](../../docs/report/scoring.md#63-신규-키-업로드)(scoring 모델)로 다시 올린다. 확인: 설명은 `sagemaker_explanation.py verify`, scoring은 객체마다 `head-object --checksum-mode ENABLED`의 `ChecksumType=FULL_OBJECT`·`ChecksumSHA256`이 레지스트리 `artifactFiles` 값과 같은지 본다.

#### RDS 복원

A 쪽(#760 A-2: A 고객 관리 KMS 키로 스냅샷 복사, 키 정책에 B 허용, 스냅샷 `restore` 속성에 B 추가)이 끝났다는 전제다(확인 필요).

```powershell
$p = '<B>'
aws rds describe-db-snapshots --include-shared --snapshot-type shared --profile $p --query 'DBSnapshots[].DBSnapshotArn'
aws rds copy-db-snapshot --source-db-snapshot-identifier <공유 스냅샷 ARN> --target-db-snapshot-identifier sagomungchi-demo-db-from-a --kms-key-id alias/aws/rds --profile $p
aws rds wait db-snapshot-available --db-snapshot-identifier sagomungchi-demo-db-from-a --profile $p
aws rds restore-db-instance-from-db-snapshot --db-instance-identifier sagomungchi-demo-db --db-snapshot-identifier sagomungchi-demo-db-from-a `
  --db-instance-class db.t4g.small --db-subnet-group-name sagomungchi-demo-db-subnet-group --vpc-security-group-ids <RDS SG ID> `
  --db-parameter-group-name default.postgres17 --no-publicly-accessible --no-multi-az --copy-tags-to-snapshot --profile $p
aws rds wait db-instance-available --db-instance-identifier sagomungchi-demo-db --profile $p
aws rds modify-db-instance --db-instance-identifier sagomungchi-demo-db --backup-retention-period 7 --preferred-backup-window 14:54-15:24 `
  --preferred-maintenance-window fri:13:31-fri:14:01 --max-allocated-storage 1000 --manage-master-user-password --enable-performance-insights --apply-immediately --profile $p
```

- 값은 `demo-stack.json` `rds`와 같게 둔다. `--manage-master-user-password`는 B Secrets Manager에 새 master 비밀번호를 만든다(`rds-bootstrap`이 쓰는 값). A의 master 비밀번호는 넘어오지 않는다.
- 복원 DB의 app·migrate 계정 6개는 A 비밀번호를 그대로 가진다(3단계에서 A와 같은 값). 다른 값으로 바꾸려면 master로 `ALTER ROLE`을 먼저 한다.
- 시험 데이터 정리(부하 시험 계정·스텁 `llm_usage`·경로 확인용 임시 계정)를 A에서 못 했으면 여기서 정한다(#760 A-1).
- 끝나면 공유 스냅샷 복사본과 A 키 공유를 정리해도 되는지 동섭에게 묻는다(#760 A-3: B 복원이 끝날 때까지 보존).

#### scoring 모델 경로 전환 (결정 필요)

scoring은 기동할 때 core의 활성 모델 목록을 받아 각 `artifactUri`에서 파일을 받는다. 하나라도 못 받으면 `/health/ready`가 실패로 남는다(`backend/scoring-service/app/model_startup.py`, `model_registry.py`의 `replace`). 복원 DB의 활성 행은 A 버킷을 가리키므로, 그대로 9단계를 실행하면 scoring이 Ready가 되지 않아 helm `--wait`이 시간 초과되고 뒤 release도 적용되지 않는다. `report-explanation`은 ai가 활성 여부와 범위만 보므로 A 주소 그대로 둬도 된다([`ml/sllm/README.md`](../../ml/sllm/README.md#승인-목록과-레지스트리-등록-2026-11-18)).

| 방법 | 내용 | 장단점 |
|---|---|---|
| 1. 비활성화 뒤 재등록 | 9단계 전에 관리자 화면에서 scoring 활성 모델을 비활성화 → 9단계(모델 없이 Ready) → B 경로로 새 버전을 사전 검사 → 등록 → 승인·활성화([scoring 7.8](../../docs/report/scoring.md#78-운영-적용-613-2026-11-17)과 같은 순서) | 레지스트리 이력이 남는다. 화면에서 활성 모델만 끄는 기능이 있는지 먼저 확인해야 하고, 재등록 동안 M2가 꺼진다 |
| 2. DB 행 수정 | 2단계 복사를 확인한 뒤 일회성 DB Pod로 활성·되돌리기 행의 `artifact_uri` 버킷 이름만 B로 UPDATE | 가장 빠르다. 사전 검사·승인 이력을 거치지 않으므로 보고서에 근거(같은 sha256 확인)를 남겨야 한다 |
| 3. A 버킷 임시 읽기 | B scoring 역할에 A models 버킷 읽기, A 버킷 정책에 B 역할 허용 → 9단계 → 재등록 뒤 회수 | DB를 건드리지 않지만 A 계정이 남아 있어야 하고 정책 두 곳을 바꾼다 |

### cd-release 범위 밖 (손으로 하는 단계)

11/19 A 재배포에서도 웹 S3 업로드, observability chart, ExternalSecret 정리(RunPod 키 2개 제거) 세 가지를 cd-release 뒤에 손으로 적용했다. B에서 손으로 하는 단계는 다음과 같다.

| 단계 | 순서 | 근거 | Argo CD면 |
|---|---|---|---|
| GitHub OIDC 제공자 | 1 | [CD README A](../cd/README.md#a-aws-github-oidc-게시-역할-aws-변경) | 같음 |
| Secrets Manager 값 | 3 | 위 3단계 | 같음 |
| CloudFront 배포·OAC·`spa-router.js` Function·웹 버킷 policy(배포 ID 필요) | 4 | `cloudfront-config.redacted.json`(직접 적용 금지, 식별값은 B에서 조회) | 같음 |
| RDS 스냅샷 복사·복원·설정 | 5 | 위 "RDS 복원" | 같음 |
| eksctl 클러스터·`--after-eksctl` | 6 | [EKS README](../eks/README.md) | 같음 |
| ESO·LB Controller·Karpenter chart, ExternalSecret·NetworkPolicy·NodePool 적용 | 7 | prod README 2절 | Application |
| observability chart와 Secret 2개 | 7a | [관측 chart README](../gitops/charts/observability/README.md) | Application(Secret은 손으로) |
| `rds-bootstrap` 앞뒤 | 8·10 | RDS master secret을 쓰므로 workflow에 넣지 않음(#760) | 훅 후보 |
| scoring 모델 경로 | 8 | 위 결정 | 같음 |
| 웹 빌드·S3 업로드·무효화 | 11 | prod README "main 기준 core·웹 재배포" | 같음 |
| ALB Ingress origin 헤더(Git 밖 실제 값, CloudFront와 양쪽 같게) | 12 | `core-ingress.redacted.json` | Ingress는 Application, 헤더 값은 손으로 |
| CloudFront `/api/*` origin·behavior | 12 | 위 "외부 요청 흐름" | 같음 |
| Google OAuth 승인 origin·redirect URI 2개 | 12 | 위 "배포·복구 유의 사항" | 같음 |
| SageMaker SG·엔드포인트·예약 | 13 | 위 SageMaker 절 | 같음 |
| fixture 쿠키·기기, 시연 주차 테마 | 15 | [CD README D](../cd/README.md#d-배포-후-경로-확인-fixture-작업자-pc에만) | 같음 |
| GitHub 변수 4개 | 선행 3 | CD README | 일부는 Argo CD 저장소 연결로 바뀜 |
| EKS 공개 접근 CIDR에 작업자 IP | 6, IP가 바뀔 때마다 | 11/19 A 재배포에서 IP가 바뀌어 다시 추가함 | 같음 |

### A 계정 값 교체

B 계정 번호를 받으면 한 번에 바꾼다. 분류 기준은 [`scripts/aws_account_switch.py`](../../scripts/aws_account_switch.py)의 `CHANGE`·`RECORD`이고, 분류되지 않은 파일에 A 번호가 있으면 스크립트가 멈춘다(새로 생긴 파일을 먼저 분류한다). 바꿀 파일 안에서도 `A 계정 347161580747`처럼 A 계정임을 밝힌 줄은 남긴다. 2026-11-19 기준 A 번호가 있는 파일은 53개였다(이 스크립트와 시험 2개 제외).

| 분류 | 파일 | 수 |
|---|---|---|
| 바꿈: IAM 원문 | `infrastructure/aws/iam/*.json` | 25 |
| 바꿈: IaC | `infrastructure/aws/demo-stack.json`, `infrastructure/eks/cluster.json`, `infrastructure/aws/cloudfront-config.redacted.json` | 3 |
| 바꿈: 배포 값 | `infrastructure/gitops/environments/prod/`의 앱 values 7개(`sllm-server.json` 포함)·`migrations/` 3개·`redeploy-app.ps1` | 11 |
| 바꿈: 시험 | `scripts/tests/test_cd_migration_runner.py`(가짜 `sts`가 돌려주는 번호가 `redeploy-app.ps1`과 같아야 함) | 1 |
| 바꿈: 절차 문서 | 이 README, `infrastructure/eks/README.md`, `infrastructure/cd/README.md`, prod README, `docs/report/scoring.md`(6.2·6.3 업로드 명령) | 5 |
| 남김: 기록·근거 | `docs/report/**`(scoring.md 빼고: `infra.md` 4절, `evidence/issue493-…json`), `infrastructure/aws/demo-observed.json`, `infrastructure/eks/demo-observed.json` | 4 |
| 남김: A에서 한 번 실행한 SQL | `add-demo-premium-product.sql`, `add-demo-test-subscription.sql`, `mark-confirmed-demo-data.sql`(아래 확인 결과) | 3 |
| 남김: A 부하 시험 | `evaluation/load/llm-stub.k8s.yaml`(이미지가 A ECR에 있음. B에서 부하 시험을 다시 하면 이미지를 B ECR에 올린 뒤 바꾼다) | 1 |

```powershell
python scripts/aws_account_switch.py plan --to <B 계정>    # 파일별 바꿀 줄·남길 줄 수. 파일은 바꾸지 않음
python scripts/aws_account_switch.py apply --to <B 계정>
python scripts/aws_account_switch.py check                 # 바꿀 파일에 A 번호가 남았으면 실패
git grep -n 347161580747    # A 계정 347161580747이 남은 곳이 위 '남김' 파일과 'A 계정 …' 줄뿐인지 눈으로
python -m unittest discover -s scripts/tests
```

`sllm-server.json`은 infra 9.13.9 정리안에서 지우기로 한 파일이다. 교체 전에 지웠으면 목록에서 빠진다. 버킷 이름(`sagomungchi-demo-<계정>-{web,missions,reports,models}`)은 계정 번호가 들어 있어 같이 바뀐다.

#### B 자원을 만든 뒤 바꿀 값

계정 번호가 아니라 자원이 생겨야 정해지는 값이다. 4·5·6단계 뒤 한 PR(6a)로 바꾼다. 리전이 바뀌면 `ap-northeast-2`·AZ·prefix list도 여기에 더한다.

| 값 | A 값으로 찾기 | 파일 |
|---|---|---|
| RDS endpoint | `git grep -n czcw0ywu2euo` | prod `core-service.json`·`learning-service.json`·`migrations/core-service.json`·`migrations/learning-service.json`·`external-secret-resources.json`(2곳), `infrastructure/aws/demo-db-oneoff.k8s.yaml` |
| VPC ID | `git grep -n vpc-0f4d9134097830b4b -- infrastructure/gitops` | prod `aws-load-balancer-controller.json` |
| 서브넷·클러스터 SG | `karpenter-nodepool.json`의 `subnet-…`·`sg-…` | prod `karpenter-nodepool.json`(EC2NodeClass. SG는 eksctl이 만든 클러스터 SG) |
| CloudFront 도메인 | `git grep -n d3jf0rnm6vhd9v -- infrastructure/gitops infrastructure/aws/verify-viewer-ip.ps1 evaluation/load/core-load.js` | core `AUTH_WEB_ORIGIN`, `verify-viewer-ip.ps1`, `core-load.js` 기본값, GitHub `CD_BASE_URL` |

`demo-observed.json` 2개, infra 보고서, 이 README 위쪽 관측 절(VPC·SG·NAT·CloudFront ID)은 A 기록이라 그대로 둔다.

### 시연 SQL 3개 확인 (2026-11-19, 저장소 기록 대조)

세 파일은 A에서 한 번 실행한 SQL이다. 행 ID·닉네임·건수를 전제(guard)로 두고, 전제가 다르면 아무것도 바꾸지 않고 멈춘다. 스냅샷을 복원하면 행 ID는 A와 같다. B에서 다시 실행할 필요는 없다. DB는 조회하지 않았으므로 아래 '예상'은 B 복원 뒤 읽기 전용 쿼리로 확인한다.

| 파일 | 전제 | A 기록 | B(스냅샷)에서 예상 | 판단 |
|---|---|---|---|---|
| `add-demo-premium-product.sql`(#361) | PREMIUM `98a998bd…`가 14,900원·월간·자녀 1명·`active=false` | #361 뒤 `active=false`로 원복(infra 9절 "남은 것") | 값이 그대로면 전제가 맞아 실행된다 | 실행하지 않는다. #624 시연 구독은 `prepare-demo-account-students.sql`이 `product_snapshot`으로 주므로 상품을 켤 필요가 없다 |
| `add-demo-test-subscription.sql`(#361) | 닉네임 `123213` 시연 자녀 1명, 구독 `3610c0de…`가 없음 | 넣은 뒤 원복 SQL로 `CANCELED`(행은 남음) | 구독 행이 남아 있어 전제에서 멈춘다(변경 없음) | 기록으로 둔다. 다시 쓰려면 새 구독 ID가 필요하다 |
| `mark-confirmed-demo-data.sql`(#185) | 학부모 1명·학생 2명, 결제·주문·구독 0건 | 11/03 실행. 뒤에 시험 계정·구독이 생김(#384·#630) | 학부모·구독 수가 달라 전제에서 멈춘다(변경 없음) | 기록으로 둔다. `is_demo` 표시는 스냅샷에 이미 있다 |

B 복원 뒤 읽기 전용 확인(core_db, `demo-db-oneoff.k8s.yaml`):

```sql
SELECT code, price, billing_cycle, child_limit, active FROM product WHERE id = '98a998bd-05c8-4ac9-b909-23c14340f6f9';
SELECT status FROM subscription WHERE id = '3610c0de-0000-4000-8000-000000000361';
SELECT (SELECT count(*) FROM user_account WHERE role = 'PARENT') AS parents, (SELECT count(*) FROM student) AS students;
```
