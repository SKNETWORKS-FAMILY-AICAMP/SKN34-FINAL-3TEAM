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

### 3.4 추억 검색 문서 임베딩 켜기 (#591)

- learning `MEMORY_EMBEDDING_ENABLED`는 앱 기본 false(#563)인데 GitOps 값 어디에도 없어 배포에서 문서가 `PENDING`에 머물고 검색이 늘 `NO_RESULTS`였음(#562 kind 확인 D에서 발견)
- GitOps local·prod learning 값에 `true` 추가. 주기 1분·선점 64행·8글 묶음은 앱 설정 그대로이고 `AI_URL`·`CORE_URL`·`INTERNAL_TOKEN`·learning→ai/core 네트워크 정책은 이미 있어 더 넣을 값 없음. 선점은 `FOR UPDATE SKIP LOCKED`라 prod HPA 최대 3대에서도 중복 임베딩 없음
- 앱 기본값은 false 유지(테스트·Compose에서 실제 OpenAI 호출을 막음). Compose는 `${MEMORY_EMBEDDING_ENABLED:-false}`로 넘겨받음. 키 없이 켜면 문서가 5회 실패 뒤 `FAILED`가 되고 자동으로 되살아나지 않음
- 비용: 문서는 8건씩 묶어 `text-embedding-3-small` 1회 호출, 검색 질문은 1회씩. kind 실측 문서 19건(평균 301자) 적재 약 6,000토큰, 1원 미만
- kind 확인(2026-11-12): `READY` 2건을 `PENDING`으로 되돌린 뒤 helm upgrade(learning 17). 새 Pod 기동 약 1분 뒤 첫 주기에서 2건 `READY`(`text-embedding-3-small`), `MEMORY_EMBEDDING` 1회·724토큰 기록. 다른 서비스 변경 없음

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
| RDS | 비공개·암호화·자동 백업 7일, Single-AZ, 삭제 보호 off. PITR 복원 1회 성공(#629, 9.12): 요청→available 약 19분(RTO 4시간 안), 요청 시각과 최신 복원 가능 시점 간격 5분 23초 | RPO 5분은 로그 업로드 주기(5분) 경계라 넘을 수 있음(9.12.4). 근거 연결·결제 행이 없어 실데이터 정합성 미확인, 앱 전환 시간 미측정 |
| 플랫폼 | RabbitMQ·Redis·관측 단일 replica, AZ 고정 PVC(RabbitMQ·Prometheus·Grafana 2a, Redis 2b) | EBS/PVC 삭제·AZ 장애 복구 미검증 |
| 진입 | CloudFront→ALB HTTP origin | custom domain·ALB TLS 미구성 |
| Secret | ESO·Secrets Manager 원격 key 참조 | 키 회전·장애 복구 미검증 |
| NetworkPolicy | 서비스별 정책 있음, 일부 외부 연결은 넓은 CIDR. 저장소 값은 app 기본 거부를 켬(#657, 9.8), 배포 중이던 환경은 `namespaceDefaultDeny=false` | 설계 호출 표 전체 미검증, 기본 거부는 재가동 때 적용·확인 |
| S3·IAM 재생성 | 인벤토리·정책 원문 보존. 테마 자산 ai·learning 역할 2개는 저장소에만 정의(#652, 9.8) | 새 계정 실제 생성 미실행 |
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
- 실측(#384, 2026-11-18 → 9.14): 노드 확장 Pending→Ready 41초, 상한(CPU 4)에서 세 번째 노드 거부, 축소는 부하 종료 10분 46초~11분 20초 뒤 노드 0대. ai도 CPU 기준으로 확장됨. **D안 삭제 순서는 보장되지 않음**(2회 중 1회 기본 Pod가 함께 지워짐, 9.14.5)
- 후속: scoring HPA, report-worker KEDA, Spot 혼합(replica 2·PDB 이후)

## 7. CD 배포 승인·이력·롤백 (#186)

`cd-release.yml`: main 수동 실행 → GitHub Environment `prod` 승인 → 작업자 PC runner에서 (배포만) DB migration Job 완료 → Helm 적용 → 경로 확인 → 이력.

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
| 이미지 | publish job이 main SHA를 `main-<12자리>`로 ECR 게시, 있으면 재사용. core·learning migration 이미지(`*-migrate`)도 같은 태그로 게시, report는 앱 이미지가 Alembic을 포함 | ECR 태그 IMMUTABLE. GitHub OIDC 역할은 ECR 쓰기만 |
| migration (2026-11-17) | 배포만. 승인 후 migration·앱 server dry-run을 모두 마친 뒤 core → learning → report 순서로 Job 적용·`Complete` 확인, 그다음 앱 적용. 실패·시간 초과면 앱 미적용, DB는 되돌리지 않음. 같은 SHA 재실행은 완료된 Job을 건너뜀. 롤백은 migration 없음 | 11/6 이후 core V29~V51·learning V11~V21·report 3개가 수동 절차에 묶여 있었음. 승인 한 번으로 스키마와 앱을 같은 SHA로 맞추고, 실패 시 앱이 새 스키마 없이 뜨는 것을 막음 |
| 계획 입력 | 실행 입력 JSON(커밋하지 않음), 원문은 artifact | 계획의 SHA가 그 계획을 담은 커밋을 가리키는 순환 회피 |
| 실행 게이트 | `scripts/cd_release.py`가 오류·차단 사유가 없을 때만 `executable=true` | 근거·승인자 미비 상태에서 게시·적용 차단 |
| 적용 | release별 server dry-run 전체 → 순서대로 `redeploy-app.ps1 -ImageDigest -Apply` | 실패하면 다음 release 미적용, 자동 롤백 없음 |
| 경로 확인 | 학생 PIN 로그인 → 시도 시작 → 답변 → 부모 refresh → 리포트 목록 | 판정(LLM)·결제 미호출. 부모 refresh 쿠키는 회전하므로 새 값을 fixture에 즉시 저장 |
| 이력 | `history.json` artifact(90일)와 실행 요약 | workflow에 `contents: write`를 주지 않음 |
| 롤백 | 이전 승인 digest를 같은 workflow·승인으로 적용 | DB downgrade 없음, migration 실행 없음 |

- OIDC trust: AWS IAM은 GitHub 토큰의 `job_workflow_ref`를 조건 키로 비교하지 못함. 저장소 OIDC subject에 `job_workflow_ref`를 포함시키고 trust를 `sub` 하나(`StringLike`)로 main의 `cd-release.yml`만 허용
- deploy job `env`에서 `${{ runner.temp }}`를 쓰면 workflow 파일 오류가 됨 → 첫 step에서 `GITHUB_ENV`로 설정
- 웹(S3/CloudFront) 배포는 범위 밖. migration은 2026-11-17부터 workflow 안에서 실행(이전에는 배포 전 prod README 절차로 수동 적용). Job 로그는 공개 Actions 로그에 옮기지 않고 작업자 PC에서 확인
- migration 게시에는 publish 역할의 ECR 대상에 `core-migrate`·`learning-migrate`가 필요하다. 저장소 정책 파일만 고쳤고 AWS 반영은 재가동 때(그 전에는 publish가 실패해 배포로 넘어가지 않음). AWS 실행 검증은 아직 없음
- main·develop 브랜치 보호 규칙 없음(2026-11-04). main 직접 push로 workflow를 바꾸면 승인 전 publish job이 ECR 게시 역할을 쓸 수 있음. main 보호는 팀 결정 사항

### 7.3 DB 호환성 검토 시 포함할 제약

- #131 `20261030_04`: 기존 report-worker 중지 → migration → 새 worker 순서. 혼합 실행 미지원. downgrade 시 실패·격리·수동 재처리 메타데이터 소실
- report 삭제 guard 제거는 삭제된 학생의 재생성 차단을 잃을 수 있어 무조건 롤백 금지
- core·learning 앱 자동 migration은 꺼져 있음. 운영 DB 초기화·Flyway 이력 수정으로 버전을 맞추지 않음
- migration은 앱보다 먼저 적용되고 롤백해도 남으므로, 현재 앱과 롤백 대상 앱이 새 스키마에서 동작해야 함(추가만, 삭제·이름 변경은 앱이 먼저 안 쓰게 된 뒤 다음 릴리스로). 이 근거를 `compatibility.schema`에 적음

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
| 월 LLM 비용 | 예산 300 USD, 80%(240 USD) 경보, KST 달력 월. core `LlmCostMetrics` gauge(단가 있는 비용·미산정 호출 수 분리). 미산정 경보는 최근 1시간에 새로 생긴 미산정만(#764) |
| 담당 | 동섭 1명, `aws-alerts` 한 채널 |
| trace 저장소 | Tempo(observability chart 선택 구성, 72h). Langfuse는 LLM 계측용으로 별도 |

### 8.1 구현에서 정한 것

- target 규칙은 `min(up{job=~...})`라 job 자체가 사라지면 발생이 아니라 NoData로 보고(NoData 알림은 전송)
- Prometheus·Collector·Grafana는 ConfigMap 변경을 다시 읽지 않아 재생성 annotation 사용
- app-service chart가 env의 `JAVA_TOOL_OPTIONS`를 agent 옵션 뒤에 합침. 이전에는 prod의 `-XX:MaxRAMPercentage`가 agent 플래그를 덮어써 agent가 빠져 있었음
- `app-metrics-missing`은 `absent() or absent()`로 쓰면 정상일 때 NoData가 됨 → `max(... or vector(0))`
- 기존 `summarize`는 미산정 호출이 섞인 call type의 비용을 null로 내므로 예산용 `monthToDate`를 따로 둠
- `llm-unpriced-calls`(#764): 처음엔 월 누적 `max(...unpriced_calls) > 0`이라 11/17 재가동 뒤 단가 등록(#651) 전 11/03~05 기록 6,748건 때문에 계속 켜져 4시간마다 Discord 알림이 반복됨. `max(delta(...[1h])) > 0`으로 바꿔 새 누락만 보고, 새 누락이 1시간 없으면 해제, 월초 0 초기화는 음수라 울리지 않음. 설계상 비용이 없는 M2는 단가 0, Veo·RunPod Gemma는 별도 청구로 미산정에서 뺌([core-gateway 33장](core-gateway.md#33-llm-미산정-경보-정리-764-2026-11-18)). model 라벨은 붙이지 않음(새 모델의 첫 시계열은 delta가 0이라 오히려 놓침)
- trace: core `OutboxWriter`가 봉투 `traceparent`를 넣고 `OutboxRelay`가 그 context에서 발행. report-worker는 `app/tracing.py`(OTel SDK)로 소비 span을 봉투 값에 연결
- span 상태는 재시도 처리기·업무 실패가 예외를 밖으로 내지 않아 ERROR가 아니라 재시도 발행·DLQ 이동으로 드러남

### 8.2 검증 상태

- 경보: kind에서 실제 DLQ 적재 → 규칙 발생 → `aws-alerts` Firing·Resolved 수신(11-04). prod는 임시 규칙으로 수신 경로 확인(11-03)
- trace: kind에서 명령 소비 → 동기 HTTP → 결과 이벤트 → 재시도·DLQ가 한 trace(span 67개). 로그인 사용자 요청 시작점은 미실행
- 검증 도구: `infrastructure/gitops/charts/observability`의 `verify_chart.py`(격리 Docker에서 규칙 발생·회복)
- 확인 필요: prod의 규칙 16개·Tempo 실제 적용 시각, core OTLP span 전송 404 경고 해소 여부
- 남은 것: ai·report(Python) 자체 HTTP 지표, 임계값 실측 조정, 서비스별 담당 라우팅

## 9. AWS 데모 부하 시험 1차 (#361)

2026-11-05, k6로 CloudFront → ALB → core에 단계별 부하. Karpenter·HPA 적용 전. 2차(#384)는 [9.14](#914-aws-데모-부하-시험-2차-hpakarpenter-확장축소-384-2026-11-18).

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
| EKS 컨트롤 플레인 + 노드그룹 정의 | 약 3,300원 | **삭제(2차).** 처음엔 재생성 절차 미검증으로 유지했으나, RDS·S3·ECR·Secrets Manager는 남아 DB 초기화·seed가 필요 없고 클러스터에만 있던 Secret을 백업한 뒤 지움. 12/8 시연 1주 전 재생성 |
| NAT 게이트웨이 + EIP | 약 2,100원 | **삭제.** 노드 0대라 외부 호출이 없음. 재개 때 다시 만듦 |
| ALB + 공인 IP 2개 | 약 1,000원 | **삭제.** 재개 때 LB Controller가 Ingress로 다시 만듦 |
| EBS(PVC 4개)·스냅숏·RDS 저장소·S3·ECR·Secrets Manager·로그 | 약 500~800원 | 유지(데이터 보존) |
| RDS 인스턴스 | 정지 중 0 | 정지 최대 7일 뒤 자동 재시작(첫 재시작 2026-11-13 10:19 KST 무렵) → 그때마다 다시 정지 |

실행(동섭 승인, 2026-11-12)
- ALB `sagomungchi-demo-core`와 대상 그룹을 지웠다. ALB 공인 IP 2개가 함께 해제됐다. LB Controller가 만든 보안 그룹 2개는 비용이 없어 남겼다
- NAT `sagomungchi-demo-nat-2a`를 지우고 EIP를 반납했다. 계정에 남은 EIP는 0개다. private route table 두 개의 `0.0.0.0/0`은 blackhole로 남는다(노드 0대라 영향 없음)
- 지우기 전 ALB 리스너·규칙·대상 그룹, NAT·EIP·route table 설정을 작업자 PC(저장소 밖)에 JSON으로 보관했다. ALB 규칙에는 CloudFront origin 헤더 값이 있어 저장소에 넣지 않는다

2차 실행: EKS 삭제(동섭 승인, 2026-11-12)
- 삭제 전 백업: ESO 동기화 대상이 아닌 Secret은 관측 2개뿐이라 Secrets Manager `sagomungchi/demo/observability/grafana-admin`·`…/discord-webhook`에 복사하고 원본과 해시로 일치를 확인했다(값 미출력). 클러스터·노드그룹·add-on·access entry·Pod Identity 8개·Helm release 11개 values·Karpenter·Ingress·PVC·replica 수는 작업자 PC(저장소 밖)에 JSON으로 보관했다
- 노드그룹 `application`·`platform-observability`(모두 0대)를 지운 뒤 클러스터 `sagomungchi-demo-eks`를 지웠다. Pod Identity 연결은 함께 사라졌고, 클러스터 SG는 RDS SG 규칙이 참조해 남았다(비용 없음, 재생성 뒤 정리)
- 남긴 것: RDS·S3·ECR·Secrets Manager·IAM 역할·VPC·스냅숏, PVC였던 EBS 4개(합계 10GiB, 월 약 1천 원, 재연결 선택지로 보존)

결과: 하루 약 7천 원 → NAT·ALB 삭제 후 약 4천 원 → EKS 삭제 후 약 700원(모두 추정). 실제 금액은 결제 콘솔에서 며칠 치 청구로 확인한다.

재개는 이제 재생성이다(→ [EKS 재생성 순서](../../infrastructure/eks/README.md#재생성-순서-2026-11-12-eks-삭제-이후)). 처음 실행하는 절차라 12/8 시연 1주 이상 전에 시작한다.

## 9.6 ai 영상 이어 붙이기 메모리 (#586, 2026-11-12)

#546 kind 확인에서 주간 테마 초안 첫 생성이 영상 컷 이어 붙이기 단계에서 ai 메모리 상한 512Mi를 넘어 OOMKilled됐다. 같은 입력을 1Gi로 다시 생성했을 때는 `READY`였다.

측정 방법
- Veo·OpenAI는 부르지 않았다. #546 때 MinIO `theme-drafts/`에 남은 INTRO·OUTRO 결과 영상(1280x720·24fps·22.5초)을 4·6·8·6초 컷으로 잘라 Veo 컷 대신 쓰고, 장면 그림(1536x864 PNG)으로 움직이는 그림 컷을 만들었다.
- kind와 같은 이미지(`sagomungchi/ai-service:local`) 컨테이너에서 `app.main`을 불러 둔 채 `app/llm/media.py`·`theme_draft/nodes/video.py` 함수를 실제 흐름 순서대로 불렀다. CPU 상한은 500m, 메모리는 2Gi로 열어 두고 cgroup `memory.current`를 10ms 간격으로 읽어 단계별 최대값을 쟀다.
- ffmpeg(libx264)는 CPU 상한이 아니라 보이는 코어 수만큼 스레드를 만든다. 그래서 kind 노드(16코어)와 운영 노드(t3.medium·t3.large, 2 vCPU)를 `--cpuset-cpus`로 나눠 쟀다.

컨테이너 메모리 최대값(MiB, 대기 상태 약 145)

| 단계 | 2코어(운영) | 4코어 | 16코어(kind) |
|---|---|---|---|
| 컷 8개 동시 검토(멈춤 감지·장면 뽑기) | 377 | 443 | 749 |
| 움직이는 그림 컷 1개(8초) | 380 | 422 | 593 |
| 컷 4개 다시 인코딩(앞뒤 멈춤 자르기) | 390 | 427 | 631 |
| **이어 붙이기(Veo 컷 4개)** | **509** | **566** | **846** |
| **이어 붙이기(Veo 1 + 그림 컷 3)** | **528** | **566** | **850** |

- 메모리 대부분은 Python이 아니라 ffmpeg 하위 프로세스다. ffmpeg 최대 RSS는 2코어 391MiB, 16코어 709MiB였다. Python 쪽 컷 바이트는 수 MB라 영향이 작다.
- 실제 서버는 측정 컨테이너보다 대기 메모리가 약 30MiB 많다(kind ai 약 175MiB).
- 운영(2 vCPU)도 이어 붙이기가 512Mi를 넘는다. 영상을 켜면 운영도 같은 실패가 난다.

결정

| 항목 | 값 | 근거 |
|---|---|---|
| 메모리 상한 | 512Mi → **1Gi**(kind·운영) | kind 최대 약 880MiB(대기 차이 포함)에 여유 약 140MiB. 운영은 약 560MiB라 여유가 크다 |
| 메모리 요청 | **256Mi 유지** | 평소 약 180MiB. 영상 작업은 주 1회 관리자 초안 생성 때만 몇 분이다 |
| 적용 범위 | **영상을 켜든 끄든 항상 1Gi** | 요청을 그대로 두면 스케줄링·노드 용량이 바뀌지 않는다. 영상 스위치와 메모리 값을 따로 맞춰야 하는 실수를 없앤다 |

영향 확인
- 스케줄링은 요청만 보므로 앱 노드그룹(t3.medium)과 NodePool `application-burst`(CPU 4·메모리 16Gi 상한) 계산은 바뀌지 않는다.
- HPA는 CPU 70%만 본다. 메모리 값은 확장 조건에 들어가지 않는다. 다만 ffmpeg가 CPU 상한 500m까지 쓰면 요청 100m 대비 70%를 넘어 영상 생성 몇 분 동안 ai가 최대 3개까지 늘 수 있다. 늘어난 Pod는 영상 작업을 나눠 받지 않고, 부하가 끝나면 줄어든다.
- 상한 합은 늘지만(최대 3 replica × 1Gi), 요청을 넘는 메모리는 노드에 여유가 있을 때만 쓴다. 노드 메모리가 부족하면 요청을 넘게 쓰는 ai가 먼저 축출될 수 있다. 영상 작업 중 축출되면 초안은 실패로 끝나고 learning이 재시도한다.
- 운영 `prod/ai-service.json`에는 아직 `THEME_VIDEO_ENABLED`·`ASSET_S3_BUCKET` 같은 테마 그림·영상 env가 없다. 운영에서 영상을 켜려면 이 env와 Google 자격 증명 배포(#538)가 따로 필요하다.

검토한 대안(적용하지 않음)
- 컷을 파일로 이어 붙이기: ffmpeg는 이미 임시 파일로 입력을 받는다. 줄일 수 있는 것은 Python이 쥔 수 MB뿐이라 효과가 거의 없다.
- ffmpeg 스레드 제한: 16코어에서 출력 쪽만 `-threads 2`로 묶으면 이어 붙이기가 850 → 650MiB로 줄었다. 하지만 컷 8개 동시 검토(디코딩)가 710MiB로 남아, 입력 디코딩 스레드와 동시 처리 수까지 손봐야 한다. 상한 1Gi로 충분해 코드는 바꾸지 않았다. 코어가 많은 노드에서 영상을 켤 때 다시 검토한다.

검증
- local·prod `helm lint --strict`·`helm template`에서 limits 1Gi, requests 256Mi를 확인했다.
- kind ai에 적용해 Running(cgroup `memory.max` 1Gi)을 확인했다. 영상은 꺼 둔 상태(`THEME_VIDEO_ENABLED=false`)다.
  - #546 때 `kubectl set resources`로 바꾼 필드 소유권이 남아 있어 Helm 적용이 충돌했다. `helm upgrade --force-conflicts`로 그 필드를 Helm이 다시 가져왔다.
- 완료 조건(영상을 켠 kind 초안 1건 `READY`)은 #546 재시도(상한 1Gi·영상 켬·`READY`·OOM 없음)와 위 실측으로 확인했다. Veo는 다시 부르지 않았다.
- 실제 Veo 컷의 앞뒤 정지 구간 자르기(다시 인코딩)가 여러 컷에서 동시에 일어나는 경우는 재지 못했다.

## 9.7 시연 계정 데이터 준비 (#624, 2026-11-13)

추억 앨범·추억 검색(FN-RET-10~12)은 진행 주 이전에 5문제를 모두 끝낸 회차가 있어야 내용이 나오고, 주간 리포트 설명(FN-RPT-09)은 그 주 M2 점수가 있는 답변이 있어야 생긴다. 새 시연 계정은 빈 화면이라 12/7(월) 시연 전에 지난 회차 기록을 만드는 절차를 정했다. 실행 순서는 [infrastructure/aws/README.md](../../infrastructure/aws/README.md#시연-계정-데이터-준비-624)에 있다.

### 9.7.1 결정 (담당자 확인 2026-11-13)

| 항목 | 결정 | 근거 |
|---|---|---|
| 기록 생성 방식 | 혼합 API: 지난 주(11/30 주)는 재가동 뒤 실제 시각으로, 앞선 2회차는 core·learning 시계를 그 주 토요일로 옮겨 같은 API 스크립트로 만든다. SQL INSERT 없음 | 시드 SQL은 learning·scoring·core·report 4개 DB의 시도·답변·판정·점수·포인트·문서·리포트 정합성을 손으로 맞춰야 하고 이슈의 "가능하면 API 흐름" 원칙과 어긋난다. 12/7이 월요일이라 지난 주는 실제로 지나가므로 시계를 옮길 필요가 없다. 실시간만으로 2회차 이상을 만들려면 EKS를 2주 켜 둬야 한다(비용) |
| 회차·학생 | 초3 무료 1명·초5 프리미엄 1명, 학생별 3회차(11/16·11/23·11/30 주) | 검색 문서가 학생당 15개라 상위 3개 카드가 의미 있게 갈린다. 설명 카드는 명세상 프리미엄·M2 승인 범위(서술 초5·6)만이라 초5에서만 확인한다 |
| 답변 내용 | 스크립트에 자체 작성한 가상 소재 15개(고양이·우산·텃밭 등)를 주·요일마다 다르게 넣는다 | 같은 미션이 반복돼도 답변 표현으로 회차가 구분돼 추억 검색을 보여 줄 수 있다(NFR-SEC-07) |
| 풀이 시점 | 토요일 | 무료도 금·토에는 다섯 요일이 모두 열리고(#483) 토요일 정답 고르기로 바로 엔딩까지 간다. 일요일은 무료가 닫힌다 |

### 9.7.2 kind 확인 (실제 17:20~17:45)

- 대상: develop 배포 그대로(core 6e4eb6c9 이미지, learning 2026-11-13 이미지). 새 시연 학부모(ID·비밀번호)와 자녀 시연3학년(G3)·시연5학년(G5, `LOCAL-PLUS` 시험 구독)
- 테마: G3 11/23은 있던 테마, 나머지 5개(G3 11/16·11/30, G5 11/16·11/23·11/30)는 기존 게시 테마를 복사해 관리자 API로 작성·게시했다(kind 게시 미션만 사용)
- 시계: 11/21(토)·11/28(토)·12/5(토) 14:00 KST에 `solve`, 12/5 23:56 → 일일 리포트, 12/6 23:56 → 월요일 00:00 주간 리포트. 12/7 00시대에 `decorate`·`verify`
- 결과(API와 웹 화면)

| 항목 | 결과 |
|---|---|
| 회차 완료 | 두 학생 모두 3회차 5문제 완료·완주(finished), 초3은 정답 고르기로 엔딩(G5 바탕 테마는 정답 후보가 없어 엔딩 전) |
| 추억 앨범 | 액자 3개, 최근 회차 "새 액자" 표시(웹 앨범 안내 "새 액자가 생겼어요!"), 회차 상세 5문제, 초3 엔딩 보임 |
| 추억 검색 | 검색 문서 30개 모두 `READY`(실제 OpenAI 임베딩). "비 오는 날 우산을 같이 쓴 이야기" → 초3 11/16 회차, "자전거 타기 연습했던 거" → 초5 11/30 회차가 결과로 나옴. 웹 검색 화면은 #567 구현 전이라 API로만 확인 |
| 추억의 벽·가구 | 벽 슬롯 3개(웹 내 방에 액자 3개·"새 액자 1"), DESK·WALL 가구 해금·착용 |
| 주간 리포트 | 11/30~12/6 두 학생 `OK`. 초5는 설명 카드 3개 `INCLUDED`(웹 "대표 답변 설명"·"AI 관찰" 카드 3개, 문구는 대역) |
| 일일 리포트 | 12/5 `OK`, 12/6(일, 기록 없음) `NO_RECORD` |
| 점검 SQL | `audit-demo-data.sql` 세 DB 모두 통과(기준 월요일을 12/7로 바꾼 복사본) |

임시로 바꾼 것(모두 되돌림): core·learning 시험 시계 이미지·환경 변수, ai `OPENAI_BASE_URL`=sllm-server(llm-stub 대역, 판정 LLM 비용 0), ai `M2_CROSS_CHECK_ENABLED=true`, sllm-server 임시 설치(KEDA 끔·1대). 되돌린 뒤 core·learning·ai ReplicaSet이 helm 상태와 같은 해시로 돌아가고 Pod 시각이 실제 시각인지 확인했다. 실제 OpenAI는 추억 검색 임베딩(문서 30건·질문 몇 건)만 불렀다.

kind에 남긴 것: 시연 학부모·자녀 2명과 미래 날짜(11/16~12/7) 기록·리포트, 위 테마 5개(게시), G5 서술 미션 3개의 기준표 v2(M2 핵심어), MinIO `models/m2-klue-narrative/3.0/`, 모델 등록 `m2-klue-narrative` 3.0·`report-explanation` kind-stub-624(활성), 시험 시계 이미지 `sagomungchi/{core,learning}-service:demo-clock`. 활성 모델을 끄는 관리자 API가 없어(rollback은 이전 승인 버전으로만) 모델 활성 상태는 정리 방법을 정할 때까지 그대로 둔다.

### 9.7.3 발견

1. **설명 카드는 지금 운영 값으로는 나오지 않는다.** ai `M2_CROSS_CHECK_ENABLED` 기본 false(#305)라 M2를 부르지 않고, 저장소 시드 미션 기준표에 M2 핵심어(`keywords`)·논술 글 종류(`essayType`)가 없어 켜더라도 M2 입력이 없다. kind에서는 둘 다 임시로 채워야 설명 카드 3개가 생겼다. 시연에서 설명 카드를 보이려면 플래그를 켤지(판정 보류 `HELD` 발생 가능)와 초5 테마 미션 기준표 보완을 정해야 한다 → 9.7.5(#668)에서 정함
2. 활성 모델을 끄는 경로가 없다. 첫 버전을 시험으로 활성화하면 DB를 직접 고치지 않고는 되돌릴 수 없다
3. 새 학부모는 자녀 등록 전에 계정 동의(TERMS·PRIVACY)가 필요하다(`children` 명령이 처리)

### 9.7.4 한계

- AWS에서는 실행하지 않았다. 운영 적용은 #601 재가동 때이고, AWS 테마·가구 아이템·M2·sLLM 상태에 따라 사전 조건이 달라진다
- 시험 시계 동안 가짜 시각으로 서명한 S3(MinIO) 그림 URL은 "not valid yet"으로 깨진다. kind 화면 확인의 그림 자리는 기본 그림이었다. AWS 지난 주 회차는 실제 시각이라 영향이 없다
- 앞선 2회차의 주간·일일 리포트는 만들지 않았다(시연에 필요한 것은 지난 주 리포트)
- 웹 추억 검색 화면(#567)은 구현 전이라 검색은 API로만 확인했다

### 9.7.5 설명 카드용 기준표 M2 입력과 교차 확인 켜기 (#668, 2026-11-16)

#661에서 설명 카드(FN-RPT-09)가 나오는 조건을 ① ai `M2_CROSS_CHECK_ENABLED=true` ② 미션 기준표 M2 입력(서술 `keywords`, 논술 `essayType`) ③ M2 활성 모델로 정리했다. ③은 #601 재가동 절차에 있고, 이번에 ①·②를 정했다.

| 항목 | 결정 | 근거 |
|---|---|---|
| 교차 확인 켜기 | 켠다. 앱 기본값(false, #305)은 두고 prod 값 `gitops/environments/prod/ai-service.json`에 `true` | prod 값이 곧 AWS 데모 환경이고 `redeploy-app.ps1`·cd-release가 매번 이 파일로 helm upgrade를 한다. 시연 절차에서 `kubectl set env`로만 켜면 그 뒤 ai 재배포 때 꺼진다. M2는 기준표에 M2 입력이 있는 미션에서만 불리므로(api-spec 4.2.2) 영향은 시연 스크립트로 보강한 초5 테마 미션뿐이고, A 계정 시험도 시연과 같은 조건이 된다 |
| 판정 보류 | 허용하고 확인 항목으로 둔다 | 켜면 LLM `CORRECT`·M2 평균 낮음(서술 2.0 이하) 또는 `RETHINK`·높음(4.0 이상)일 때 `HELD(MODEL_DISAGREEMENT)`가 생긴다(글자 수 하한 미만 제외). `audit-demo-data.sql`에 `demo668_recent_judgments`(최근 3주 판정 결과·보류 사유별 건수)를 더해 `solve` 뒤 확인한다 |
| 기준표 M2 입력 위치 | 운영 시드 migration이 아니라 #624 시연 스크립트 `demo_account_data.py m2-rubric`에서만 | 운영 시드를 바꾸면 모든 환경 판정에 M2가 붙는다. 스크립트는 공개 기준표를 복사해 M2 입력만 더한 새 기준표 버전 → 검토 승인 → 재게시(api-spec 2.8 관리자 미션, P07 불변 버전)로 넣고, 이미 있으면 그대로 둔다 |
| 입력 값 | 시드 G5 미션 4개는 스크립트 상수(`M2_INPUTS`): DEMO-11·13·15 서술 핵심어 3묶음(`핵심어(비슷한 말)`), DEMO-12 논술 `주장`. 관리자 화면·초안으로 만든 테마 미션은 `--m2-input` JSON | DEMO-11·15는 9.7.2 kind 확인 때 쓴 값 그대로. 설명은 생각 유형이 겹치지 않는 M2 점수 답변 최대 3개이고 초5 M2 활성 범위가 서술이라, 주마다 생각 유형이 다른 서술 미션 3개에 핵심어가 있어야 카드 3개가 나온다. 스크립트가 주별 "M2 입력 서술 N유형"을 출력한다 |

kind 확인(실제 2026-11-16 09:57~10:07 KST, 공유 `kind-sagomungchi-local`)

- 대상: develop 배포 그대로(helm ai rev 21·learning rev 18·core rev 13). 9.7.2의 시연 학부모·시연5학년(프리미엄 시험 구독)과 게시된 G5 테마 11/16·11/23·11/30
- ai `kubectl set env M2_CROSS_CHECK_ENABLED=true` 적용
- `m2-rubric --dry-run` → 실제 실행 → 재실행

| 항목 | 결과 |
|---|---|
| 기준표 보강 | DEMO-12(논술) v1→v2 `essayType`, DEMO-13(서술) v1→v2 핵심어, kind 초안 M-E1708259 v8→v9 핵심어(`--m2-input`) 저장·검토 승인·재게시. DEMO-11·15·M-D0651927은 9.7.2 때 넣은 v2라 그대로. 세 주 모두 "M2 입력 서술 3유형(ANALYZE·CREATE·REFLECT)" |
| 다시 실행 | 모든 미션 "있음"으로 아무것도 바꾸지 않음 |
| 입력 없음 | 보강 전 `--m2-input` 없이 `--dry-run`하면 M-E1708259를 이름으로 알려 주고 실패 |
| 새 답변 M2 점수 | learning만 시험 시계(12/5 토 14:00 KST)로 옮겨 시연5학년이 보강한 DEMO-13·M-E1708259를 추가 문제(`EXTRA`)로 풂(실제 LLM 판정 2건). 두 판정 모두 보강한 기준표 버전(v2·v9)으로 `model_scores.m2` 있음, `versions.model` `m2-klue-narrative@3.0`, 결과 `RETHINK`(보류 아님) |
| 주간 설명 카드 | sLLM 서버 대역(llm-stub) 임시 설치 뒤 시연5학년 11/30~12/6 주간 리포트를 학부모 재생성 → `OK`, 설명 `INCLUDED` 카드 3개(ANALYZE·CREATE·REFLECT, 검사 통과). 카드는 같은 주 9.7.2 테마 답변(DEMO-11·M-D0651927·DEMO-15)이 뽑혔다. 새 답변 2개도 후보였지만 가짜 시각이 같은 12/5 05:00 UTC에서 시작해 9.7.2 답변이 약 20초 늦게 제출돼 "같은 생각 유형은 최근 답변 우선" 규칙으로 밀렸다 |
| 점검 SQL | `demo668_recent_judgments`에 `MODEL_DISAGREEMENT` 0건, `demo668_published_m2_rubrics` 서술 G5 5개·논술 G5 1개 |

임시로 바꾼 것(되돌림): learning 시험 시계 이미지·환경 변수(되돌린 뒤 helm 상태와 같은 ReplicaSet·실제 시각 확인), sLLM 서버 대역 설치(helm uninstall). 실제 OpenAI는 답변 2건의 판정·되묻기와 재생성 리포트 서술 1건만 불렀다.

kind에 남긴 것: **ai `M2_CROSS_CHECK_ENABLED=true`**(kind ai는 helm rev 21 값과 다르다. 이어지는 #630 실측을 시연과 같은 조건으로 재기 위해 켜 둠, `helm upgrade`나 local 값 재적용 때 false로 돌아감), 위 기준표 새 버전 3개(게시), 시연5학년 12/5 추가 문제 시도 2건, 11/30 주 재생성 리포트(학부모 재생성 기회 사용).

AWS에서 남은 확인(#601 재가동 뒤 B 계정)

- prod 값 반영 뒤 ai Pod 환경 변수 `M2_CROSS_CHECK_ENABLED=true`
- 시드·관리자 테마 기준으로 `m2-rubric`이 세 주 모두 "서술 3유형"을 내는지(초안 미션이면 `--m2-input` 준비)
- 12/4~12/5 실제 시각 `solve` 뒤 `demo668_recent_judgments`의 보류 건수, 12/7 주간 리포트 설명 카드 3개(`verify`). 새 답변으로만 뽑히는 확인은 여기서 된다(지난 주 답변이 모두 보강 뒤에 생기므로)
- 실제 sLLM 서버(llama.cpp)·`report-explanation` 활성 상태에서의 설명 문구(kind는 대역 문구)

## 9.8 prod 테마 자산 버킷과 네임스페이스 기본 거부 준비 (#652·#657, 2026-11-16)

AWS가 내려가 있어(EKS 삭제, RDS 정지) 저장소 값과 문서만 고쳤다. AWS 호출은 읽기도 하지 않았고, 적용·확인은 A 계정 재가동(#601) 때 한다. 2026-11-17 재가동 때 실제로 적용·확인한 결과는 9.8.3에 있다.

### 9.8.1 테마 자산 버킷 (#652)

- 문제: prod ai·learning 값에 `ASSET_S3_BUCKET`이 없어 ai는 그림·영상 단계를 건너뛰고(`app/theme_draft/storage.py` `create_storage`, `app/llm/media.py` `create_media_clients`), learning은 자산 URL을 null로 준다(`app.assets.bucket`). 오류가 나지 않아 눈에 띄지 않았다.
- 값: 두 서비스에 `ASSET_S3_BUCKET=sagomungchi-demo-<A 계정>-missions`, `S3_REGION`·`AWS_REGION=ap-northeast-2`. local과 달리 `S3_ENDPOINT_URL`(ai)·`S3_PUBLIC_ENDPOINT_URL`(learning)은 넣지 않는다. 비어 있어야 AWS S3 주소로 올리고 서명한다(local 값은 MinIO 주소).
- 권한: `infrastructure/aws/iam`에 ai·learning용 역할이 없었다(report·scoring만 있음). 역할 2개(ai `PutObject`, learning `GetObject`, 둘 다 `theme-drafts/*`만)와 trust를 정의하고 `demo-stack.json`(IAM 역할 12개)·`eks/cluster.json`(Pod Identity 10개)에 넣었다. 재가동 절차는 [AWS README 테마 자산 버킷 권한](../../infrastructure/aws/README.md#테마-자산-버킷-권한-652-2026-11-16-정의미적용).
- #537(2026-11-17): ai 역할 정책에 `s3:GetObject`를 더함(`theme-drafts/*` 그대로). 테마 초안 부분 다시 생성이 S3에 둔 재료 그림(테마 옷 뭉치·컷 첫 그림)을 다시 읽기 때문. 정책 이름 `sagomungchi-demo-ai-asset-s3-write`는 `demo-stack.json`·AWS 역할과 이어져 있어 바꾸지 않음. 역할은 아직 AWS에 없어 #652로 만들 때 같이 들어가고, 그 뒤에 들어오면 정책만 다시 적용(#652 담당 확인)
- 네트워크: 두 앱은 이미 자기 NetworkPolicy로 egress가 격리돼 있어, 역할만 연결하면 Pod Identity agent(`169.254.170.23:80`)에 못 닿아 자격 증명을 못 받는다. 두 앱 egress에 agent를 더했다(report·scoring·sLLM과 같은 규칙).
- 한계: presigned URL은 Pod Identity 임시 자격 증명으로 서명하므로, 자격 증명 만료가 1시간(`url-ttl`)보다 가까우면 URL이 더 일찍 만료될 수 있다(`AssetUrls` 주석). 화면에서 그림이 중간에 안 보이면 이것부터 본다.
- B 계정 이전 때 바꿀 항목: 버킷 이름·IAM 원문·`cluster.json`의 계정 번호(AWS README 같은 절).

### 9.8.2 app 네임스페이스 기본 거부 (#657)

결정(권장안): prod 값에 켜고 필요한 허용을 더하며, 실제 확인은 A 계정 재가동 때 한다.

판단 근거(읽기 위주): 공유 local kind는 이날 Docker가 꺼져 있어 조회하지 못했고, 켜 보는 시험도 하지 않았다. 대신 다음으로 판단했다.

- local은 이미 core 값에서 `namespaceDefaultDeny: true`로 app 기본 거부를 켜 둔 상태로 kind 확인 A~D(#436)·#546·#624를 통과했다. 기본 거부 아래에서 앱 7개·migration Job(Argo PreSync 정책 포함)이 동작한 근거다.
- prod 앱 values 7개와 migration 덮어쓰기 3개를 helm 4.3.1로 렌더링해 모든 Pod 라벨이 어떤 정책에 선택되는지 대조했다. 앱 Deployment 7개는 이미 자기 정책(ingress·egress)으로 격리돼 있어 기본 거부를 더해도 허용 범위가 같다. NetworkPolicy는 합집합이므로 기본 거부는 "자기 정책이 없는 Pod"에만 영향을 준다.

기본 거부를 켜면 막히는 것과 처리:

| 대상 | 현재 prod | 처리 |
|---|---|---|
| migration Job(core·learning·report) | `--show-only migration-job.yaml`로 Job만 적용 → 정책 없음 | `migrations/*.json`에 `networkPolicy.migrationEgress`(RDS 5432) 추가, prod README 절차와 ci-gitops 렌더링에 `migration-networkpolicy.yaml`을 같이 넣음 |
| `rds-bootstrap` Job(`demo_stack.py`), `demo-db-oneoff` Pod | 정책 없음 | `prod/app-oneoff-db-network.json`(DNS·RDS 5432) |
| 배포 확인 Pod(`deployment-check` 라벨) | core·learning·scoring ingress만 허용, Pod 자체 egress 정책 없음 | `prod/app-check-pods-network.json`(DNS·core·learning·scoring) |
| `kubectl run` 등 그 밖의 임시 Pod | 정책 없음 | 막히는 것이 의도. 필요하면 위 라벨을 쓰거나 정책을 먼저 만든다 |
| KEDA(#476 sLLM cron) | prod 미설치 | cron 스케일러는 app Pod와 통신하지 않음. RabbitMQ 스케일러를 쓰면 platform 정책(`platform-network.json`) 문제이고 app 기본 거부와 무관 |
| 관측(Collector·Prometheus·Langfuse) | 앱별 `egressToCollector`·`ingressFromPrometheus`·`egressToLangfuse` | 앱 Pod가 이미 격리돼 있어 변화 없음. 관측 Pod는 `observability` namespace라 대상 아님 |
| ALB → core, kubelet probe, `kubectl exec`·`logs` | `core-alb-network.json`, 기존 격리 상태에서 동작 | 변화 없음 |

- `app-default-deny`는 core release만 만든다. 두 release에 켜면 같은 이름 객체로 Helm 소유권 충돌이 난다.
- 재가동 때 확인할 것: core 재배포 뒤 `kubectl -n app get networkpolicy app-default-deny`, 앱 7개 readiness, migration Job 1회 성공, `demo-db-oneoff`로 `select 1`, 정책 없는 `kubectl run` Pod의 DNS 조회가 실패하는지. 되돌리기는 prod README NetworkPolicy 절.

### 9.8.3 A 계정 재가동 확인 결과 (2026-11-17)

운영 기준 main `e3cb5084`로 재가동하며 실제로 실행한 결과다. 순서는 9.11.5를 따랐다.

#### 테마 자산 버킷 (#652)

실행:

- `demo_stack.py apply`로 역할 `sagomungchi-demo-ai-asset-s3-role`·`sagomungchi-demo-learning-asset-s3-role` 생성(15:45 KST). 원문은 `e3cb5084` 기준이라 ai 정책에 #537 `s3:GetObject`가 이미 들어 있다
- 새 클러스터 `eksctl create cluster`로 Pod Identity 연결 `app/ai-service`·`app/learning-service` 생성(16:18)
- ai·learning을 main prod values(`ASSET_S3_BUCKET` 포함)로 설치
- 관리자 화면에서 테마 초안 1건 요청(초5, 2026-11-16 주, 18:03)

결과:

| 확인 | 결과 |
|---|---|
| 초안 생성 | READY(18:17, 1회 시도) |
| 그림 저장 | 그림 16장이 missions 버킷 `theme-drafts/<초안 ID>/`에 저장됨(18:10:53, PNG 1.1~1.7MiB). 초안 출력 `images`에 S3 키가 연결됨 |
| 사용량 | `THEME_IMAGE` 15건(18:08~18:10) |
| 학생 자산 URL | 채택·미션 5개·테마 게시 뒤 학생 `GET /students/me/weekly-theme`에서 `introImageUrl`·`introVideoUrl`이 서명 URL(유효 3600초)로 내려옴 |
| 서명 URL 열기 | 두 URL에 실제 GET → 206(`image/png`, `video/mp4`) |

- `outroImageUrl`·`outroVideoUrl`은 null이었다. 주 마감 전이라 정상인지는 확인하지 않았다
- 영상(Veo) 저장은 #600에서 따로 확인했다(mp4 2개)

#### app 네임스페이스 기본 거부 (#657)

실행:

- core를 prod values(`namespaceDefaultDeny: true`)로 설치 → `app-default-deny`(podSelector 전체, Ingress·Egress) 생성
- 기본 거부 아래에서 필요한 정책을 함께 적용: migration 정책 3개(chart 렌더링), `app-oneoff-db`, `app-deployment-checks`, `core-demo-alb-ingress`

결과:

| 확인 | 결과 |
|---|---|
| 앱 | 6개 서비스 정상 기동, ALB → core 경로 정상 |
| migration Job | core·learning·report 3개 모두 성공. learning은 첫 실행이 pgvector 권한(DB 권한, 네트워크 아님)으로 실패해 `rds-bootstrap` 뒤 다시 실행 |
| 일회성 DB Pod | `rds-bootstrap`·`demo-db-oneoff` 정상 동작 |
| 정책 없는 Pod | app namespace에 busybox 시험 Pod: 기동 직후 DNS 조회 성공, 약 20초 뒤 같은 조회 실패 → 기본 거부 적용 확인 |

- 기동 직후 허용 구간: VPC CNI 기본(표준) 모드의 NetworkPolicy는 새 Pod에 정책이 적용되기 전까지 짧게 통신을 허용한다. 이번 확인에서 약 20초였다. 정책 없는 임시 Pod도 이 구간에는 통신할 수 있으므로, 기본 거부를 "기동 순간부터 차단"으로 설명하지 않는다
- KEDA는 prod에 설치돼 있지 않아 영향 확인 대상이 아니다. observability·platform은 별도 namespace라 대상이 아니다

## 9.9 서비스별 내부 토큰·브로커 계정 분리 (2026-11-16)

전 서비스가 내부 토큰 1개(`INTERNAL_TOKEN`)와 RabbitMQ 기본 관리자 계정 1개를 공유해 한 Pod 토큰이 새면 모든 서비스의 `/internal/**`를 부르고 모든 큐를 읽기·삭제·발행할 수 있었다(예: report-worker 토큰으로 core 결제 사용 예약). 설계 문서에 분리 요구가 없어 DB 계정 분리(#230)와 같은 기준으로 나눴다. 규칙은 [아키텍처 2.2](../design/architecture.md#22-의존-규칙)·[4.5 Secret](../design/architecture.md#45-cicd), 허용 경로 표는 [API 명세서 4장](../design/api-spec.md#4-내부-api-internal).

### 9.9.1 결정

| 항목 | 결정 | 근거 |
|---|---|---|
| 토큰 단위 | 호출 주체 7개(core·learning·ai·scoring·report-api·report-worker·ops)마다 1개. 보내는 쪽 `INTERNAL_TOKEN`은 그대로 자기 토큰 | 클라이언트(`InternalRestClientFactory`·`internal_client`) 코드 변경 없음. 호출 쌍마다 토큰(14개)은 관리 부담 대비 이득이 작음 |
| 받는 쪽 검사 | 토큰으로 호출자 식별 후 호출자별 경로 허용 목록. 불일치 401, 허용 밖 403 | report-worker는 원래 core 별명 조회를 부르므로 호출자만 확인하면 예시 위험이 남음(사용자 결정: 호출자+경로) |
| 허용 목록 위치 | 받는 쪽 코드 상수(Spring `InternalCallerPolicy`, Python `CALLER_PATHS`) | 권한은 코드 리뷰 대상. 토큰 값만 환경 변수 |
| 같은 토큰 여러 호출자 | 허용 범위 합집합 | 테스트·일회용 검증 스택이 토큰 하나로 동작. 운영 값 중복·16자 미만은 `create-app-secrets.ps1`이 거부 |
| 브로커 계정 | 서비스별 5개(이름 고정), 최소 권한 + `events.topic` 토픽 권한. 관리자는 앱에 미주입 | 큐 삭제·남의 큐 소비·남의 이벤트 키 발행 차단 |
| 재시도 경로 | 기본 exchange → `core.retry`·`learning.retry`·`report.retry` | 기본 exchange 쓰기 권한은 큐 이름만으로 남의 큐에 넣을 수 있어 제거(사용자 결정) |
| core 큐 현황 | core 계정에 `monitoring` 태그 | 관리 API 큐 목록 조회용. 메시지 내용 접근 없음 |

### 9.9.2 남는 위험

- 받는 쪽 Pod가 새면 그 Pod가 받는 호출자 토큰도 노출된다(예: learning Pod에는 core 토큰 포함). 해시 저장은 ESO·compose 값 생성이 복잡해져 이번 범위에서 제외
- kind는 Secret 객체 1개(`app-service-credentials`)에 모든 키가 있고 Pod별로 필요한 키만 `secretKeyRef`로 받는다. Secret 읽기 RBAC가 있으면 전체가 보이는 점은 #230과 같다
- learning은 core에게 `/internal/**` 전체를 연다(관리자·학습 프록시 대부분). core 토큰 유출은 여전히 learning 내부 API 전체 위험

### 9.9.3 적용 절차

- 로컬 `.env`: `.env.example`의 `INTERNAL_TOKEN_*` 6개(+선택 ops)와 `RABBITMQ_<SVC>_PASSWORD` 5개를 채우고 기존 `INTERNAL_TOKEN`은 지운다. compose는 `rabbitmq-init`이 실행될 때마다 계정·비밀번호·권한을 다시 반영한다
- kind: 기존 `platform/platform-data-credentials`·`app/app-service-credentials`는 키가 달라 스크립트가 중단한다. 두 Secret을 지우고 `create-platform-secret.ps1`·`create-app-secrets.ps1`을 다시 실행한 뒤 platform-data(새 init Job)와 앱을 동기화한다
- AWS 데모: Secrets Manager `sagomungchi/demo/app/internal`에 `INTERNAL_TOKEN_<호출자>` 6개, `sagomungchi/demo/platform/rabbitmq`에 `core_password`·`learning_password`·`ai_password`·`scoring_password`·`report_password`를 추가한다(기존 secret 이름이라 ESO IAM 변경 없음). 그 뒤 platform-data → 앱 순서로 재배포한다. 저장소에는 정의만 반영했고 실제 값 생성·재배포는 하지 않았다
- 운영 스크립트(`scripts/knowledge`, `evaluation/runners/judgment_eval.py`)는 `INTERNAL_TOKEN` 환경 변수에 ops 토큰을 넣어 실행한다. kind에서 쓰려면 `.env`에 `INTERNAL_TOKEN_OPS`를 넣고 app Secret을 다시 만든다

## 9.10 실제 LLM 조건 로컬 응답 시간 실측 (#630, 2026-11-16)

1차 부하 시험(9절)은 LLM 스텁 기준이라 실제 LLM 지연이 빠져 있었다. 실제 OpenAI로 화면과 같은 core 경로의 응답 시간을 처음 쟀다. 결과 수치·호출 종류별 토큰·원가 산식은 [ai 19절](ai.md#19-실제-llm-조건-응답-시간원가-산식-630-2026-11-16).

### 9.10.1 환경

| 항목 | 값 |
|---|---|
| 클러스터 | local kind `kind-sagomungchi-local`, develop 배포(006c2476 기준) 그대로 |
| 진입 | `http://127.0.0.1` + Host `api.sagomungchi.local`(ingress-nginx → core), 측정 PC = 클러스터 호스트 |
| ai | 실제 OpenAI(`OPENAI_MODEL=gpt-6-luna`, 테마 검토 `gpt-6.1-terra`), `M2_CROSS_CHECK_ENABLED=true`(시연 조건, #668이 적용), `THEME_VIDEO_ENABLED=false` |
| 동시 사용자 | 1명(요청을 한 건씩 차례로) |
| 시각 | 2026-11-16 10:09~11:28 KST. 판정·분석·리포트 10:09~10:16, 테마 10:18~11:28 |
| 재시작 | 측정 구간 동안 앱 Pod 재시작·교체 없음(15~20초마다 확인). 테마 초안만 ai에 `IMAGE_PROVIDER=fake`를 넣어 재시작한 뒤 재고 측정 뒤 원래 ReplicaSet으로 되돌림 |

### 9.10.2 절차와 표본

`evaluation/load/llm_latency.py`가 요청 시작부터 SSE `done`(리포트는 관리자 작업 `COMPLETED`, 테마는 초안이 `GENERATING`을 벗어날 때)까지를 잰다. 같은 시간대 `llm_usage`는 `llm_usage_window.sql`로 묶는다.

| 흐름 | 경로 | 표본 |
|---|---|---|
| 판정·되묻기 | 학생 `POST /missions/{id}/attempts` → `POST /attempts/{id}/answers` → `POST /answers/{id}/feedback`(SSE). 되묻기가 오면 `followupId`로 답해 다시 판정 | 판정 SSE 30건(그중 LLM 되묻기 20건), 초5 서술 미션 10개 |
| 분석 대화 | 학부모 `POST /conversations` → `POST /conversations/{id}/messages`(SSE) | 20건 |
| 주간 리포트 서술 | 관리자 `POST /reports/{id}/regenerate` → `GET /admin/jobs/{jobId}` | 같은 리포트(시험 계정 `kindqa1` 자녀, 11/09 주) 5회 |
| 테마 초안 글 | 관리자 `POST /admin/theme-drafts`(`G3`·`G4`·`G5`, 2027-01-04 주) → `GET /admin/theme-drafts/{id}` | 3건, 끝난 뒤 버림 처리 |

- 시작 직후 learning이 다른 작업(#668)으로 교체돼 판정 4건(10:02~10:03)을 버리고 처음부터 다시 쟀다
- 테마 G4는 관리자 access 토큰(15분) 만료로 폴링이 끊겨 learning `theme_draft.created_at → updated_at`(36분 27초)으로 보정했다. 스크립트는 401이면 다시 로그인하도록 고쳤다
- 비용: 이번 측정 전체 $0.665(테마 글 $0.644)

### 9.10.3 결과 요약

| 흐름 | 건수 | p50 | p95 | 최대 |
|---|---|---|---|---|
| 판정 SSE(되묻기 없음) | 10 | 5.2초 | 8.9초 | 9.4초 |
| 판정 + 되묻기 SSE | 20 | 7.2초 | 12.5초 | 14.0초 |
| 분석 대화 SSE | 20 | 3.6초 | 8.9초 | 11.8초 |
| 주간 리포트 재생성 | 5 | 13.2초 | 35.3초 | 40.6초 |
| 테마 초안 글 | 3 | 4.8분 | — | 36.4분(`CHECK_FAILED`) |

- 1차 부하 시험 판정 SSE p95(스텁 2.5~4초)와 바로 비교하지 않는다. 동시 사용자 수·환경이 달라 개선율·악화율을 내지 않는다
- 실패 0건(HTTP·SSE `error` 없음). 분석 대화 LLM 호출 33회 중 1회 실패가 있었지만 응답은 정상 종료됐다

### 9.10.4 만든 시험 데이터 (kind에 남김)

| 대상 | 내용 |
|---|---|
| 학부모 `perf6301`(ID·비밀번호, `is_demo=false`) | 자녀 초5 `부하1`·`부하2`·`부하3`, 학생 기기 1대·PIN, 보호자 공유 켬. `prepare_accounts.py`로 만듦 |
| 구독 3건 | 위 자녀 3명 `LOCAL-PLUS` ACTIVE(11/16~12/16, 자동 갱신 없음). 결제 없이 core_db에 직접 넣음(무료 학생은 일반 미션 시작 불가) |
| 관리자 `perf630-admin` | CONTENT·SERVICE_OPS. `scripts/admin_account_sql.py`로 만듦 |
| 학습 기록 | 서술 미션 시도 12개(버린 표본 포함)와 답변·판정·되묻기, 분석 대화 1개(질문 20개) |
| 리포트 | `kindqa1` 자녀 11/09 주 주간 리포트 revision 2~6 |
| 테마 초안 | 2027-01-04 주 G3·G4·G5 초안 3건(`DISCARDED`). 대역 그림은 MinIO `theme-drafts/` 아래 |
| `llm_usage` | 10:02~11:28 KST 실제 호출 약 380건(같은 시간대 다른 세션의 kind 확인 호출이 일부 섞임, 측정분은 시간 구간으로 구분) |

비밀번호·PIN·기기 쿠키는 저장소 밖 파일에만 있다. 정리(관리자 비활성화 `admin_account_sql.py --disable`, 구독 해지, 계정 탈퇴)는 #601 AWS 실측 뒤 함께 정한다.

### 9.10.5 한계와 남은 것

- 로컬 kind·동시 1명이라 NAT·ALB·실제 네트워크 지연과 동시 부하에서의 OpenAI 지연·429는 반영되지 않았다
- AWS 실측은 #601 A 계정 재가동 때 같은 도구(`LOAD_API_BASE`·`LOAD_API_HOST`만 바꿈)로 한다. 동시 사용자를 늘린 실제 LLM 부하는 #384 범위
- 테마 초안은 그림 대역이라 그림 생성 시간(1장 p50 약 34초, 11/12 기록)이 빠졌다

## 9.11 A 계정 재가동 당일 체크리스트 (#601, 2026-11-17 준비)

재가동 전에 AWS 읽기 전용 조회(describe·list·get, `demo_stack.py plan`)만으로 확인한 결과와, 재가동 당일 순서다. 이 절을 쓰면서 AWS 자원을 만들거나 바꾸지 않았다. 계정 번호는 `<계정>`으로 적는다. 모든 명령에 `--profile sagomungchi-provided --region ap-northeast-2`를 붙인다(아래에서는 생략).

### 9.11.1 0단계 점검 결과 (2026-11-17 읽기 전용)

**`demo_stack.py plan`**: OK 40 · DIFF 2 · MISSING 4

| 상태 | 항목 | 비고 |
|---|---|---|
| MISSING | NAT `sagomungchi-demo-nat-2a` | 11/12 삭제(9.5). EIP도 0개 |
| MISSING | IAM `sagomungchi-demo-ai-asset-s3-role`·`learning-asset-s3-role` | #652 역할 2개. 예상대로 MISSING |
| MISSING | EKS `sagomungchi-demo-eks` | 노드그룹·add-on·Pod Identity는 클러스터가 없어 검사 생략 |
| DIFF | private route table 2개의 `0.0.0.0/0` | 지운 NAT를 가리키는 `blackhole`. `apply`는 기존 경로를 바꾸지 않으므로 `replace-route`가 필요 |
| OK | VPC·IGW·subnet·S3 4개·ECR 7개·Secret 12개·RDS SG·subnet group·RDS(stopped)·IAM 10개 | ECR `llm-stub`(스텁 이미지 1개)·관측 Secret 2개는 plan 대상 밖이며 별도로 있음을 확인 |

- 옛 PVC EBS 4개(9.5 표)는 `available`로 남아 있다. 새 PVC로 시작하므로 재가동이 끝나고 필요 없음을 확인한 뒤 지운다.
- ECR에 삭제 전 앱 이미지 digest 5개(ai·core·learning·report·scoring)가 모두 남아 있다. lifecycle policy 없음.

**RDS `sagomungchi-demo-db` 메타데이터 (정지 상태, 시작하지 않음)**

| 항목 | 값 |
|---|---|
| 엔진 | PostgreSQL 17.11, 자동 마이너 업그레이드 켬, 같은 메이저의 상위 마이너 대상 없음, 대기 중 유지보수 없음 |
| 사양 | db.t4g.small(2 GiB), gp3 20 GiB(최대 1,000), Single-AZ 2b, 암호화, 비공개, 삭제 보호 꺼짐, Performance Insights 켬 |
| 백업 | 보존 7일, 백업 창 14:54~15:24 UTC, 유지보수 창 금 13:31~14:01 UTC(금 22:31 KST). 수동 snapshot `sagomungchi-demo-db-pause-20261106-100937` |
| PITR 범위(현재) | 2026-11-06 03:12 ~ 2026-11-13 03:12 UTC. 정지 중이라 최신 시점이 멈춰 있다 |
| 파라미터 그룹 | `default.postgres17`(in-sync). `max_connections = LEAST(DBInstanceClassMemory/9531392, 5000)`, `superuser_reserved_connections=3`, `rds.force_ssl=1` |
| 정지·자동 시작 | 11/13 01:19 UTC 7일 규칙으로 자동 시작 → 03:23 UTC 재정지. **다음 자동 시작은 2026-11-20(금) 12:24 KST 무렵**. 같은 날 22:31 KST가 유지보수 창 |
| 기타 | 11/13 자동 시작 때 관리 마스터 비밀번호가 재설정됨(앱 계정 Secret과 무관, bootstrap을 다시 하지 않으므로 영향 없음) |

`max_connections` 계산: 2 GiB 전체로 계산하면 2,147,483,648 / 9,531,392 ≈ 225가 상한이고, `DBInstanceClassMemory`는 OS·RDS 예약분을 뺀 값이라 실제 값은 그보다 작다. 재가동 뒤 `SHOW max_connections;`로 확정한다. 앱이 쓸 수 있는 수는 여기서 superuser 예약 3과 `rds_superuser` 예약 2를 더 뺀 값이다.

DB 안의 내용(레지스트리 행, 활성 모델·프롬프트, 적용된 migration 번호)은 클러스터가 없어 보지 못했다. 재가동 4단계에서 확인한다.

**삭제 전 Helm values(저장소 밖 백업)와 현재 develop prod values 차이**

| release | 차이 |
|---|---|
| ESO·LB Controller·Karpenter·platform-data | values 차이 0. 단 platform-data chart는 서비스별 브로커 계정 init을 새로 가짐(9.9) |
| observability | 경보 규칙 `uid`·`title` 추가, `rabbitmqDlqMetrics`, Tempo(PVC 2Gi) 추가 |
| core | 내부 토큰·브로커 계정 서비스별 키(9.9), `SCORING_URL`·scoring egress, `namespaceDefaultDeny` false → **true**(#657), report-api ingress 제외 |
| learning | 서비스별 키, `ASSET_S3_BUCKET`·`S3_REGION`·`AWS_REGION`(#652), `MEMORY_EMBEDDING_ENABLED`·`MEMORY_QUERY_REWRITE_*`, Pod Identity agent egress |
| ai | 서비스별 키, 자산 버킷, Veo(`THEME_VIDEO_*`·`ai-theme-video` Secret·볼륨), `M2_CROSS_CHECK_ENABLED=true`, `EXPLANATION_BASE_URL`(sllm-server), `OPENAI_MODEL` gpt-6.1-terra → gpt-6-luna, 메모리 상한 512Mi → 1Gi, 리포트 Gemma RunPod 주소·키(`ai-provider-credentials`, #751) |
| report-worker | 서비스별 키, 설명 시간 예산 400초·제한 130초, 테마 요약, 종료 유예 180 → 480초 |
| report-api·scoring | 서비스별 키, scoring ingress에 core 추가 |
| 이미지 | 앱 values의 `image`는 저장소에 없음(cd-release가 main SHA digest로 채움). migration 이미지는 `migrations/*.json`에 core·learning `main-c6809ddb65ee`, report `b67d8a462b6b`로 고정 |

**"옛 values로 복구 → 최신 main으로 업그레이드"에서 막히는 곳**

1. **옛 앱 values가 지금 ESO 매니페스트로는 뜨지 않는다.** 옛 values는 `internal-service-credentials/INTERNAL_TOKEN`, `rabbitmq-credentials/RABBITMQ_URL`·`RABBITMQ_USERNAME`·`RABBITMQ_PASSWORD`를 참조한다. 지금 `external-secret-resources.json`은 서비스별 키(`INTERNAL_TOKEN_CORE`…, `RABBITMQ_<SVC>_PASSWORD`·`_URL`)만 만들어서 앱 6개 모두 `CreateContainerConfigError`가 난다. Secrets Manager에는 옛 키(`INTERNAL_TOKEN`, `username`·`password`)가 남아 있으므로, 옛 앱을 올리려면 app 네임스페이스 ExternalSecret을 `e8b89000` 시점 파일로 적용해야 한다. 그 뒤 최신 파일로 바꾸면 옛 키가 Secret에서 빠진다.
2. **migration 이미지가 main SHA로 자동 빌드되지 않는다.** cd-release는 앱 이미지만 게시하고 migration을 실행하지 않는다(`databaseAction`은 `none`만 허용). 11/6 이후 develop에 core V29~V51·learning V11~V21·report 3개 revision이 들어왔으므로, 새 main SHA로 core-migrate·learning-migrate 이미지를 빌드·푸시하고 `migrations/*.json` digest·revision을 바꿔 **앱 배포 전에** Job으로 적용해야 한다. report는 cd-release가 게시한 report-service 이미지 digest로 바꾼다.
3. **#657 기본 거부**: core를 새 values로 올리는 순간 정책 없는 Pod는 DNS부터 막힌다. migration NetworkPolicy, `app-oneoff-db-network.json`·`app-check-pods-network.json`을 같이 적용해야 한다. #384 LLM 스텁으로 바꿀 때 ai egress에 `llm-stub:8080`이 없으므로 임시 values에 `networkPolicy.egressToApps`를 더해야 한다.
4. **IAM 순서**: `cluster.json`의 Pod Identity 10개 중 자산 역할 2개는 역할이 있어야 연결된다. `apply`(역할 생성)를 `eksctl create` 전에 한다. #537이 ai 역할 정책에 `GetObject`를 더하면, 그 전에 만든 역할은 `plan`에서 DIFF가 되고 `apply`는 기존 역할을 고치지 않으므로 `put-role-policy`가 필요하다.
5. **설명 sLLM 미배포**: prod ai는 `EXPLANATION_BASE_URL`이 sllm-server를 가리키지만 #476은 이번 범위 밖이다. 주간 리포트 설명 단계가 연결 실패·시간 초과로 끝나는지, 리포트 본문은 정상인지 확인하고 #630 리포트 시간에 이 상태를 같이 적는다.

**결정됨(2026-11-17)**: DB는 11/6 이후 바뀌지 않았고 옛 이미지로 확인할 것이 없으므로 **앱은 옛 values 단계를 건너뛰고** 플랫폼(차이 0)만 보관 values로 올린 뒤, 새 main SHA로 migration → cd-release 배포한다. #537 병합 전에 재가동해야 하면 그때만 1번 방식(옛 ExternalSecret)을 쓴다.

migration 이미지는 cd-release에 migration 단계가 들어가면(별도 작업, 브랜치 `feature/cd-release-migrations` 예정) 그 단계로 빌드·적용하고, 재가동 전에 들어가지 못하면 2번처럼 수동으로 빌드한다.

### 9.11.2 #384 준비

**연결 수 (HPA 최대 기준)**

| 대상 | DB 사용 | 최대 Pod | Pod당 풀 | 최대 연결 |
|---|---|---|---|---|
| core | core_db, Hikari 기본 10(설정 없음) | 3(HPA) | 10 | 30 |
| learning | learning_db, Hikari 기본 10 | 3(HPA) | 10 | 30 |
| ai | **DB 연결 없음** | 3(HPA) | 0 | 0 |
| report-api | report_db, SQLAlchemy 기본(5 + overflow 10) | 1 | 15 | 15 |
| report-worker | 〃 | 1 | 15 | 15 |
| scoring | DB 연결 없음 | 1 | 0 | 0 |
| 합계 | | | | **90** |

rolling update 중 core·learning이 1개씩 더 뜨면 +20, migration·일회용 Pod 몇 개를 더해도 약 115로, `max_connections`(최대 225에서 예약분을 뺀 값) 안에 든다. 풀 크기를 바꾸지 않는다. 다만 1차 시험의 한계는 연결 수가 아니라 RDS CPU(300명 68%)였고, 연결 100개 안팎이면 2 GiB 인스턴스의 메모리를 차지하므로 시험 중 CloudWatch `FreeableMemory`·`DatabaseConnections`를 같이 본다. 재가동 뒤 실제 `max_connections`가 120 아래로 나오면 이 판단을 다시 한다.

**시험 계정**: `prepare_accounts.py`로 4개(자녀 3명·초5). 같은 IP 10분 5회 가입 한도 때문에 `--wait`로 약 10분.

```powershell
python evaluation/load/prepare_accounts.py --base-url https://d3jf0rnm6vhd9v.cloudfront.net --count 4 --prefix load2 --wait --secrets 'C:\Users\kds20\sagomungchi-load\secrets-384.json'
```

분석 시나리오에 쓸 시험 구독은 `infrastructure/aws/add-demo-test-subscription.sql`을 demo-db-oneoff Pod로 넣고 시험 뒤 같은 파일의 원복 SQL로 해지한다(승인 지점).

**LLM 스텁 (1차 #361 방식)**: ECR `sagomungchi/llm-stub@sha256:603dc658…`(11/05)이 남아 있다.
1. `kubectl apply -f evaluation/load/llm-stub.k8s.yaml` → Ready 확인
2. ai를 임시 values로 올린다: `OPENAI_BASE_URL=http://llm-stub.app.svc.cluster.local:8080/v1`, `networkPolicy.egressToApps`에 `{name: llm-stub, port: 8080}` 추가. `helm template`로 env·정책을 먼저 확인
3. 원복: ai를 prod values로 다시 올리고(ReplicaSet 해시가 helm 상태와 같은지), 스텁을 같은 파일로 `delete`

**k6 시나리오**: `core-load.js`·`run-stage.ps1`·`collect_metrics.py`는 재사용한다. 1차와 달리 HPA·Karpenter 관측이 필요하므로 단계마다 아래를 결과 폴더에 같이 남긴다(새 도구는 만들지 않음).

```powershell
kubectl get hpa -n app -w                          # 별도 창, 확장 시점
kubectl get nodeclaims,nodes -L karpenter.sh/nodepool -w   # 별도 창, 노드 생성·삭제 시점
```

단계는 1차와 같은 10 → 50 → 100 → 200 → 300 VU(한 번 약 6분), 부하 종료 뒤 축소(HPA 5분 + consolidateAfter 5분)를 15분 지켜본다.

**팀 공지 문구(초안)**

> [AWS 데모 부하 시험 안내] ○월 ○일 ○○:○○~○○:○○(약 2시간) AWS 데모에서 확장 부하 시험(#384)을 합니다. 이 시간에는 AI 답변이 시험용 문장으로 바뀌고 응답이 느리거나 실패할 수 있으니 데모 주소로 시연·확인하지 말아 주세요. 끝나면 이 스레드에 알리겠습니다.

### 9.11.3 #629 PITR 복구 시험 준비

조건: 재가동 뒤 앱 쓰기가 1시간 이상 이어진 다음 한다. 복원 시점 T는 "지금 − 1시간"으로 정하되, **T 이전 표지 A**(시험 계정의 답변 1건)와 **T 이후 표지 B**(답변 1건)를 미리 만들어 둔다. 복원본에 A는 있고 B는 없어야 한다.

```powershell
# 1. 요청 직전: 최신 복원 가능 시점(RPO 기준)과 요청 시각 기록
aws rds describe-db-instances --db-instance-identifier sagomungchi-demo-db --query 'DBInstances[0].LatestRestorableTime'
# 2. 복원 (승인 지점: 새 인스턴스 비용 발생)
aws rds restore-db-instance-to-point-in-time --source-db-instance-identifier sagomungchi-demo-db `
  --target-db-instance-identifier sagomungchi-demo-db-pitr-629 --restore-time <T, UTC ISO> `
  --db-instance-class db.t4g.small --db-subnet-group-name sagomungchi-demo-db-subnet-group `
  --vpc-security-group-ids <sagomungchi-demo-rds-sg ID> --no-publicly-accessible --no-multi-az `
  --no-deletion-protection --tags Key=purpose,Value=pitr-test-629
aws rds wait db-instance-available --db-instance-identifier sagomungchi-demo-db-pitr-629
aws rds describe-events --source-type db-instance --source-identifier sagomungchi-demo-db-pitr-629 --duration 120
```

**정합성 확인**: 원본과 복원본에 같은 쿼리를 돌려 비교한다. 각 DB의 앱 계정(이미 있는 `core-db-credentials`·`learning-db-credentials`·`report-db-credentials`)으로 접속하고, demo-db-oneoff Pod의 `PGHOST`만 복원본 주소로 바꾼다. 원본은 T 이후에도 쓰이므로 T 이전 행만 비교한다.

```sql
-- learning_db: 원본 답변
select count(*), md5(string_agg(id::text || ':' || version, ',' order by id)) from answer where submitted_at <= :'t';
select j.process_status, count(*) from judgment j join answer a on a.id = j.answer_id where a.submitted_at <= :'t' group by 1;
-- core_db: 분석 대화 근거 연결 · 결제 상태
select count(*), md5(string_agg(e.answer_id::text || ':' || e.answer_version, ',' order by e.id))
  from message_evidence e join conversation_message m on m.id = e.message_id where m.created_at <= :'t';
select status, entitlement_status, count(*) from payment where updated_at <= :'t' group by 1, 2;
select status, count(*) from subscription where updated_at <= :'t' group by 1;
-- report_db: 리포트 근거 연결
select count(*), md5(string_agg(e.answer_id::text || ':' || e.answer_version, ',' order by e.id))
  from report_item_evidence e join report_item i on i.id = e.item_id join weekly_report r on r.id = i.report_id where r.created_at <= :'t';
```

- 복원본 안에서 근거가 가리키는 답변이 learning_db에 있는지: core·report에서 `select distinct answer_id`를 뽑아 learning_db `answer`와 대조한다(DB가 나뉘어 있어 한 쿼리로는 못 함). 없는 수가 0이어야 한다.
- T 무렵 진행 중이던 판정은 원본에서 상태가 바뀌었을 수 있으므로 `process_status` 차이는 건수와 이유를 따로 적는다.
- 기록: 요청 시각 → `available` 시각 → 확인 끝 시각(RTO 4시간 비교), 요청 시각 − `LatestRestorableTime`(RPO 5분 비교), 복원본 크기·비용 시간. 결과는 4.1 표를 갱신한다.

```powershell
# 3. 삭제 (승인 지점: 식별자가 -pitr-629인지 다시 확인. 원본에 절대 쓰지 않음)
aws rds delete-db-instance --db-instance-identifier sagomungchi-demo-db-pitr-629 --skip-final-snapshot --delete-automated-backups
aws rds wait db-instance-deleted --db-instance-identifier sagomungchi-demo-db-pitr-629
```

### 9.11.4 #630·#613·#493 당일 절차

**#630 AWS 실측**: 9.10과 같은 도구·표본(판정 30·되묻기 20·분석 20·리포트 5·테마 3)으로, 진입 주소만 바꾼다. #384 부하가 없는 시간대에 실제 OpenAI로 하고 #384 결과를 본 뒤 표본을 조정한다.

```powershell
$env:LOAD_API_BASE = 'https://d3jf0rnm6vhd9v.cloudfront.net/api/v1'
$env:LOAD_API_HOST = 'd3jf0rnm6vhd9v.cloudfront.net'
$env:LOAD_ORIGIN   = 'https://d3jf0rnm6vhd9v.cloudfront.net'
python evaluation/load/llm_latency.py judge --secrets <밖>/secrets-630.json --out <밖>/aws-630.jsonl --judgments 20 --followups 20
```

`llm_usage_window.sql`은 core_db에서 돌린다. AWS에는 psql 접속 경로가 demo-db-oneoff Pod뿐이므로, 파일 앞에 `\set from '''<시작 UTC>'''`·`\set to '''<끝 UTC>'''`를 붙인 사본을 ConfigMap으로 넣어 실행한다. 관리자 계정(리포트·테마)과 프리미엄 구독 자녀는 #384와 같은 승인 절차로 만든다.

**#613 모델 새 버전 등록 (운영 관리자 화면, SERVICE_OPS)**
1. 선행: scoring·ai가 새 main 이미지인지(#588 이후) 확인
2. `GET /admin/model-versions?kind=MODEL`로 현재 행·`artifactUri`·revision 기록(복귀 기준)
3. 사전 검사 `POST /admin/models/preflight`: `artifactUri`는 `models/m2-klue-essay/3.1-1112b/`·`models/m2-klue-narrative/3.0-1112b/`, 파일 6개 해시는 `metadata/1112b` manifest 값 → `PASS` 확인
4. 등록: `(kind,name,version)`이 UNIQUE이고 이미 활성화된 버전은 다시 활성화할 수 없으므로(409) **새 버전 문자열** `3.1-1112b`·`3.0-1112b`로 등록
5. 승인·활성화: 논술 scope는 초5·초6(11/17 결정), 서술은 기존 scope 그대로
6. scoring `/internal/versions`에서 새 revision 로딩, 서술·논술 요청 1건씩 새 경계 확인. 복귀는 `rollback`으로 이전 버전

**#493 확인**: 위 3번 사전 검사가 실제 scoring Pod 자격 증명(Pod Identity)으로 활성 경로 `3.1/`·`3.0/`과 새 경로 둘 다 `PASS`이면 남은 AWS 항목이 끝난다. `CHECKSUM_UNAVAILABLE`이 나오면 해당 객체를 `put-object --checksum-sha256` 단일 PUT으로 다시 올린다.

### 9.11.5 당일 순서

예상 시간은 처음 실행하는 절차의 추정이다. 실제 시간을 옆에 적는다. ★는 실행 전 동섭 님 승인 지점이다.

| # | 단계 | 명령·방법 | 확인 | 예상 |
|---|---|---|---|---|
| 0 | 선행(전날까지) | #537 병합 → develop→main 병합 SHA 확정. migration 이미지: cd-release에 migration 단계가 들어가면 그것으로, 아니면 새 main으로 core-migrate·learning-migrate 이미지 수동 빌드·ECR 푸시 후 `migrations/*.json` digest·revision PR. 팀 공지 | main SHA·digest 3개 기록 | — |
| 1 | 읽기 점검 | `demo_stack.py plan` | 9.11.1과 같은지(MISSING 4, DIFF 2) | 2분 |
| 2★ | NAT·IAM 생성 | `demo_stack.py apply --confirm-account <계정>` → `aws ec2 replace-route --route-table-id <private 2개> --destination-cidr-block 0.0.0.0/0 --nat-gateway-id <새 NAT>` | `plan`에서 nat·route·IAM 2개 OK(EKS만 MISSING) | 10분 |
| 3★ | RDS 시작 | `aws rds start-db-instance` → `wait db-instance-available` | endpoint·`rds.force_ssl`·백업 7일. 11/20 자동 시작 뒤라면 이미 available | 10분 |
| 4★ | 클러스터 | `render-eksctl --operator-cidr <IP>/32 --out <밖>` → `eksctl create cluster -f <파일>` | 노드그룹 2개(2a·2b 1대씩 platform), add-on 7개, Pod Identity 10개, access entry가 백업(`access-entries.json`)과 같은 권한 | 30~40분 |
| 5★ | RDS SG | `apply --after-eksctl` → 옛 SG `sg-086c7c83b3638da59` 규칙·SG 정리 | 새 SG에서 5432 허용 | 5분 |
| 6 | 플랫폼 | gp3·namespace·ESO 2.14.0·LB Controller 1.14.1·`rds-ca`·ExternalSecret(현재 파일)·platform-data·Karpenter 1.15.1 + NodePool·EC2NodeClass(`karpenter.json` 대조) | ESO Ready, Secret 키가 서비스별 키, `ai-provider-credentials`에 `OPENAI_API_KEY`·`SAGOMUNGCHI_SLLM_SERVERLESS_GEMMA`·`SAGOMUNGCHI_SLLM_SERVERLESS_KEY_GEMMA` 3개(값 미출력), RabbitMQ 서비스별 계정 5개, NodePool limits CPU 4·16Gi | 30분 |
| 7 | DB 상태 | demo-db-oneoff(core 앱 계정)로 `SHOW max_connections`, `model_version` 행·활성 상태 조회. 앱 계정은 migration 이력 테이블 권한이 없으므로 적용 번호는 8단계 Job 로그로 본다 | 9.11.2 연결 판단, #613 등록 전 기준 | 10분 |
| 8★ | migration | 기본 거부용 정책 2개 → core·learning·report migration Job(9.11.1 2·3번). cd-release에 migration 단계가 들어갔으면 그 단계로 실행 | Job complete, 로그의 시작·끝 schema 버전(Flyway)·revision(Alembic) | 15분 |
| 9★ | 앱 배포 | cd-release(plan JSON, 승인 2명), 6개 서비스 | 앱 readiness, `app-default-deny` 1개, 정책 없는 Pod DNS 실패 | 30~40분 |
| 10 | 관측 | Secrets Manager 백업으로 관측 Secret 2개 생성(값 미출력) → observability | Grafana 로그인·datasource·경보 평가 | 15분 |
| 11★ | 진입 | `core-alb-network.json` + Ingress(origin 헤더 Git 밖 주입) → 새 ALB DNS로 CloudFront `/api/*` origin 변경 | prefix list 제한, CloudFront 배포 완료 | 20분 |
| 12 | 흐름 확인 | 로그인 → 학습 제출 → 리포트 조회, 테마 초안 1건(자산 버킷·Veo, #652·#600), 설명 단계 상태, 리포트 AI 요약(RunPod Gemma, 503이면 6단계 Secret 키 확인) | 걸린 시간·실패 항목을 #601에 기록 | 20분 |
| 13 | #613·#493 | 9.11.4 | 사전 검사 PASS, 새 revision | 30분 |
| 14★ | #384 | 공지 → 계정 4개 → 스텁 → 단계별 k6 → 축소 관찰 → 원복 | Karpenter 노드 0대로 끝남 | 2~3시간 |
| 15 | #630 | 9.11.4(실제 LLM, 부하 없는 시간) | 표본·비용 기록 | 1.5시간 |
| 16★ | #629 | 9.11.3(재가동 1시간 뒤부터 가능) | A 있음·B 없음, RPO·RTO | 1시간 |
| 17★ | 내리기 | 시험 데이터 정리 범위 확인 → `demo_stack.py pause --execute` 또는 클러스터·NAT 삭제(9.5 방식) | RDS stopped, 실행 중 EC2 0대, 정지 시각과 7일 뒤 자동 시작 기록 | 1시간 |

0~12는 한 번에 약 4시간이다. 13~16은 하루 안에 모두 끝내지 않아도 되지만, 켜 둔 동안 고정비(EKS·NAT·노드 4대·RDS)가 쌓이므로 이틀을 넘기지 않는다.

## 9.12 RDS PITR 복구 시험 (#629, 2026-11-18)

NFR-DAT-05(RPO 5분·RTO 4시간, 복구 시험 기록)를 A 계정 운영 RDS에서 처음 실행했다. 원본 `sagomungchi-demo-db`는 수정·재시작하지 않았고, 새 인스턴스로 복원해 확인한 뒤 바로 삭제했다. 절차는 9.11.3을 따랐다.

### 9.12.1 조건

| 항목 | 값 |
|---|---|
| 복원 시점 T | 2026-11-18 09:30:00 KST(00:30:00 UTC). 재가동(11/17 15:43) 뒤 17시간이 지난 시점이고, #384 부하 시험 시작(첫 시험 계정 가입 09:37:26) 전이다 |
| 표지 A(T 이전) | learning `answer` 1건(11/17 18:29:49 KST 제출, ID 앞 8자리 `429717b2`) |
| 표지 B(T 이후) | core `user_account`의 #384 시험 계정 10개(`load2` 접두사, 09:37:26~09:48:03 KST 가입) |
| 복원본 | `sagomungchi-demo-db-pitr629`, db.t4g.micro(가장 작은 사양), 원본과 같은 서브넷 그룹·RDS SG, 비공개, Single-AZ(2b), 태그 `purpose=pitr-test-629` |
| 확인 방법 | 클러스터 안 임시 Pod(`demo-db-oneoff` 정책 라벨, 앱 계정 Secret·RDS CA 사용)로 원본과 복원본에 같은 SQL을 실행. 건수·md5·짧은 ID만 출력하고 학생 원문·개인정보는 출력하지 않음. Pod·ConfigMap은 실행 직후 삭제 |

### 9.12.2 시간 기록 (KST)

| 시각 | 단계 |
|---|---|
| 09:46:14 | 요청 직전 원본 `LatestRestorableTime` |
| 09:51:37 | `restore-db-instance-to-point-in-time` 요청 |
| 09:54:20 | 인스턴스 생성 시각(`InstanceCreateTime`) |
| 09:58:31 | RDS 이벤트 "Restored from DB instance sagomungchi-demo-db to 2026-11-18 00:30:00.0" |
| 09:59:07 | 재시작 |
| 10:01:00~10:09:43 | 복원본 첫 자동 백업(보존 기간 7일을 원본에서 이어받음) |
| 10:10:45 | `available`(30초 간격 조회라 ±30초) |
| 10:11:08 | 표지·행 수·스키마 대조 끝 |
| 10:11:15 | 삭제 요청(`--skip-final-snapshot --delete-automated-backups`) |
| 10:12:50 | 삭제 완료(`wait db-instance-deleted`, 이후 `DBInstanceNotFound`) |
| 10:15:12 | 복원본 자동 스냅샷 `rds:sagomungchi-demo-db-pitr629-…`이 사라짐(삭제 뒤 약 2분 남아 있었음). 남은 자동 백업은 원본 것 1개, `purpose=pitr-test-629` 태그 자원 0개, RDS SG 규칙 변경 없음, 임시 Pod·ConfigMap 0개 |

- **RTO**: 요청→`available` **19분 8초**, 요청→확인 끝 19분 31초. 목표 4시간 안이다. 이 중 약 9분은 복원본 첫 자동 백업이라, 데이터 복원 자체는 요청 뒤 약 7분(09:58:31 이벤트)에 끝났다
- **RPO**: 요청 시각 − `LatestRestorableTime` = **5분 23초**. 같은 날 09:49:51에 본 값은 3분 37초였다. RDS는 트랜잭션 로그를 약 5분마다 올리므로 이 간격은 0~5분대에서 오르내리고, 이번 측정은 목표 5분을 23초 넘었다(9.12.4)

### 9.12.3 대조 결과

| 대상 | 원본(T 이전으로 거름) | 복원본 | 판정 |
|---|---|---|---|
| 표지 A 답변 | 1 | 1 | 있음 |
| 표지 B 시험 계정 | 10(전체) | 0 | 없음 |
| 계정(T 이전 / 전체) | 6 / 16 | 6 / 6 | 같음 |
| 학생 | 36 | 6 | T 이후 생긴 30명 없음 |
| 답변(T 이전) 건수·md5(`id:version`) | 2,814 · 같음 | 2,814 · 같음 | 같음 |
| 판정 상태(T 이전 답변) | DONE 2,812·PENDING 2 | 같음 | 같음 |
| 시도·판정·미션·테마 초안 | 2,812 · 2,814 · 25 · 8 | 같음 | 같음 |
| 분석 대화 메시지·`llm_usage`(T 이전) | 562 · 7,410 | 같음 | 같음 |
| 구독(T 이전 상태별) | ACTIVE 1·CANCELED 1 | 같음 | 같음 |
| 주간 리포트·항목 | 5 · 25 | 같음 | 같음 |
| 근거 연결(core `message_evidence`, report `report_item_evidence`)·결제 `payment` | 0 · 0 · 0 | 0 · 0 · 0 | 행 없음(9.12.4) |
| 근거가 가리키는 답변 중 learning에 없는 수 | 0/0 | 0/0 | 행 없음 |
| 스키마 | core V51 있음·V52 없음, learning V21 있음, report `20261110_08` 제약 있음 | 같음 | 같음 |
| 열 지문(`information_schema.columns` md5) | core 535·learning 352·report 66열 | 세 DB 모두 같음 | 같음 |

- T 직전 가장 가까운 쓰기는 테마 초안(09:01:52), T 직후 가장 가까운 쓰기는 시험 계정 가입(09:37:26)이다. 경계 정밀도는 이 36분 안에서만 확인했다
- 앱 계정은 `flyway_schema_history`·`alembic_version` 읽기 권한이 없어(permission denied) Flyway·Alembic 버전 번호는 직접 읽지 못했다. 마지막으로 적용된 migration이 만든 열·제약과 열 지문으로 대신했다

### 9.12.4 한계와 남은 것

- **RPO 5분 경계**: 측정 1회에서 5분 23초였다. PITR만으로는 "최대 약 5분 + 업로드 지연"이 실제 값이라, NFR-DAT-05의 RPO 5분을 지키려면 목표를 "약 5분(로그 업로드 주기)"으로 적거나 별도 수단(읽기 복제본 등)이 필요하다. 설계 문구 변경은 담당자 결정 사항이라 이번에 바꾸지 않았다
- **근거 연결·결제 정합성**: AWS 데모 DB에 `message_evidence`·`report_item_evidence`·`payment` 행이 0건이라 대조 쿼리는 실행됐지만 실데이터로 확인한 것은 아니다. PG 상태 별도 대조도 결제가 없어 하지 않았다
- **RTO 범위**: 데이터가 작다(답변 2,814건, gp3 20 GiB). 앱 Secret의 DB 주소를 복원본으로 바꾸고 재배포하는 전환 시간은 재지 않았다
- 복원본은 가장 작은 사양(t4g.micro)이라 원본(t4g.small)과 사양이 다르다.

## 9.13 리포트 Gemma CPU·GPU 서빙 비교와 S3 반입 (#743·#745, 2026-11-18)

에픽 #742에서 리포트 Gemma(26B-A4B QAT + LoRA r16)를 RunPod에서 클러스터 안 `sllm-server`로 옮기기로 했다. 그 전에 CPU와 GPU를 AWS A 계정의 임시 EC2에서 같은 입력으로 쟀다. 수치 원본은 [`ml/sllm/results/serving-compare-20261118.json`](../../ml/sllm/results/serving-compare-20261118.json)에 있고, 측정 스크립트는 [`ml/sllm/scripts/serving/`](../../ml/sllm/scripts/serving/)에 있다.

### 9.13.1 결정 (2026-11-18 팀 방향)

**SageMaker 실시간 엔드포인트(GPU) + 0대 축소**로 간다. 아래 측정에서는 CPU가 변경량이 가장 적었다. 그래도 GPU 생성 속도(상세 1건 약 16초)를 쓰면서, 노드·드라이버·이미지를 EKS 안에서 직접 관리하지 않는 쪽을 골랐다. 실제로 되는지는 새 이슈에서 검증한다.

| 항목 | 내용 |
|---|---|
| 위치 | 같은 AWS 계정의 SageMaker 엔드포인트(VPC 안). 학생 글이 AWS 밖으로 나가지 않는 원칙(#473)을 유지한다. 클러스터 밖이라 architecture 7장 "클러스터 안 GPU 두지 않음"(#725)은 바꾸지 않아도 된다. 대신 4.4의 `sllm-server`(클러스터 안 llama.cpp) 구조는 바뀐다(#744) |
| 모델 | S3 `base-awq/` + `adapter/`(9.13.6) 그대로. vLLM 계열 컨테이너(SageMaker LMI)에 LoRA를 붙인다 |
| 할당량 (2026-11-18 조회) | 서울 `ml.g6.xlarge for endpoint usage` 2, `ml.g5.xlarge` 4, `ml.g6e.xlarge` 2. 증설 요청은 필요 없다 |
| 요금 (서울, 시간당) | `ml.g6.xlarge` $1.385(같은 EC2 $0.990보다 약 40% 비쌈), `ml.g5.xlarge` $1.732, `ml.g6e.xlarge` $3.200. 창(130분) 기준 월 약 $13(`ml.g6.xlarge`) |
| 콜드 스타트 | 0대에서 깨어나면 인스턴스 준비 + 모델 17GB 적재(EC2 실측 기동 224초 + 이미지)로 몇 분 걸린다. RunPod의 191~315초 문제가 그대로 남으므로, 창 시작 전 예약 확장으로 1대를 미리 켜는 방식을 검증한다 |
| 확인할 것 | Gemma 4를 지원하는 LMI·vLLM 버전, `ml.g6.xlarge`(L4, 호스트 16GiB)에서 9.13.5의 메모리 옵션이 그대로 통하는지(안 되면 `ml.g6e.xlarge`), 실제 콜드 시간, GPU 재고 부족 때의 동작, ai 호출 방식(`InvokeEndpoint`·SigV4) |
| 하위 이슈 영향 | #744 문서(4.4·7장 결정 줄), #745 레지스트리 등록과 쓰지 않을 `base-gguf/`·`adapter-gguf/` 정리, #746 범위를 EKS NodePool에서 SageMaker 엔드포인트·예약 확장·IAM으로 변경, #747 ai 클라이언트를 RunPod에서 SageMaker로 변경 |

### 9.13.2 측정 기준 검토안 (참고, 채택하지 않음)

| 항목 | 검토안 |
|---|---|
| CPU/GPU | CPU. GPU(g6.xlarge)는 배치 창이 커지거나 1건 지연이 중요해질 때 쓰는 대안으로 둔다 |
| 인스턴스 | `c7i.4xlarge`(16 vCPU, 32GiB), On-Demand. 지금 NodePool `explanation-cpu`의 `c7i·c6i.xlarge`(8GiB)에는 모델이 올라가지 않는다 |
| 서버·모델 형식 | 지금 구조인 llama.cpp `llama-server`를 유지한다. 기반 모델은 Google 공식 QAT Q4_0 GGUF, LoRA는 `convert_lora_to_gguf.py`로 바꾼 GGUF(`--lora`)다. `--jinja --reasoning off`가 꼭 있어야 한다 |
| 자원 요청 | `--threads 16 --parallel 2`, `-c 16384`(요청당 8192). 측정 RSS는 28GiB(mmap 포함)이고, 실제 사용량은 15GiB였다. Pod 메모리 요청은 약 20Gi, 한도는 노드가 허용하는 만큼 둔다. 정확한 값은 #746에서 정한다 |
| 가동 창 | KEDA cron 일 23:50~월 02:00(130분)을 그대로 둔다. 30명 배치가 약 70~75분 걸린다 |
| architecture 7장 | CPU로 가면 "클러스터 안 GPU 두지 않음"(#725)을 바꿀 필요가 없다. GPU를 고르면 개정해야 한다 |

측정만 놓고 본 기준(①12/7 준비 가능 ②배치 창 안 완료 ③비용 ④변경량)별 근거는 다음과 같다.

- ① CPU는 기존 `sllm-server` 구조(llama.cpp, S3 initContainer, KEDA cron, 전용 NodePool)를 그대로 쓰고, 인스턴스·자원·모델 키만 바꾸면 된다. GPU는 GPU NodePool·NVIDIA AMI·device plugin, 36GB vLLM 이미지, L4에 맞춘 vLLM 옵션(아래 9.13.4)이 새로 필요하고, 서울 G 계열 On-Demand 용량도 확보해야 한다
- ② CPU는 30명에 약 70~75분으로 창(130분) 안에 들어온다. 학생이 50명을 넘으면 창이 모자라므로 그때 GPU로 간다. GPU는 30명에 10~15분이다
- ③ 창 기준 월 컴퓨팅 비용은 CPU 약 $7.6, GPU 약 $9.3이다. 둘 다 작아서 결정 요인은 아니다
- ④ CPU의 단점은 모델 파일 형식이 RunPod에서 검증한 AWQ와 다르다는 점이다. 그래도 같은 QAT 체크포인트의 공식 Q4_0이고, LoRA는 QAT 16비트 원본으로 학습했다. 가상 글 3건씩은 `checks.py`를 모두 통과했다. 출력 품질이 AWQ와 같은지는 학습 담당(kim-4480)의 확인이 필요하다

### 9.13.3 측정 조건

| 항목 | 값 |
|---|---|
| 입력 | ai-service 실제 프롬프트(`report@2` 서술, `report-explanation@3` 상세)에 가상 데이터만 넣음(`gen_prompts.py`). 서술 1,137토큰·최대 2,048, 상세 1,360토큰·최대 4,096, `json_schema` strict, temperature 0 |
| 자원 | 임시 VPC(기존 EKS VPC 밖)의 퍼블릭 서브넷, EC2 2대(SSH는 측정 PC IP만 허용), S3 `explanation/*`만 쓸 수 있는 임시 IAM 역할 |
| 시각 | 2026-11-18 09:52~11:10 KST |
| GPU | g6.xlarge(L4), DLAMI Ubuntu 24.04, vLLM 0.34.0. LoRA는 `explain` 이름으로 붙임 |
| CPU | c7i.4xlarge(Xeon 8488C, AVX-512·AMX), llama.cpp 52975342 직접 빌드 |
| 기동 시간 | 페이지 캐시를 비운 뒤 서버 시작부터 `/health` 200까지 |

### 9.13.4 결과

| 항목 | CPU c7i.4xlarge | GPU g6.xlarge |
|---|---|---|
| 시간당 요금 | $0.806 | $0.990 |
| 서버 기동(모델 적재 포함) | 53초 | 224초(가중치 54초 + torch.compile 48초 + CUDA graph 등). 컴파일 캐시가 있으면 148초(업로드와 겹쳐 잰 값) |
| 그 밖의 콜드 요소 | 모델 14.4GB 받기(HF에서 35초) | vLLM 이미지 36.3GB pull 133초, 모델 17.2GB 받기(HF에서 72초) |
| 메모리 | RSS 28GiB(mmap 포함), 사용 15GiB | VRAM 20.3GiB / 22.0GiB, 호스트 8GiB |
| 생성 속도(1건, LoRA) | 18.4 tok/s | 49 tok/s(LoRA 없이 54) |
| 리포트 서술 1건 | 23.6초(캐시 없음) | 6.2초(30명 배치 p50) |
| 상세 설명 1건 | 50.2초(캐시 없음) | 16.4초(30명 배치 p50, p95 21.2초) |
| 30명 배치(120요청) | 약 70~75분(동시 2, 추정) | 10~15분(동시 4·8, 실측 3회) |
| 최대 토큰까지 반복 생성 | 38건 중 2건(상세) | 120건 중 9·19·19건(모두 상세) |
| `checks.py` | 상세 3/3 통과, 서술 JSON 3/3 | 상세 3/3 통과, 서술 3건 중 2건이 73자에서 끊김 |

- CPU `llama-bench`(LoRA 없음)의 생성 속도는 4·8·16스레드에서 11.2·20.0·24.1 tok/s다. 8스레드인 `m7i.2xlarge`(32GiB, $0.50)도 후보이지만 서버로는 재지 않았다
- CPU 동시 2는 처리량이 19.8 tok/s로 동시 1(18.4)과 거의 같고, 슬롯당 속도는 11 tok/s로 떨어진다
- CPU 30명 배치는 #384 부하 시험에 계정을 넘기려고 22요청에서 멈췄다. 70~75분은 4명 배치(583초)와 22요청 기록으로 추정한 값이다

### 9.13.5 발견

- **반복 생성**: 상세 설명이 `max_tokens` 4096까지 반복하는 경우가 GPU에서 8~21%, CPU에서 약 5% 나왔다. 서비스에서는 `finish_reason=length`가 `LLM_INVALID_OUTPUT`이 되어 설명 없이 발행된다. CPU에서는 이런 1건이 약 400초를 점유해, 지금 상세 마감(305초)을 넘는다. #747에서 상세 `max_tokens`(정상 출력은 520~710토큰)와 마감을 함께 조정해야 한다
- **L4 메모리 한계**: 17.2GB 단일 safetensors는 16GiB 호스트에서 mmap 실패(ENOMEM)로 vLLM이 기동하지 않았다. 4조각으로 나누자 기동했다. VRAM은 bf16 KV로는 8192 길이 1건분도 남지 않아, `--kv-cache-dtype fp8 --max-num-seqs 8 --max-num-batched-tokens 2560 --gpu-memory-utilization 0.97`와 멀티모달 0개 설정이 필요했다. 그래도 KV는 12,653토큰(8192 기준 1.54건)뿐이다
- **생각 모드**: llama.cpp `--jinja`의 기본값에서는 Gemma 4가 생각(reasoning)부터 출력해, 서술 1건이 2,048토큰을 모두 쓰고 본문이 비었다. `--reasoning off`로 해결했다. vLLM은 기본값으로도 생각 출력이 없었다
- **운영 호출 모델 이름**: ai-service `REPORT_GEMMA_MODEL` 기본값과 prod 설정은 기반 이름 `gemma-4-26b-a4b-it-qat-awq-int4`다. vLLM에서 이 이름으로 부르면 LoRA가 붙지 않는다(LoRA는 `explain`). 같은 입력에서 두 이름의 출력이 달랐다. 지금 RunPod 호출에 LoRA가 적용되는지 확인이 필요하다(#747). llama.cpp `--lora`는 모델 이름과 상관없이 모든 요청에 붙는다

### 9.13.6 S3 반입 (#745)

경로는 `s3://sagomungchi-demo-<계정>-models/explanation/gemma4-26b-a4b-lora-20261118/` 아래 18개 객체(31.7GB)다. 파일별 크기·sha256은 결과 JSON의 `s3`에 있다.

| 하위 경로 | 내용 |
|---|---|
| `adapter/` | PEFT 원본 `adapter_model.safetensors`·`adapter_config.json`(로컬 사본, `ml/sllm/README.md` 해시와 같음) |
| `adapter-gguf/` | `explain-lora-f16.gguf`(CPU용 변환본, 230 텐서) |
| `base-awq/` | AWQ 기반 모델 설정·토크나이저와 `model-0000{1..4}-of-00004.safetensors` + index(GPU용) |
| `base-gguf/` | 공식 QAT Q4_0 GGUF를 `llama-gguf-split`으로 나눈 4개 파일(CPU용, 1번 파일로 기동) |

- 모든 객체를 `PutObject` 1회 + `ChecksumSHA256`으로 올렸고, HEAD에서 `ChecksumType=FULL_OBJECT`와 값이 일치함을 확인했다(`upload.py`). 덮어쓰기는 `If-None-Match: *`로 막았다
- **5GB 초과 파일**: S3는 multipart 업로드에 SHA-256 `FULL_OBJECT`를 허용하지 않는다(2026-11-18 실제 요청이 `InvalidRequest`). multipart SHA-256은 COMPOSITE뿐이라 #368·#493 원칙(전체 SHA-256만 인정)에 맞지 않는다. 그래서 형식이 지원하는 방법으로 파일을 나눴다. safetensors는 텐서 바이트를 그대로 옮겨 4조각으로 나누고, 원본과 35,743개 텐서의 dtype·shape·sha256이 같음을 대조했다(`reshard.py`·`verify_shards.py`). GGUF는 `llama-gguf-split`으로 나눴다. 원본 단일 파일의 sha256은 HF LFS 값과 같고(AWQ `c0b6bbe9…`, GGUF `3eca3b8f…`), 이 값도 결과 JSON에 남겼다
- 대안으로 원본을 바이트 단위로 잘라 올리고 받을 때 이어 붙이는 방법, multipart CRC64 FULL_OBJECT + 메타데이터 sha256 방법도 있었다. 앞의 것은 서버가 그대로 읽지 못하고, 뒤의 것은 #368 원칙(CRC·메타데이터 불인정)에 맞지 않아 쓰지 않았다
- `sllm-server` initContainer는 지금 `MODEL_KEY` 파일 1개와 `MODEL_SHA256` 1개만 받는다. 여러 파일과 LoRA를 받도록 바꾸는 일은 #746 범위다
- 결정하지 않은 형식 쪽(CPU를 고르면 `base-awq/`, GPU를 고르면 `base-gguf/`·`adapter-gguf/`)은 결정 뒤 지울지 정한다. 보관 비용은 31.7GB에 월 약 $0.8다
- core 모델 레지스트리 `report-explanation` 등록은 하지 않았다. 관리자 화면 작업이고, 형식 결정과 #746 서버 변경 뒤에 해야 의미가 있다

### 9.13.7 임시 자원과 정리

| 자원 | 이름·종류 | 상태 |
|---|---|---|
| VPC·서브넷·IGW·라우트 테이블 | `sagomungchi-tmp-gemma-bench`, 10.99.0.0/24, 2a | 삭제 |
| 보안 그룹 | 같은 이름, 22/tcp를 측정 PC IP만 허용 | 삭제 |
| 키 페어 | 같은 이름, ed25519 | 삭제(로컬 개인 키도 지움) |
| IAM 역할·인스턴스 프로필 | 같은 이름, S3 `explanation/*` Put·Get만 허용 | 삭제 |
| EC2 | g6.xlarge·c7i.4xlarge 각 1대(gp3 200·120GB, 종료 시 삭제) | 종료, 볼륨 없음 확인 |

2026-11-18 11:12 KST에 태그 `Purpose=issue-743-745-temp` 기준 인스턴스·볼륨·VPC·IGW와 이름 기준 보안 그룹·키 페어·IAM이 모두 0개이고, `explanation/` 아래 남은 multipart 업로드가 0건임을 확인했다. EKS·RDS 자원은 건드리지 않았다. 측정 비용은 약 $2.5(EC2 2대 약 1.3시간과 EBS)다.

### 9.13.8 한계와 남은 것

- 입력이 고정 가상 글 1편과 서술 1건이라 같은 프롬프트가 반복된다. 그래서 2회째부터는 접두 캐시로 입력 처리 시간이 줄었다. 표의 1건 값은 첫 실행(캐시 없음)이나 배치 p50으로 적었다. 글 길이가 다른 여러 입력과 RunPod 출력 비교(`explanation_eval.py`)는 하지 않았다
- 품질은 `checks.py` 통과와 JSON 형식만 봤다. CPU(GGUF)와 GPU(AWQ) 출력의 의미 차이는 사람 검토가 필요하다
- EKS 안 기동 시간(노드 준비, S3 initContainer 내려받기)은 재지 않았다
- 학습 기준 모델 확인: 어댑터의 `base_model_name_or_path`는 `/workspace/models/gemma-4-26b-qat`(로컬 경로)라 정확한 원본 저장소·revision을 알 수 없다. 구조(30층, hidden 2816, 전역 주의 층의 K=V 공유로 `v_proj` 25개)는 두 기반 모델과 모두 맞는다. kim-4480에게 확인을 요청했다
- 다음 순서: SageMaker 검증 이슈(LMI 버전, LoRA, 콜드 스타트, 예약 확장, 재고 부족 동작) → #744 문서 → #746 SageMaker 엔드포인트·IAM → 레지스트리 등록 → #747 호출 전환(SageMaker 클라이언트, 모델 이름, `max_tokens`·마감)

## 9.14 AWS 데모 부하 시험 2차: HPA·Karpenter 확장·축소 (#384, 2026-11-18)

1차(9장)와 같은 도구(`evaluation/load/`)로 CloudFront → ALB → core에 단계별 부하를 주고, #211·#372로 켠 HPA·Karpenter가 실제로 늘고 주는지 쟀다. 운영 쓰기(계정·구독·LLM 스텁·pause Pod·정리)는 시작 전에 묶어서 담당자 승인을 받았다.

### 9.14.1 조건

| 항목 | 1차(11-05) | 2차(11-18) |
|---|---|---|
| 앱 | core replica 1, HPA·Karpenter 없음 | main `e3cb5084`. HPA core·learning·ai 최소 1·최대 3·CPU 70%(요청 대비), NodePool `application-burst`(t3.medium·t3.large, CPU 4·메모리 16Gi 상한, `consolidateAfter 5m`) |
| 노드 | — | 관리형 `application` t3.medium 2대 + `platform-observability` 2대(taint) |
| LLM | 클러스터 안 스텁(2.5~4초) | 같은 스텁 이미지. ai `OPENAI_BASE_URL`만 스텁으로 바꿈(임베딩은 이 값을 따르지 않아 실제 OpenAI 호출, 비용 무시할 수준) |
| 시험 계정 | 1개(자녀 3명, 학습 칸 15) | `prepare_accounts.py`로 14개(초5 자녀 3명씩 42명, 학습 칸 420). 자녀마다 결제 없는 시험 구독·보호자 공유 켬 |
| RDS | db.t4g.small | 같음. `max_connections` 181 → 앱이 쓸 수 있는 수 176(예약 5 제외) |
| 단계 | 50·100·200·300명 | 50~300명은 1차와 같은 중단 기준(API 오류 1%·p95 1초). 400~1000명은 한계 찾기로 기준을 p95 10초(1000명은 60초)·오류 5%로 올림(`P95_API_MS`·`MAX_API_ERROR_RATE`) |
| 범위 밖 | — | KEDA(AWS 미설치), NAT 실측(스텁이라 외부 호출이 거의 없음) |

연결 수(시작 전 계산): core 3×10 + learning 3×10 + report-api·worker 15+15 = 90, rolling update 여유 +20 → 110 ≤ 176. 풀 크기는 바꾸지 않았다. 시험 중 RDS 연결은 최대 68개였다.

### 9.14.2 단계별 결과

| 항목 | 50 | 100 | 200 | 300 | 400 | 600 | 800 | 1000 |
|---|---|---|---|---|---|---|---|---|
| API 오류 | 0/5,619 | 0/11,201 | 2/22,173 | 15/28,574 | 28/38,015 | 68/38,128 | 9/6,526 | 648/11,998 (5.4%) |
| API p95 (ms) | 109 | 136 | 238 | 1,042 | 1,984 | 4,935 | 10,674 | 15,123 |
| 판정 SSE p95 (초) | 7.8 | 7.6 | 7.7 | 9.6 | 13.2 | 22.7 | 33.8 | 50.7 |
| 학습 성공 | 297/297 | 596/596 | 1,196/1,197 | 1,513/1,513 | 1,980/1,981 | 1,519/1,521 | 203/203 | 274/428 |
| core 처리량 (req/s) | 28.7 | 55.3 | 107.9 | 160.0 | 151.7 | — | — | — |
| RDS CPU 최대 (%) | 13 | 24 | 58 | 72 | 98 | 98 | 90 | 97 |
| learning DB 풀 대기 최대 | 0 | 0 | 0 | 18 | 36 | — | — | 178(로그) |
| Pod 최대 core/learning/ai | 3/1/1 | 3/3/1 | 3/3/2 | 3/3/3 | 3/3/3 | 3/3/3 | 3/3/3 | 3/3/3 |
| Karpenter 노드 | 0 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| 결과 | | | | p95 1초 넘어 끝 무렵 중단 | | | 1분 54초에 p95 10초 넘어 중단 | 2분 46초에 오류 5% 넘어 중단 |

- 요청 수는 400명(약 3.8만)과 600명(약 3.8만)이 같다. 400명부터 처리량이 늘지 않고 지연만 늘었다.
- 1000명 오류 대부분은 learning Hikari 풀 대기 30초 초과다(`Connection is not available, request timed out after 30000ms (total=10, active=10, waiting=178)`). 그래서 API p99가 30초 근처에 몰렸다. CloudFront 원본 읽기 제한(60초)·k6 제한(60초)에는 닿지 않았다.
- 400명 11:47 이후 JVM·DB 풀 지표는 수집되지 않았다(9.14.6). 표의 "—"는 그 때문이다. Pod 수·HPA CPU는 metrics-server 기준이라 끝까지 있다.
- Pod 재시작은 전 단계 0회, RabbitMQ 적체(ready)는 0, ALB ELB 5xx는 0이었다.

### 9.14.3 HPA 확장

| 시각(KST) | 사건 |
|---|---|
| 09:37 | 부하 전, 시험 계정 가입 중 core 1→3. 가입 비밀번호 해시 CPU에 새로 뜬 JVM의 기동 CPU(Pod당 0.6~1코어)가 평균에 더해져 바로 최대까지 감 |
| 11:13:03 | 50명 시작 27초 만에 core 1→3(181%). k6 `setup()`의 보호자 14·학생 42명 로그인(비밀번호·PIN 해시)이 몰린 순간이다. 정상 부하는 core 3개 합계 0.36~0.85코어였다 |
| 11:23:14 | 100명, learning 1→2(81%) |
| 11:24:59 | learning 2→3(136%) |
| 11:29:26 | 200명, ai 1→2(121%), 300명에서 3 |

- 먼저 바빠진 것은 core가 아니라 learning이었다. 1차는 core만 봤고 learning은 1개 고정이었다.
- ai는 LLM을 기다리는 서비스지만 스텁 지연 동안에도 요청 처리 CPU로 70%를 넘어 늘었다. CPU 기준 확장이 ai에도 걸린다는 것은 확인했지만, 늘어난 ai가 병목을 풀지는 않았다(병목은 DB).
- HPA 확장 중 오류는 늘지 않았다(100명 0건, 200명 2건).

### 9.14.4 Karpenter 확장·상한

자연 부하(100명, learning 2→3):

| 시각 | 사건 | 경과 |
|---|---|---|
| 11:24:59 | learning Pod Pending(`1 Too many pods, 2 Insufficient memory`) | 0 |
| 11:25:00 | NodeClaim `application-burst-…` 배정 | 1초 |
| 11:25:03 | 인스턴스 Launched(t3.medium, 2a) | 4초 |
| 11:25:21 | 노드 Registered | 22초 |
| 11:25:36 | Pod 배치 | 37초 |
| 11:25:40 | 노드 Ready | **41초** |
| 약 11:26:55 | learning Pod Ready(JVM 기동 포함) | **약 1분 55초** |

- 새 노드의 learning Pod는 400~1000명 동안 RDS·RabbitMQ로 정상 처리했다(학습 성공률 유지, 그 Pod 재시작 0). CloudFront → ALB → core → learning(새 노드) 경로가 그대로 동작했다.
- 관리형 노드 2대의 여유는 CPU보다 Pod 수(t3.medium 17개)와 메모리가 먼저 찼다. 6.의 예상과 같다.
- 600·800·1000명에서도 Karpenter 노드는 1대였다. HPA 최대 3에 막혀 더 늘 Pod가 없었기 때문이다.

상한(12:15, pause Pod 900m×5개를 Karpenter 노드에만 띄움):

- NodeClaim 2개를 동시에 만들고 39초 뒤 둘 다 Ready. DaemonSet 요청 때문에 t3.medium 한 대에 900m Pod가 1개씩만 들어갔다.
- 남은 3개는 Pending으로 남고 Karpenter는 `all available instance types exceed limits for nodepool`을 기록했다. 세 번째 노드는 만들지 않았다. 상한에서 멈추고 Pod가 기다리는 동작을 확인했다.
- pause Pod 삭제 뒤 두 노드도 빈 노드 정리로 사라졌다(9.14.5).

### 9.14.5 축소와 D안 삭제 순서

두 번 관찰했다. 두 번 모두 부하를 끝낸 뒤 10명 저부하(알림 SSE 유지)를 걸어 둔 채 Pod·노드가 줄어드는 것을 봤다.

| | 1회(1000명 중단 12:02:17 뒤) | 2회(200명 종료 12:29:47 뒤) |
|---|---|---|
| HPA 축소 | ai 12:07:04(3→2, Karpenter 노드 Pod)·12:07:49(→1), learning 12:07:49(3→1), core 12:08:50(3→1) | ai 12:31:52(3→2, Karpenter 노드 Pod)·12:34:22(→1), core 12:34:22(3→2)·12:34:37(→1), learning 12:34:22(3→2)·12:34:52(→1) |
| 지워진 learning Pod | Karpenter 노드 Pod + **가장 오래된 기본 Pod(관리형 노드, 18시간)** | Karpenter 노드 Pod → 관리형 노드 Pod(같은 노드에 core 2개와 함께 있던 것) |
| Karpenter 노드 빈 시각 → 정리 시작 → 삭제 | 12:07:50 → 12:13:10 → 12:13:37 | 12:34:22 → 12:39:54 → 12:40:33 |
| 부하 종료 → 노드 0대 | **11분 20초** | **10분 46초** |

- HPA 축소는 부하 종료 뒤 약 5분(기본 축소 안정화 5분)에 시작했다. 노드는 빈 뒤 `consolidateAfter 5m` + 약 20~30초에 정리가 시작돼 30초 안팎에 사라졌다.
- **D안 삭제 순서는 보장되지 않는다.** 2회는 의도대로 Karpenter 노드 Pod가 먼저 지워졌지만, 1회는 learning 3→1에서 가장 오래된 기본 Pod도 함께 지워지고 39분 된 Pod가 남았다. core는 세 번(09:37 확장 뒤 포함) 모두 같은 노드에 몰린 두 Pod가 지워졌다. ReplicaSet 축소는 생성 순서보다 "같은 노드에 같은 ReplicaSet Pod가 몇 개 있는지"를 먼저 보기 때문이다.
- 노드 정리 때 실행 중인 Pod를 내보내는 일은 없었다. HPA가 Pod를 먼저 줄여 Karpenter 노드가 빈 다음에 지웠다(`Disrupting Node: Empty`).
- **축소 중 끊김(2회, DEBUG 기록)**: 축소 구간 12:34~12:37에 API 오류는 0건이었다. 알림 SSE 1건이 core Pod 삭제(12:34:37) 33초 뒤인 12:35:10에 `stream error: INTERNAL_ERROR; received from peer`로 끊겼다. 지워진 Pod에 붙어 있던 SSE가 종료 유예가 끝날 때 끊긴 것이다(웹 EventSource는 다시 연결한다). 판정 2건은 learning Pod 삭제 즈음 `PENDING` 상태로 다시 받아 끝났다(k6 경합 처리). 12:37:09 이후 401 `TOKEN_EXPIRED`는 k6가 시작 때 받은 학생 토큰(15분)이 25분 실행 중 만료된 것이라 축소와 무관하다.
- 1회 관찰의 오류(API 1.11%)는 1000명 단계에서 밀린 요청이 남은 첫 1분(ALB 대상 5xx 636건, learning 풀 시간 초과 로그가 모두 12:02)에 몰려 있어 축소 영향과 가를 수 없었다. 그래서 2회를 다시 쟀다.

### 9.14.6 발견

1. **한계는 RDS CPU이고, 원인은 learning 쿼리 두 개다.** 400~1000명 구간 Performance Insights(평균 활성 세션)는 `learning_app` 5.30, `core_app` 0.63이었다. 상위 두 쿼리가 전체의 약 82%다.
   - 학생 학습 기록 목록(`learning-service` `RecordMapper.xml`, 3.49): 시도마다 `hint_usage`·`followup`·`answer.followup_id`를 상관 서브쿼리로 찾는다
   - 최근 되묻기 조회(`JudgmentMapper.xml`, 1.56): `followup`을 `attempt_id`로 찾는다
   - learning migration에는 `answer(attempt_id, submitted_at)` 인덱스만 있다. **`followup(attempt_id)`·`hint_usage(attempt_id)`·`answer(followup_id)` 인덱스가 없어** 시도 하나마다 테이블 전체를 읽는다. 시험으로 시도가 쌓일수록 느려졌다
   - 쌓인 데이터의 영향: 11:20 100명 학습 기록 p95 287ms·RDS CPU 24% → 12:20 10명(시험 데이터가 쌓인 뒤) 학습 기록 p95 1,014ms·RDS CPU 13~15%. 같은 200명도 11:27에는 API p95 238ms, 12:20에는 1분 만에 1초를 넘었다(바로 앞 축소 관찰 중이라 시작이 느렸고, 12:22 재시도는 423ms)
2. **앱 확장은 DB 앞에서 멈췄다.** core CPU는 3개 합계 0.75~0.85코어로 여유가 있었고 DB 연결은 68/176이었다. 병목이 DB인 동안에는 HPA 최대 수·노드를 늘려도 처리량이 늘지 않는다.
3. **HPA가 로그인 순간에 최대까지 간다.** 비밀번호·PIN 해시(로그인·가입)가 몰리면 core가 수십 초 안에 1→3이 된다. 새 JVM 기동 CPU가 평균을 더 올린다.
4. **D안 삭제 순서는 보장되지 않는다**(9.14.5).
5. **관측 경로가 부하에 같이 무너졌다.** Tempo가 CrashLoopBackOff(재시작 57회)인 상태에서 trace가 늘자 OTel Collector가 재시도 대기로 메모리 상한(soft limit)에 닿았고, 받는 데이터를 거부하면서 JVM·DB 풀 지표까지 버렸다(400명 11:47부터, 시험 뒤에도 앱 쪽 `HTTP 503`). trace 경로 장애가 지표 수집까지 막는다.

1차와 비교(300명): API p95 374 → 1,042ms, RDS CPU 68 → 72%. 1차는 학습 칸이 15개라 300명 API의 약 35%가 가벼운 경합 호출이었고, 2차는 칸 420개로 학습·판정이 실제로 돌았다. 그래서 같은 300명이라도 2차가 DB에 더 무겁다. "DB가 먼저 한계"라는 1차 결론은 계정을 늘린 2차에서도 맞았고, 그 DB 부하의 대부분이 learning이라는 것이 새로 드러났다.

해석 주의: k6 사용자 하나는 1~3초마다 요청을 보낸다. 실제 아이는 답을 쓰고 읽느라 훨씬 드물게 보내므로 k6 300명은 실제 동시 사용자 300명보다 무겁다. 또 시험 자녀 한 명이 한 시간에 수십~수백 번 시도해 학습 기록 쿼리(기간 안 시도 수에 비례) 비용이 실제보다 크다.

### 9.14.7 개선안

| 우선 | 제안 | 근거 |
|---|---|---|
| 1 | learning 인덱스 3개 추가: `followup(attempt_id, created_at)`, `hint_usage(attempt_id)`, `answer(followup_id)` | DB 부하 약 82%가 이 인덱스가 없는 두 쿼리. 별도 이슈로 migration 후 같은 단계로 다시 잰다 |
| 2 | HPA 기준: CPU 70% 유지, `behavior.scaleUp` 안정화 30~60초 또는 JVM 기동 구간 제외 | 로그인 순간·JVM 기동 CPU로 바로 최대까지 감(9.14.3). 비용이 크지 않아 지금 값도 위험하지 않지만 확장이 실제 부하를 따라가지 않는다 |
| 3 | 최대 Pod 수: 1이 해결될 때까지 3 유지. 그 뒤 learning 최대를 먼저 올림 | 지금은 DB가 병목이라 늘려도 처리량이 같다. learning이 core보다 먼저 바빠짐 |
| 4 | Hikari 풀: 지금 10 유지. 1 뒤 learning 풀 대기가 남으면 15까지 | 연결 상한 계산: core 3×10 + learning 3×15 + report 30 = 105(+rolling 25) ≤ 176 |
| 5 | RDS 사양: 1을 먼저. 그래도 부족하면 t4g.medium 이상 또는 읽기 복제본 | 지금 효율 그대로 단순 비례하면 k6 1000명에 vCPU 약 7개가 필요(300명에서 2 vCPU의 72%). 1로 이 숫자가 크게 줄 것으로 본다 |
| 6 | 축소 끊김: D안 대신 최소 2 + PDB, 또는 `controller.kubernetes.io/pod-deletion-cost`로 Karpenter 노드 Pod 우선 삭제 | 9.14.5 |
| 7 | 관측: Tempo 장애 해결, Collector에서 trace와 지표 파이프라인의 메모리 제한 분리 | 9.14.6-5 |

### 9.14.8 운영 변경과 원복

| 변경 | 원복·정리 | 확인 |
|---|---|---|
| LLM 스텁 Deployment·Service·NetworkPolicy 2개(`llm-stub.k8s.yaml`) | 같은 파일로 delete(12:50) | app 네임스페이스에 `llm-stub` 자원 0 |
| ai `OPENAI_BASE_URL`=스텁(`kubectl set env`, 09:36) | `OPENAI_BASE_URL-`(12:49) | 시험 전 ReplicaSet `ai-service-d4888b47`로 복귀, helm 매니페스트와 `kubectl diff` 차이 없음 |
| 시험 계정 `load21`~`load214`(자녀 42명, 기기 14대) | 비밀번호 재확인 → `POST /me/withdrawal` 14건(202) | core `load2` 계정 0·연결 자녀 0, learning 11/18 시도·답변·되묻기 0, 분석 대화 0 |
| 시험 구독 42건(결제 없음, 1차 SQL과 같은 형식) | 해지 → 이용 기간을 당일로 끝냄 | 활성 0. 탈퇴 사전 확인은 해지만 해도 이용 기간이 남은 구독을 "진행 중"으로 세서 기간을 끝내야 탈퇴됐다 |
| pause Deployment `karpenter-limit-probe` | delete(12:15:59) | 노드 2대 빈 노드 정리 |
| 일회용 DB Pod·ConfigMap(`-384`) | 실행마다 delete | 0 |
| 비밀 파일(작업자 PC, 저장소 밖) | 삭제 | — |

- 시험 뒤 상태(12:55): 노드 4대(관리형 2 + 관측 2), NodeClaim 0, EC2 4대. HPA 설정은 시험 전과 같다(최소 1·최대 3·70%). 탈퇴 처리의 로그인·재확인 해시로 core가 잠시 3개가 됐다가(12:50:53) 12:57:54에 1개로 돌아왔다. core·learning·ai 모두 1개.
- 바꾸지 않은 것: HPA·Hikari·NodePool 값, 모델 레지스트리, scoring. core HPA 임시 상한 6은 필요 없어 쓰지 않았다(9.14.9).
- 남긴 것: 스텁 호출 `llm_usage` 21,629행(판정 9,289·되묻기 9,282·분석 3,058, 합계 $0.013). 스텁인데 모델명이 `gpt-6-luna`로 기록돼 호출 수 집계에서 실제 호출과 구분되지 않는다. 금액이 작아 지우지 않았다
- 1차(11-05) 시험 데이터(Google 시험 계정 자녀, 시도 약 2,800건)는 Google 재인증이 필요해 이번에 지우지 못했다. 보호자 화면의 자녀 삭제로 담당자가 정리한다
- app 네임스페이스에 11/17 재가동 때 만든 `demo-db-oneoff-sql` ConfigMap이 남아 있다(이 시험과 무관, 손대지 않음)

### 9.14.9 한계

- KEDA·report-worker 큐 확장은 AWS에 없어 재지 않았다.
- NAT는 스텁이라 외부 호출이 거의 없어 재지 않았다(최대 활성 연결 30, 포트 할당 오류 0은 임베딩·OAuth 등 기본 호출).
- core HPA 최대를 6으로 올려 Karpenter를 띄우려던 계획은 learning 확장으로 자연스럽게 노드가 떠서 하지 않았다. 그래서 HPA 최대가 3보다 클 때의 동작은 재지 않았다.
- 400명 11:47 이후 JVM·DB 풀 지표가 없다(관측 경로 장애). 1000명 풀 대기는 learning 로그 값이다.
- 실제 LLM 지연·429는 반영되지 않았다(#630은 동시 1명).

## 10. 근거 링크

- [ingress-nginx 지원 버전](https://github.com/kubernetes/ingress-nginx#supported-versions-table), [종료 공지](https://kubernetes.io/blog/2025/11/11/ingress-nginx-retirement/), [kind v0.33.0](https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0)
- [Calico 요구사항](https://docs.tigera.io/calico/latest/getting-started/kubernetes/requirements), [native v3 CRD](https://docs.tigera.io/calico/latest/operations/native-v3-crds)
- [MinIO 배포 방식](https://github.com/minio/minio#source-only-distribution), [Chainguard MinIO](https://images.chainguard.dev/directory/image/minio/overview), [curl SigV4](https://curl.se/docs/manpage.html#--aws-sigv4)
- [Compose 변수 해석](https://docs.docker.com/reference/compose-file/interpolation/), [RabbitMQ 메모리](https://www.rabbitmq.com/docs/memory), [quorum WAL](https://www.rabbitmq.com/docs/quorum-queues#resource-use), [Redis eviction](https://redis.io/docs/latest/develop/reference/eviction/)
- [Langfuse 자체 호스팅 자원](https://langfuse.com/self-hosting/configuration/scaling), [Langfuse OTel 계약](https://langfuse.com/integrations/native/opentelemetry/migration-to-v4), [VPC 요금](https://aws.amazon.com/vpc/pricing/)
