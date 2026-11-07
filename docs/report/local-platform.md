# 로컬 플랫폼·앱 배포 (#17·#171·#273·#236·#312)

[아키텍처 4.1](../design/architecture.md#41-환경-구분)의 로컬 Kubernetes 환경을 구체화한 설정과 근거. 실행 절차는 [kind](../../infrastructure/kind/README.md)·[platform-data](../../infrastructure/gitops/charts/platform-data/README.md), 설정값은 [local values](../../infrastructure/gitops/environments/local/platform-data.yaml).

## 1. 환경 경계

- 로컬은 kind 단일 노드에 PostgreSQL·RabbitMQ·Redis·MinIO, 운영은 RDS·S3와 RabbitMQ·Redis StatefulSet 설계 유지
- 저장소 구성은 `platform-data` chart 하나로 관리하고 PostgreSQL·MinIO는 로컬 values에서 활성화(1~6절). 앱 배포·관측은 7절 이후(#171), AWS 자원은 [aws-deploy](aws-deploy.md)
- 로컬 API·HTTP·HTTPS는 loopback에만 노출. 다른 기기 접근은 별도 진입 설계 필요
- 팀 개발 PC가 기준 PC(Windows 11, i5-1135G7 4코어·8스레드, 16GB, Docker Desktop WSL 2)와 같다는 전제

## 2. Kubernetes·CNI·Ingress 조합

| 설정 | 근거 |
|---|---|
| kind v0.33.0 / Kubernetes v1.35.8 | ingress-nginx v1.15.1의 E2E 범위가 1.35까지. 공식 노드 이미지 digest로 고정 |
| Calico v3.33.0 / IPv4·iptables | Calico의 1.35 테스트 범위. 기본 CNI 비활성 |
| `MutatingAdmissionPolicy` feature gate·beta API | Calico native v3 CRD 기본값 처리에 필요, 1.35에서 기본 비활성 |
| Pod `10.244.0.0/16`, Service `10.96.0.0/12` | 기준 PC의 Wi-Fi·WSL·Docker 대역과 비중복(Calico 예시 `192.168.0.0/16`은 Wi-Fi 대역 포함). 다른 네트워크에서는 재확인 |
| ingress-nginx controller v1.15.1 / chart 4.15.1 | 이슈 지정 유지(사용자 결정). 유지보수 종료 프로젝트라 버전 고정이 보안 패치를 뜻하지 않음. 운영 ALB 설계는 불변 |

## 3. MinIO 이미지와 버킷

- 커뮤니티판의 소스 전용 배포 전환으로 사전 빌드된 Chainguard 공개 이미지 사용. linux/amd64 digest를 [공통 values](../../infrastructure/gitops/charts/platform-data/values.yaml) `minio.image`에 고정, 업데이트는 digest 변경으로만
- 서버 이미지에 shell·curl이 있다고 가정하지 않음. 버킷 초기화는 `curlimages/curl:8.17.0`의 S3 SigV4 요청, 인증은 curl 설정 stdin(인자·로그에 비밀번호 없음). 이미 소유한 버킷만 재실행 성공 처리

| 버킷 | 분리 이유 |
|---|---|
| `sagomungchi-local-missions` | learning 미션 장면 파일 |
| `sagomungchi-local-reports` | 권한 확인 후 제공할 리포트 파일 |
| `sagomungchi-local-models` | 모델 버전별 가중치 |

- 세 버킷은 단일 MinIO Pod·2Gi PVC 공유. 버킷 분리가 앱의 사용자별 권한 검사를 대체하지 않음. 운영 S3 이름·정책은 AWS 작업에서 확정

## 4. 초기화와 자격 증명

- Compose MinIO는 [compose.minio.yaml](../../compose.minio.yaml)로 분리. Compose는 병합 전에 각 파일의 변수를 해석하므로 profile만으로는 `${VAR:?}` 검사를 피할 수 없음. 기본 실행에는 MinIO 이미지·포트·메모리를 추가하지 않음. 실행 절차는 [루트 README](../../README.md#81-빠른-실행)
- Secret 준비 스크립트는 PowerShell 7 이상(프로세스 인자 목록·UTF-8 stdin·JSON Hashtable·프로세스 트리 종료 API 사용). MinIO 사용자명 3자·비밀번호 8자 이상
- RabbitMQ는 계정 기동 후 Job이 관리 API로 `definitions.json` 반영(계정을 JSON에 넣지 않으려고 순서 분리). `default_queue_type`을 전역 quorum으로 강제하지 않음(Pod별 exclusive 브로드캐스트 큐와 충돌 방지)
- `init.sql`·`definitions.json`은 원래 위치에 두고 Helm `.Files`와 Compose 마운트가 같은 파일을 읽음
- `.env`의 PostgreSQL·RabbitMQ·MinIO 계정 6개만 `platform/platform-data-credentials` Secret으로 준비. 기존 Secret과 값이 다르면 덮어쓰지 않음(환경 변수 변경만으로 계정이 회전되지 않으므로)
- 활성 저장소의 requests·limits·필수 설정이 없으면 렌더링 중단

## 5. 자원 예산

requests는 스케줄링 기준, limits는 컨테이너별 상한이며 실측값이 아님.

| 대상 | CPU request | CPU limit | 메모리 request | 메모리 limit |
|---|---:|---:|---:|---:|
| PostgreSQL | 100m | 500m | 256Mi | 512Mi |
| RabbitMQ | 250m | 1000m | 512Mi | 2Gi |
| Redis | 50m | 250m | 64Mi | 256Mi |
| MinIO | 100m | 500m | 256Mi | 1Gi |
| ingress-nginx controller | 100m | 500m | 128Mi | 512Mi |
| **상시 합계** | **600m** | **2750m** | **1216Mi** | **4.25Gi** |
| 초기화 Job(RabbitMQ·MinIO 각 1개) | 50m씩 | 250m씩 | 64Mi씩 | 128Mi씩 |

- control plane·etcd·CoreDNS·Calico·기반 구성에 1.5GiB 계획 여유를 더해 플랫폼 전체 약 6GiB 예산. 앱·모델 추론·관측·동시 이미지 빌드는 제외
- Docker 상한(약 7.62GiB)은 유지. 기동 전 불필요한 앱을 정리하고, Compose 전체와 kind는 동시에 실행하지 않음
- 저장소 내부 시작값
  - PostgreSQL: `shared_buffers=64MB`, `max_connections=40`, `work_mem=2MB`, `maintenance_work_mem=32MB`(work_mem은 동시 작업 수에 비례). 운영 튜닝 값 아님
  - RabbitMQ: quorum WAL 512MiB의 3배 권장을 고려해 limit 2Gi, `vm_memory_high_watermark.absolute=1GiB`(발행 제한 기준이며 OOM 방지 보장 아님)
  - Redis: `maxmemory=128mb`, `noeviction`(한도 초과 쓰기를 오류로 드러냄)
  - MinIO: limit 1Gi는 소규모 파일 검증용. 대형 모델 파일·동시 업로드는 미검증

| 볼륨 | PVC 요청 | 범위 |
|---|---:|---|
| PostgreSQL | 2Gi | DB 3개 소규모 데이터·WAL |
| RabbitMQ | 2Gi | quorum queue·DLQ 소규모 메시지 |
| Redis | 512Mi | 로컬 영속화 |
| MinIO | 2Gi | 세 버킷 공유 |
| **합계** | **6.5Gi** | 이미지·로그·시스템 데이터 제외 |

- StatefulSet 삭제·축소 시 PVC 보존(kind 노드 삭제로부터는 보호하지 않음). 로컬 provisioner는 PVC 요청을 디스크 quota로 강제하지 않을 수 있어 호스트 여유 공간을 따로 확인. 전체 검증 전 30GiB 이상 여유 권장
- 미사용 kind 노드는 삭제하지 않고 정지해 보관 가능. MinIO 볼륨 준비 단계는 볼륨 루트 소유권만 바꾸고 기존 파일을 지우지 않음

## 6. 검증 순서

1. Helm lint·렌더링, Compose 설정 검사, 비밀 값 포함 여부, `git diff --check`
2. kind 생성 후 노드 allocatable·시스템 Pod requests, 저장소 Pod Ready·초기화 Job 성공, DB 3개·버킷 3개·RabbitMQ topology 확인
3. OOMKilled·재시작·CPU throttling·저장소 alarm 확인, 합성 데이터로 DB·AMQP·Redis·MinIO 읽기·쓰기(지표가 없으면 미검증으로 보고)
4. 기본 Compose가 MinIO 계정 없이 해석되는지, `-f compose.yaml -f compose.minio.yaml`로 MinIO 기동·버킷 준비 확인

## 7. 앱 배포 인터페이스 (#171)

EKS 사용 확정(#171 PM 결정). AWS 자원·운영 값은 #185, 이미지 게시·승인·롤백은 #186, 경보·실패 trace는 #187, 신뢰 프록시 IP는 #133.

| 릴리스 | 이미지·명령 | Service / readiness | migration |
|---|---|---|---|
| core-service | 기존 Spring Boot JAR | 8080 / `/actuator/health/readiness` | 전용 Flyway 이미지의 `migrate` |
| learning-service | 기존 Spring Boot JAR | 8081 / `/actuator/health/readiness` | 전용 Flyway 이미지의 `migrate` |
| ai-service | 기존 Uvicorn | 8000 / `/health/ready` | 없음 |
| scoring-service | 기존 Uvicorn | 8001 / `/health/ready` | 없음 |
| report-api | 기존 report 이미지·Uvicorn | 8002 / `/health/ready` | 기존 report 이미지의 `alembic upgrade head` |
| report-worker | 같은 report 이미지·`python -m app.worker` | HTTP Service 없음 | report-api의 동일 DB migration 선행 |

- core·learning Flyway는 테스트 의존성이고 앱 기동에서는 비활성. 기존 SQL을 전용 이미지에 복사해 `FLYWAY_URL`·`FLYWAY_USER`·`FLYWAY_PASSWORD`만 주입. migration 허용 NetworkPolicy는 PreSync wave -2, Job은 wave -1. `migration.revision`은 SQL/Alembic 변경 시 명시적으로 갱신, 루틴 재동기화에서 무조건 재실행하지 않음. 실패 시 앱 sync 중단
- local values의 이미지 이름·`:local` 태그는 kind에 직접 로드할 빌드 입력(GHCR/ECR 게시 이미지 아님). 운영 rollback은 이미지와 DB 스키마 호환성 판단을 분리
- Secret: `app/app-service-credentials`, `observability/observability-credentials`. chart는 이름·키만 참조. 다른 namespace Secret은 직접 참조 불가라 앱 Secret은 원본 값에서 별도 준비, `platform/platform-data-credentials`는 덮어쓰지 않음. URL 비밀번호는 URL 인코딩. 운영 공급은 #185 Secrets Manager·External Secrets
- **report Alembic URL 이스케이프**: 앱 SQLAlchemy는 URL 인코딩된 `REPORT_DATABASE_URL` 사용. `migrations/env.py`가 같은 URL을 `ConfigParser.set_main_option`에 넘겨 `%`가 보간 오류를 일으키므로, Alembic Job에만 `%`→`%%` 이중 이스케이프한 `REPORT_ALEMBIC_DATABASE_URL`을 별도 키로 제공. 운영 Secret 공급자도 두 키를 같은 원본 계정에서 생성
- core·learning Java agent는 chart의 선택적 initContainer([OTel Java agent 2.33.1](https://github.com/open-telemetry/opentelemetry-operator/pkgs/container/opentelemetry-operator%2Fautoinstrumentation-java) digest 고정)로 local에서 metrics만 Collector로 전송. 서비스 Gradle·application 파일은 변경하지 않음
- local report presigned URL은 `S3_PUBLIC_ENDPOINT_URL=http://127.0.0.1:19000`. 호스트 다운로드 확인 시 MinIO 9000을 19000으로 port-forward 필요

## 8. 로컬 네트워크·확장 (#171)

- `app`·`platform`·`observability` 기본 거부 + 서비스 이름·namespace 라벨 기준 필요한 포트만 허용. app ingress는 ingress-nginx → core 8080과 설계 4.3의 내부 호출만. app egress는 kube-dns 53과 실제 호출 대상(AI→core 8080, scoring→core 8080, report-worker→core/learning/ai, report-api→Postgres/MinIO). platform 정책은 기존 리소스를 수정하지 않고 새 NetworkPolicy로 감쌈. RabbitMQ 관리 15672는 core와 초기화 Job, metrics 15692는 Prometheus만. KEDA는 RabbitMQ 5672
- startup·liveness는 `/health/live`·`/actuator/health/liveness`, readiness만 `/health/ready`·`/actuator/health/readiness`. core snapshot·scoring 모델 준비가 오래 실패해도 startup probe가 백그라운드 재시도를 끊지 않도록 분리
- local 단일 레플리카에서는 HPA/PDB 비활성(공통 chart 제공). report-worker는 `report.report.generate`·`report.student.deleted` 두 큐 기준 KEDA 0–1, `CONSUMER_PREFETCH=1`(로컬 상한, 운영 LLM 동시 호출 상한 아님)
- core 15초 preStop·180초 grace·Spring graceful 30초는 SSE executor 85초·timer 5초를 고려한 시작값(롤링 종료 실측 전)
- NetworkPolicy 렌더만으로 Calico/VPC CNI 동작이 증명되지 않음. 운영 NAT·RDS·S3 CIDR·ALB 진입 경계는 #185

## 9. 관측 (#171)

- local `observability` chart: OTel Collector metrics OTLP 수신, Prometheus의 Collector·RabbitMQ scrape, Grafana datasource. 외부 Ingress 없음, 저장은 `emptyDir`(Pod 재생성 시 이력 소실). 버전: [OTel Collector v0.164.0](https://github.com/open-telemetry/opentelemetry-collector/releases/tag/v0.164.0), [Prometheus v3.15.1](https://github.com/prometheus/prometheus/releases/tag/v3.15.1), [Grafana v13.3.0](https://github.com/grafana/grafana/releases/tag/v13.3.0), [KEDA 2.21.0](https://github.com/kedacore/charts/releases/tag/v2.21.0)
- Grafana: 저메모리 첫 기동이 60초를 넘어 startup probe 300초, RollingUpdate가 Pod 두 개를 겹쳐 유지해 `Recreate`, CPU 한도 `250m`에서 throttling으로 startup 실패해 local 요청 `100m`·한도 `1`
- AI·scoring·report에는 exporter가 없어 전체 앱 지표·trace는 수집되지 않음(core·learning Java agent 지표만 실제 확인)
- Collector에 EKS용 선택적 OTLP traces → Langfuse `/api/public/otel` 전달 설정. endpoint·Basic 인증 헤더는 환경 values·기존 Secret에서만 주입, v4 실시간 수집 헤더 전송, local 비활성([Langfuse OTel 계약](https://langfuse.com/integrations/native/opentelemetry/migration-to-v4))
- Langfuse는 EKS 자체 호스팅 예정(#379, 미배포). trace 저장은 Tempo로 정함([ops-observability](ops-observability.md)). [공식 최소 자원](https://langfuse.com/self-hosting/configuration/scaling)(웹 4GiB·worker 4GiB·PostgreSQL 4GiB·ClickHouse 8GiB·캐시 1.5GiB)이 로컬 한도 초과
- AI Langfuse v4 계측: `LANGFUSE_ENABLED` 기본 false. true이면 public/secret key와 Collector `/v1/traces` endpoint가 모두 필요(빠지면 기동 오류). LLM 시도마다 generation 생성, call type·프롬프트 버전·모델·토큰·오류 코드만 기록. 원문·학생 ID 미전달, SDK span만 내보내도록 필터링. 기존 CloudEvents 사용량 데이터에는 `traceparent`만 연결

## 10. #171 검증 결과와 교훈

당시 전용 kind(`sagomungchi-issue171`, #273으로 폐지)와 합성 Secret 기준.

| 항목 | 결과 |
|---|---|
| Helm lint·template, 렌더 YAML 대조 | 통과 |
| Calico NetworkPolicy | core→PostgreSQL·RabbitMQ·Redis 허용, core→MinIO 차단, scoring→MinIO 허용, scoring→PostgreSQL 차단(두 라벨 경로만) |
| migration Job | core v19·learning v7(Flyway), report `20261030_04`(Alembic) Complete |
| KEDA·HPA·PDB(합성 부하) | 큐 메시지 1개마다 worker 0→1, ACK 후 0. HPA 1→2, PDB 허용 중단 수 replica에 따라 0→1 |
| 관측 | Collector·RabbitMQ target up, 합성 gauge 조회, core·learning Java agent JVM·HTTP 지표 조회 |
| 실제 서비스 | core·AI·learning·report-api·scoring readiness, AI 2레플리카 버전 일치·core 중단 시 503 후 재시작 없이 복구·RabbitMQ 재연결, report-worker 두 큐 바인딩, scoring MinIO `HeadBucket` |
| Argo CD v3.5.5 | 하위 Application 10개 Synced·Healthy, PreSync migration Job Complete |
| 미검증 | 실제 모델 가중치 로딩·추론, 활성 버전 이벤트, SSE 진행 중 종료, 실제 LLM·PDF 생성, Langfuse 저장·조회, 운영 EKS·배포 CI/롤백 |

- 다중 플랫폼 캐시 이미지는 `kind load docker-image`에서 digest 누락 오류 → `docker image save --platform linux/amd64` archive로 로드
- kind 노드 `/tmp`는 별도 tmpfs라 archive를 넣어도 containerd에서 보이지 않음 → 노드 `/root`에 복사
- KEDA `scaledjobs.keda.sh` CRD가 client-side apply의 262144-byte annotation 한도 초과(`ServerSideApply=true`로 미해결) → KEDA chart `crds.additionalAnnotations`에 `argocd.argoproj.io/sync-options: Replace=true`(local 전용, KEDA 업그레이드 시 CRD 호환성 재확인)
- ingress-nginx controller를 0개로 줄인 상태에서는 admission webhook 연결 거부로 Helm 설치 실패 → controller 먼저 복구
- Helm으로 직접 설치할 때는 Argo PreSync 훅이 없으므로 core·learning·report-api를 먼저 설치하고 migration Job 완료 후 나머지 설치

## 11. GitOps chart CI (#238)

[testing-ci 4절](testing-ci.md#4-gitops-chart-ci-238)로 옮김.

## 12. kind 클러스터 통합 (#273)

#171의 전용 `sagomungchi-issue171` 클러스터·Secret 원본 분리를 없애고 로컬 kind를 `sagomungchi-local` 하나로 통합(Docker 메모리 약 7.6GiB에서 두 클러스터 동시 운영 곤란).

| 항목 | 변경 |
|---|---|
| 앱 Secret | `create-app-secrets.ps1`. 대상 context·노드를 `kind-sagomungchi-local`·`sagomungchi-local-control-plane`으로 고정 검사, 기본 입력 루트 `.env`. UTF-8 stdin 전달, 기존 Secret 값과 불일치 시 중단 |
| platform Secret | 기존 `create-platform-secret.ps1`. 두 스크립트가 같은 `.env`를 읽어 계정 원본 단일화 |
| 관측 Secret | `.env`에 `GRAFANA_ADMIN_USER`·`GRAFANA_ADMIN_PASSWORD`가 둘 다 있을 때만 생성, 하나만 있으면 실패 |
| 제거 | `issue-171-verification.yaml`, `calico-issue-171-installation.yaml`, `issue-171-secrets.env.example`, `README-issue-171.md`. 이미지 로드·context 명시·기동 순서는 [kind 안내](../../infrastructure/kind/README.md) 5절 |

남은 `sagomungchi-issue171` 클러스터·`kind-issue171` 네트워크는 담당자가 `kind delete cluster --name sagomungchi-issue171`, `docker network rm kind-issue171`로 정리.

## 13. kind 환경값·외부 egress (#236)

kind/GitOps local values가 `compose.yaml`보다 적어 Google 로그인·토스 결제·LLM 판정이 동작하지 않던 문제 보완.

| 서비스 | compose에만 있던 값 | 처리 |
|---|---|---|
| core | `GOOGLE_CLIENT_ID`·`GOOGLE_CLIENT_SECRET` | 앱 Secret 선택 키 |
| core | `TOSS_TEST_SECRET_KEY`·`TOSSPAYMENTS_SECRET_KEY`·`TOSS_TEST_MID`·`TOSS_TEST_WEBHOOK_SECURITY_KEY`, 빌링 `TOSS_TEST_BILLING_*` 3종 | 앱 Secret 선택 키, `live_` 키 거부 |
| core | `PAYMENT_BILLING_ENCRYPTION_KEY`·`PAYMENT_FREE_PRODUCT_ID` | 앱 Secret 선택 키 (상품 UUID는 환경마다 다름) |
| core | `AUTH_ACCESS_TTL`·`AUTH_STUDENT_ACCESS_TTL`·`AUTH_REAUTH_TTL`·`AUTH_REFRESH_TTL`·`REDIS_PORT`·`STUDENT_DEVICE_TTL`·`STUDENT_DEVICE_ATTEMPT_LIMIT` | values에 compose 기본값 |
| core | `REDIS_PASSWORD` | 추가하지 않음. compose·platform-data Redis 모두 비밀번호 없음 |
| ai | `LLM_PROVIDER`·`OPENAI_MODEL`·`OPENAI_JSON_MODE`·`ANTHROPIC_MODEL`·`ANTHROPIC_EFFORT`·`ANTHROPIC_FALLBACK` | values에 compose 기본값 (`LLM_PROVIDER=openai`) |
| ai | `ANTHROPIC_API_KEY` | 앱 Secret 선택 키 (`OPENAI_API_KEY`는 기존 선택 키) |
| ai | `OPENAI_BASE_URL` | 추가하지 않음. sLLM 사용 시에만 필요 |
| report-api | `REPORT_DOWNLOAD_TTL_SECONDS`·`RABBITMQ_URL` | 추가하지 않음. 앱 기본값과 같음, 메시지 소비는 report-worker만 |

- 외부 키는 루트 `.env`를 원본으로 `create-app-secrets.ps1`이 값이 있을 때만 앱 Secret에 복사. values는 `optional: true` 참조라 키가 없으면 환경 변수 미생성(compose 빈 기본값과 같은 동작)
- egress: core·ai에만 `0.0.0.0/0`에서 사설(10/8·172.16/12·192.168/16)·CGNAT(100.64/10)·link-local(169.254/16)·loopback을 뺀 TCP 443 허용. Calico 오픈소스판·기본 NetworkPolicy에 FQDN 규칙이 없고 공급자 IP 대역 목록은 유지 곤란. 운영 EKS의 NAT·도메인 제한은 #185
- 웹은 호스트 Vite에서 `CORE_PROXY_TARGET`·`CORE_PROXY_HOST`로 `/api`를 kind Ingress(`api.sagomungchi.local`)에 전달. 미지정 시 기존 compose 대상 유지. Google 콜백은 `AUTH_WEB_ORIGIN` 기준이라 기존 리디렉션 URI 그대로
- 토스 웹훅은 외부에서 로컬 kind로 들어올 수 없어 확인 범위 밖. 결제 승인은 core가 토스 API를 직접 호출해 확인

실제 확인(2026-11-03, kind v0.33.0·Kubernetes v1.35.8·Calico v3.33.0·ingress-nginx 4.15.1): platform 4종·앱 6종 기동, Ingress `/api` 200·외부 `/internal` 404, core→Google·토스·ai→OpenAI egress 허용과 learning 외부 443·core 외부 80 차단, Google 로그인·재인증, LLM 판정 `DONE`·`llm_usage` 기록, 토스 테스트 결제 승인·구독 `ACTIVE`.

- 토스 결제위젯 키(`test_gck_`·`test_gsk_`)는 전자결제 신청 이후에만 개발자센터에 보임. 신청 전에는 문서 테스트 키(`test_gck_docs_`·`test_gsk_docs_`) 사용, 결제는 공용 문서 상점 `tgen_docs`에 기록되므로 `TOSS_TEST_MID=tgen_docs` 필요(다르면 core MID 대조에서 `PAYMENT_PG_MISMATCH`)
- 문서 테스트 키는 주문번호 조회(`GET /v1/payments/orders/{orderId}`)에 `NOT_FOUND_MERCHANT` 반환 → 상태 다시 확인·복구·관리자 대조 경로는 이 키로 검증 불가
- 관측 chart가 없는 환경에서는 core·learning Java agent가 Collector 주소 경고를 남기지만 앱 동작에는 영향 없음

## 14. 교차 확인·이관·content_3 설정 전달 (#312)

기준 develop `e583f86`에서 감사 B41을 수정했다. 구현 전에 #69·PR #303, [AI 보고서 4.3](ai.md#43-판정-모델-교차-확인-69)의 11/03 담당자 확정 내용, 앱 Settings 및 [이관 로컬 체험](auth-account.md#격리-로컬-체험)을 대조했다. 이슈에 적힌 개별 보고서는 현재 두 주제 보고서로 통합되어 있다.

### 노출 범위와 기존 결정 적용

- 플래그뿐 아니라 기존 #69 설정 10개(판정 마감·scoring timeout·reserve, M2 플래그·서술/논술 낮은·높은 경계, M1 플래그·신뢰도)를 Compose·`.env.example`·GitOps local AI values에 전달한다. 기존 Settings가 이미 환경 변수로 받는 값이며, 시간 배분·불일치 기준이 담당자 확정 보고서에 있어 새 판정 정책은 정하지 않았다. 값과 기본 false는 그대로다. 이 범위 선택은 기존 구현을 배포 설정에 노출하는 결정이며 추가 담당자 승인을 받았다는 뜻은 아니다.
- GitOps local core에 `APP_GUARDIAN_TRANSFER_ENABLED=false`, scoring에 `M2_CONTENT3_RULE_ENABLED=false`를 추가한다. Compose·`.env.example`에 있던 값과 일치한다. 실제 활성화·원복은 [README](../../README.md#64-구현과-활성화-상태)의 서비스별 설정 방법을 따른다.
- 기존 #69 계약에서 M2 플래그 off도 scoring을 호출한다. 따라서 transfer-local은 scoring 제외 프로필을 제거하고 AI의 `service_healthy` 의존성을 추가한다. 모델 미등록/승인 범위 밖이면 실제 scoring의 `active:false` 응답을 따른다. keywords·essayType을 제거하거나 실패를 비활성으로 위장하지 않는다. scoring 호스트 포트는 계속 닫아 둔다.
- scoring을 끈 채 판정을 계속하게 만드는 정책(I1, 현재 #305 A20·B36)은 미확정이므로 변경하지 않았다. 임의 중지·장애는 기존 `503 SCORING_UNAVAILABLE`이다. 이번 변경은 함께 실행하여 해당 단절을 없애는 구성 보완이며 #305 해결로 집계하지 않는다.
- API·DB·모델 가중치·score_cuts·승인 조건·운영 배포는 변경하지 않았다. 이관 체험은 기존 별도 프로젝트·볼륨·네트워크를 유지한다.

### 검증

계약 회귀 검사는 `scripts/tests/test_runtime_config.py`에서 앱 기본값과 예제·values를 대조하고, 합성 환경 파일로 실제 Compose 렌더링의 기본값/재설정 및 이관 서비스 의존성을 확인한다. 실제 개인 `.env`를 읽거나 서비스를 배포하지 않는다. 해당 환경 파일 변경도 계약 CI를 실행하도록 경로 필터를 보완했다.

| 검사 (2026-11-04) | 결과 |
|---|---|
| `python -O -m unittest discover -s scripts/tests -v` | 155개 통과, 신규 설정 회귀 검사 4개 포함 |
| Compose 기본값·명시적 false·변경값 렌더링 | AI 10개와 core/scoring 플래그 2개가 기대값으로 전달됨 |
| 이관 오버레이 병합 | AI의 scoring 준비 의존성, scoring 프로필 제외 없음·호스트 포트 없음, 프로젝트 전용 볼륨·loopback 포트 유지 |
| Helm 4.3.1 `lint --strict`·`template` | local values 8개 전체 통과, Kubernetes 1.35.8 기준 |
| values 변경 렌더링 | AI·core·scoring 기본/변경 조합 6개 lint·template 통과. Deployment 환경 변수 12개 대조, AI Settings의 기본/변경 문자열 해석 확인 |
| AI `ruff check .`·`ruff format --check .`·`pytest -q` | 린트·서식 통과, pytest 344개 통과. off 점수 기록·active:false·scoring 오류 503 회귀 포함 |
| 새 계약 검사 Ruff·`git diff --check` | 통과 |

AI 테스트 종료 시 aio-pika의 `RobustConnection.close` 미대기 RuntimeWarning 1건이 출력됐으며 테스트 종료 코드는 0이다. 이번 변경은 설정 전달·의존성 구성과 문서에 한정한다. 전체 이관 브라우저 E2E, 실제 클러스터 적용, 모델 추론 품질·운영 활성화는 재검증하지 않았다.

### 이슈 체크리스트 대조

- [x] 노출 범위 확인: 기존 확정 문서·Settings에 있는 플래그·임계값·시간 10개를 기본값 그대로 선택
- [x] Compose·`.env.example`·GitOps local 전달 추가 및 기본값 유지
- [x] transfer-local 입력 처리 정리: 기존 호출 계약을 유지하도록 scoring 함께 실행, 입력 삭제·장애 우회 없음
- [x] `.env`·local values만으로 교차 확인·이관·content_3 설정 전달 가능
- [x] GitOps `helm lint --strict`·`helm template` 통과
- [x] audit B41 처리 열 갱신

## 근거

- [ingress-nginx 지원 버전](https://github.com/kubernetes/ingress-nginx#supported-versions-table), [종료 공지](https://kubernetes.io/blog/2025/11/11/ingress-nginx-retirement/), [kind v0.33.0](https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0)
- [Calico 요구사항](https://docs.tigera.io/calico/latest/getting-started/kubernetes/requirements), [native v3 CRD](https://docs.tigera.io/calico/latest/operations/native-v3-crds)
- [MinIO 배포 방식](https://github.com/minio/minio#source-only-distribution), [Chainguard MinIO](https://images.chainguard.dev/directory/image/minio/overview), [curl SigV4](https://curl.se/docs/manpage.html#--aws-sigv4)
- [Compose 변수 해석](https://docs.docker.com/reference/compose-file/interpolation/), [Compose 파일 병합](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/), [PowerShell 7](https://learn.microsoft.com/en-us/powershell/scripting/install/install-powershell-on-windows)
- [WSL 자원](https://learn.microsoft.com/en-us/windows/wsl/wsl-config), [Kubernetes requests·limits](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/), [PostgreSQL 17 메모리](https://www.postgresql.org/docs/17/runtime-config-resource.html), [RabbitMQ 메모리](https://www.rabbitmq.com/docs/memory), [quorum WAL](https://www.rabbitmq.com/docs/quorum-queues#resource-use), [Redis eviction](https://redis.io/docs/latest/develop/reference/eviction/)
