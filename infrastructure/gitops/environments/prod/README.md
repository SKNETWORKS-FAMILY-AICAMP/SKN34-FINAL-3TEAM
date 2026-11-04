# AWS 데모 환경 설정 (#185)

2026-11-03의 `sagomungchi-demo-eks`에서 읽은 **사용자 지정 Helm values**다. JSON은 Helm이 지원하는 values 형식이다. `prod`는 목표 디렉토리 이름이며, 이 파일이 고가용성 운영 구성을 뜻하지 않는다. 현재는 데모 계정만 사용하는 단일 replica 환경이다.

## 파일과 적용 대상

후속 최소 관측 배포는 `observability.json` → namespace/release `observability`, chart `../../charts/observability`를 사용한다. RabbitMQ 수집 허용은 `observability-platform-network.json`이며 platform에 적용한다. 기존 앱 values는 변경하지 않는다. Secret 입력·PVC 보존·한계는 [관측 chart](../../charts/observability/README.md)를 따른다.

| 파일 | namespace / release | chart |
|---|---|---|
| `core-service.json`, `learning-service.json`, `ai-service.json`, `scoring-service.json`, `report-api.json`, `report-worker.json` | app / 파일명 | `../../charts/app-service` |
| `platform-data.json` | platform / platform-data | `../../charts/platform-data` |
| `external-secrets.json` | external-secrets / external-secrets | external-secrets/external-secrets 2.14.0 |
| `aws-load-balancer-controller.json` | kube-system / aws-load-balancer-controller | eks/aws-load-balancer-controller 1.14.1 |
| `external-secret-resources.json` | app·platform | SecretStore 2개, ExternalSecret 12개. 비밀 값 없이 원격 이름·키만 보존 |
| `platform-network.json` | platform | 기본 ingress 거부, RabbitMQ·Redis 클라이언트 허용 |
| `core-alb-network.json` | app | ALB public subnet에서 core:8080 허용 |

이 values는 현재 라이브 리소스에서 수집했다. Helm chart 기본값 전체를 복사한 파일은 아니다. 배포된 앱 chart의 기반은 `b67d8a462b6b3dc239ecfc14b2aa185766c0c293`이며, 저장소 chart 변경 시 렌더링 차이를 먼저 검토한다. 앱 이미지는 각 파일의 digest로 고정한다. core digest에는 아직 커밋되지 않은 이용권 수정이 들어 있으므로 기반 SHA만으로 같은 이미지를 재빌드할 수 있다고 주장하지 않는다. scoring은 PR #288 병합 SHA `f6250bdd131c4875feba99212212bfdb580c353e`를 사용한다.

## 선행 조건

