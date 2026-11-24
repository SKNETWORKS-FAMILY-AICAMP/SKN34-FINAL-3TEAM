# AWS 데모 진입·저장소 구성

2026-11-03 실제 계정의 설정 보존이다. Terraform/CloudFormation 등 새 실행 계층을 도입하지 않았다. `demo-observed.json`은 RDS·S3 관측 결과이며 배포 명령 입력이 아니다.

## IaC: eksctl + AWS CLI 스크립트 (#185)

EKS는 [eksctl 설정](../eks/cluster.json), 나머지는 `demo-stack.json`(원하는 상태)과 `iam/`(trust·policy 원문)이 정의한다. `demo_stack.py`는 Python 표준 라이브러리와 aws CLI·kubectl만 쓴다. 저장소 루트에서 실행한다.

| 명령 | 동작 | AWS 변경 |
|---|---|---|
| `plan` | VPC·subnet·route·NAT·S3 endpoint, S3 4개, ECR 9개(#985 `tox-retrain` 포함), Secret 이름 12개, RDS·SG·subnet group, IAM 역할 13개(trust·정책 원문, #211 Karpenter 컨트롤러, #652 테마 자산 ai·learning 포함), EKS·노드그룹·add-on·Pod Identity를 실제와 비교. 차이가 있으면 exit 1 | 없음 |
| `apply --confirm-account 347161580747` | `plan`에서 MISSING인 자원만 생성. 기존 자원은 변경·삭제하지 않는다. Secret 값과 EKS는 만들지 않는다. `--without-rds`면 RDS 인스턴스만 만들지 않는다(SG·서브넷 그룹은 만듦, 스냅샷 복원용 #809) | 생성만 |
| `render-eksctl --operator-cidr <IP>/32 --out <저장소 밖>` | 현재 subnet ID를 채운 eksctl 설정 출력 → `eksctl create cluster -f <파일>` (2026-11-04 eksctl 0.231.0 `--dry-run` 통과) | 없음 |
| `apply --after-eksctl ...` | 새 클러스터의 cluster SG에서 RDS 5432 허용 | 생성만 |
| `rds-bootstrap --kubeconfig <파일>` | 입력(ESO Secret 6개·`rds-ca`) 확인. `--execute`일 때 RDS 관리 master secret을 임시 Secret으로 넣고 `rds-bootstrap*.sql` Job 실행 후 삭제 | `--execute`일 때만 |
| `pause` / `resume --state <저장소 밖 파일>` | [EKS 중단·재개 절차](../eks/README.md#데모-종료축소재개-실행안-185) 자동화. 기본은 계획 출력 | `--execute --confirm-account`일 때만 |

```powershell
python infrastructure/aws/demo_stack.py --profile sagomungchi-provided plan
```

새 환경 순서: `apply` → 비밀 값 입력(Secrets Manager, 담당자) → `render-eksctl` → `eksctl create cluster` → `apply --after-eksctl` → [prod 초기 배포 절차](../gitops/environments/prod/README.md#초기-배포-재현-절차-185)(ESO·LB Controller·`rds-bootstrap`·migration·앱). CloudFront 배포·OAC·Function, ALB Ingress의 origin 헤더, 웹 업로드, Google OAuth 등록은 이 스크립트 범위 밖이며 아래 redacted 설정과 절차로 수동 구성한다. 계정 ID와 이름이 고정이므로 다른 계정에는 `demo-stack.json`·`iam/`·`cluster.json`을 먼저 바꾼다. B 계정처럼 처음부터 올리는 순서는 아래 [B 계정 전환 런북](#b-계정-전환-런북-809), 11/17 재가동에서 빠졌던 단계와 11/25 A 재가동 순서는 [infra 보고서 9.16](../../docs/report/infra.md#916-빈-클러스터-첫-배포와-b-계정-부트스트랩-보완-760-2026-11-18)이다.

[`rds-bootstrap.sql`](../gitops/charts/platform-data/files/postgres/rds-bootstrap.sql)은 로컬 PostgreSQL init과 같은 파일(#230)이며 DB 3개, DB별 migration(DDL)·app(DML) 계정, PUBLIC CONNECT 회수, migration 계정 소유 객체의 default privileges를 멱등으로 만든다. learning_db에는 지식 저장소용 `vector` 확장도 만든다(#466). AWS 재가동 때 RDS 엔진의 pgvector 버전과 `rds.allowed_extensions` 허용 여부를 먼저 확인한다. 계정 이름·비밀번호는 ESO Secret에서 환경변수로만 받고, 이미 있는 계정의 비밀번호는 바꾸지 않는다. migration 후 한 번 더 실행하면 기존 테이블 권한을 맞추고 `flyway_schema_history`·`alembic_version`의 app 권한을 회수한다.

## 외부 요청 흐름

`https://www.sagomungchi.co.kr`(가비아 DNS `www` CNAME → CloudFront 기본 주소 `d3jf0rnm6vhd9v.cloudfront.net`, 2026-11-24, [infra 보고서 9.22](../../docs/report/infra.md#922-시연-도메인-wwwsagomungchicokr-전환-2026-11-24)) → 정적 경로는 비공개 S3 웹 버킷(OAC), `/api/*`는 ALB → app/core-service:8080.

- CloudFront ID: `EW2QD9OAPEVRK`. 웹과 API가 같은 origin을 사용하므로 Secure 인증 쿠키를 사용한다.
- API는 CachingDisabled, AllViewerExceptHostHeader, 압축 false, origin read timeout 60초. ALB idle timeout 120초, XFF preserve.
- ALB inbound는 CloudFront origin-facing prefix list `pl-22a6434b`로 제한한다. 추가로 CloudFront와 ALB rule의 `X-Sagomungchi-Origin` 값이 일치해야 한다.
- CloudFront→ALB는 현재 HTTP이며 전 구간 TLS는 아니다. 사용자→CloudFront는 HTTPS(대체 도메인 `www.sagomungchi.co.kr`, us-east-1 ACM 인증서, TLSv1.2_2021). 루트 `sagomungchi.co.kr`은 CloudFront 별칭에 넣지 않고 가비아 포워딩으로 www에 넘긴다. ALB 인증서 적용은 별도 결정이다.
- core `AUTH_WEB_ORIGIN`은 `https://www.sagomungchi.co.kr` 하나라 기본 주소(`d3jf0rnm6vhd9v.cloudfront.net`)로 열면 로그인·refresh가 막힌다(OAuth callback 불일치, `PublicAuthFilter` Origin 403).
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

B 계정(시연, 11/30 무렵)으로 옮길 때 바꿀 항목: 버킷 이름의 계정 번호(`prod/ai-service.json`·`learning-service.json`의 `ASSET_S3_BUCKET`, `report-worker.json`의 그림책 그림 허용 출처 `MEMORY_BOOK_ASSET_ORIGINS`(#974)), `iam/ai-asset-s3-role.*`·`iam/learning-asset-s3-role.*`의 버킷·클러스터 ARN, `eks/cluster.json`의 두 연결 role ARN. 다른 계정 번호 항목과 함께 바꾼다(#601 11/14 메모). 전체 순서와 교체 목록은 아래 [B 계정 전환 런북](#b-계정-전환-런북-809)이다.

## 리포트 Gemma SageMaker 엔드포인트 (#746, 2026-11-18)

리포트 상세 설명 Gemma는 같은 계정·VPC의 SageMaker 실시간 엔드포인트에서 돈다. 검증 결과와 결정은 [infra 보고서 9.13.9](../../docs/report/infra.md#9139-sagemaker-검증과-엔드포인트-구성-746-2026-11-18)에 있다.

| 파일 | 내용 |
|---|---|
| `sagemaker/explanation-endpoint.json` | 원하는 상태: 이미지, S3 경로, 인스턴스, 메모리 예약, vLLM 환경 변수, LoRA 사용 여부, 예약 창 |
| `sagemaker_explanation.py` | `status`·`manifest`·`verify`·`lock`·`apply`·`schedule`·`copies`·`invoke`·`delete`. aws CLI만 쓴다 |
| `sagemaker/model-check/` | 서빙 이미지(#777): vLLM DLC + 시작 때 `/opt/ml/model` 해시 검사 + `POST /adapters` LoRA 검사. 수동 빌드·게시, digest 고정 |
| `iam/sagemaker-explanation-role.*` | SageMaker 실행 역할(S3 `explanation/*` 읽기, DLC·검사 이미지 받기, 로그·지표, VPC ENI) |
| `iam/ai-asset-s3-role.inline.ai-sagemaker-explanation-invoke.json` | ai Pod Identity 역할의 `sagemaker:InvokeEndpoint`(엔드포인트와 IC ARN 모두 필요) |

새 계정 순서:

1. `demo_stack.py apply --confirm-account <계정>`으로 실행 역할을 만든다. 역할이 이미 있으면 inline 정책은 `aws iam put-role-policy`로 넣는다(ai 역할 추가분 포함). Pod 재시작은 필요 없다.
2. 보안 그룹 `sagomungchi-demo-sagemaker-explanation-sg`를 VPC에 만든다. ingress는 없고 egress는 tcp 443만 둔다.
3. `sagemaker_explanation.py manifest --upload`로 승인 목록을 한 번만 올린다. 이때 LoRA 사용 여부(`useAdapter`)를 먼저 정한다. 버전 경로(`explanation/<버전>/`)에는 manifest.json과 manifest에 적힌 파일만 둔다(`base-gguf/`·`adapter-gguf/` 등은 지운다). SageMaker가 버전 경로 전체를 받고, 컨테이너가 남는 파일을 거부하기 때문이다.
4. 검사 이미지를 빌드해 그 계정 ECR `sagomungchi/sagemaker-explanation`(IMMUTABLE)에 올리고, 받은 digest를 `explanation-endpoint.json` `imageDigest`에 적는다(#777, 절차는 [infra 9.17](../../docs/report/infra.md#917-리포트-gemma-sagemaker-경로-잠금과-적재-때-해시-검사-777-2026-11-18)).
5. `lock --confirm-account <계정>`(먼저 `--dry-run`)으로 버전 경로의 쓰기·삭제를 버킷 정책으로 막는다. `verify`가 통과해야 잠근다.
6. `apply --confirm-account <계정>`을 실행한다. manifest 대조 → 모델 → 설정 → 엔드포인트 → IC(어댑터 포함) → Auto Scaling 대상 순서다. 인스턴스가 이미 떠 있어도 IC가 InService가 되기까지 약 9분 걸린다.
7. `schedule`로 주간 창(일 23:30·월 02:00 KST, 0대에서 켜지는 데 약 21분)을 건다. 시험은 `--test-start/--test-end`(UTC)로 시각을 당겨 확인한다.

- 계정 번호가 들어간 곳: `iam/sagemaker-explanation-role.*`, `iam/ai-asset-s3-role.inline.ai-sagemaker-explanation-invoke.json`. 버킷 이름과 이미지 레지스트리는 스크립트가 sts로 채운다. `imageDigest`는 계정마다 게시한 값으로 바꾼다.
- 시험 엔드포인트는 `--spec <다른 JSON>`으로 이름·경로를 바꿔 같은 명령으로 만들고 지운다(#777 시험).
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
- `audit-demo-data.sql`: read-only transaction에서 건수만 조회한다. core_db(core_app)는 계정·학생의 demo flag별 건수, 결제 건수, DB CONNECT 권한과 #624 시연 학생 준비 상태(프리미엄·추억의 벽·가구·지난 주 리포트)를 본다. learning_db(learning_app)는 진행 주 이전 액자 수·검색 문서 상태·지난 주 M2 점수 답변, 최근 3주 판정 결과·보류 사유별 건수(`MODEL_DISAGREEMENT` 포함)와 M2 입력이 있는 공개 기준표 수(#668)를, report_db(report_app)는 지난 주 주간 리포트의 설명 카드·최근 일일 리포트를 본다. `dummy854_*`는 #808 더미 가족(아래 절) 점검과 결제의 시연 표시별 집계(#811 NFR-QA-03)다. 접속한 DB에 맞는 절만 실행되므로 같은 파일을 세 DB에 각각 돌린다(`demo-db-oneoff.k8s.yaml`의 `PGDATABASE`·Secret을 바꿔 실행). 개인정보를 출력하지 않는다. demo flag가 false라고 실제 사용자라고 단정하거나, 별도 DB라는 이유만으로 모든 데이터가 demo라고 단정하지 않는다. 실제 배포의 외부 키·접속 대상·데이터 생성 절차와 함께 해석한다.
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

1. 자녀 등록: `python demo_account_data.py children --child <초3 닉네임>:3 --child <초5 닉네임>:5`. 이미 있는 자녀는 그대로 둔다. 필수 동의 문서 새 버전 시행일(예: #732 처리방침 1.2·법정대리인 동의서 1.1, 2026-11-23) 뒤에는 같은 명령을 다시 돌려 계정 동의(`/me` `CONSENT_REQUIRED`일 때)와 기존 자녀 법정대리인 재동의(`guardianConsentRequired`일 때)를 보낸다. 안 하면 `student`·`solve`의 학생 세션이 403이다(#894)
2. 시연 표시·프리미엄: `demo-db-oneoff.k8s.yaml`로 `prepare-demo-account-students.sql` 실행(`psql -v g3=<초3> -v g5=<초5> -v product_code=PREMIUM`). Pod의 `command`에 `-v` 세 개를 더한다.
3. 설명 카드용 기준표(첫 `solve` 전에): `python demo_account_data.py m2-rubric --weeks 2026-11-16,2026-11-23,2026-11-30 [--m2-input <JSON>]`. 먼저 `--dry-run`으로 채울 미션을 본다. 공개 기준표를 복사해 M2 입력만 더한 새 기준표 버전을 저장·검토 승인·재게시하고, 이미 있으면 그대로 둔다. 주마다 "M2 입력 서술 3유형"이 나와야 한다. 입력이 없는 미션이나 공개 안 된 수정본이 걸린 미션이 있으면 실패하고 이름을 알려 준다. 판정은 답변 때의 공개 기준표로 하므로 보강 전에 푼 답변에는 M2 점수가 생기지 않는다
4. 앞선 2회차(시험 시계):
   - `docker build -f infrastructure/aws/demo-clock.Dockerfile --build-arg BASE=<배포 중인 core 이미지> -t <같은 ECR 저장소>:<태그>-demo-clock .`(learning도 같게) → ECR push
   - core·learning Deployment를 그 이미지로 바꾸고 `LD_PRELOAD=/usr/lib/x86_64-linux-gnu/faketime/libfaketime.so.1`, `FAKETIME=@2026-11-21 05:00:00`(UTC, 토요일 14:00 KST), `FAKETIME_FORCE_MONOTONIC_FIX=1`, `FAKETIME_DONT_RESET=1`을 넣는다. monotonic을 위조하지 않으면(`FAKETIME_DONT_FAKE_MONOTONIC=1`) JVM 대기 스레드가 CPU 1코어를 계속 쓴다
   - 롤아웃이 끝나면 `solve --child <초3>`, `solve --child <초5>`. 이어서 `FAKETIME=@2026-11-28 05:00:00`으로 바꿔 두 번 더 `solve`
   - 앞선 주의 주간 리포트까지 원하면 그 주 일요일 23:56 KST로 옮겨 월요일 00:00 스케줄을 기다린다(리포트 Gemma SageMaker 예약 확장은 실제 시각 기준이라 이때만 기반 IC 사본을 1로 직접 올린다). 시연에 필요한 것은 지난 주 리포트뿐이라 생략할 수 있다
   - 원래 이미지·환경 변수로 되돌리고(`kubectl set image`·`kubectl set env ...-`), Pod 시각이 실제 시각인지 확인한다. 이 동안 가짜 시각으로 서명한 S3 그림 URL은 403이고, 다른 사용자가 쓰지 않는 시간에만 한다
5. 지난 주(실제 시각): 12/4(금)~12/5(토)에 `solve` 두 번. 무료도 금·토에는 다섯 요일이 모두 열린다(#483). 12/6 00:00 일일, 12/7 00:00 주간 리포트가 정기 스케줄로 만들어진다
6. 12/7 00:00 이후: `decorate --child <닉네임> --min-frames 3 --keep-newest-unseen --furniture <DESK 코드>,<WALL 코드>`(가장 최근 회차는 "새 액자"로 남김) → `verify --child <닉네임> --query "<답변 소재 질문>"` → 세 DB에 `audit-demo-data.sql`

되돌리기: 시험 구독은 `prepare-demo-account-students.sql` 머리말의 UPDATE로 해지한다. 학습 기록은 자녀 프로필 삭제(학부모 설정)로 지운다.

## 전체 서비스 더미 데이터 (#808)

2026-11-22 작성, 2026-11-23 kind 리허설(가족 6개)로 한 번 돌렸다([infra 9.7.6.7](../../docs/report/infra.md#9767-u5-kind-리허설-결과-2026-11-23)). B에서는 아직 실행하지 않았다. 12/7 시연에서 학생 커뮤니티(친구 생각·반응·친구 방)·학부모(리포트·분석 대화·알림)·관리자 화면(운영 현황·작업 상태·AI 사용량·결제·신고·문의·공지)이 비어 보이지 않게, 가상 가족 30개(자녀 36명)에 4주(W1 11/9·W2 11/16·W3 11/23은 시험 시계, W4 11/30은 실제 시각) 기록을 공개 API로 쌓는다. 계획·화면별 최소 건수·결정은 [infra 9.7.6](../../docs/report/infra.md#976-전체-서비스-시연용-더미-데이터-생성-계획-854-2026-11-22), 실행 결과는 그 절 아래에 남긴다. 위 #624 시연 학생 절차와 같은 시계 정지점에서 함께 돈다.

테마·미션·가구·소품은 만들지 않는다. 테마·미션은 LLM·RAG 생성 담당자가 게시한다(#890). 스크립트는 게시 여부만 확인하고 없으면 멈춘다.

| 파일 | 역할 |
|---|---|
| `dummy854-families.json` | 가족 목록(로그인 ID `dm854p01`~`30`·이름 `가상가족01`~`30`·자녀 별명·학년·무리·프리미엄·공개)과 무리별 주 문제 수. 비밀값 없음. 앞 6가족(자녀 8명)이 kind 리허설용 |
| `evaluation/load/prepare_accounts.py --families` | 가입·계정 동의·자녀(GUARDIAN)·자녀별 COMMUNITY 동의·기기·PIN. 비밀번호·PIN은 저장소 밖 비밀 파일. 가입 직후 비밀번호를 먼저 저장해 중간에 멈춰도 다음 실행이 이어서 한다. 다시 돌리면 준비된 가족도 로그인해 계정 동의와 기존 자녀 법정대리인 재동의(`guardianConsentRequired`일 때)를 다시 보낸다(#894) |
| `add-dummy854-subscriptions.sql` | dm854p 자녀 중 프리미엄 학생에게 결제 없는 시험 구독(`product_snapshot.demoAccount = '854'`), dm854p 학부모·자녀 `is_demo` 표시 |
| `dummy854_data.py` | `plan`(API 없이 무리·주별 문제 수·구독 SQL 값) → `community`(원문 공개·커뮤니티 공개) → `solve --stage wed\|sat`(무리별 문제 수만큼) → `react` → `room` → `converse` → `support` → `admin-ops`. `demo_account_data.py`의 풀이 흐름을 그대로 쓰고 학생마다 답변 소재가 다르다 |
| `audit-demo-data.sql` | `dummy854_*`: core 학년별 학생·구독·주별 리포트 작업·신고·문의·대화·공지·결제(시연 표시별), learning 주별 완료 문제 수 분포·액자·공유물·반응, report 주별 리포트 상태 |

### 사전 조건(0단계)

1. #890 테마: `python demo_account_data.py themes --weeks 2026-11-09,2026-11-16,2026-11-23,2026-11-30,2026-12-07 --grades G3,G4,G5,G6`이 모두 "게시됨". 12/7 주 테마가 있어야 실제 12/2(수) 03:00 자동 초안이 건너뛴다. kind 리허설은 게시된 학년만 `--grades`로 돌리고 빠진 주·학년은 결과에 적는다
2. 판매 중 가구(DESK 등)·소품(DECOR) 코드 확인: 관리자 `GET /admin/look-items?status=ON_SALE`(50개씩). 없으면 `room`은 생략하고 기록한다
3. 관리자 계정: CONTENT(`DEMO_ADMIN_*`, 정답 조회), ADMIN+SERVICE_OPS(`DEMO_OPS_ADMIN_*`, 공지·문의 답변·신고 처리. 같은 계정이면 생략)
4. 비용: OpenAI 누적 $5 상한(결정 3). 단계마다 `psql -v from="'<시작 UTC>'" -v to="'<끝 UTC>'" -f evaluation/load/llm_usage_window.sql`(실제 시각)로 보고 넘을 것 같으면 멈춘다

### 순서

환경 변수는 `demo_account_data.py` 머리말과 같다. 아래 `D`는 `python infrastructure/aws/dummy854_data.py --secrets <비밀 파일>`(kind 리허설은 `--count 6`, 테마가 일부 학년만 있으면 `--grades G3,G5`도). B는 `prepare_accounts.py`에 `--base-url https://www.sagomungchi.co.kr`, kind는 `--base-url http://127.0.0.1 --host api.sagomungchi.local --origin http://localhost:5173`.

| 단계 | 시각(KST) | 명령 | 확인 |
|---|---|---|---|
| 1 | 실제 | `python evaluation/load/prepare_accounts.py --families infrastructure/aws/dummy854-families.json --secrets <저장소 밖>/dummy854.json --wait [--count 6]` | "30/30 families ready"(가입 제한 IP당 10분 5회라 약 60분). 다시 돌리면 가입 없이 가족마다 로그인·동의만 확인. 필수 동의 문서 새 버전 시행일 뒤 첫 풀이 전에 다시 돌린다(#894) |
| 2 | 실제 | `D plan`의 프리미엄 별명 목록으로 `add-dummy854-subscriptions.sql`(`psql -v premium=<목록> -v expected=12 -v product_code=PREMIUM`, kind는 `expected=4`·`LOCAL-PLUS`). AWS는 `demo-db-oneoff.k8s.yaml`의 `command`에 `-v` 세 개를 더한다 | 학년별 `premium_854` 합이 expected |
| 3 | 실제, 첫 풀이 전 | `D community --demo-child <초3 시연 별명> --demo-child <초5 시연 별명>` | 공개 켬 20명+시연 2명. 공유물은 돌아보기 저장 때만 생기므로 반드시 W1 전에 |
| 4 | 시계 시작 전 | 아래 "시계 켜기" | Pod 시각이 첫 정지점 |
| 5~7 | W1~W3 정지점 | 아래 정지점 표 | 정지점마다 실패 학생 없음 |
| 8 | W3 끝 | 아래 "시계 끄기" | Pod 실제 시각, 이미지·환경 변수가 배포 값 |
| 9 | 수 12/2 19:00 | `D solve --stage wed` | |
| 9 | 토 12/5 14:00 | `D solve --stage sat` → #624 `solve`(위 절 순서 5) → `D react` → `D room --furniture <가구 코드> --decor <소품 코드 2개>` → `D converse` → `D support` | 정정 요청 4·커뮤니티 신고 2(G4·G6 공유물만, 처리 전까지 숨김)·문의 8 |
| 9 | 일 12/6 | `D admin-ops`, 토스 테스트 결제(위젯이 동작할 때만 손으로, 결정 4) | 공지 3·문의 답변 4·정정 처리 2 |
| 10 | 12/7 00:00 뒤 | #624 `decorate`·`verify`, 세 DB `audit-demo-data.sql`, `llm_usage_window.sql`, 리텐션(`scripts/retention_metrics` `-v from=2026-11-09 -v to=2026-12-07 -v include_demo=1`), 화면 확인 | infra 9.7.6.2 화면별 최소 건수 |

### 시계 정지점(W1~W3)

`FAKETIME`은 UTC다. 정지점마다 core·learning 두 Deployment의 `FAKETIME`만 바꾸고 롤아웃을 기다린다(Pod가 다시 뜨고 그 사이 자정은 지나가지 않는다). 리포트 ShedLock은 DB(실제) 시각 기준 최소 1분 잠금이라 경계 정지점 사이 실제 간격을 1분 넘게 둔다.

- 롤아웃이 끝나도 이전 Pod가 `Terminating`으로 약 1분 더 요청을 받는다. 그동안 API를 부르면 이전 가짜 시각으로 발급한 토큰을 새 Pod가 `TOKEN_EXPIRED`로 거절한다. `kubectl -n app get pods`에서 core·learning `Terminating`이 없어진 뒤 명령을 돌린다(kind 리허설 실측: 정지점 전환 약 40초)
- 같은 `FAKETIME` 값을 다시 넣으면 Pod가 다시 뜨지 않는다(시계가 그대로 흐름). 같은 시각에서 다시 시작하려면 `kubectl -n app rollout restart`
- Git Bash에서 `kubectl set env`를 부르면 `LD_PRELOAD=/usr/...` 경로가 Windows 경로로 바뀌어 시계가 켜지지 않는다. `MSYS_NO_PATHCONV=1`을 붙이거나 PowerShell에서 실행하고, 켠 뒤 `kubectl -n app get deploy core-service -o yaml`의 `LD_PRELOAD` 값을 본다

| 주 | 수 19:00(5문제 무리 월~수) | 토 14:00(나머지·정답·반응) | 토 23:56(→ 일 00:00 일일) | 일 23:56(→ 월 00:00 일일·주간) |
|---|---|---|---|---|
| W1 | `@2026-11-11 10:00:00` | `@2026-11-14 05:00:00` | `@2026-11-14 14:56:00` | `@2026-11-15 14:56:00` |
| W2 | `@2026-11-18 10:00:00` | `@2026-11-21 05:00:00` | `@2026-11-21 14:56:00` | `@2026-11-22 14:56:00` |
| W3 | `@2026-11-25 10:00:00` | `@2026-11-28 05:00:00` | `@2026-11-28 14:56:00` | `@2026-11-29 14:56:00` |

- 수 19:00: `D solve --stage wed`
- 토 14:00: `D solve --stage sat` → (W2·W3만) #624 `solve --child <초3>`·`solve --child <초5>` → `D react`(모든 풀이 뒤)
- 토 23:56·일 23:56: 롤아웃 뒤 가짜 00:00이 지나고 5분 더 기다린 뒤 관리자 작업 상태 또는 `audit-demo-data.sql` `dummy854_report_jobs`로 그 기간 작업이 `COMPLETED`인지 본다. 주간 서술도 리포트 Gemma(SageMaker)로 부르고 실패하면 대체 문구 없이 작업이 `FAILED(GENERATION_FAILED)`가 된다(설계상 대체 없음, kind 리허설 발견). SageMaker는 실제 시각 예약이라 W1~W3 경계에서는 0대이므로, **시계 동안 SageMaker를 손으로 1대로 켜 둔다(2026-11-23 결정)**. 켜 두지 않으면 그 주 기록이 있는 프리미엄 학생(더미 꾸준·보통 프리미엄, 시연 초5 W2·W3)의 주간 리포트가 실패한다. 기록 없는 학생·무료 학생·일일 리포트는 SageMaker와 상관없이 `COMPLETED`다
- 정지점 중간에 실패하면 같은 정지점에서 같은 명령을 다시 돌린다(끝난 요일·반응은 건너뜀). 주를 넘긴 뒤 빠진 데이터는 채우지 않고 기록한다
- 수요일 03:00을 넘는 정지점은 없다(테마 초안 자동 생성, 1개 $4~5). 시계 동안 learning 초안 생성도 끈다

### 시계 켜기·끄기

시험 시계 이미지는 위 #624 순서 4와 같다(`demo-clock.Dockerfile`, core·learning 각각 ECR push).

켜기
0. B만: 시계 시작 약 30분 전에 `sagemaker_explanation.py --profile <B> copies 1`로 리포트 Gemma를 1대로 켜고(0대에서 약 21분) `status`로 InService·copies 1을 확인한다. 주간 예약(`schedule`)은 건드리지 않는다. 비용은 `ml.g6e.xlarge` 시간당 약 $3.2, W1~W3 동안 켜 두면 약 3시간·$10
1. B만: Argo CD가 되돌리지 않게 한다. ApplicationSet 템플릿이 자동 동기화라 Application만 끄면 ApplicationSet 컨트롤러가 다시 켤 수 있으므로 컨트롤러를 먼저 멈춘다
   - `kubectl -n argocd get deploy`로 이름 확인 → `kubectl -n argocd scale deploy argocd-applicationset-controller --replicas=0`
   - `argocd app set prod-core-service --sync-policy none`, `argocd app set prod-learning-service --sync-policy none`
   - B 첫 정지점에서 1~2분 뒤 `argocd app get prod-core-service`의 Sync Policy가 계속 `<none>`인지 확인(kind에는 ApplicationSet·자동 동기화가 없어 확인 불가)
2. `kubectl -n app set image deploy/core-service core-service=<core 시계 이미지>`, learning도 같게
3. `kubectl -n app set env deploy/core-service LD_PRELOAD=/usr/lib/x86_64-linux-gnu/faketime/libfaketime.so.1 FAKETIME="@2026-11-11 10:00:00" FAKETIME_FORCE_MONOTONIC_FIX=1 FAKETIME_DONT_RESET=1`, learning은 같은 값에 `APP_THEMEDRAFT_ENABLED=false`(수 03:00 자동 초안·초안 생성 주기 끔)
4. `kubectl -n app rollout status deploy/core-service`·`learning-service` → 이전 Pod `Terminating`이 없어질 때까지 기다린다. `kubectl exec ... date -u`는 새 프로세스라 늘 `FAKETIME` 시작 값만 보여 주므로 앱 시각 확인으로 쓰지 않는다. 앱 시각은 `kubectl -n app logs deploy/core-service -c core-service --tail=1`의 로그 시각 또는 `FAKETIME` + (지금 − 컨테이너 시작 시각)으로 본다

끄기(W3 끝)
1. B: `argocd app set prod-core-service --sync-policy automated --auto-prune --self-heal`(learning도) → selfHeal이 이미지·환경 변수를 Git 값으로 되돌린다 → `kubectl -n argocd scale deploy argocd-applicationset-controller --replicas=1` → 두 Application Synced·Healthy
2. kind: `kubectl -n app set image`로 원래 이미지, `kubectl -n app set env deploy/<앱> LD_PRELOAD- FAKETIME- FAKETIME_FORCE_MONOTONIC_FIX- FAKETIME_DONT_RESET-`(learning은 `APP_THEMEDRAFT_ENABLED-`도)
3. 두 Pod `date -u`가 실제 시각이고 ReplicaSet이 배포 상태와 같은지 확인. 시계 동안 가짜 시각으로 서명한 S3 그림 URL은 깨지므로 화면 확인은 끈 뒤에 한다
4. B: W1~W3 주간 리포트(일 23:56 정지점)가 모두 `COMPLETED`인지 본 뒤 `sagemaker_explanation.py --profile <B> copies 0`으로 내린다. **11/29 23:30 실제 주간 창(#886 PRF-03 0대 복귀 확인) 전에 끝낸다.** 예약은 그대로라 그 창은 평소대로 켜지고 월 02:00에 0대로 돌아간다
5. 실제 11/30 00:00 정기 실행이 가짜 11/30 00:00에 만든 W3 주간 리포트를 다시 만들지 않는지 `dummy854_report_jobs`로 확인(kind 리허설 확인 항목)

되돌리기: 시험 구독은 `add-dummy854-subscriptions.sql` 머리말의 UPDATE로 해지한다. 더미 기록은 dm854p 학부모가 자녀 프로필을 삭제(학부모 설정)해 지운다.

## B 계정 전환 런북 (#809)

2026-11-19 작성, **아직 실행하지 않은 절차**다. 시연용 B 계정을 11/26~27에 부트스트랩하고 11/28에 배포한다(#783). B의 DB는 A 최종 RDS 스냅샷을 복원한다(2026-11-18 결정). 이 문서 작업에서 AWS는 조회도 변경도 하지 않았다.

- 위치: 실행 절차는 쓰는 스크립트(`demo_stack.py`·`sagemaker_explanation.py`) 옆인 이 README에 둔다. `docs/report/infra.md`는 A에서 한 일의 기록이라 계정 번호를 바꿀 때도 A 값을 그대로 둔다. #760의 빈 클러스터 첫 배포와 B DB용 A 쪽 스냅샷 단계(A-1~A-3)는 [infra 보고서 9.16](../../docs/report/infra.md#916-빈-클러스터-첫-배포와-b-계정-부트스트랩-보완-760-2026-11-18)에 있고(세부 KMS 단계는 아래 "선행 (A 계정, 11/25 A 종료 직전)", 결정은 infra 9.19), B 순서는 이 런북 하나로 둔다. 실행 결과와 실제 걸린 시간은 끝난 뒤 infra 보고서에 절로 남긴다.
- 배포 방식: 지금 방식(cd-release가 앱 5종을 배포하고 나머지는 손으로 적용)을 기준으로 썼다. 팀이 B에 Argo CD 도입을 검토 중이며(미결정), 도입하면 달라지는 단계를 표의 "Argo CD면" 열에 적었다.
- ★는 실행 전 동섭 승인 지점이다. 예상 시간은 11/17·11/19 A 실측(infra 9.11, #601 기록)을 바탕으로 한 추정이다. 명령의 `<B>`는 B 프로필, `<B 계정>`은 12자리 번호다.

### 확인 필요

값을 받으면 채운다. 질문은 #809 댓글에 남겼다.

| 항목 | 값 | 영향 |
|---|---|---|
| B 계정 번호 | (미정) | 아래 "A 계정 값 교체", CD 변수 |
| 리전 | (미정. A와 같은 `ap-northeast-2`로 가정) | `demo-stack.json` `region`·서브넷 AZ(2a·2b), CloudFront origin-facing prefix list `pl-22a6434b`(리전별 값), ECR 주소, `CD_AWS_REGION`, prod 앱 values의 S3 443 egress 대역(S3 prefix list 대역, report-api·report-worker·scoring), report-worker `MEMORY_BOOK_ASSET_ORIGINS`의 `s3.<리전>` 부분(#974). 다르면 계정 번호와 별도로 바꾼다 |
| 도메인 | `https://www.sagomungchi.co.kr`(가비아 DNS, `www` CNAME → CloudFront, 2026-11-24 결정). B에서 할 일: B us-east-1 ACM 인증서 재발급(www·루트) → 가비아에 검증 CNAME 추가 → A CloudFront에서 대체 도메인을 뗀 뒤 B CloudFront에 붙이기(같은 별칭은 두 배포에 동시에 둘 수 없음) → 가비아 `www` CNAME 대상을 B CloudFront 기본 주소로 바꾸기 | 앱 값은 그대로: core `AUTH_WEB_ORIGIN`, Google OAuth origin·callback, `CD_BASE_URL`, 쿠키(같은 도메인이라 그대로). 별칭을 떼고 DNS가 바뀌는 동안 시연 주소가 잠깐 끊긴다 |
| A 최종 스냅샷·KMS 키 공유 | 11/19 스냅샷은 `aws/rds` 키라 공유할 수 없고 11/25 재가동으로 DB가 바뀌므로 B에 쓰지 않는다(2026-11-23 정리). 11/25 A 종료 직전 새로 만든다(아래 "선행 (A 계정, 11/25 A 종료 직전)") | 선행 A-K, 5단계 |
| B 복원 주체 | (미정. B 루트 위임으로 둘지, B 복원 역할 하나만 허용할지) | A-K1 키 정책의 주체, B 작업자 IAM 정책 |
| A Secrets Manager 값 보존 | (미정. DB 계정 6개·결제 암호화 키를 B 입력 때까지 저장소 밖에 보관했는지) | 3단계 |
| A S3 객체 | (미정. A 버킷을 B 복사가 끝날 때까지 남기고 B 작업자가 읽게 하는지) | 2단계 |
| B AWS CLI 프로필 이름 | (미정) | 명령의 `--profile`, `redeploy-app.ps1` 기본값 `sagomungchi-provided`, runner의 `CD_AWS_PROFILE` |
| scoring 모델 경로 전환 | (결정 필요) | 8단계. 정하지 않으면 첫 배포가 scoring에서 멈춘다 |
| #777 적재 때 검사 이미지 | 미정 | 13단계 |

### 선행 (저장소, 11/26 전)

1. #760(계획 `currentRelease: "none"`, `redeploy-app.ps1 -AllowInstall`, scoring·report SA를 chart가 만듦)이 develop에 병합돼 있다. 없으면 11/17처럼 첫 배포가 `release: not found`로 멈춘다.
2. 계정 번호 교체 PR(아래 "A 계정 값 교체")을 develop에 병합한다. cd-release는 main SHA만 배포하고 `redeploy-app.ps1`이 계정 번호를 확인하므로, 이 교체와 6a단계 값 교체가 main에 들어가야 B에 배포된다(develop → main 릴리스, #623 시연 고정 버전).
3. GitHub 변수(손으로, A 종료 뒤): Repository `CD_AWS_ROLE_ARN`·`CD_ECR_REGISTRY`·`CD_AWS_REGION`, Environment `prod` `CD_BASE_URL`(도메인이 같아 `https://www.sagomungchi.co.kr` 그대로, [CD README](../cd/README.md)). OIDC subject 설정은 저장소 단위라 바꾸지 않는다. Argo CD(#858) 방식이면 `CD_BASE_URL`은 비상용 Helm 경로만 쓰고, 경로 확인은 작업자 PC에서 `https://www.sagomungchi.co.kr`을 직접 준다. digest PR 저장소 설정(Actions PR 생성 허용·main 보호·CODEOWNERS, [CD README B2](../cd/README.md#b2-digest-pr-저장소-설정-858-관리자-손-작업-1124-예정))은 11/24에 이미 적용돼 있어야 하며 계정과 무관해 다시 하지 않는다. main의 `images/<release>.json` 저장소 주소는 A 레지스트리로 남아 있으므로 B 첫 digest PR은 서비스 5개 전부와 `"jobs": ["tox-retrain"]`(재학습 이미지 파일도 A 주소, #985)을 넣고 `allowRepositoryChange=true`로 실행한다(16단계).

### 선행 (A 계정, 11/25 A 종료 직전)

B 5단계(RDS 복원)에 쓸 공유 스냅샷을 A에서 만든다. 결정과 이유는 [infra 보고서 9.19](../../docs/report/infra.md#919-b-복원용-스냅샷의-고객-관리-kms-키-공유-809-2026-11-23), A 11/25 순서에서는 [9.16.2](../../docs/report/infra.md#9162-계정별-순서)의 11단계다.

- **11/19 최종 스냅샷 `sagomungchi-demo-db-final-20261119`은 B에 쓰지 않는다.** AWS 관리 키(`aws/rds`)로 암호화된 스냅샷은 다른 계정과 공유할 수 없고(키 정책을 바꿀 수 없음), 11/25 A 재가동에서 migration·시연 데이터(#897 재동의 등)로 DB가 바뀌어 그 뒤 상태가 필요하다.
- 시점: 11/25 A 작업(#927 11/25 항목)이 모두 끝나고 **A RDS를 정지·삭제하기 전**. A-1(시험 데이터 정리, infra 9.16.2)을 A에서 하기로 했으면 그 뒤에 뜬다.
- B 계정 번호가 11/25까지 정해지지 않으면 A-K1(키 생성)~A-K3(CMK 복사)까지만 하고, A-K1의 B 허용과 A-K4 공유는 번호를 받은 뒤 한다. 두 작업은 A RDS가 꺼져 있어도 된다.
- 명령은 예시다. `<A>`는 A 프로필, `<A 계정>`·`<B 계정>`은 12자리 번호, `<CMK ARN>`은 A-K1에서 만든 키 ARN이다. 실제 값은 저장소에 적지 않는다.

| # | 단계 | 명령·방법 | 확인 | 예상 |
|---|---|---|---|---|
| A-K1★ | 고객 관리 KMS 키(CMK) | 대칭 키 1개를 만들고(기존 고객 관리 키가 있으면 그것을 써도 된다) 별칭 `alias/sagomungchi-demo-db-share`를 붙인다. 키 정책에 A 관리 문장(기본값)과 **B 허용 문장 2개**를 더한다(아래 정책 예시). 주체는 B 루트(`arn:aws:iam::<B 계정>:root`, B 안에서 IAM 정책으로 다시 좁힘) 또는 B 복원 역할 ARN(확인 필요 표의 "B 복원 주체") | `describe-key`의 `KeyManager=CUSTOMER`·`KeyState=Enabled`, `get-key-policy`에 B 주체 | 10분 |
| A-K2★ | 새 수동 스냅샷 | `create-db-snapshot`으로 A RDS의 현재 상태를 뜬다. 이 스냅샷은 인스턴스와 같은 `aws/rds` 키로 암호화된다 | `Status=available` | 확인 필요(20GiB gp3, 11/19 소요 시간 기록 없음. 실측을 9.19에 적는다) |
| A-K3★ | CMK로 스냅샷 복사 | `copy-db-snapshot --kms-key-id <CMK ARN>`. 같은 리전 복사지만 키가 바뀌어 전체 복사가 된다 | 복사본 `KmsKeyId`가 `<CMK ARN>`, `Encrypted=true`, `Status=available` | 확인 필요(같은 리전 키 변경 복사, 실측 기록) |
| A-K4★ | B에 공유 | `modify-db-snapshot-attribute --attribute-name restore --values-to-add <B 계정>`. CMK 복사본만 공유한다(`aws/rds` 스냅샷은 이 명령이 거부됨) | `describe-db-snapshot-attributes`의 `restore`에 B 번호만(`all` 없음) | 5분 |
| A-K5 | 보존 | CMK·공유 스냅샷(A-K3 복사본)·A-K2 원본·A Secrets Manager의 DB 계정 값 6개·`PAYMENT_BILLING_ENCRYPTION_KEY`를 **B 5단계 복원 확인 전까지 지우지 않는다**(infra 9.16.2 A-3). A 정리 목록에서 이 다섯 가지를 빼 둔다 | A 정리 뒤에도 키 `Enabled`, 스냅샷 `available` | — |

```powershell
$p = '<A>'
# A-K1 키 생성(정책은 저장소 밖 파일. 아래 예시 문장을 기본 정책에 더함)
aws kms create-key --description "sagomungchi demo DB snapshot share to B" --key-usage ENCRYPT_DECRYPT --key-spec SYMMETRIC_DEFAULT --profile $p
aws kms create-alias --alias-name alias/sagomungchi-demo-db-share --target-key-id <키 ID> --profile $p
aws kms put-key-policy --key-id <CMK ARN> --policy-name default --policy file://<저장소 밖>/db-share-key-policy.json --profile $p
# A-K2·A-K3
aws rds create-db-snapshot --db-instance-identifier sagomungchi-demo-db --db-snapshot-identifier sagomungchi-demo-db-final-20261125 --profile $p
aws rds wait db-snapshot-available --db-snapshot-identifier sagomungchi-demo-db-final-20261125 --profile $p
aws rds copy-db-snapshot --source-db-snapshot-identifier sagomungchi-demo-db-final-20261125 --target-db-snapshot-identifier sagomungchi-demo-db-share-20261125 `
  --kms-key-id <CMK ARN> --copy-tags --profile $p
aws rds wait db-snapshot-available --db-snapshot-identifier sagomungchi-demo-db-share-20261125 --profile $p
# A-K4
aws rds modify-db-snapshot-attribute --db-snapshot-identifier sagomungchi-demo-db-share-20261125 --attribute-name restore --values-to-add <B 계정> --profile $p
aws rds describe-db-snapshot-attributes --db-snapshot-identifier sagomungchi-demo-db-share-20261125 --profile $p
```

키 정책에 더할 B 허용 문장 예시(AWS 문서 "Sharing a DB snapshot"의 암호화 스냅샷 예시 기준, 실행 전 문서로 다시 확인):

```json
{
  "Sid": "AllowBUseOfTheKey",
  "Effect": "Allow",
  "Principal": { "AWS": "arn:aws:iam::<B 계정>:root" },
  "Action": ["kms:Encrypt", "kms:Decrypt", "kms:ReEncrypt*", "kms:GenerateDataKey*", "kms:DescribeKey"],
  "Resource": "*"
},
{
  "Sid": "AllowBGrantsForRds",
  "Effect": "Allow",
  "Principal": { "AWS": "arn:aws:iam::<B 계정>:root" },
  "Action": ["kms:CreateGrant", "kms:ListGrants", "kms:RevokeGrant"],
  "Resource": "*",
  "Condition": { "Bool": { "kms:GrantIsForAWSResource": "true" } }
}
```

- 다른 계정 키는 키 정책만으로 쓸 수 없다. B 5단계를 하는 B 작업자(또는 복원 역할)의 IAM 정책에도 같은 동작을 `Resource: <CMK ARN>`으로 허용해야 한다(B 변경, 5단계 전에).
- 키 삭제 주의: `schedule-key-deletion`은 대기 기간(7~30일, 기본 30일)을 두지만 **예약하는 순간부터 키를 쓸 수 없다**. B가 자기 계정으로 복사(5단계 첫 `copy-db-snapshot`)하기 전에 예약하면 B는 복원할 수 없다. 잘못 예약했으면 `cancel-key-deletion` → `enable-key`로 되돌린다. A 계정을 닫으면 키·스냅샷도 쓸 수 없으므로 계정 해지도 B 복원 확인 뒤에 한다.
- 비용: KMS 고객 관리 키는 키당 월 $1(시간 비례), API 요청은 1만 건당 $0.03(AWS 공개 가격 기준, 실행 전 가격 페이지로 확인). 스냅샷은 A-K2 원본과 A-K3 복사본이 각각 전체 크기(20GiB 할당)로 과금될 수 있다. 서울 리전 스냅샷 GB-월 단가와 실제 크기는 확인 필요. B 복원이 확인되면 정리 여부를 동섭에게 묻는다.

### 순서

| # | 단계 | 명령·방법 | 확인 | 예상 | Argo CD면 |
|---|---|---|---|---|---|
| 0 | 도구·로그인 | AWS CLI v2, eksctl 0.231.0(공식 릴리스, 체크섬 확인), kubectl 1.35, Helm 4.3.1, argocd CLI v3.5.7(공식 릴리스 `argocd-windows-amd64.exe`, `cli_checksums.txt`로 확인), PowerShell 7, Python 3.12, Node.js·npm, gh. `aws sts get-caller-identity --profile <B>` | 계정이 B. 선행 1·2가 들어간 main SHA | 30분 | argocd CLI는 이 단계에 포함(#855) |
| 1★ | IAM·OIDC·ECR·S3·VPC | GitHub OIDC 제공자를 먼저 만든다([CD README A](../cd/README.md#a-aws-github-oidc-게시-역할-aws-변경), `demo_stack.py`가 관리하지 않음) → `python infrastructure/aws/demo_stack.py --profile <B> plan` → `apply --confirm-account <B 계정> --without-rds`. VPC·NAT·S3 endpoint, S3 4개, ECR 9개(재학습 `tox-retrain` 포함, #985), IAM 역할 13개(SageMaker 실행 역할·ai invoke 정책 포함), RDS SG·서브넷 그룹을 만들고 RDS 인스턴스만 만들지 않는다 | `plan`에서 `eks`·`secret`·`rds`만 MISSING | 20분 | 같음 |
| 2★ | S3 데이터 | 아래 "S3 복사" | `sagemaker_explanation.py --profile <B> verify` 13개 일치, scoring 객체 `FULL_OBJECT` SHA-256 | 서버 간 30분, 로컬 경유 1~2시간 | 같음 |
| 3★ | Secrets Manager 12개 | 이름은 `demo-stack.json` `secrets`. 값은 저장소 밖 파일로 `create-secret --secret-string file://…`(출력하지 않음). **A와 같아야 하는 값**: DB 계정 6개(복원 DB의 계정이 A 비밀번호를 그대로 갖고 `rds-bootstrap`은 비밀번호를 바꾸지 않음), `app/payment`의 `PAYMENT_BILLING_ENCRYPTION_KEY`(DB에 암호화해 둔 값을 읽는 키). **새 값 가능**: `app/internal` 6개·`platform/rabbitmq`(RabbitMQ는 새 PVC), `app/auth` JWT(새 값이면 기존 로그인은 다시 함). `app/ai`는 `OPENAI_API_KEY`·`THEME_VIDEO_CREDENTIALS_JSON`·`VIDEO_PROJECT`만 넣고 RunPod 키 `SAGOMUNGCHI_SLLM_SERVERLESS_GEMMA`·`SAGOMUNGCHI_SLLM_SERVERLESS_KEY_GEMMA`는 넣지 않는다(11/19 결정, ExternalSecret도 `OPENAI_API_KEY`만 읽음) | `plan`의 secret OK. 값은 보지 않고 `describe-secret`로 이름만 본다 | 30분 | 같음(ESO) |
| 4★ | CloudFront 먼저 | 아래 "손으로 하는 단계"의 CloudFront를 웹 origin만으로 먼저 만든다(OAC·`spa-router.js`·웹 버킷 policy). 시연 주소 `www.sagomungchi.co.kr`은 저장소 값이 바뀌지 않으므로, B 인증서·대체 도메인·가비아 CNAME 전환은 위 "확인 필요" 도메인 행 순서대로 A 종료 뒤 한다. `/api/*`의 ALB origin은 12단계에서 붙인다 | 배포 Deployed, B 기본 주소 기록 | 20분 | 같음 |
| 5★ | RDS 스냅샷 복원 | 선행 A-K4(공유)가 끝났는지 본 뒤 아래 "RDS 복원": B 작업자 IAM에 A CMK 허용 → 공유 스냅샷을 B 키로 복사 → 복원 | 복사본 `KmsKeyId`가 B 키, `plan`의 rds OK, `rds.force_ssl`, 새 endpoint 기록 | 40~60분 + 복사 시간(확인 필요) | 같음 |
| 6★ | EKS | `render-eksctl --operator-cidr <작업자 IP>/32 --out <저장소 밖>` → `eksctl create cluster -f <파일>` → `apply --confirm-account <B 계정> --after-eksctl`(RDS SG에 클러스터 SG 5432) → `plan` | 노드그룹 2개 OK, add-on 7개, Pod Identity 10개 | 30~40분(11/17 실측 17분) | 같음 |
| 6a | 자원 값 교체 PR | 아래 "B 자원을 만든 뒤 바꿀 값"(RDS endpoint·VPC·서브넷·클러스터 SG) → develop → main | main SHA에 B 값 | 1시간(리뷰 포함) | Argo CD가 읽을 브랜치에 같은 값 |
| 7 | 플랫폼 | **Argo CD 먼저(#855)**: [prod Argo CD README](../gitops/argocd/prod/README.md)대로 `helm install argocd argo/argo-cd --version 10.11.7 -n argocd --create-namespace -f infrastructure/gitops/environments/prod/argocd.json` → `argocd-notifications-secret`(Discord webhook, 값은 저장소 밖 파일) → `project.yaml` → `root-app.yaml` → root 손 동기화 1회 → admin 비밀번호 변경·초기 Secret 삭제. 그다음 [prod README 2절](../gitops/environments/prod/README.md#2-기반-자원--secret--저장소): gp3·namespace → ESO 2.14.0 → LB Controller 1.14.1(B `vpcId`) → `app/rds-ca` → `kubectl apply -f external-secret-resources.json` → `platform-network.json`·platform-data → Karpenter 1.15.1 → `karpenter-nodepool.json`(B 서브넷·SG) → `app-oneoff-db-network.json`·`app-check-pods-network.json` | Argo CD Pod 6개 Running(`application` 노드), `sagomungchi-prod-root` Synced·Healthy, Discord에 동기화 성공 1건. ESO Ready 14개(ExternalSecret 14, SecretStore 2), `ai-provider-credentials`에 `OPENAI_API_KEY`만, RabbitMQ 서비스별 계정 5개, NodePool limits CPU 4·16Gi | 30분(11/17 실측 3분) + Argo CD 15분 | 외부 chart·ExternalSecret·NetworkPolicy를 Application으로. ESO·CRD 순서는 sync wave |
| 7a | 관측(#784) | **7단계 root app 동기화 전에** `kubectl create namespace observability` → 관측 Secret 2개(`observability-credentials`의 Grafana admin, `discord-alert-webhook`의 `DISCORD_WEBHOOK_URL`. 값은 담당자, 출력하지 않음). 나머지는 플랫폼 Application([prod README](../gitops/environments/prod/README.md#argo-cd-플랫폼-application-856-2026-11-20))이 한다: wave 4 `prod-platform-network`(`observability-platform-network.json`), wave 8 `prod-observability`(Tempo 1Gi·Collector 지표 격리 포함). Secret이 없으면 wave 8이 Healthy가 안 되어 앱(wave 10)도 멈춘다. 비상용은 `helm upgrade --install observability infrastructure/gitops/charts/observability -n observability -f infrastructure/gitops/environments/prod/observability.json`(먼저 자동 동기화를 끈다) | `prod-observability` Synced/Healthy, Grafana 로그인·datasource, Tempo `/ready` 200, Prometheus `up`. 앱이 뜨기 전에는 LLM 비용 경보가 NoData로 Discord에 온다(11/17) | 15분 | Application(Secret 2개는 손으로, #856) |
| 8★ | DB 확인·모델 경로 | `demo_stack.py rds-bootstrap --kubeconfig <파일> --execute`(복원 DB라 DB·계정·`vector` 확장은 확인만, 멱등) → demo-db-oneoff로 `model_version` 활성 행과 `artifactUri` 조회 → **scoring 모델 경로 전환**(아래) | 활성 scoring 모델의 경로가 B 버킷에서 읽힘 | 30분 | 같음(master secret을 쓰므로 손으로, 훅으로 옮기지 않음). 경로 전환 전이면 `prod-scoring-service`만 Degraded로 남고 다른 앱 동기화는 막히지 않는다 |
| 9★ | 첫 배포 | Argo CD(#857): root app이 ApplicationSet `sagomungchi-prod-apps`(wave 10, 플랫폼 뒤)를 만들고 Application `prod-<앱>` 6개가 main의 `<앱>.json` + `images/<앱>.json`으로 자동 동기화. core·learning·report-api는 PreSync로 NetworkPolicy `<앱>-migration` → Job `<앱>-migrate-<revision>` 뒤 앱. `kubectl -n argocd get applications`, `kubectl -n app get jobs` | migration Job 3개 Complete(복원 DB라 새 migration만 적용), Application 6개 Synced/Healthy(scoring은 8단계 결정에 따라). 경로 확인은 fixture 쿠키 때문에 실패할 수 있다(15단계) | 30~40분 | (이 행이 Argo CD 기준) 막히면 비상용 Helm: 해당 Application 자동 동기화를 끄고 cd-release 계획 `currentRelease: "none"`, `services` 5개, 승인 1명(`redeploy-app.ps1 -AllowInstall`, [prod README](../gitops/environments/prod/README.md#argo-cd-배포-857-2026-11-20)) |
| 10 | 권한 정리 | 9단계 migration Job 3개 Complete 뒤 `rds-bootstrap --execute` 한 번 더(손으로) | 새 테이블 app 권한, 이력 테이블 app 권한 회수 | 5분 | 같음(master secret을 쓰므로 PostSync 훅으로 옮기지 않음, #857) |
| 11 | 웹 | 9단계와 같은 main SHA로 `frontend/web`에서 `npm ci && npm run build`(11/19처럼 env 없음) → `aws s3 cp dist/assets s3://<web 버킷>/assets --recursive` → 그 밖 정적 파일 → `index.html`을 `--cache-control no-cache`로 마지막 → `aws cloudfront create-invalidation --distribution-id <ID> --paths "/*"`(Git Bash면 `MSYS_NO_PATHCONV=1`) | CloudFront index의 해시 파일이 로컬 빌드와 같은 sha256, 콘솔 오류 0 | 15분 | 같음(Argo CD는 S3를 다루지 않음) |
| 12★ | ALB·API origin | `core-alb-network.json`은 플랫폼 Application wave 9 `prod-app-network`가 이미 적용했다(확인만). 검토한 core Ingress는 손으로(origin 헤더 실제 값은 Git 밖, Argo CD 대상 아님) → 새 ALB DNS로 CloudFront `/api/*` origin·behavior 추가(Google OAuth는 도메인이 같아 그대로) | `prod-app-network` Synced, prefix list만 허용, idle 120·XFF preserve, `/api/*` 응답 | 20분(11/17 실측 4분) | NetworkPolicy는 Application(#856), Ingress·CloudFront·OAuth는 손으로 |
| 13★ | SageMaker | [위 절](#리포트-gemma-sagemaker-엔드포인트-746-2026-11-18)의 새 계정 순서: SG `sagomungchi-demo-sagemaker-explanation-sg`(ingress 없음, egress 443) → `sagemaker_explanation.py --profile <B> verify` → `apply --confirm-account <B 계정>` → `schedule` → 확인 뒤 `copies 0`. `manifest.json`은 2단계에서 같은 sha256으로 복사했으므로 `manifest --upload`는 하지 않는다(같은 키면 `PreconditionFailed`). #777 검사 이미지는 미정: 쓰기로 하면 ECR 저장소 추가·이미지 게시 뒤 apply, 아니면 지금처럼 AWS DLC | 엔드포인트 InService, ai Pod에서 호출 200(infra 9.13.9), IC 0대로 내림 | 40분(IC 9분 + 인스턴스) | 같음 |
| 14 | 운영 데이터 | 스냅샷에 관리자·동의 문서·FREE 상품·모델 버전·성취기준 표·시연 학부모가 있다. 관리자 로그인, 모델 활성 상태·로딩(관리자 화면), 테마 그림 URL(learning presigned, B 버킷), 리포트 다운로드 | 모두 B 버킷에서 열림 | 20분 | 같음 |
| 15 | fixture·테마 | `www` CNAME을 B로 바꾼 뒤 `https://www.sagomungchi.co.kr`에서 fixture 학부모 Google 로그인(refresh 쿠키 7일)·학생 기기 등록(`student_device`, 도메인별)으로 fixture 파일 갱신. 시연 주차 테마 초안 생성 → 채택 → 미션 검토·게시(11/17 A에서 READY까지 14분). 11/30~12/8은 두 주라 주마다 | 학생 로그인이 `CHILD_NOT_LINKED`가 아님, 학생 주간 테마에 시연 주차 문제 | 1시간 | 같음 |
| 16 | 확인 | 같은 계획을 다시 승인받아 실행(migration `already-complete`, 앱 `upgrade`) 또는 `python scripts/verify_cd_deployment.py --base-url https://www.sagomungchi.co.kr --fixture <파일> --output <파일>` → 리포트 설명(SageMaker 창 안에서만) → #624 시연 데이터·#668 M2 입력은 각 절차대로 | 6단계 통과, 결과를 #783에 기록 | 30분 | 동기화 상태 Healthy를 함께 본다. 배포는 cd-release `delivery=pull-request`(B 첫 실행은 서비스 5개·`allowRepositoryChange=true`) → digest PR 승인·병합 → Synced/Healthy → `verify_cd_deployment.py` 결과를 PR 댓글로 → (시연 일정에 지장 없는 시점에) digest PR revert 복구 1회와 재배포([CD README](../cd/README.md#digest-pr-배포-기본-858)). 막히면 비상용 Helm(`delivery=helm-emergency`, 자동 동기화 끄고) |

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

위 "선행 (A 계정, 11/25 A 종료 직전)"의 A-K1~A-K4(A 고객 관리 KMS 키로 스냅샷 복사, 키 정책에 B 허용, 스냅샷 `restore` 속성에 B 추가)가 끝났다는 전제다. 11/19 최종 스냅샷 `sagomungchi-demo-db-final-20261119`은 `aws/rds` 키라 공유할 수 없고 11/25 뒤 DB와 다르므로 쓰지 않는다. 공유 스냅샷은 `sagomungchi-demo-db-share-20261125`(A 계정 소유)다.

1. B 작업자(또는 복원 역할) IAM 정책에 A CMK 동작을 허용한다: `kms:Decrypt`·`kms:DescribeKey`·`kms:ReEncrypt*`·`kms:GenerateDataKey*`·`kms:CreateGrant`(조건 `kms:GrantIsForAWSResource=true`), `Resource: <CMK ARN>`. 키 정책(A-K1)과 IAM 정책 둘 다 있어야 한다.
2. 공유 스냅샷을 B 계정 스냅샷으로 복사하면서 **B의 키로 다시 암호화**한다(아래는 B `aws/rds`. B에서 다시 공유할 일이 없으므로 관리 키로 충분하다). 복사본은 B 소유라 그 뒤 복원은 A 키·A 계정과 무관하다. 공유 스냅샷에서 바로 복원하지 않는 것은 A 키가 지워지거나 A 계정이 닫혀도 B가 다시 복원할 수 있게 하려는 것이다.
3. 복사본으로 복원·설정한다.

```powershell
$p = '<B>'
aws rds describe-db-snapshots --include-shared --snapshot-type shared --profile $p --query 'DBSnapshots[].[DBSnapshotArn,KmsKeyId,Status]'
aws rds copy-db-snapshot --source-db-snapshot-identifier arn:aws:rds:ap-northeast-2:<A 계정>:snapshot:sagomungchi-demo-db-share-20261125 `
  --target-db-snapshot-identifier sagomungchi-demo-db-from-a --kms-key-id alias/aws/rds --copy-tags --profile $p
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
- 시험 데이터 정리(부하 시험 계정·스텁 `llm_usage`·경로 확인용 임시 계정)를 A에서 못 했으면 여기서 정한다(infra 9.16.2 A-1).
- 복사가 `KMSKeyNotAccessibleFault`·`AccessDenied`로 멈추면 A-K1 키 정책의 B 주체, 1번 IAM 정책, 키 상태(`Enabled`, 삭제 예약 아님)를 차례로 본다.
- 끝나면 A 쪽 보존 자원(A-K5: CMK·공유 스냅샷·A-K2 원본·DB Secret 값)을 정리해도 되는지 동섭에게 묻는다(infra 9.16.2 A-3: B 복원 확인 전까지 보존). 정리 순서는 공유 해제(`--values-to-remove <B 계정>`) → 스냅샷 삭제 → 키 삭제 예약이다.

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
| A CMK 생성·키 정책 B 허용, 스냅샷 생성·CMK 복사·B 공유, 보존 | 선행 A-K1~A-K5(11/25 A 종료 직전, A 계정) | 위 "선행 (A 계정, 11/25 A 종료 직전)" | 같음 |
| B 작업자 IAM에 A CMK 허용, RDS 스냅샷 복사(B 키)·복원·설정 | 5 | 위 "RDS 복원" | 같음 |
| eksctl 클러스터·`--after-eksctl` | 6 | [EKS README](../eks/README.md) | 같음 |
| ESO·LB Controller·Karpenter chart, ExternalSecret·NetworkPolicy·NodePool 적용 | 7 | prod README 2절 | Application |
| 관측 Secret 2개(chart는 Application) | 7a(root app 전) | [관측 chart README](../gitops/charts/observability/README.md) | Secret만 손으로, chart·수집 정책은 Application(#856) |
| `rds-bootstrap` 앞뒤 | 8·10 | RDS master secret을 쓰므로 workflow에 넣지 않음(#760) | 훅 후보 |
| scoring 모델 경로 | 8 | 위 결정 | 같음 |
| 웹 빌드·S3 업로드·무효화 | 11 | prod README "main 기준 core·웹 재배포" | 같음 |
| ALB Ingress와 origin 헤더(Git 밖 실제 값, CloudFront와 양쪽 같게) | 12 | `core-ingress.redacted.json` | Ingress는 손으로 유지(헤더 실제 값이 Git 밖), `core-alb-network.json`은 Application(#856) |
| CloudFront `/api/*` origin·behavior | 12 | 위 "외부 요청 흐름" | 같음 |
| Google OAuth 승인 origin·redirect URI 2개 | 12 | 위 "배포·복구 유의 사항" | 같음 |
| SageMaker SG·엔드포인트·예약 | 13 | 위 SageMaker 절 | 같음 |
| fixture 쿠키·기기, 시연 주차 테마 | 15 | [CD README D](../cd/README.md#d-배포-후-경로-확인-fixture-작업자-pc에만) | 같음 |
| GitHub 변수 4개 | 선행 3 | CD README | 일부는 Argo CD 저장소 연결로 바뀜 |
| EKS 공개 접근 CIDR에 작업자 IP | 6, IP가 바뀔 때마다 | 11/19 A 재배포에서 IP가 바뀌어 다시 추가함 | 같음 |

### A 계정 값 교체

B 계정 번호를 받으면 한 번에 바꾼다. 분류 기준은 [`scripts/aws_account_switch.py`](../../scripts/aws_account_switch.py)의 `CHANGE`·`RECORD`이고, 분류되지 않은 파일에 A 번호가 있으면 스크립트가 멈춘다(새로 생긴 파일을 먼저 분류한다). 바꿀 파일 안에서도 `A 계정 347161580747`처럼 A 계정임을 밝힌 줄은 남긴다. 2026-11-19 기준 A 번호가 있는 파일은 53개였고, #835에서 `sllm-server.json`을 지워 52개다(이 스크립트와 시험 2개 제외).

| 분류 | 파일 | 수 |
|---|---|---|
| 바꿈: IAM 원문 | `infrastructure/aws/iam/*.json` | 25 |
| 바꿈: IaC | `infrastructure/aws/demo-stack.json`, `infrastructure/eks/cluster.json`, `infrastructure/aws/cloudfront-config.redacted.json` | 3 |
| 바꿈: 배포 값 | `infrastructure/gitops/environments/prod/`의 앱 values 5개(core는 ECR 주소가 `images/`로 옮겨 없음)·`images/` 6개·`redeploy-app.ps1`(#857 뒤. `images/`는 main에서 digest PR(#858)도 바꾸므로 develop과 main 양쪽 값을 맞춘다) | 12 |
| 바꿈: 시험 | `scripts/tests/test_cd_migration_runner.py`(가짜 `sts`가 돌려주는 번호가 `redeploy-app.ps1`과 같아야 함), `scripts/tests/test_cd_digest_pr.py`(#858 fixture의 ECR 주소. 시험 안에서만 쓰여 B 번호로 바꿔도 통과하고, 바꾸면 `check`에 A 번호가 남지 않음) | 2 |
| 바꿈: 절차 문서 | 이 README, `infrastructure/eks/README.md`, `infrastructure/cd/README.md`, prod README, `docs/report/scoring.md`(6.2·6.3 업로드 명령) | 5 |
| 남김: 기록·근거 | `docs/report/**`(scoring.md 빼고: `infra.md` 4절, `evidence/issue493-…json`), `infrastructure/aws/demo-observed.json`, `infrastructure/eks/demo-observed.json` | 4 |
| 남김: A에서 한 번 실행한 SQL | `add-demo-premium-product.sql`, `add-demo-test-subscription.sql`, `mark-confirmed-demo-data.sql`(아래 확인 결과) | 3 |
| 남김: A 부하 시험 | `evaluation/load/llm-stub.k8s.yaml`(이미지가 A ECR에 있음. B에서 부하 시험을 다시 하면 이미지를 B ECR에 올린 뒤 바꾼다) | 1 |

`unknown <파일>`로 멈추면 그 파일을 분류하고 위 표에도 적은 뒤 다시 돌린다. B에서 실행·배포하거나 B 전환 뒤에도 통과해야 하는 값은 `CHANGE`, A에서 관측·실행한 기록은 `RECORD`로 넣는다(11/22 `test_cd_digest_pr.py`가 이렇게 멈췄다).

```powershell
python scripts/aws_account_switch.py plan --to <B 계정>    # 파일별 바꿀 줄·남길 줄 수. 파일은 바꾸지 않음
python scripts/aws_account_switch.py apply --to <B 계정>
python scripts/aws_account_switch.py check                 # 바꿀 파일에 A 번호가 남았으면 실패
git grep -n 347161580747    # A 계정 347161580747이 남은 곳이 위 '남김' 파일과 'A 계정 …' 줄뿐인지 눈으로
python -m unittest discover -s scripts/tests
```

`sllm-server.json`은 infra 9.13.9 정리안대로 #835에서 지웠다. 버킷 이름(`sagomungchi-demo-<계정>-{web,missions,reports,models}`)은 계정 번호가 들어 있어 같이 바뀐다. prod `report-worker.json`의 그림책 그림 허용 출처 `MEMORY_BOOK_ASSET_ORIGINS`(`https://sagomungchi-demo-<계정>-missions.s3.ap-northeast-2.amazonaws.com`, #974)도 missions 버킷 이름이라 이 스크립트가 같이 바꾼다. learning `ASSET_S3_BUCKET`과 어긋나면 그림책 PDF에서 그림이 모두 빠지므로 `python -m unittest scripts.tests.test_runtime_config`로 둘이 맞는지 확인한다.

#### B 자원을 만든 뒤 바꿀 값

계정 번호가 아니라 자원이 생겨야 정해지는 값이다. 4·5·6단계 뒤 한 PR(6a)로 바꾼다. 리전이 바뀌면 `ap-northeast-2`·AZ·prefix list도 여기에 더한다.

| 값 | A 값으로 찾기 | 파일 |
|---|---|---|
| RDS endpoint | `git grep -n czcw0ywu2euo` | prod `core-service.json`(2곳)·`learning-service.json`(2곳, migration `FLYWAY_URL` 포함, #857)·`external-secret-resources.json`(2곳), `infrastructure/aws/demo-db-oneoff.k8s.yaml` |
| VPC ID | `git grep -n vpc-0f4d9134097830b4b -- infrastructure/gitops` | prod `aws-load-balancer-controller.json` |
| 서브넷·클러스터 SG | `karpenter-nodepool.json`의 `subnet-…`·`sg-…` | prod `karpenter-nodepool.json`(EC2NodeClass. SG는 eksctl이 만든 클러스터 SG) |
| CloudFront 도메인 | 저장소 값 없음(앱·스크립트는 `https://www.sagomungchi.co.kr`을 씀) | 바꾸지 않는다. 가비아 `www` CNAME 대상만 B CloudFront 기본 주소로 바꾼다(위 "확인 필요" 도메인 행). 이 README 위쪽 `d3jf0rnm6vhd9v`는 A 관측 기록 |

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
