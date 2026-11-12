# 인프라·배포·운영

로컬 kind 플랫폼, AWS 데모 배포, CD, 운영 경보·trace, 부하 시험의 결정과 근거. 실행 절차는 각 디렉터리 문서가 소유한다: [kind](../../infrastructure/kind/README.md), [platform-data](../../infrastructure/gitops/charts/platform-data/README.md), [prod 환경](../../infrastructure/gitops/environments/prod/README.md), [EKS](../../infrastructure/eks/README.md), [AWS](../../infrastructure/aws/README.md), [CD](../../infrastructure/cd/README.md), [부하 시험](../../evaluation/load/README.md). 경보 규칙·경계는 [아키텍처 4.7](../design/architecture.md#47-운영-경보-구성-경계-187).

## 1. 로컬 플랫폼 (#17)

[아키텍처 4.1](../design/architecture.md#41-환경-구분)의 로컬 Kubernetes 환경. 설정값은 [local values](../../infrastructure/gitops/environments/local/platform-data.yaml).

### 1.1 환경 경계

- 로컬은 kind 단일 노드에 PostgreSQL·RabbitMQ·Redis·MinIO, 운영은 RDS·S3와 RabbitMQ·Redis StatefulSet
- 저장소 구성은 `platform-data` chart 하나. PostgreSQL·MinIO는 로컬 values에서만 활성화
- 로컬 API·HTTP·HTTPS는 loopback에만 노출
- 기준 PC: Windows 11, i5-1135G7 4코어·8스레드, 16GB, Docker Desktop WSL 2

### 1.2 Kubernetes·CNI·Ingress 조합

| 설정 | 근거 |
|---|---|
| kind v0.33.0 / Kubernetes v1.35.8 | ingress-nginx v1.15.1의 E2E 범위가 1.35까지. 공식 노드 이미지 digest 고정 |
| Calico v3.33.0 / IPv4·iptables | Calico의 1.35 테스트 범위. 기본 CNI 비활성 |
| `MutatingAdmissionPolicy` feature gate·beta API | Calico native v3 CRD 기본값 처리에 필요, 1.35에서 기본 비활성 |
| Pod `10.244.0.0/16`, Service `10.96.0.0/12` | 기준 PC의 Wi-Fi·WSL·Docker 대역과 비중복. 다른 네트워크에서는 재확인 |
| ingress-nginx controller v1.15.1 / chart 4.15.1 | 이슈 지정 유지(사용자 결정). 유지보수 종료 프로젝트라 버전 고정이 보안 패치를 뜻하지 않음. 운영 ALB 설계는 불변 |

### 1.3 MinIO

- 커뮤니티판의 소스 전용 배포 전환으로 Chainguard 공개 이미지 사용. linux/amd64 digest를 [공통 values](../../infrastructure/gitops/charts/platform-data/values.yaml) `minio.image`에 고정
- 서버 이미지에 shell·curl이 있다고 가정하지 않음. 버킷 초기화는 `curlimages/curl:8.17.0`의 S3 SigV4 요청, 인증은 curl 설정 stdin
- 버킷 3개(`sagomungchi-local-missions`·`-reports`·`-models`)가 단일 Pod·2Gi PVC 공유. 버킷 분리가 앱의 사용자별 권한 검사를 대체하지 않음

### 1.4 초기화와 자격 증명

- Compose MinIO는 [compose.minio.yaml](../../compose.minio.yaml)로 분리. Compose는 병합 전에 각 파일의 변수를 해석해 profile만으로 `${VAR:?}` 검사를 피할 수 없기 때문
- Secret 준비 스크립트는 PowerShell 7 이상. MinIO 사용자명 3자·비밀번호 8자 이상
- RabbitMQ는 계정 기동 후 Job이 관리 API로 `definitions.json` 반영(계정을 JSON에 넣지 않으려고 순서 분리). `default_queue_type`을 전역 quorum으로 강제하지 않음(Pod별 exclusive 큐와 충돌)
- `init.sql`·`definitions.json`은 원래 위치에 두고 Helm `.Files`와 Compose 마운트가 같은 파일을 읽음
- `.env`의 계정 6개만 `platform/platform-data-credentials` Secret으로 준비. 기존 Secret과 값이 다르면 덮어쓰지 않음(환경 변수 변경만으로 계정이 회전되지 않음)
- 활성 저장소의 requests·limits·필수 설정이 없으면 렌더링 중단

### 1.5 자원 예산

requests는 스케줄링 기준, limits는 상한이며 실측값이 아님.

| 대상 | CPU request / limit | 메모리 request / limit | PVC |
|---|---|---|---|
| PostgreSQL | 100m / 500m | 256Mi / 512Mi | 2Gi |
| RabbitMQ | 250m / 1000m | 512Mi / 2Gi | 2Gi |
| Redis | 50m / 250m | 64Mi / 256Mi | 512Mi |
| MinIO | 100m / 500m | 256Mi / 1Gi | 2Gi |
| ingress-nginx controller | 100m / 500m | 128Mi / 512Mi | - |
| **상시 합계** | **600m / 2750m** | **1216Mi / 4.25Gi** | **6.5Gi** |

- 초기화 Job(RabbitMQ·MinIO)은 각 50m/250m, 64Mi/128Mi
- 플랫폼 전체 약 6GiB 예산(control plane 등 1.5GiB 포함). 앱·모델 추론·관측·이미지 빌드는 제외. Docker 상한 약 7.62GiB라 Compose 전체와 kind는 동시에 실행하지 않음
- 시작값: PostgreSQL `shared_buffers=64MB`·`max_connections=40`·`work_mem=2MB`, RabbitMQ `vm_memory_high_watermark.absolute=1GiB`(quorum WAL 512MiB의 3배 고려해 limit 2Gi), Redis `maxmemory=128mb`·`noeviction`. 운영 튜닝 값 아님
- StatefulSet 삭제·축소 시 PVC 보존(kind 노드 삭제로부터는 보호하지 않음). 로컬 provisioner는 PVC 요청을 quota로 강제하지 않을 수 있어 호스트 여유 30GiB 이상 권장

## 2. 로컬 앱 배포·네트워크·관측 (#171)

EKS 사용 확정(#171 PM 결정).

| 릴리스 | Service / readiness | migration |
|---|---|---|
| core-service | 8080 / `/actuator/health/readiness` | 전용 Flyway 이미지 `migrate` |
| learning-service | 8081 / `/actuator/health/readiness` | 전용 Flyway 이미지 `migrate` |
| ai-service | 8000 / `/health/ready` | 없음 |
| scoring-service | 8001 / `/health/ready` | 없음 |
| report-api | 8002 / `/health/ready` | report 이미지의 `alembic upgrade head` |
| report-worker | HTTP Service 없음 (`python -m app.worker`) | report-api의 migration 선행 |

### 2.1 배포

- core·learning Flyway는 앱 기동에서 비활성. 기존 SQL을 전용 이미지에 복사해 `FLYWAY_*`만 주입. migration 허용 NetworkPolicy는 PreSync wave -2, Job은 wave -1. `migration.revision`은 SQL/Alembic 변경 시 명시적으로 갱신. 실패 시 앱 sync 중단
- local values의 `:local` 태그는 kind에 직접 로드할 빌드 입력
- Secret: `app/app-service-credentials`, `observability/observability-credentials`. chart는 이름·키만 참조. URL 비밀번호는 URL 인코딩
- **report Alembic URL**: `migrations/env.py`가 URL을 `ConfigParser`에 넘겨 `%`가 보간 오류를 일으킴. Alembic Job에만 `%`→`%%` 이스케이프한 `REPORT_ALEMBIC_DATABASE_URL`을 별도 키로 제공
- core·learning Java agent는 chart의 선택적 initContainer(OTel Java agent 2.33.1 digest 고정)
- local report presigned URL은 `S3_PUBLIC_ENDPOINT_URL=http://127.0.0.1:19000`. 호스트 다운로드 확인 시 MinIO 9000을 19000으로 port-forward

### 2.2 네트워크·확장

- `app`·`platform`·`observability` 기본 거부 + 필요한 포트만 허용. app ingress는 ingress-nginx → core 8080과 설계 4.3의 내부 호출만. RabbitMQ 관리 15672는 core와 초기화 Job, metrics 15692는 Prometheus만
- startup·liveness는 `/health/live`·`/actuator/health/liveness`, readiness만 ready 경로. core snapshot·scoring 모델 준비가 오래 실패해도 startup probe가 백그라운드 재시도를 끊지 않도록 분리
- local 단일 레플리카에서는 HPA/PDB 비활성. report-worker는 두 큐 기준 KEDA 0–1, `CONSUMER_PREFETCH=1`
- core 15초 preStop·180초 grace·Spring graceful 30초는 SSE executor 85초·timer 5초를 고려한 시작값(롤링 종료 실측 전)
- NetworkPolicy 렌더만으로 Calico/VPC CNI 동작이 증명되지 않음

### 2.3 관측

- local `observability` chart: OTel Collector v0.164.0, Prometheus v3.15.1, Grafana v13.3.0, KEDA 2.21.0. 외부 Ingress 없음, 저장은 `emptyDir`
- Grafana: 저메모리 첫 기동이 60초를 넘어 startup probe 300초, Pod 두 개가 겹치지 않게 `Recreate`, CPU 한도 250m에서 throttling으로 startup 실패해 요청 100m·한도 1
- AI·scoring·report-api에는 exporter가 없어 core·learning Java agent 지표만 수집
- Langfuse: EKS 자체 호스팅 예정(#379, 미배포). 공식 최소 자원이 로컬 한도 초과. Collector에 EKS용 OTLP traces → Langfuse 전달 설정만 있음(local 비활성)
- AI Langfuse v4 계측: `LANGFUSE_ENABLED` 기본 false. true이면 public/secret key와 Collector endpoint가 모두 필요(빠지면 기동 오류). call type·프롬프트 버전·모델·토큰·오류 코드만 기록, 원문·학생 ID 미전달

### 2.4 검증에서 얻은 교훈

- 다중 플랫폼 캐시 이미지는 `kind load docker-image`에서 digest 누락 오류 → `docker image save --platform linux/amd64` archive로 로드
- kind 노드 `/tmp`는 별도 tmpfs라 archive가 containerd에서 보이지 않음 → 노드 `/root`에 복사
- KEDA `scaledjobs.keda.sh` CRD가 client-side apply annotation 한도(262144 bytes) 초과 → chart `crds.additionalAnnotations`에 `argocd.argoproj.io/sync-options: Replace=true`(local 전용)
- ingress-nginx controller가 0개면 admission webhook 연결 거부로 Helm 설치 실패 → controller 먼저 복구
- Helm으로 직접 설치할 때는 Argo PreSync 훅이 없으므로 core·learning·report-api를 먼저 설치하고 migration Job 완료 후 나머지 설치
- 미검증: 실제 모델 가중치 추론, SSE 진행 중 종료, Langfuse 저장·조회

## 3. kind 통합과 환경값 (#273·#236·#312)

### 3.1 kind 클러스터 통합 (#273)

로컬 kind를 `sagomungchi-local` 하나로 통합(Docker 메모리 약 7.6GiB에서 두 클러스터 동시 운영 곤란).

- 앱 Secret `create-app-secrets.ps1`과 platform Secret `create-platform-secret.ps1`이 같은 루트 `.env`를 읽어 계정 원본 단일화. 대상 context·노드를 고정 검사, 기존 Secret 값과 불일치 시 중단
- 관측 Secret은 `.env`에 `GRAFANA_ADMIN_USER`·`GRAFANA_ADMIN_PASSWORD`가 둘 다 있을 때만 생성
- 옛 `sagomungchi-issue171` 클러스터·`kind-issue171` 네트워크가 남아 있으면 `kind delete cluster --name sagomungchi-issue171`, `docker network rm kind-issue171`

### 3.2 kind 환경값·외부 egress (#236)

kind values가 `compose.yaml`보다 적어 Google 로그인·토스 결제·LLM 판정이 동작하지 않던 문제 보완.

- 외부 키(Google·토스·결제 암호화 키·`ANTHROPIC_API_KEY`)는 루트 `.env`를 원본으로 `create-app-secrets.ps1`이 값이 있을 때만 앱 Secret에 복사. values는 `optional: true` 참조. 토스 `live_` 키 거부
- 인증 TTL·Redis 포트·LLM 공급자·모델 등 비밀이 아닌 값은 values에 compose 기본값
- 추가하지 않은 값: `REDIS_PASSWORD`(양쪽 모두 비밀번호 없음), `OPENAI_BASE_URL`(sLLM 사용 시에만), report-api의 `RABBITMQ_URL`(소비는 worker만)
- egress: core·ai에만 사설·CGNAT·link-local·loopback을 뺀 TCP 443 허용. Calico 오픈소스판에 FQDN 규칙이 없고 공급자 IP 목록은 유지 곤란
- 웹은 호스트 Vite에서 `CORE_PROXY_TARGET`·`CORE_PROXY_HOST`로 `/api`를 kind Ingress(`api.sagomungchi.local`)에 전달
- 토스 웹훅은 외부에서 로컬 kind로 들어올 수 없어 확인 범위 밖
- 토스 결제위젯 키(`test_gck_`·`test_gsk_`)는 전자결제 신청 이후에만 보임. 신청 전에는 문서 테스트 키(`test_gck_docs_`·`test_gsk_docs_`)와 `TOSS_TEST_MID=tgen_docs` 사용(다르면 `PAYMENT_PG_MISMATCH`). 문서 테스트 키는 주문번호 조회가 `NOT_FOUND_MERCHANT`라 상태 재확인·복구·관리자 대조 경로 검증 불가
- 실제 확인(2026-11-03): Ingress `/api` 200·외부 `/internal` 404, core→Google·토스와 ai→OpenAI 허용, learning 외부 443 차단, Google 로그인·LLM 판정·토스 테스트 결제 승인

### 3.3 교차 확인·이관·content_3 설정 전달 (#312)

- [AI 4.3](ai.md#43-판정-모델-교차-확인-69)의 교차 확인 설정 10개(판정 마감·scoring timeout·reserve, M2·M1 플래그와 경계)를 Compose·`.env.example`·GitOps local AI values에 전달. 값과 기본 false는 그대로
- GitOps local core `APP_GUARDIAN_TRANSFER_ENABLED=false`, scoring `M2_CONTENT3_RULE_ENABLED=false` 추가
- transfer-local은 scoring을 함께 실행하고 호스트 포트는 닫음. #305 이후 교차 확인이 꺼져 있으면 scoring을 부르지 않아 AI→scoring `service_healthy` 의존성은 제거(#502)
- 회귀 검사: `scripts/tests/test_runtime_config.py`가 앱 기본값과 예제·values를 대조하고 합성 환경 파일로 Compose 렌더링 확인

## 4. AWS 데모 구성 (#185)

계정 347161580747 / ap-northeast-2. 수집한 values는 배포 상태를 보존한 것이며 새 계정을 처음부터 만드는 완성된 IaC는 아니다. 비밀 값·Secret data·CloudFront origin header 원문은 기록하지 않는다.

| 항목 | 결정 |
|---|---|
| IaC | eksctl(`infrastructure/eks/cluster.json`) + AWS CLI 스크립트(`demo_stack.py` plan·apply·pause·resume). IAM 원문은 `infrastructure/aws/iam/` |
| 진입 | 기본 cloudfront.net 도메인, CloudFront→ALB HTTP(ALB SG는 CloudFront prefix list만 허용, origin 헤더 규칙) |
| 노드그룹 | 모두 On-Demand t3.medium: `application` 2대(최대 3), `platform-observability` 2대(`workload=platform:NoSchedule`). 상태 저장 서비스(replica 1, AZ 고정 EBS)에 Spot이 맞지 않아 설계의 Spot을 변경(PM 승인). scoring 메모리 예약 2Gi → 1Gi |
| Pod 권한 | 설계의 IRSA 대신 EKS Pod Identity |
| RDS | db.t4g.small Single-AZ. 서비스별 계정은 [db-dev-guide 8절](db-dev-guide.md#8-서비스별-db-계정-230) |
| 데모 외 기간 | 노드 0대 + RDS 정지(`demo_stack.py pause`/`resume`, Karpenter 정지 포함). control plane·NAT·저장소 비용은 남음 |
| 배포 기준 | develop → main 릴리스 PR 병합 후 그 SHA만 배포(ECR 태그 `main-<sha>`) |
| 시연 계정 | `AUTH_NEW_ACCOUNT_DEMO=true`로 새 Google 부모를 `is_demo=true` 저장 |
| 결제 | 공용 문서 테스트 키를 `sagomungchi/demo/app/payment` Secret으로 ESO 연결. 일반 결제 승인만 시연 가능 |
| 비밀 스캔 | Gitleaks 8.30.1, 루트 `.gitleaks.toml`. 재실행 도구 `infrastructure/aws/scan-repository-secrets.py` |

### 4.1 설계와 남은 차이

| 항목 | 현재 | 남은 일 |
|---|---|---|
| RDS | 비공개·암호화·자동 백업 7일, Single-AZ, 삭제 보호 off | PITR 실제 복원, RPO 5분·RTO 4시간 미검증 |
| 플랫폼 | RabbitMQ·Redis·관측 단일 replica, AZ 고정 PVC(RabbitMQ·Prometheus·Grafana 2a, Redis 2b) | EBS/PVC 삭제·AZ 장애 복구 미검증 |
| 진입 | CloudFront→ALB HTTP origin | custom domain·ALB TLS 미구성 |
| Secret | ESO·Secrets Manager 원격 key 참조 | 키 회전·장애 복구 미검증 |
| NetworkPolicy | 서비스별 정책 있음, `namespaceDefaultDeny=false`, 일부 외부 연결은 넓은 CIDR | 설계 호출 표 전체·새 Pod 기본 거부 미검증 |
| S3·IAM 재생성 | 인벤토리·정책 원문 보존 | 새 계정 실제 생성 미실행 |
| NAT | 2a 한 곳 | 다중 AZ는 담당자 결정 사항(5절) |

### 4.2 실제 서비스 검증 (11-03~04)

- CloudFront URL에서 학부모 Google 로그인·답변 제출·AI 피드백·돌아보기, 주간 리포트 생성과 PDF·Markdown 다운로드
- 클라이언트 IP 판정([검증 스크립트](../../infrastructure/aws/verify-viewer-ip.ps1)): viewer IP 제한 카운터 증가, 위조 XFF 무시
- 미실행: 신규 Google 가입 실계정, 공용 테스트 키 결제 승인, 새 클러스터 복원

## 5. S3 Gateway 엔드포인트와 NAT 점검 (#212)

10/29 멘토링의 "S3 엔드포인트 연결, core·NAT 구간 병목" 지적을 읽기 전용으로 점검(2026-11-04). AWS 자원 변경 없음.

- S3 Gateway 엔드포인트(`sagomungchi-demo-vpce-s3`)가 이미 있고 private 라우팅 테이블 2개 모두 S3 prefix list → vpce 경로 active
- **엔드포인트 정책은 기본 전체 허용 유지**: 노드의 ECR 이미지 layer도 AWS 소유 S3 버킷을 이 엔드포인트로 받아, 우리 버킷으로 좁히면 이미지 pull이 깨짐. 버킷 접근 제한은 Pod Identity 역할 정책이 맡음
- S3가 NAT를 거치지 않는 근거: scoring Pod가 모델 약 844MiB를 받는 동안 NAT 수신 0.04MiB, Pod 안 DNS 해석 IP가 모두 S3 prefix list 대역
- NAT를 거치는 것은 외부 호출뿐: ai→LLM API, core→토스·Google OAuth, ESO·Pod Identity→Secrets Manager·STS, kubelet→ECR API·공개 레지스트리, Grafana→Discord
- **NAT 병목 없음**: 51시간 지표에서 활성 연결 최대 126(한도 55,000), 포트 할당 오류 0, 처리량 약 4.8GiB
- 남은 위험은 가용성: NAT가 2a 한 곳이라 2a 장애 시 2b Pod도 외부 호출 불가

| 완화안 | 월 추가 비용 | 판단 |
|---|---|---|
| A. 현재 유지(zonal NAT 1개) | $0 | **데모 기간 채택**. 2a 장애 때는 RabbitMQ·관측 EBS도 2a라 서비스가 이미 함께 멈춤 |
| B. AZ별 zonal NAT | 약 +$46.7 | 운영 전환 결정 시 재검토(가장 단순) |
| C. Regional NAT GW | 약 +$43~47 | 기존 NAT 교체, 도구 지원 확인 필요 |
| D. Interface 엔드포인트 4종 | 약 +$76 | LLM·토스·OAuth는 그대로 NAT. 현재 양 대비 비쌈 |

한계: VPC Flow Logs 없음(패킷 단위 경로 기록 없음), 350초 넘는 유휴 연결의 stale 오류는 미확인.

## 6. Karpenter와 앱 HPA (#211·#372)

Karpenter는 트래픽을 보지 않고 Pending Pod가 생길 때만 노드를 추가한다. 흐름은 트래픽 증가 → HPA가 Pod 증가 → 기존 노드 자리 부족 → Pending → Karpenter 노드 추가 → 부하 종료 후 HPA 축소 → 빈 노드 정리.

| 항목 | 결정 | 근거 |
|---|---|---|
| 설치 | Karpenter 1.15.1 Helm(OCI), 수동 Helm. values `environments/prod/karpenter.json` | 1.35는 1.9 이상 지원. prod는 Argo CD 미구성 |
| 노드 | t3.medium·t3.large On-Demand, 2a·2b. Spot·중단 알림 큐 미사용 | 앱이 replica 1·PDB 없음이라 Spot 회수가 곧 중단 |
| 상한 | NodePool `limits` CPU 4·메모리 16Gi(최대 약 2대, 최악 약 $156/월) | 평소 0대 |
| 정리 | `WhenEmptyOrUnderutilized`, `consolidateAfter 5m`, 한 번에 1노드, `expireAfter 720h` | 부하 종료 후 비용이 남지 않게 |
| 기존 노드그룹 | 둘 다 유지. 컨트롤러는 `application` 노드에 replica 1 | 컨트롤러가 자기가 만든 노드에 있으면 안 됨 |
| AZ·EBS | NodePool에 `workload=platform` taint 없음 → 상태 저장 Pod는 Karpenter 노드에 가지 않음 | PV의 AZ 제약 유지 |
| HPA | core·learning·ai, 최소 1·최대 3·CPU 70%. scoring·report-api는 고정 | 평소 비용 불변. scoring은 모델 로딩·메모리 1Gi |
| 축소 끊김 | 최소 1 유지 + `application` 노드그룹 preferred nodeAffinity + ReplicaSet 기본 삭제 순서(최근 Pod부터) | 아래 |

- replica 1에서 노드를 정리하면 eviction이 Pod를 먼저 지워 새 Pod가 Ready가 될 때까지 끊긴다. 기본 Pod를 관리형 노드에 두고 늘어난 Pod만 Karpenter 노드에 올려, 축소 때 최근 Pod부터 지워지게 했다. 부하 중 재배포로 Pod 나이 순서가 바뀌면 한 번 끊길 수 있다. 최소 2 + PDB 안은 상시 노드 1대(약 $38/월)가 뜰 수 있어 보류
- 적용(2026-11-05): metrics-server add-on, IAM 역할·Pod Identity, Karpenter, NodePool `application-burst`, 세 앱 HPA. 이미지 digest는 바꾸지 않음
- t3.medium은 노드당 Pod 17개 제한이라 CPU·메모리보다 Pod 수로 먼저 Pending이 날 수 있음
- 미실측: 부하 시 노드 확장·축소, 삭제 순서, ai의 CPU 기반 확장(2차 부하 시험 #384)
- 후속: scoring HPA, report-worker KEDA, Spot 혼합(replica 2·PDB 이후)

## 7. CD 배포 승인·이력·롤백 (#186)

`cd-release.yml`: main 수동 실행 → GitHub Environment `prod` 승인 → 작업자 PC runner에서 Helm 적용 → 경로 확인 → 이력.

### 7.1 확정 정책 (담당자 답변)

- 이전 승인 앱이 현재 DB 스키마·데이터와 호환될 때만 새 승인을 받아 이미지 버전을 복귀. 비호환·미확인은 모두 복귀 차단. DB 버전 번호만으로 호환성을 판정하지 않음
- API·이벤트 계약, 진행 중 학습·결제 작업 영향과 검증 근거를 함께 기록
- DB 자동 downgrade·백업 자동 복원은 구현하지 않음
- 운영 승인자는 `20220348-kim`·`kty2001` 2명(2026-11-03). 둘 중 한 명의 승인 없이는 실행하지 않음

### 7.2 구현 결정

| 결정 | 내용 | 근거 |
|---|---|---|
| 적용 위치 | 작업자 PC의 self-hosted runner(`cd-prod`) | EKS API 공개 접근이 작업자 공인 IP로 제한 |
| 승인 | Environment `prod` 필수 승인자, main만 허용 | 승인자는 GitHub 승인 기록 API로 읽어 이력에 남김. 계획 파일의 승인 표시는 읽지 않음 |
| 이미지 | publish job이 main SHA를 `main-<12자리>`로 ECR 게시, 있으면 재사용 | ECR 태그 IMMUTABLE. GitHub OIDC 역할은 ECR 쓰기만 |
| 계획 입력 | 실행 입력 JSON(커밋하지 않음), 원문은 artifact | 계획의 SHA가 그 계획을 담은 커밋을 가리키는 순환 회피 |
| 실행 게이트 | `scripts/cd_release.py`가 오류·차단 사유가 없을 때만 `executable=true` | 근거·승인자 미비 상태에서 게시·적용 차단 |
| 적용 | release별 server dry-run 전체 → 순서대로 `redeploy-app.ps1 -ImageDigest -Apply` | 실패하면 다음 release 미적용, 자동 롤백 없음 |
| 경로 확인 | 학생 PIN 로그인 → 시도 시작 → 답변 → 부모 refresh → 리포트 목록 | 판정(LLM)·결제 미호출. 부모 refresh 쿠키는 회전하므로 새 값을 fixture에 즉시 저장 |
| 이력 | `history.json` artifact(90일)와 실행 요약 | workflow에 `contents: write`를 주지 않음 |
| 롤백 | 이전 승인 digest를 같은 workflow·승인으로 적용 | DB downgrade 없음 |

- OIDC trust: AWS IAM은 GitHub 토큰의 `job_workflow_ref`를 조건 키로 비교하지 못함. 저장소 OIDC subject에 `job_workflow_ref`를 포함시키고 trust를 `sub` 하나(`StringLike`)로 main의 `cd-release.yml`만 허용
- deploy job `env`에서 `${{ runner.temp }}`를 쓰면 workflow 파일 오류가 됨 → 첫 step에서 `GITHUB_ENV`로 설정
- migration과 웹(S3/CloudFront) 배포는 범위 밖. migration은 배포 전 prod README 절차로 적용
- main·develop 브랜치 보호 규칙 없음(2026-11-04). main 직접 push로 workflow를 바꾸면 승인 전 publish job이 ECR 게시 역할을 쓸 수 있음. main 보호는 팀 결정 사항

### 7.3 DB 호환성 검토 시 포함할 제약

- #131 `20261030_04`: 기존 report-worker 중지 → migration → 새 worker 순서. 혼합 실행 미지원. downgrade 시 실패·격리·수동 재처리 메타데이터 소실
- report 삭제 guard 제거는 삭제된 학생의 재생성 차단을 잃을 수 있어 무조건 롤백 금지
- core·learning 앱 자동 migration은 꺼져 있음. 운영 DB 초기화·Flyway 이력 수정으로 버전을 맞추지 않음

### 7.4 운영 실행에서 얻은 주의점

- 11-04 첫 배포(main `a47a596`)·scoring 롤백 리허설·복귀, 11-05 두 번째 배포(main `322e797`) 완료. run 이력은 Actions artifact
- 경로 확인 fixture 미션의 `inputType`이 답변 형식과 같아야 함(처음에 `CHOICE` 미션으로 400)
- 이전 확인이 남긴 진행 중 시도를 돌려받으면 첫 답변 재제출이 422 → 저장된 답변 조회 경로로 처리(#376·#377)
- runner가 쓰는 AWS 프로필은 `sagomungchi-provided`. 세션 만료 시 `aws login --profile sagomungchi-provided`
- 배포 후 prod values의 앱 digest·migration 값을 실제 적용값으로 맞춤

## 8. 운영 경보와 trace (#185·#187)

| 항목 | 결정 |
|---|---|
| 경보 경로 | Grafana Alerting → 팀 디스코드 `aws-alerts`(webhook은 Secret `discord-alert-webhook`). SNS→Lambda 중계안은 채택하지 않음 |
| chart 구조 | #185의 observability chart 구조(values `rules`, 조직 notification policy, datasource UID `prometheus`)가 기준. #187 독립 생성기는 제거 |
| DLQ 수집 | opt-in `rabbitmq-dlq` job(`<큐>.dlq`만). DLQ 규칙이 있는데 수집이 꺼져 있으면 렌더 실패 |
| 월 LLM 비용 | 예산 300 USD, 80%(240 USD) 경보, KST 달력 월. core `LlmCostMetrics` gauge(단가 있는 비용·미산정 호출 수 분리) |
| 담당 | 동섭 1명, `aws-alerts` 한 채널 |
| trace 저장소 | Tempo(observability chart 선택 구성, 72h). Langfuse는 LLM 계측용으로 별도 |

### 8.1 구현에서 정한 것

- target 규칙은 `min(up{job=~...})`라 job 자체가 사라지면 발생이 아니라 NoData로 보고(NoData 알림은 전송)
- Prometheus·Collector·Grafana는 ConfigMap 변경을 다시 읽지 않아 재생성 annotation 사용
- app-service chart가 env의 `JAVA_TOOL_OPTIONS`를 agent 옵션 뒤에 합침. 이전에는 prod의 `-XX:MaxRAMPercentage`가 agent 플래그를 덮어써 agent가 빠져 있었음
- `app-metrics-missing`은 `absent() or absent()`로 쓰면 정상일 때 NoData가 됨 → `max(... or vector(0))`
- 기존 `summarize`는 미산정 호출이 섞인 call type의 비용을 null로 내므로 예산용 `monthToDate`를 따로 둠
- trace: core `OutboxWriter`가 봉투 `traceparent`를 넣고 `OutboxRelay`가 그 context에서 발행. report-worker는 `app/tracing.py`(OTel SDK)로 소비 span을 봉투 값에 연결
- span 상태는 재시도 처리기·업무 실패가 예외를 밖으로 내지 않아 ERROR가 아니라 재시도 발행·DLQ 이동으로 드러남

### 8.2 검증 상태

- 경보: kind에서 실제 DLQ 적재 → 규칙 발생 → `aws-alerts` Firing·Resolved 수신(11-04). prod는 임시 규칙으로 수신 경로 확인(11-03)
- trace: kind에서 명령 소비 → 동기 HTTP → 결과 이벤트 → 재시도·DLQ가 한 trace(span 67개). 로그인 사용자 요청 시작점은 미실행
- 검증 도구: `infrastructure/gitops/charts/observability`의 `verify_chart.py`(격리 Docker에서 규칙 발생·회복)
- 확인 필요: prod의 규칙 16개·Tempo 실제 적용 시각, core OTLP span 전송 404 경고 해소 여부
- 남은 것: ai·report(Python) 자체 HTTP 지표, 임계값 실측 조정, 서비스별 담당 라우팅

## 9. AWS 데모 부하 시험 1차 (#361)

2026-11-05, k6로 CloudFront → ALB → core에 단계별 부하. Karpenter·HPA 적용 전. 2차는 #384.

조건: core replica 1(CPU limit 1, Hikari 풀 10), RDS db.t4g.small, LLM은 클러스터 안 스텁(지연 2.5~4초), 시험 계정 1개(자녀 3명). 시나리오 `evaluation/load/core-load.js`(browse 55%·learn 20%·notify 15%·analyze 10%).

| 항목 | 50명 | 100명 | 200명 | 300명 |
|---|---|---|---|---|
| API 오류 | 0/5,705 | 0/12,338 | 0/26,968 | 0/40,312 |
| API p95 (ms) | 150 | 159 | 204 | 374 |
| core 처리량 (req/s) | 26.9 | 59.3 | 133.1 | 197.4 |
| core CPU 최대 (코어) | 0.13 | 0.23 | 0.48 | 0.69 |
| core DB 풀 사용 / 대기 최대 | 1 / 0 | 1 / 0 | 2 / 0 | 9 / 8 |
| RDS CPU 최대 (%) | 16 | 24 | 46 | 68 |

**결론**

1. 먼저 한계에 닿은 것은 DB 계층. RDS CPU가 VU에 비례해 약 350명에서 80%에 닿을 추세, 300명에서 core Hikari 풀 포화 직전
2. core CPU는 그다음(약 400명에서 한도 추정)
3. NAT는 훨씬 나중(계산 판단). 실제 LLM을 가정한 300명 트래픽도 약 6건/초·동시 연결 50개로 한도의 1% 미만
4. 가상 스레드 pinning 기록 0건, Pod 재시작 0, RabbitMQ 적체 0

**해석상 주의**

- 시도는 자녀×미션마다 하나라 학습 칸이 3 × 5 = 15개로 고정. 판정 처리량 상한 약 1.4건/초이고 75명을 넘으면 LLM 쪽 부하가 늘지 않음
- 칸을 얻지 못한 VU는 경합 호출을 반복해 300명 API의 약 35%가 경합. "DB가 먼저" 결론은 계정을 늘린 2차에서 재확인
- 판정 경로까지 보려면 계정 수 × 15 ≥ 0.2 × VU(300명은 계정 4개). #415 이후 `evaluation/load/prepare_accounts.py`로 ID·비밀번호 시험 계정 생성 가능

**개선 제안**

| 우선 | 제안 |
|---|---|
| 1 | RDS Performance Insights로 상위 쿼리 확인. `student_attempts`(p95 818ms)·`student_home` 쿼리 계획·인덱스 점검 |
| 2 | HPA 최대 Pod 수와 Hikari 풀 크기를 함께 정함(Pod 수 × 풀 ≤ RDS 최대 연결) |
| 3 | RDS 사양·읽기 복제본·자주 읽는 조회 캐시 검토(t4g는 CPU 크레딧 방식) |
| 4 | core HPA 기준은 CPU 0.5코어 근처로 시작 |
| 5 | NAT 실측은 실제 LLM 또는 클러스터 밖 스텁으로 따로 |

**남은 것**

- 토스 공용 위젯 키가 500(code 5000)을 돌려줘 결제 불가였음. 팀 전용 테스트 키 전환 검토
- 시험 데이터(시도 약 2,800건, 대화 106건 등)는 2차 시험 뒤 보호자 화면의 자녀 삭제 절차로 정리. SQL로 직접 지우지 않음. 시험용 기기 해제·k6 비밀 파일 삭제도 그때
- ECR `sagomungchi/llm-stub` 이미지는 2차 시험용으로 보존. 그 외 변경(스텁 배포, ai `OPENAI_BASE_URL`, core `JAVA_TOOL_OPTIONS`, PREMIUM 상품, 시험 구독)은 원복 완료

## 9.5 정지 중 고정비 축소 (#573, 2026-11-12)

데모는 2026-11-06부터 정지 상태(노드그룹 0대, RDS stopped)인데도 하루 약 7천 원이 나가 지원 예산을 넘을 우려가 있었다(#573). 계정 SCP가 Cost Explorer(`ce:GetCostAndUsage`)를 막아 서비스별 청구는 조회하지 못했고, 아래 금액은 서울 리전 공시 단가로 계산한 추정이다.

| 항목 | 하루 추정 | 결정 |
|---|---|---|
| EKS 컨트롤 플레인 | 약 3,300원 | **유지.** 지우면 eksctl 재생성·RDS bootstrap·Secret 복구·초기 데이터가 필요한데 재생성 절차가 검증되지 않았고, 12/8 최종 시연 전에 다시 켜야 함 |
| NAT 게이트웨이 + EIP | 약 2,100원 | **삭제.** 노드 0대라 외부 호출이 없음. 재개 때 다시 만듦 |
| ALB + 공인 IP 2개 | 약 1,000원 | **삭제.** 재개 때 LB Controller가 Ingress로 다시 만듦 |
| EBS(PVC 4개)·스냅숏·RDS 저장소·S3·ECR·Secrets Manager·로그 | 약 500~800원 | 유지(데이터 보존) |
| RDS 인스턴스 | 정지 중 0 | 정지 최대 7일 뒤 자동 재시작(첫 재시작 2026-11-13 10:19 KST 무렵) → 그때마다 다시 정지 |

실행(동섭 승인, 2026-11-12)
- ALB `sagomungchi-demo-core`와 대상 그룹을 지웠다. ALB 공인 IP 2개가 함께 해제됐다. LB Controller가 만든 보안 그룹 2개는 비용이 없어 남겼다
- NAT `sagomungchi-demo-nat-2a`를 지우고 EIP를 반납했다. 계정에 남은 EIP는 0개다. private route table 두 개의 `0.0.0.0/0`은 blackhole로 남는다(노드 0대라 영향 없음)
- 지우기 전 ALB 리스너·규칙·대상 그룹, NAT·EIP·route table 설정을 작업자 PC(저장소 밖)에 JSON으로 보관했다. ALB 규칙에는 CloudFront origin 헤더 값이 있어 저장소에 넣지 않는다

결과: 하루 약 7천 원 → 약 4천 원(추정, 약 43% 감소). 실제 금액은 결제 콘솔에서 며칠 치 청구로 확인한다.

재개 때 추가 단계(→ [EKS 재개 순서 0단계](../../infrastructure/eks/README.md#재개-순서와-완료-기준))
1. `demo_stack.py apply`로 NAT·EIP를 다시 만든다. 이 스크립트는 기존 route table의 경로를 고치지 않으므로 private route table 두 개에 `replace-route`로 새 NAT를 연결하고 `plan`이 차이 없음을 확인한다
2. ALB는 LB Controller가 다시 만들며 DNS 이름이 바뀐다. CloudFront `/api/*` origin을 새 ALB DNS로 바꾸고 origin 헤더·prefix list 제한을 확인한다

남은 고정비를 더 줄이려면 EKS 클러스터 삭제가 유일한 큰 항목이다. 재생성 절차 검증(#380 resume 검증과 함께) 전에는 하지 않는다.

## 10. 근거 링크

- [ingress-nginx 지원 버전](https://github.com/kubernetes/ingress-nginx#supported-versions-table), [종료 공지](https://kubernetes.io/blog/2025/11/11/ingress-nginx-retirement/), [kind v0.33.0](https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0)
- [Calico 요구사항](https://docs.tigera.io/calico/latest/getting-started/kubernetes/requirements), [native v3 CRD](https://docs.tigera.io/calico/latest/operations/native-v3-crds)
- [MinIO 배포 방식](https://github.com/minio/minio#source-only-distribution), [Chainguard MinIO](https://images.chainguard.dev/directory/image/minio/overview), [curl SigV4](https://curl.se/docs/manpage.html#--aws-sigv4)
- [Compose 변수 해석](https://docs.docker.com/reference/compose-file/interpolation/), [RabbitMQ 메모리](https://www.rabbitmq.com/docs/memory), [quorum WAL](https://www.rabbitmq.com/docs/quorum-queues#resource-use), [Redis eviction](https://redis.io/docs/latest/develop/reference/eviction/)
- [Langfuse 자체 호스팅 자원](https://langfuse.com/self-hosting/configuration/scaling), [Langfuse OTel 계약](https://langfuse.com/integrations/native/opentelemetry/migration-to-v4), [VPC 요금](https://aws.amazon.com/vpc/pricing/)