1. [EKS 관측 구성](../../../eks/README.md)의 클러스터·add-on·Pod Identity·IAM 역할을 준비한다. 이 디렉토리는 IAM 권한을 생성하지 않는다. 생성은 [AWS IaC](../../../aws/README.md#iac-eksctl--aws-cli-스크립트-185)가 담당한다.
2. `app`, `platform`, `external-secrets` namespace, gp3 StorageClass 및 기존 Secrets Manager 비밀을 준비한다. 기존 DB·RabbitMQ 비밀번호를 임의로 새로 만들지 않는다.
3. ESO chart를 설치한 뒤 SecretStore·ExternalSecret을 적용한다. `SecretSynced` / `Ready=True`를 확인한 뒤 앱을 배포한다. CRD 버전은 `external-secrets.io/v1`이다.
4. `app/rds-ca` ConfigMap에 AWS RDS 공개 CA bundle을 `global-bundle.pem` 키로 준비한다. DB URL은 `sslmode=verify-full`과 이 파일을 참조한다. CA 출처: https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem
5. RDS 서비스별 DB·app/migrate 계정·권한과 migration을 먼저 준비한다. 이 values 적용은 DB 초기화·관리자 등록·동의 문서·FREE 상품·모델 활성화를 재현하지 않는다. DB 데이터 준비는 별도 작업이다. 계정·권한은 `demo_stack.py rds-bootstrap`, migration은 아래 3절을 따른다.
6. [AWS 진입 구성](../../../aws/README.md)의 ALB와 CloudFront를 준비한다. Google OAuth 클라이언트에는 해당 CloudFront origin과 callback/reauth callback을 등록한다.

## 렌더링과 기존 클러스터 적용

`redeploy-app.ps1`은 기존 앱 release 한 개의 재배포 진입점이다. AWS 계정·실제 EKS endpoint·고정 digest·기존 release 상태를 확인하고 기본 실행은 server dry-run만 수행한다. `-Apply`를 지정할 때만 ESO Ready 확인 후 배포한다. 새 클러스터·DB 초기화·Secret 생성·웹 빌드·Ingress 생성은 수행하지 않는다. 현재 노드의 Pod 슬롯과 메모리 여유가 작으므로 preview 성공을 실제 rollout 성공으로 해석하지 않는다. 적용 전에 기존 Pod와 비교할 계획을 검토한다.

승인 절차를 거친 배포·롤백은 [#186 운영 배포](../../../cd/README.md)의 `cd-release` workflow가 이 스크립트를 `-ImageDigest`(저장소 values는 그대로 두고 digest만 바꾼 임시 사본)로 호출한다.

```powershell
pwsh -File infrastructure/gitops/environments/prod/redeploy-app.ps1 -Service core-service -Kubeconfig '<AWS kubeconfig 절대 경로>' -Helm '<helm 실행 파일>'
# 검토 후 같은 명령에 -Apply를 추가하면 해당 앱만 실제 재배포한다.
```

저장소 루트에서 실행한다. 아래 명령의 kubeconfig는 작업자가 지정한다. 기본 kind context를 변경하지 않는다.

```powershell
$kubeconfig = '<AWS kubeconfig 절대 경로>'
$envDir = 'infrastructure/gitops/environments/prod'
helm lint infrastructure/gitops/charts/app-service -f "$envDir/core-service.json"
helm template core-service infrastructure/gitops/charts/app-service -n app -f "$envDir/core-service.json"
# 렌더링 결과·이미지·환경 참조를 검토한 뒤 필요한 release만 적용한다.
helm upgrade --install core-service infrastructure/gitops/charts/app-service -n app --kubeconfig $kubeconfig -f "$envDir/core-service.json" --wait --timeout 10m
```

다른 앱도 같은 방식으로 release와 파일명을 일치시킨다. platform은 `platform-data` chart와 namespace `platform`을 사용한다. 무조건 전체 재배포하지 않는다. Helm 밖에서 생성한 ServiceAccount가 있으면 소유권을 먼저 확인하고, 기존 객체를 삭제하거나 강제로 소유권을 이전하지 않는다.

```powershell
kubectl --kubeconfig $kubeconfig apply -f "$envDir/external-secret-resources.json"
kubectl --kubeconfig $kubeconfig get externalsecret -A
kubectl --kubeconfig $kubeconfig get deployments -n app
kubectl --kubeconfig $kubeconfig get pods,pvc -n platform
```

NetworkPolicy는 기존 chart 정책과 **합집합**으로 동작한다. 정책 변경은 별도 검토 후 `platform-network.json`, `core-alb-network.json`을 적용한다. 현재 app namespace 전체 default-deny 여부와 서비스별 egress 허용 범위는 [누락 점검](../../../../docs/report/issue-185-aws.md)을 따른다.

## main 기준 core·웹 재배포 (2026-11-04, #185)

배포 기준은 **main**이다. 기능 PR은 develop에 병합하고, 배포할 때 develop → main 릴리스 PR을 병합한 뒤 그 main SHA로 빌드한 이미지만 배포한다.

| 항목 | 값 |
|---|---|
| 소스 | main `cc860eb2ee851e2998d25f38cfabd8926a1fb685` (develop bddccca와 동일 트리, CI 10개 통과) |
| core 이미지 | ECR `sagomungchi/core-service:main-cc860eb2ee85` = `sha256:1e8e1d4b…a9997` |
| core migration | ECR `sagomungchi/core-migrate:main-cc860eb2ee85` = `sha256:8fc89e6a…58439`, Job `core-service-migrate-main-cc860eb2ee85` |
| 웹 | 같은 SHA, 공개 `TOSSPAYMENTS_CLIENT_KEY`(`test_gck_docs_`)만 주입. 이전 `index.html` 버전 `dOBiv3R_dos14ACh8LzsWN.YkAuY.Ok7` |

적용 순서와 결과:

1. 결제 Secret: Secrets Manager `sagomungchi/demo/app/payment`(공용 문서 테스트 키 `TOSS_TEST_SECRET_KEY`·`TOSS_TEST_MID`와 `PAYMENT_BILLING_ENCRYPTION_KEY`) → ESO 역할 inline 정책 `sagomungchi-demo-external-secrets-payment-read`(작업자 실행) → `external-secret-resources.json`의 `payment-credentials` Ready, 키 3개 동기화.
2. [V26 사전 점검](../../../aws/check-v26-preconditions.sql): core_app 읽기 전용 Job으로 위반 0건, flyway 25 확인 후 Job 삭제.
3. migration: `helm template … -f core-service.json -f migrations/core-service.json --show-only templates/migration-job.yaml`을 **`-n app`으로** 적용한다(렌더링 결과에 namespace가 없어 생략하면 kubeconfig 기본 namespace에 생성된다). V25 → V26 성공.
4. core: `core-service.json` digest 교체와 결제 키 8개(`payment-credentials`, `optional: true`)·`AUTH_NEW_ACCOUNT_DEMO=true` 추가 → `redeploy-app.ps1` dry-run → `-Apply`. release revision 5, 재시작 0. 보호자 이관(`APP_GUARDIAN_TRANSFER_ENABLED`)은 설정하지 않아 꺼져 있다.
5. 웹: `npm ci && npm run build` → S3 web 버킷에 assets·정적 파일 먼저, `index.html` 마지막(`no-cache`). 이전 assets는 지우지 않았다.

되돌리기: core는 `helm rollback core-service 4 -n app`, 웹은 S3 `index.html` 이전 버전 복원. V26은 되돌리는 migration이 없다. V26은 컬럼·테이블·제약 추가뿐이라 이전 core로 rollback해도 동작할 것으로 보이나 검증하지 않았다.

core 외 learning·ai·scoring·report는 b67d8a 이미지로 남아 있다.

2026-11-04 #186 배포 준비: main `a47a596`의 learning V9(`rubric_version` nullable 컬럼 2개·CHECK 제약)를 `learning-migrate:main-a47a596247ad`(`sha256:80254f13…d7bba`) Job `learning-service-migrate-main-a47a596247ad`로 적용했다. V8 → V9 성공, 앱 재시작 0. 기존 learning 이미지는 새 컬럼을 읽지 않아 호환된다. 앱은 `cd-release`로 같은 main SHA에 맞춘다. 2026-11-04 `cd-release` run 41796499774로 6개 release를 `main-a47a596247ad`로 배포했고 이 디렉토리의 앱 digest를 실제값으로 맞췄다. 롤백 리허설(run 41800966528·41802823411) 후 scoring도 같은 버전이다. 서비스 간 호출 계약은 이번 core 변경과 호환됨을 확인했으며, 같은 main 기준으로 맞추는 일은 후속이다.

## 보존과 환경 경계

- Secret 실제 값, Google/LLM 키, DB 비밀번호, JWT·내부 토큰은 Git에 넣지 않는다. ESO가 Secrets Manager에서 읽는다.
- 공개가 아닌 origin 검증 헤더는 [별도 redacted 파일](../../../aws/README.md)에 표시만 하고 값은 보존하지 않는다.
- 이 설정은 계정 `347161580747`, 서울 리전 및 현재 데모 DB/S3를 가리킨다. 다른 환경에 그대로 적용하지 않는다.
- PVC 삭제·Helm uninstall·RDS 삭제·노드 축소는 이 정리 작업에서 실행하지 않았다. 현재 RabbitMQ/Redis 단일 replica는 노드 축소 시 서비스 중단 가능성이 있다.
- Argo CD prod, Autoscaler, HPA/KEDA, 앱 PDB는 미구성이다. 최소 관측 스택은 수동 Helm으로 배포했으며 Discord 경보는 전용 Secret 연결 후 활성화했다. 실제 검증 범위는 #185 보고서를 따른다. 전체 운영 관측 완료를 뜻하지 않는다.

## 초기 배포 재현 절차 (#185)

2026-11-03 기준 실행 순서다. **절차 작성과 새 환경 재현 성공은 구분한다.** 현재 노드그룹·권한 방식은 유지하며 해당 설계 결정과 #186 자동 배포는 이 절에서 변경하지 않는다. `redeploy-app.ps1`은 기존 release 전용이므로 빈 클러스터 초기 설치 도구로 사용하지 않는다.

### 1. 실행 대상과 입력 확정

| 입력 | 현재 환경 | 재현 전 확인 |
|---|---|---|
| 계정·리전·클러스터 | 347161580747 / ap-northeast-2 / sagomungchi-demo-eks | STS 계정, 전용 kubeconfig endpoint, 작업자 EKS 접근 권한 |
| VPC·RDS·S3 | [AWS 인벤토리](../../../aws/README.md) | 기존 자원 재사용인지 별도 환경인지 먼저 구분. 이름·주소를 복사해 운영 데이터에 연결하지 않음 |
| 소스·이미지 | 앱 JSON의 ECR digest | 각 digest의 존재와 소스 SHA·빌드 입력 연결. core·웹 미커밋 수정 때문에 현재 소스 재빌드 동일성은 미확보 |
| 데이터 | 기존 RDS/PVC/S3 또는 검증된 복원본 | 기존 데이터 재사용 시 초기화·seed를 다시 실행하지 않음. 빈 DB에는 migration과 초기 운영 데이터 준비 필요 |
| 외부 입력 | Google OAuth·LLM·JWT·내부 토큰·DB·RabbitMQ | Secrets Manager의 원격 이름·JSON property는 external-secret-resources.json 기준. 실제 값은 Git·터미널 출력에 남기지 않음 |
| 웹·origin | CloudFront URL·OAC·ALB origin 검증 헤더 | OAuth callback과 AUTH_WEB_ORIGIN 일치, origin 헤더는 양쪽에 동일한 실제 값 주입 |
| 관측 | Grafana admin·Discord webhook | ESO 12개와 별개인 observability Secret 2개를 안전하게 복구해야 함 |

저장소 루트, PowerShell 7에서 작업하며 모든 kubectl/helm 명령에 전용 kubeconfig를 명시한다.

```powershell
$profile = 'sagomungchi-provided'
$region = 'ap-northeast-2'
$kubeconfig = '<전용 kubeconfig 절대 경로>'
$envDir = 'infrastructure/gitops/environments/prod'
aws sts get-caller-identity --profile $profile
aws eks describe-cluster --name sagomungchi-demo-eks --region $region --profile $profile --query 'cluster.{status:status,endpoint:endpoint}'
kubectl --kubeconfig $kubeconfig config view --minify
```

계정·endpoint가 다르거나 자원 소유자가 불명확하면 적용을 중단한다. `demo-observed.json`은 생성 입력이 아니다. 새 VPC/EKS/IAM/RDS/S3 생성은 현재 완성된 IaC가 없어 이 절만으로 실행할 수 없다.

### 2. 기반 자원 → Secret → 저장소

1. 기존 클러스터의 VPC CNI·CoreDNS·kube-proxy·EBS CSI·Pod Identity Agent 상태와 namespace, gp3 StorageClass를 확인한다. gp3 정의는 [gp3.json](../../../eks/gp3.json)이다. namespace는 app/platform/external-secrets/observability를 준비한다. 기존 객체에는 소유권 강제 이전·삭제를 하지 않는다.
2. 현재 역할·ServiceAccount·Pod Identity 연결을 [EKS 인벤토리](../../../eks/demo-observed.json)와 대조한다. ESO 자체의 AWS 권한이 먼저 준비돼야 다른 Secret을 동기화할 수 있다.
3. 공식 chart 저장소에서 ESO 2.14.0을 external-secrets namespace에, LB Controller 1.14.1을 kube-system에 각 JSON values로 설치한다. 버전이 없어지거나 CRD 호환성이 다르면 임의 최신 버전으로 바꾸지 않는다. 이미 설치됐으면 새 설치 대신 버전·values 차이를 검토한다.
4. Secrets Manager에 필요한 값과 JSON property가 준비된 뒤 external-secret-resources.json을 적용한다. 원격 비밀을 먼저 생성하지 않고 ESO 오류를 임시 값으로 우회하지 않는다.
5. RDS 공개 CA를 공식 URL에서 받아 app/rds-ca ConfigMap의 global-bundle.pem 키로 준비한다. 앱 values는 해당 파일을 sslmode=verify-full로 참조한다.
6. platform-network.json을 적용하고 platform-data를 설치한다. PostgreSQL·MinIO는 비활성, RabbitMQ·Redis만 배포한다. platform-data-credentials 동기화와 PVC Bound, RabbitMQ 초기화 Job Complete를 확인한다. 기존 PVC가 있다면 새 비밀번호로 덮어쓰지 않는다.

```powershell
kubectl --kubeconfig $kubeconfig apply -f "$envDir/external-secret-resources.json"
kubectl --kubeconfig $kubeconfig -n app wait --for=condition=Ready externalsecret --all --timeout=120s
kubectl --kubeconfig $kubeconfig -n platform wait --for=condition=Ready externalsecret --all --timeout=120s
kubectl --kubeconfig $kubeconfig apply -f "$envDir/platform-network.json"
helm upgrade --install platform-data infrastructure/gitops/charts/platform-data -n platform --kubeconfig $kubeconfig -f "$envDir/platform-data.json" --wait --wait-for-jobs --timeout 10m
```

위 명령은 선행 조건 확인 후 실행하는 절차이며 이번 문서 작업에서 실행하지 않았다.

### 3. RDS 초기화와 migration

빈 RDS에는 core_db·learning_db·report_db를 만들고 서비스별 migration(DDL)·app(DML) 계정을 준비한다. DB별 PUBLIC CONNECT를 회수하고 해당 두 계정만 접속시키며, schema 사용 권한과 앱의 테이블·sequence 권한을 부여한다. 앞으로 migration 계정이 만드는 객체에도 앱 권한이 적용되도록 해당 객체 생성자 기준 default privileges를 설정한다. RDS 관리자는 초기 설정에만 사용하며 앱 Secret에 넣지 않는다. 비밀번호는 승인된 비밀 입력 경로로 전달한다.

`charts/platform-data/files/postgres/init.sql`은 로컬 DB 3개 생성만 담당하므로 운영 권한 초기화 스크립트로 사용하지 않는다. RDS 초기화는 [`demo_stack.py rds-bootstrap`](../../../aws/README.md#iac-eksctl--aws-cli-스크립트-185)과 `rds-bootstrap*.sql`이 담당한다. ESO Secret 6개와 `app/rds-ca`가 준비된 뒤 실행하고, migration 성공 후 한 번 더 실행해 기존 테이블 권한을 맞춘다. SQL은 이미 있는 계정의 비밀번호를 바꾸지 않으므로 기존 RDS에도 안전하게 재실행되도록 작성했지만, 현재 RDS에서는 아직 실행하지 않았다. 로컬 PostgreSQL 17.11의 비-superuser(CREATEROLE·CREATEDB) 관리자로 두 번 실행해 멱등성, app 계정의 DML 허용·DDL 거부·다른 DB 접속 거부, 이력 테이블 권한 회수를 확인했다.

2026-11-03 읽기 전용 조회에서 다음 Job은 succeeded=1이었다. 이는 과거 실행 이력이며 새 DB에서 재실행한 결과는 아니다.

| 대상 | 기존 Job | migration 이미지 digest (ECR repository 접두사 생략) |
|---|---|---|
| core | core-migrate-b67d8a462b6b, core-migrate-v25-93581368 | core-migrate@sha256:fc93bb566fb5f958da595df509f20c6ef7bda8c12194555d16776ede6a4381e6 |
| learning | learning-migrate-b67d8a462b6b | learning-migrate@sha256:5af016a5b9d07a4d2ef12d54017e29d0466e38312ca7a283edd865404ef4f8a6 |
| report | report-migrate-b67d8a462b6b | report-service@sha256:87cb1d57edb3acd8b70dcdb17b1d2d587b1a92fd2040070a1178a61c6eb33eee |

core/learning migration 이미지는 [core.Dockerfile](../../migrations/core.Dockerfile)·[learning.Dockerfile](../../migrations/learning.Dockerfile)로 같은 소스 revision에서 빌드한다. 현재 develop의 migration을 과거 배포 digest와 임의 조합하지 않는다. Flyway validate/migrate와 report Alembic upgrade head는 각 DB migration 계정·TLS로 별도 Job에서 실행하고 성공 이력을 확인한 후 앱을 올린다.

prod 앱 values는 `migration.enabled=false`를 유지한다(실제 release와 일치). migration 입력은 [`migrations/`](migrations/)의 덮어쓰기 values이며, 공통 chart의 `migration.extraVolumes`·`extraVolumeMounts`로 `rds-ca`를 마운트하고 migrate Secret·고정 digest를 사용한다. Argo PreSync는 수동 Helm에서 선행을 보장하지 않으므로 Job만 렌더링해 먼저 적용한다.

```powershell
helm template core-service infrastructure/gitops/charts/app-service -n app -f "$envDir/core-service.json" -f "$envDir/migrations/core-service.json" --show-only templates/migration-job.yaml | kubectl --kubeconfig $kubeconfig apply -f -
kubectl --kubeconfig $kubeconfig -n app wait --for=condition=complete job/core-service-migrate-b67d8a462b6b --timeout=600s
```

learning-service·report-api도 같은 방식이다. **core-migrate 고정 digest는 V23까지만 포함한다.** 현재 RDS의 V24·V25는 기존 Job이 별도 ConfigMap SQL로 적용했다. 빈 DB 재현에는 배포할 core 이미지와 같은 소스로 core-migrate를 다시 빌드해 digest와 `revision`을 바꿔야 한다(core 이미지의 미커밋 이용권 수정과 같은 소스 재현성 문제). 빈 DB에 앱부터 설치하지 않는다.

### 4. 앱 → 초기 운영 데이터 → 외부 진입

1. DB migration 성공 후 core, learning, report-api, scoring, ai, report-worker 순으로 설치 입력을 준비한다. core/learning/report-api를 먼저 기동하고, scoring/ai의 활성 설정 조회를 위한 core 운영 데이터를 준비한다. 서로 의존하는 서비스는 모두 배포한 뒤 readiness를 확인하며 초기 NotReady를 임의 성공 처리하지 않는다. prod JSON의 digest·Secret·CA·자원·NetworkPolicy를 사용한다.
2. 운영 데이터는 별도 승인된 절차로 준비한다: 관리자와 필요한 permission, 현행 동의 문서, 무료 상품과 PAYMENT_FREE_PRODUCT_ID, 시연 미션, 프롬프트·모델 버전 및 승인·활성화 상태. S3 모델 파일 존재·무결성과 활성 버전의 연결을 확인한다. 로컬/E2E seed 전체를 운영에 복사하지 않는다. 등록 성공과 사람의 승인·실제 모델 로딩 성공을 구분한다.
3. 현재 Google 신규 가입은 is_demo=false를 저장한다. 데모 전용 환경의 새 시연 학부모·학생은 대상 확인 후 별도 보정하고 실사용 데이터를 섞지 않는다. mark-confirmed-demo-data.sql은 2026-11-03 특정 건수용이므로 일반 seed로 사용하지 않는다. 토스 키가 없으면 테스트 결제 완료로 표시하지 않는다.
4. core-alb-network.json과 검토한 ALB Ingress를 적용한다. core-service.json의 ingress.enabled=false이므로 앱 설치만으로 ALB가 만들어지지 않는다. core-ingress.redacted.json의 치환 문자열은 절대 그대로 적용하지 않는다. origin 검증 헤더는 Git 밖에서 안전하게 주입하고 CloudFront와 일치시킨다.
5. CloudFront의 S3 OAC·웹/API 분기·API 캐시/압축 off·전달 정책·origin 60초, ALB 120초·XFF preserve·CloudFront prefix list 제한을 확인한다. 웹 빌드는 확정 소스·lockfile·공개 환경값만 사용한다. assets 먼저, index.html 마지막으로 업로드하고 이전 assets를 바로 지우지 않는다. AWS/Google/LLM 비밀을 VITE 변수에 넣지 않는다.
6. Google OAuth에는 실제 HTTPS origin과 /api/v1/auth/google/callback, /api/v1/auth/google/reauth/callback을 등록한다. CloudFront 주소가 바뀌면 OAuth와 AUTH_WEB_ORIGIN도 함께 변경해야 한다.
7. 관측은 기존 chart README대로 admin·Discord Secret 준비 → network policy → observability values 배포 순으로 수행한다. Secret 원문은 Helm values·출력에 포함하지 않는다.

### 5. 완료 판정과 실패 처리

구현·설정 준비를 끝낸 후 한 단계에서 Helm 렌더링/server dry-run, ESO Ready, migration 성공, 앱 readiness, PVC, DB 계정 격리, 큐·Redis, 모델 파일 접근, CloudFront 로그인→학습 제출→리포트 조회와 비밀 스캔을 확인한다. 부모 다운로드는 공유 권한을 임의 변경하지 않고 별도 확인한다. 실제 실행하지 않은 항목은 미검증으로 남긴다.

실패 시 실패 단계 이후 진행을 멈추고 그 단계의 원인을 수정한다. migration 실패를 앱 재시작으로 숨기지 않고 DB restore나 down migration을 자동 수행하지 않는다. 기존 데이터가 있는 환경의 재배포는 앱 하나씩 preview/적용하며, 초기 설치와 혼동하지 않는다.

현재 완료된 것은 **절차 정리, 기존 앱 6개 server dry-run, AWS 자원·EKS 생성 정의(`demo_stack.py`·`cluster.json`), RDS bootstrap SQL·Job, migration Job 입력**이다. 초기 운영 데이터 seed, core·웹 소스 재빌드 동일성(core-migrate V24·V25 포함), 신규 환경 전체 재현 실행은 미완료다.
