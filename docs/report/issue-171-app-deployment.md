# 앱 배포·네트워크·확장·관측 (#171)

## 근거와 경계

2026-10-30 기준 `feature/infra-app-deployment`는 `develop`의 `cc2ccc653f7579d866271c21eba5c1885004ed58`에서 분기했다. 2026-10-31에는 #68 PR 병합이 포함된 `origin/develop`의 `94bf3ea6056878873100c5361000c288876e576f`로 fast-forward하고 #171 작업만 다시 적용했다. [이슈 #171](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/171)의 PM은 [EKS 사용을 확정](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/171#issuecomment-6513691250)했다. AWS 자원과 운영 환경 값은 #185, 이미지 게시·승인·롤백은 #186, 경보와 실패 trace 검증은 #187, 신뢰 프록시 IP 판정은 #133이다.

기존 `sagomungchi-local` kind는 platform-data·ingress-nginx가 실행 중이며 플랫폼 Secret 1개와 PVC 4개가 있다. 읽기 전용 인벤토리만 수행했다. 앱·관측·Argo CD namespace는 없었다. 이 클러스터는 다른 작업의 자산으로 보존하고, #171 검증은 별도 이름의 클러스터와 별도 시점에서 수행한다. Docker Desktop 메모리 한도는 약 7.62GiB, 기존 노드 allocatable은 `7990912Ki`다. [#17의 플랫폼 자원 계획](local-platform.md)은 기반 구성만 약 6GiB이며 전체 앱·모델·관측 동시 실행을 보장하지 않는다.

## 배포 인터페이스

| 릴리스 | 이미지·명령 | Service / readiness | migration |
|---|---|---|---|
| core-service | 기존 Spring Boot JAR | 8080 / `/actuator/health/readiness` | 전용 Flyway 이미지의 `migrate` |
| learning-service | 기존 Spring Boot JAR | 8081 / `/actuator/health/readiness` | 전용 Flyway 이미지의 `migrate` |
| ai-service | 기존 Uvicorn | 8000 / `/health/ready` | 없음 |
| scoring-service | 기존 Uvicorn | 8001 / `/health/ready` | 없음 |
| report-api | 기존 report 이미지·Uvicorn | 8002 / `/health/ready` | 기존 report 이미지의 `alembic upgrade head` |
| report-worker | 같은 report 이미지·`python -m app.worker` | HTTP Service 없음 | report-api의 동일 DB migration 선행 |

core·learning의 Flyway는 테스트 의존성이고 애플리케이션 기동에서는 비활성화돼 있다. 기존 SQL을 새 전용 이미지에 복사해 `FLYWAY_URL`·`FLYWAY_USER`·`FLYWAY_PASSWORD`만 주입한다. report의 Alembic 파일은 기존 이미지에 이미 있다. 앱 기본 거부 정책 아래서도 Job이 DB에 닿도록 migration 허용 NetworkPolicy를 PreSync wave -2, Job을 wave -1에 둔다. `migration.revision`은 SQL/Alembic 변경에 맞춰 명시적으로 갱신하고 완료된 이름의 PreSync Job을 보존한다. 루틴 재동기화나 앱 재기동 때 migration을 무조건 다시 실행하지 않는다. 실행 실패 시 앱 sync를 중단한다.

local values의 이미지 이름·`:local` 태그는 **전용 kind에 직접 로드할 빌드 입력**이다. GHCR/ECR에 게시된 이미지라는 뜻이 아니다. #186은 같은 revision의 서비스·migration 이미지를 게시하고 환경별 repository/tag 또는 digest를 갱신한다. 운영 rollback은 이미지와 DB 스키마 호환성 판단을 분리한다.

local Secret 이름은 `app/app-service-credentials`와 `observability/observability-credentials`다. chart는 이름과 키만 참조하고 값을 저장하지 않는다. Kubernetes는 다른 namespace의 Secret을 직접 참조할 수 없으므로, 앱 Secret은 승인된 원본 값에서 별도로 준비해야 한다. 기존 `platform/platform-data-credentials`는 덮어쓰거나 복제 정의 파일로 대체하지 않는다. URL 비밀번호는 URL 인코딩이 필요하다. 운영 Secret 공급은 #185의 Secrets Manager·External Secrets에 연결한다.

report 앱의 SQLAlchemy에는 URL 인코딩된 `REPORT_DATABASE_URL`을 사용한다. 기존 Alembic `migrations/env.py`는 같은 URL을 `ConfigParser.set_main_option`에 넘기므로 인코딩된 `%`가 있으면 보간 오류가 난다. #171 Secret 준비는 앱 URL을 보존하고, Alembic Job에만 `%`를 `%%`로 이중 이스케이프한 `REPORT_ALEMBIC_DATABASE_URL`을 별도 키로 제공한다. ConfigParser가 이를 읽을 때 정상 URL 인코딩으로 되돌린다. 기존 report 코드나 DB 계정은 바꾸지 않는다. 운영 Secret 공급자(#185)도 두 키를 같은 원본 계정에서 만들어야 한다.

2026-10-31 사용자 허락에 따라 별도 #171 클러스터에서 **새 합성 테스트 값**을 동일 원본으로 platform·app Secret에 각각 저장한다. 새 `create-issue-171-secrets.ps1`은 고정 context/노드 검사, Secret 불일치 시 중단, stdin 전달을 사용한다. 기존 `sagomungchi-local`의 Secret은 읽거나 변경하지 않는다. 같은 날 사용자는 develop에 반영된 core·learning의 `build.gradle.kts`·`application.yml` 수정은 허락하지 않았다. 두 서비스의 기존 파일은 유지한다. chart의 선택적 Java agent initContainer가 로컬에서 metrics만 Collector로 전송하도록 정의했으며 실제 Pod 시작·지표 수집은 검증 전이다. 공식 [Java agent 이미지 2.33.1](https://github.com/open-telemetry/opentelemetry-operator/pkgs/container/opentelemetry-operator%2Fautoinstrumentation-java) digest를 고정했다.

local report API의 presigned URL은 `S3_PUBLIC_ENDPOINT_URL=http://127.0.0.1:19000`으로 생성한다. 호스트에서 실제 다운로드를 검증할 때 전용 클러스터의 MinIO Service 9000을 호스트 19000에 명시적으로 port-forward해야 한다. 포워딩이 없으면 URL 생성만으로 다운로드 성공을 주장하지 않는다.

## 로컬 네트워크·확장

`app`·`platform`·`observability`에 기본 거부를 두고, 서비스 이름·namespace 라벨을 기준으로 필요한 포트만 허용한다. app ingress는 로컬 ingress-nginx controller → core 8080과 설계 4.3의 내부 호출만 허용한다. app egress에는 kube-dns 53과 실제 호출 대상이 포함된다. AI→core 활성 버전 조회 8080, scoring→core 모델 조회 8080, report-worker→core/learning/ai, report-api→Postgres/MinIO를 분리했다. platform 정책은 기존 RabbitMQ·Postgres·Redis·MinIO 리소스를 수정하지 않고 새 NetworkPolicy로 감싼다. RabbitMQ 관리 15672는 core와 초기화 Job, metrics 15692는 Prometheus만 허용한다. KEDA는 RabbitMQ 5672를 읽는다.

startup·liveness probe는 각 서비스의 `/health/live` 또는 Spring `/actuator/health/liveness`, readiness probe만 `/health/ready` 또는 Spring `/actuator/health/readiness`를 사용한다. core snapshot이나 scoring 모델 준비가 오래 실패해도 startup probe가 프로세스를 재시작해 백그라운드 재시도를 끊지 않도록 분리했다. 실제 kubelet 동작은 아직 검증하지 않았다.

외부 LLM·토스 호출을 허용하는 local stub이 아직 저장소에 없으므로 해당 egress를 임의의 인터넷 CIDR로 열지 않았다. 이 경로를 포함한 기능 시험은 stub이나 별도 허용 정책을 완성한 뒤에만 가능하다. 운영 NAT·RDS·S3 CIDR과 ALB 진입 경계는 #185 값으로 정해야 한다. NetworkPolicy 렌더만으로 Calico/VPC CNI의 허용·거부 동작이 증명되지는 않는다.

local 단일 레플리카 values에서는 HPA/PDB를 활성화하지 않는다. 공통 chart가 HPA·PDB를 제공하며, scale 실험에서 metrics-server와 자원을 준비해 서비스별로 검증한다. report-worker는 `report.report.generate`와 `report.student.deleted` 두 큐를 보는 KEDA 0–1, `CONSUMER_PREFETCH=1`로 시작한다. 이 숫자는 로컬 검증 상한일 뿐 운영 LLM 동시 호출 상한으로 확정한 값이 아니다. core의 15초 preStop·180초 grace와 Spring graceful 종료 30초는 기존 SSE executor 85초·timer 5초를 고려한 시작값이며 롤링 종료 실측 전에는 충분하다고 단정하지 않는다.

## 관측 단계

로컬 `observability` chart는 OTel Collector의 metrics OTLP 수신, Prometheus의 collector·RabbitMQ scrape, Grafana datasource를 제공한다. 외부 Ingress는 없고 저장 공간은 `emptyDir`이므로 Pod 재생성 시 이력은 사라진다. 후속 전용 kind 검증에서 공통 chart의 core·learning Java agent metrics export를 실제 확인했다. AI·scoring·report에는 exporter가 없어 이 구성만으로 전체 앱 지표·trace가 수집되지는 않는다. [OTel Collector v0.164.0](https://github.com/open-telemetry/opentelemetry-collector/releases/tag/v0.164.0), [Prometheus v3.15.1](https://github.com/prometheus/prometheus/releases/tag/v3.15.1), [Grafana v13.3.0](https://github.com/grafana/grafana/releases/tag/v13.3.0), [KEDA 2.21.0](https://github.com/kedacore/charts/releases/tag/v2.21.0)을 공식 릴리스 기준으로 선택했다.

Collector에는 EKS용 선택적 OTLP traces → Langfuse `/api/public/otel` 전달 설정을 추가했다. endpoint와 Basic Authorization 헤더는 환경 values·기존 Secret에서만 주입하고, v4 실시간 수집 헤더를 보낸다. local에서는 비활성화한다. [Langfuse OTel 계약](https://langfuse.com/integrations/native/opentelemetry/migration-to-v4)의 endpoint·인증·헤더를 따르지만, #185의 Langfuse 실제 배포와 trace 조회 전에는 작동으로 주장하지 않는다.

Langfuse는 EKS의 관측 노드와 데이터 서비스를 #185가 준비한 뒤 자체 호스팅한다. [공식 최소 자원](https://langfuse.com/self-hosting/configuration/scaling)은 웹 4GiB·worker 4GiB·PostgreSQL 4GiB·ClickHouse 8GiB·캐시 1.5GiB 등으로 현재 로컬 한도를 넘는다. backend 배포·실제 trace 저장은 아직 완료되지 않았다. #68의 AI 버전·readiness 코드는 develop 병합본을 유지하고, 2026-11-01 사용자 허락을 받은 AI 파일에 Langfuse v4 계측을 추가했다. AI 설정의 `LANGFUSE_ENABLED` 기본값은 false다. true이면 앱 namespace Secret의 public/secret key와 Collector `/v1/traces` endpoint가 모두 필요하며, 빠진 값은 기동 오류로 드러난다. SDK는 LLM 시도마다 generation을 만들고 call type·프롬프트 버전·모델·토큰·오류 코드만 설정한다. 원문·학생 ID는 observation에 전달하지 않고, SDK가 생성한 span만 내보내도록 필터링한다. 기존 CloudEvents 사용량 데이터에는 `traceparent`만 연결한다. Collector 수신부터 Langfuse 저장·조회까지는 #185 환경에서 별도 검증해야 한다. core·learning·scoring·report의 기반영 서비스 파일 수정은 이번 허락 범위에 포함되지 않는다.

## 검증·완료 판정

현재 이 문서는 구현 중 설계 기록이다. 공식 SHA256을 대조한 Helm v4.3.1로 여섯 앱 values와 관측 chart의 `helm lint`·`helm template`이 각각 통과했다. 렌더된 YAML에서 Deployment·NetworkPolicy·migration Job, core Ingress·probe, AI의 core URL·probe, report-worker의 분리 명령과 두 KEDA 큐를 대조했다. local/Argo/policy 파일 18개는 PyYAML 구문 검사를 통과했고 `git diff --check`는 오류 없이 종료했다. Secret 값 없이도 렌더되며, 아래의 전용 클러스터에서는 새 합성 값의 Secret 3개를 실제로 준비했다.

전용 kind Node/CNI·Ingress, platform-data Pod/초기화 Job·PVC, core/learning Flyway·report Alembic Job, 합성 Pod 기반 NetworkPolicy 허용·차단을 아래 범위에서 실제 확인했다. KEDA/HPA/PDB는 **합성 부하**, Collector→Prometheus→Grafana 기반은 합성 지표와 실제 core·learning JVM/HTTP 지표로 검증했다. 실제 core·AI·learning·report-api readiness, AI 두 레플리카 버전 일치·초기 조회 실패/복구·Rabbit 재연결, report-worker 두 큐 바인딩도 확인했다. AI Langfuse SDK는 메모리 내 exporter로 호출별 메타데이터와 `traceparent` 연결을 검증했다. **전체 서비스 동시 기동, scoring 실제 앱, 활성 버전 이벤트, Argo sync, SSE 종료, 실제 LLM·report 생성, Langfuse trace 저장·조회는 미검증이다.** 실제 Langfuse 수집이 남아 있어 이슈 #171 전체 완료로 보고하지 않는다.

## #68 브랜치 대조 (2026-10-31)

`feature/ai-active-version-events`의 `d2deda0d4d01e88699d420ad938c094527806459`(로컬 원격 추적 브랜치와 동일)을 기준 커밋 `cc2ccc6`과 비교했다. #68은 AI `bootstrap.py`·`health/router.py`·버전 소비자·프롬프트 경로와 API/설계 문서를 바꿨다. #171은 AI 앱·의존성·Dockerfile을 수정하지 않았다. #171의 `CORE_URL`, RabbitMQ 5672와 AI→core 8080 정책, `/health/ready` probe는 #68의 큐 바인딩 → core snapshot → 준비 상태 흐름과 맞는다. probe는 캐시된 readiness만 호출해 매 요청마다 core를 조회하지 않는다.

두 브랜치에서 함께 바뀐 파일은 `docs/README.md`와 `docs/design/architecture.md`뿐이다. 두 파일의 기준·#171 작업 트리·#68 브랜치를 `git merge-file -p --diff3`로 대조했으며 충돌 마커 없이 종료 코드 0이었다. 이는 문서 내용의 3-way 결합 가능성 검사였고, 아래의 최신 develop 반영과 실제 서비스 통합 테스트는 별도로 구분한다.

2026-10-31 [#68 PR #194](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/pull/194)가 `develop`에 병합됐다. #171의 미커밋 파일은 고유 stash에 보존한 뒤 clean 브랜치를 `origin/develop`로 fast-forward하고 같은 stash를 적용했다. `docs/README.md`·`docs/design/architecture.md`는 자동 병합됐고 미해결 충돌은 없었다. 위 3-way 검사는 병합 전 사전 점검 결과다. 2026-11-01에는 사용자 허락에 따라 병합본 AI의 설정·lifespan·LLM 공통 호출·사용량 이벤트 발행에 #171 계측을 더했다. #68의 버전 소비·readiness 계약은 유지하고 관련 회귀 검증을 최종 검증 단계에 포함한다.

2026-11-01 [#195·#196 PR #198](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/pull/198)과 [AI 테스트 PR #197](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/pull/197)이 `develop`에 병합된 것을 확인했다. #198은 core·web·API 문서와 관련 테스트를, #197은 AI 테스트 파일을 변경했다. #171 수정 파일과 경로가 겹치지 않아 작업 트리를 유지한 채 `origin/develop`의 `2db122c2b4a973e1d9c8b267893cf45b03d2c3d6`로 fast-forward했다. 충돌은 없었고, 이 기준의 AI 전체 302개 테스트가 통과했다. #198의 새 `/auth/student/logout`과 상세 응답 캐시 정책은 core Ingress의 기존 `/api` 경로에 포함된다. #171이 이 공개 API나 core 코드를 바꾸지는 않는다.

같은 날 전용 kind 실행 전 읽기 검사에서 Docker Desktop Linux Engine pipe가 없어 `docker ps/info/network ls`가 실패했고 기존 kind API `127.0.0.1:6443`도 연결 거부를 반환했다. 별도 16443·18080·18443·19000 포트는 LISTEN 상태가 관찰되지 않았다. Docker Desktop 재시작이나 기존 클러스터 기동·중단은 수행하지 않았다. 따라서 새 클러스터 생성·이미지 빌드·Pod/NetworkPolicy/Argo/KEDA/수집 실동작 검증은 미실행이다.

이후 사용자가 Docker Desktop을 다시 실행했다. 기존 `sagomungchi-local-control-plane`이 자동 기동해 약 2.26GiB를 사용했고, 사용자 명시 허락을 받아 해당 노드 컨테이너만 `docker stop --timeout 30`으로 일시 중지했다. PVC·Secret·Docker 네트워크를 삭제하거나 수정하지 않았다. 중지 직후 다른 작업의 `issue35-verify-*`와 `issue195-core-test` 컨테이너가 실행 중이며, 읽기 시점의 Windows 가용 메모리는 약 0.8~2.3GiB로 변동했다. C: 여유는 약 17.3GB이고 Docker 이미지·볼륨 정리는 수행하지 않았다. 이 상태에서 별도 클러스터를 시작하면 자원 경합 우려가 있어 아직 생성하지 않았다. 공식 SHA256을 확인한 kind v0.33.0 실행 파일만 임시 폴더에 준비했다.

사용자가 동시 진행을 요청한 뒤 2026-10-31 전용 Docker 네트워크 `kind-issue171`(`172.30.0.0/16`)과 `sagomungchi-issue171` kind 클러스터를 새로 생성했다. API/Ingress 포트는 16443/18080/18443, Pod/Service CIDR는 `10.245.0.0/16`/`10.112.0.0/12`다. kind가 공유 kubectl 기본 context를 바꾼 직후 원래 `kind-sagomungchi-local`로 복구했고, 이후 모든 Kubernetes 호출에 전용 context를 명시했다. 전용 Calico v3.33.0 CRD·Operator·Installation을 적용한 뒤 Node Ready, CoreDNS·Calico Pod Ready를 확인했다. 기존 platform-data·Secret·PVC에는 접근하거나 적용하지 않았다.

Calico가 기동된 시점에 다른 작업의 검증 컨테이너가 추가로 실행돼 전용 노드 메모리 약 2.12GiB, 호스트 가용 물리 메모리 약 1GiB였다. Ingress·저장소·앱을 더 올리면 자원 경합 위험이 있어 **전용 노드만** `docker stop --timeout 30 sagomungchi-issue171-control-plane`으로 중지했다. 전용 네트워크·클러스터와 Calico 상태는 삭제하지 않고 보존했다. 이 시점에는 Node/CNI만 실제 확인했으며 후속 검증은 아래와 같다.

## 전용 kind 후속 실제 검증 (2026-10-31)

다른 Docker 컨테이너가 종료된 뒤 전용 노드를 다시 시작했고 Node·Calico·CoreDNS Ready를 확인했다. ingress-nginx chart 4.15.1/controller v1.15.1을 전용 클러스터에 설치해 controller 1/1 Ready와 loopback 18080 경로를 확인했다. 앱 chart의 합성 core·AI 릴리스는 캐시한 Python 이미지를 사용하고 비밀 env·migration·Java agent·probe를 시험용 values로 끈 **대역**이다. 외부 `Host: api.sagomungchi.local` 요청 `/api/`는 `200 issue171-ok`, 합성 AI Pod → core Service도 `200`이었다. 직접 Service `/internal/`은 `200`이었지만 외부 Ingress의 `/internal/`은 nginx `404`였다. 기본 거부만 적용한 Pod → core ClusterIP 요청은 차단됐다. 이 결과는 실제 core/AI 앱의 인증·readiness나 운영 ALB를 검증한 것이 아니다. 합성 릴리스·Pod는 제거했다.

전용 클러스터에 새로 생성한 합성 계정으로 platform/app/observability Secret을 준비했다. platform-data는 메모리 때문에 먼저 PostgreSQL·RabbitMQ만 설치하고, 자원을 확인한 뒤 원래 local values로 Redis·MinIO를 추가했다. 최종적으로 네 Pod가 모두 Ready, RabbitMQ·MinIO 초기화 Job 2개가 Complete, PVC 4개가 Bound였다. **실제 버킷 목록·자격 증명 회전·애플리케이션 저장 성공**까지 뜻하지 않는다. 기존 공유 클러스터의 Secret·PVC·버킷은 변경하지 않았다.

core/learning SQL을 담은 전용 Flyway 이미지를 각각 `issue171/*-migrate:local`로 빌드해 전용 노드에 로드했다. 앱 namespace 기본 거부와 chart의 migration 허용 NetworkPolicy를 함께 적용한 뒤 Job 완료를 확인했다. core는 성공 migration 17개와 최종 버전 `19`, learning은 7개와 최종 버전 `7`을 Job 로그 및 각 DB `flyway_schema_history`로 대조했다. 실패 무시나 앱 기동 시 migration은 사용하지 않았다. 향후 Helm/Argo 리소스 소유권 충돌을 막기 위해 수동 적용한 시험 Job·Policy·Pod를 제거했으며 DB·Secret·PVC는 보존했다.

실제 Calico 정책에서 core 라벨 Pod → PostgreSQL 5432·RabbitMQ 5672/15672·Redis 6379는 연결됐고 core → MinIO 9000은 차단됐다. scoring 라벨 Pod → MinIO 9000은 연결됐고 scoring → PostgreSQL 5432는 차단됐다. 허용 대상은 정상 포트의 실제 platform Pod였고, 차단 대상은 DNS를 우회해 Service ClusterIP로 직접 시험했다. 시험 Pod와 수동 적용한 app/platform NetworkPolicy는 제거했다. 이 부분은 **local Calico의 두 서비스 라벨 경로**에 대한 검증이며 전체 4.3 표, 운영 VPC CNI 및 실제 서비스 호출 경로를 보장하지 않는다.

Docker의 다중 플랫폼 캐시 이미지를 `kind load docker-image`로 직접 로드할 때 누락 digest 오류가 발생했다. 시험용 이미지는 `docker image save --platform linux/amd64` archive를 만든 뒤 전용 kind에 로드해 해결했고, 기반 이미지·다른 작업 태그는 변경하지 않았다. full platform 기동 후 Windows 가용 물리 메모리는 약 0.8~1GiB, C: 여유는 약 16GB였다. 이 시점에는 실제 앱 전체·Argo·KEDA·관측을 동시에 추가하지 않았다.

### KEDA·HPA·PDB 대역 검증

KEDA chart 2.21.0의 operator·metrics API·admission webhook 3개가 전용 클러스터에서 Ready였다. report-worker chart를 Python `sleep` 명령과 32Mi request의 합성 Deployment로 실행하고, 기존 `app-service-credentials`의 AMQP URL을 TriggerAuthentication에 연결했다. `report.report.generate`와 `report.student.deleted`가 모두 비어 있을 때 ScaledObject `Ready=True, Active=False`, Deployment 0개였다. 전용 RabbitMQ 관리 API로 각 큐에 합성 메시지 1개를 넣을 때마다 `Active=True`, Deployment 1개 Available로 확장됐고, 메시지를 ACK로 제거한 뒤 30초 시험 cooldown 이내에 0개로 축소됐다. 삭제 이벤트는 정의된 fan-out에 따라 `learning.student.deleted`에도 들어갔으며 두 큐의 합성 메시지를 모두 ACK했다. 세 큐의 Ready 메시지 수가 0인 것을 다시 확인했다. 첫 관리 API 시도는 문서의 `PUT`에 405를 반환해, 큐 길이 0을 확인한 후 해당 서버가 허용하는 `POST`로 게시했다. **실제 report-worker의 소비·LLM 동시 호출·prefetch 상한은 검증하지 않았다.** 시험 릴리스·helper Pod와 전용 KEDA 릴리스는 정리했다.

metrics-server chart 3.14.0/app 0.9.0을 kind kubelet TLS 시험 설정으로 설치하고 `kubectl top nodes` 응답을 확인했다. 저장소 `hpa-check-values.yaml`을 CPU request 10m·limit 100m의 합성 Python Deployment에 적용했다. CPU 지표가 `1010%/70%`일 때 HPA가 replica 1→2, Deployment Available 2/2로 확장됐다. PDB `minAvailable:1`의 `ALLOWED DISRUPTIONS`은 replica 1에서 0, replica 2에서 1로 바뀌었다. 노드 drain·실제 core SSE 종료는 실행하지 않았다. CPU 부하 시험 릴리스와 metrics-server는 정리했다.

### 로컬 관측 대역 검증

관측 chart를 전용 `observability` namespace에 설치해 Collector·Prometheus·Grafana가 1/1 Ready였다. Grafana 13.3.0은 첫 기동의 초기 migration·API 준비가 60초 startupProbe를 넘겨 한 차례 재시작했다. startup 허용을 300초로 늘린 뒤 Ready가 됐다. 저메모리 환경에서 RollingUpdate가 Grafana Pod 두 개를 겹쳐 유지하므로 chart를 `Recreate`로 수정했다. 첫 Helm upgrade는 기존 Deployment의 `rollingUpdate` 필드가 남아 API 검증에 실패했고, 전용 Deployment에서 그 필드만 제거해 전략을 맞춘 뒤 재실행해 revision 3이 성공했다. 마지막 상태는 세 Pod 1/1 Ready, Grafana `Recreate`·startup threshold 60이다.

Prometheus API의 active targets에서 RabbitMQ 15692와 Collector 8889가 모두 `health=up`, PromQL `up=1`이었다. OTLP/HTTP JSON으로 학생·서비스 데이터가 없는 합성 gauge 값 7을 Collector 4318에 보내 HTTP 200을 받았다. 첫 PromQL은 원래 이름으로 조회해 빈 결과였으나, Collector exporter가 단위 `1`을 반영한 `issue171_synthetic_gauge_ratio` 시계열을 확인해 값 7을 조회했다. Grafana 자기 API에는 Prometheus가 기본 datasource로 등록돼 있었다. 임시 loopback port-forward는 종료했다. 이 시점에는 실제 core·learning Java agent 지표를 확인하지 않았으며 아래 후속 결과와 구분한다. Python 서비스 지표, Langfuse 저장·조회와 운영 보존성은 여전히 미검증이다.

## 실제 서비스 통합 검증 (2026-10-31)

리소스 경합을 피하려고 전용 노드를 잠시 중지한 상태에서 현재 `develop`의 core·AI·learning·report Dockerfile을 각각 `docker build --pull=false`로 빌드했다. 전용 태그는 `issue171/{core-service,ai-service,learning-service,report-service}:local`이고 모두 빌드가 성공했다. core·learning 빌드는 기존 Dockerfile대로 `bootJar -x test`이므로 단위 테스트 통과를 뜻하지 않는다. Docker의 다중 플랫폼 archive 문제를 피하려고 linux/amd64 archive로 전용 노드에만 로드했다. 이 이미지는 GHCR/ECR 게시 결과가 아니다.

실제 core Pod는 기존 core Flyway v19 DB·RabbitMQ·Redis와 합성 Secret을 사용해 1/1 Ready, 재시작 0이었다. #68 병합본 AI Pod도 1/1 Ready이고 `/health/ready`가 `rabbitmq=UP, versions=UP`, AI→core readiness가 HTTP 200이었다. AI를 0개로 내린 뒤 core를 중지하고 새 AI Pod만 띄우자 프로세스는 Running을 유지하면서 `503, rabbitmq=UP, versions=DOWN`이었다. core를 복구하자 Pod 재시작 없이 `200, versions=UP`으로 전환됐다. AI를 2개로 확장한 때 두 Pod 모두 Ready·재시작 0, `/internal/versions`의 네 프롬프트 버전(`analysis@2`, `followup@4`, `judge@2`, `report@1`)이 일치했다. RabbitMQ에는 소비자 1개씩의 서로 다른 exclusive 큐 2개가 있었다.

전용 RabbitMQ StatefulSet만 PVC를 유지하며 0개로 내렸을 때 AI 두 Pod는 모두 `503 versions=DOWN`이었다. 다시 1개로 복구하자 두 Pod가 재시작 없이 Ready로 돌아오고 이전과 다른 exclusive 큐 2개를 바인딩했으며 프롬프트 버전도 다시 일치했다. 이 테스트의 core 활성 목록은 비어 있어 내장 프롬프트 버전 기준이다. **실제 관리자 활성화 이벤트·미보유 프롬프트·외부 LLM 호출·토큰 사용량 trace**는 검증하지 않았다. AI는 로컬 기본 레플리카 1개로 되돌렸다.

core Ingress controller를 잠시 1개로 복구한 뒤 실제 공개 `/api/v1/me` 요청은 인증되지 않은 상태의 `401 UNAUTHENTICATED` Problem Details를 반환했고, 외부 `/internal/model-versions/active`는 nginx `404`였다. 공개 API의 인증 흐름 전체나 active SSE 연결 종료는 검증하지 않았다.

실제 core 이미지에 chart의 고정 Java agent initContainer를 적용해 1/1 Ready, 재시작 0을 확인했다. Prometheus `target_info`에는 `exported_job=core-service`, agent `2.33.1`이 기록됐고, 같은 라벨의 JVM 메모리 시계열 8개와 HTTP 요청 집계 17을 조회했다(조회 시점의 누적값). 같은 방식으로 실제 learning 이미지도 Flyway v7 DB·RabbitMQ 아래 1/1 Ready, `/actuator/health/readiness=UP`, 재시작 0이었다. `exported_job=learning-service` 지표에서 JVM 메모리 시계열 8개와 HTTP 요청 집계 8을 조회했다. 두 서비스의 기존 Gradle·application 파일은 변경하지 않았다. 수집 경로는 이 로컬 Java agent → Collector OTLP → Prometheus이며 trace export는 꺼져 있다.

report 이미지의 Alembic Job 첫 실행은 합성 DB 비밀번호를 URL 인코딩한 `%`가 기존 `migrations/env.py`의 `ConfigParser.set_main_option` 보간과 충돌해 실패했다. 실패 예외에 **전용 클러스터 테스트 계정의 URL 일부가 출력**됐다. 실제 또는 공유 계정은 사용하지 않았고 이 합성 값을 다른 환경에서 재사용하지 않는다. 기존 report 소스를 바꾸지 않고, #171 Secret 준비 스크립트가 일반 `REPORT_DATABASE_URL`과 `%`를 `%%`로 변환한 Job 전용 `REPORT_ALEMBIC_DATABASE_URL`을 만들도록 수정했다. 전용 클러스터의 기존 Secret 값은 모두 유지하고 새 키만 stdin을 통해 추가했다. 실패 Job만 삭제·재생성한 뒤 Alembic upgrade가 `20261030_04`까지 완료됐고 `report_db.alembic_version`에서 대조했다. 실제 report-api는 일반 URL을 사용해 `/health/ready=200, database=UP`, MinIO report 버킷 `HeadBucket`도 성공했다.

같은 report 이미지의 기존 `python -m app.worker`를 별도 Deployment로 1개 실행했을 때 `CONSUMER_PREFETCH=1`, RabbitMQ `report.report.generate`·`report.student.deleted`의 소비자가 각각 1개였다. 기동 초기 `report.student.deleted` 바인딩 재시도 경고가 한 차례 있었으나 두 구독이 연결됐다. worker를 0개로 내리자 두 큐의 소비자와 unacked 수가 모두 0이 됐다. **실제 생성 명령 소비·learning/AI 호출·PDF 작성·LLM 동시 호출**은 실행하지 않았다. 시험 뒤 앱 Helm 릴리스와 수동 Alembic Job·Policy만 제거했고 DB·Secret·PVC는 보존했다.

전용 노드는 메모리 회수를 위해 다시 중지했다. Ingress controller는 설정대로 1개로 복구한 상태에서 노드를 중지했고, MinIO도 기존 PVC로 1개 복구했다. 관측·KEDA·metrics-server 시험 릴리스와 임시 이미지 archive·values·포트 포워딩은 정리했다. 기존 `sagomungchi-local` 클러스터, 다른 작업 컨테이너와 데이터는 정리하거나 덮어쓰지 않았다. Argo CD local sync, 실제 서비스 전체 동시 기동, 운영 EKS·Langfuse 및 배포 CI/롤백은 아직 미검증이다.

### scoring 이미지와 자원 중단점

현재 develop의 scoring-service Dockerfile도 `docker build --pull=false -t issue171/scoring-service:local`로 빌드에 성공했다. CPU용 PyTorch 2.14.1, Transformers 5.21.0 등이 lockfile에서 설치됐다. 그러나 빌드 후 C: 여유 약 6.7GB, 호스트 가용 메모리 약 0.62GiB였고, linux/amd64 archive 저장·전용 노드 재시작 뒤에는 C: 약 5.7GB·호스트 약 0.43GiB였다. PostgreSQL·Redis·MinIO와 Ingress controller를 **전용 클러스터에서만** 일시 0개로 줄였지만 여유가 회복되지 않아 scoring 이미지를 kind에 풀거나 Pod를 실행하지 않았다. archive는 삭제해 디스크를 회수했고 빌드된 `issue171/scoring-service:local` 이미지만 남겼다. scoring readiness·실제 모델 artifact 로딩·AI→scoring 경로는 미검증이다.

이 자원 중단점 이후 `sagomungchi-issue171-control-plane`을 중지했다. 전용 클러스터에는 PostgreSQL·Redis·MinIO StatefulSet과 ingress-nginx controller의 replica가 0으로 남아 있고, RabbitMQ는 설정상 1이다(노드 중지로 실행 중인 Pod 없음). 전용 플랫폼 PVC 4개·Secret 3개·Docker 네트워크와 이미지 태그는 보존했다. 재개할 때 전용 노드만 시작하고 자원 여유를 확인한 뒤 축소한 StatefulSet·Ingress controller를 1개로 되돌려야 한다. 공유 `sagomungchi-local` 및 다른 작업 자원에는 이 단계에서 변경을 가하지 않았다.

2026-11-01 재확인 시 Docker의 `on-failure` 정책 때문에 공유·전용 kind 노드가 모두 실행 중이었고, #35 검증용 Compose 컨테이너도 실행 중이었다. 이 작업에서는 어느 컨테이너도 중지·재설정하지 않았다. C: 여유는 약 5.5GB이므로 새 AI 이미지 빌드·scoring 이미지 로드·전체 앱 동시 기동은 진행하지 않았다. 전용 클러스터에서 앞서 0으로 줄인 PostgreSQL·Redis·MinIO·Ingress controller의 desired replica는 복구 검증 전까지 0인 상태로 취급한다. 별도 AI Python 환경에서 `uv sync --frozen`, `uv lock --check`, AI 전체 `pytest -q` 302개는 통과했다. 새 Langfuse SDK의 메모리 내 exporter 테스트는 두 번의 재시도 시도·스트리밍·토큰·오류·부모 span ID를 확인했고 학생 ID·시스템/사용자 프롬프트·응답 조각이 span 속성에 없음을 확인했다. 이 검증은 실제 Collector OTLP 수신이나 Langfuse 저장 검증이 아니다.

### #35 종료 후 새 AI 이미지 재검증 (2026-11-01)

#35 Compose 검증 종료를 사용자에게 확인받은 뒤 공유 `sagomungchi-local-control-plane`만 기존 허락대로 일시 중지했다. 전용 노드를 잠시 중지해 새 `issue171/ai-service:local` 이미지를 `docker build --pull=false`로 빌드했고, 잠금 파일의 Langfuse 4.18.0과 OTLP HTTP exporter가 이미지에 설치된 것을 빌드 로그에서 확인했다. 합성 로컬 OTLP/HTTP 수신기로 실제 exporter 전송 200·generation span 1개와 프롬프트·응답 원문 비전송을 확인했다. 새 이미지의 별도 `--network none` 컨테이너에서는 합성 키로 `LANGFUSE_ENABLED=true` 기동·종료가 성공했고, 의도대로 `/health/live=200`, 연결 대상이 없는 `/health/ready=503`이었다. 이 시험은 Langfuse backend 저장 결과가 아니다.

이미지 archive를 전용 kind의 `/tmp`로 복사한 첫 시도는 별도 tmpfs 마운트 때문에 containerd에서 보이지 않았다. 전용 노드의 `/root`에만 linux/amd64 archive를 복사해 containerd에 등록했고, 호스트·노드의 해당 임시 archive를 지웠다. 처음 `/tmp` 마운트 아래에 숨었던 전용 시험 archive·작은 probe 파일도 별도 마운트 namespace에서 정확한 두 경로만 제거했으며, 원래 tmpfs 마운트와 다른 클러스터는 변경하지 않았다. `crictl images`에서 새 AI 이미지 ID `7b9ec52c5591`을 확인했다.

전용 PostgreSQL·Redis를 보존된 PVC로 1개씩 복구했다. 첫 core Helm 설치는 이전 단계에서 0개로 축소된 ingress-nginx admission webhook 연결 거부로 중단됐고, 전용 ingress controller를 1개로 복구한 뒤 다시 설치했다. 이번 재검증은 이미 완료된 Flyway를 다시 실행하지 않도록 `migration.enabled=false`, Collector가 없는 상태의 Java agent를 다시 시작하지 않도록 `javaAgent.enabled=false`, 이미지 repository는 `issue171/*`로만 임시 override했다. core·새 AI release는 1/1 Ready·재시작 0, AI `/health/ready`의 RabbitMQ·버전은 모두 UP, AI→core readiness는 200이었다. 실제 AI Pod의 이미지 ID가 새 빌드와 일치했다. AI를 잠시 2 Pod로 늘렸을 때 두 Pod가 같은 내장 네 프롬프트 버전을 반환하고 RabbitMQ에 각각 소비자 1명의 exclusive 큐가 생겼다. 검증 후 AI를 local 기본값 1 Pod로 복구했다.

이 시점의 전용 클러스터에는 core·AI, PostgreSQL·RabbitMQ·Redis, ingress controller가 실행 중이고 MinIO는 0개다. C: 여유는 약 3.6GB, Windows 가용 물리 메모리는 약 1.9GiB다. #35 컨테이너와 공유 kind는 실행하지 않는다. scoring 이미지의 kind 로드·실제 모델 readiness, Argo CD 설치·sync, Langfuse backend 저장·조회는 아직 진행하지 않았다. 호스트의 오래된 `issue171/report-service:local` 태그만 제거했으나 전용 kind의 report 이미지는 그대로 있다.

시험을 마친 core·AI Helm 릴리스만 전용 클러스터에서 제거했다. 전용 PostgreSQL·Redis와 ingress controller는 replica 0으로 돌리고 Pod 종료를 기다린 뒤 전용 노드를 중지했다. RabbitMQ 설정 replica 1, 전용 PVC·Secret·이미지 저장소는 유지했다. 앞서 허락받아 중지했던 공유 `sagomungchi-local-control-plane`은 다시 시작했다. 이후 C: 여유는 약 3.6GB다. 사용자와 scoring 이미지 로드·Argo CD 동기화 시험을 위해 C: 여유를 6GB 이상 확보한 뒤 재개하기로 조율했다. #171 파일은 아직 feature 브랜치에 미커밋·미푸시 상태이며 실제 Argo sync는 수행하지 않았다.

### 저장공간 확보 후 scoring·Argo 준비 (2026-11-01)

사용자가 C: 여유를 약 25GB로 확보했다. Docker 재시작으로 공유·전용 kind가 모두 실행됐지만 전용 노드의 호스트 포트 바인딩이 누락돼 `16443` API가 거부됐다. 기존 허락대로 공유 노드만 일시 중지하고 전용 노드만 재시작하자 설정된 `16443/18080/18443` 바인딩과 API Ready가 회복됐다. 기존 전용 PVC·Secret은 유지됐다. scoring의 기존 linux/amd64 이미지를 전용 containerd에 로드하고 임시 archive를 삭제했다. 원격 registry나 다른 작업 이미지 태그는 바꾸지 않았다.

전용 PostgreSQL·Redis·MinIO·Ingress controller를 각각 1개로 복구했다. #35 PR #198의 변경이 반영된 `origin/develop` 기준 core 이미지를 `docker build --pull=false`로 새로 빌드·로드했다. Dockerfile의 `bootJar -x test`는 성공했고 core 테스트 통과를 의미하지 않는다. 이 재검증에서도 완료된 Flyway를 중복 실행하지 않도록 `migration.enabled=false`, 현재 관측 릴리스가 없는 동안 `javaAgent.enabled=false`, 이미지 repository만 `issue171/*`로 임시 override했다. 실제 core·scoring Pod는 각각 1/1 Ready·재시작 0이었다. scoring `/health/ready`는 `rabbitmq=UP, models=UP`, 내부 버전 목록과 core 활성 모델 snapshot은 모두 빈 목록이었다. scoring Pod에서 MinIO의 `sagomungchi-local-models` 버킷 `HeadBucket`이 성공해 실제 egress와 인증 경로를 확인했다. 버킷에는 객체가 없으므로 **실제 모델 가중치 다운로드·CPU 로딩·추론은 검증하지 않았다**. 승인되지 않은 모델을 임의로 활성화하지 않았다.

공식 v3.5.5 Argo CD의 고정 버전 설치 manifest를 전용 kind에만 적용했고, application-controller·ApplicationSet controller·repo-server·server·Redis·Dex·notifications의 Pod 7개가 1/1 Ready였다. 클러스터 전체에 Argo CRD·RBAC가 추가되는 설치 범위이며 공유 kind에는 적용하지 않았다. root Application과 여섯 앱 등의 **실제 Git sync는 아직 수행하지 않았다**. 현재 `feature/infra-app-deployment` 파일이 미커밋·미푸시이므로 원격 Argo repo-server에서 읽을 수 없다. 검증된 작업을 feature 브랜치에 게시한 뒤, 전용 클러스터에서만 targetRevision을 해당 feature ref로 임시 지정해 sync를 확인해야 한다. 저장소에 기록하는 desired ref는 병합 후 `develop`을 유지한다.

### 원격 feature ref의 Argo CD 동기화 (2026-11-01)

검증된 #171 파일 59개만 `027ebc770461c9dec5ef4a85c49fe944b1526c0b`(`feat: 앱 배포와 관측 계측 구성`)으로 커밋해 `origin/feature/infra-app-deployment`에 push했다. PR은 생성하지 않았다. 전용 Argo CD root Application의 targetRevision만 임시로 feature ref로 적용하자 repo-server가 정확히 이 SHA를 읽었고 root sync가 Synced·Healthy로 완료됐다. 하위 파일의 Git 참조는 저장소의 병합 후 desired state인 `develop`이라, 전용 클러스터의 ApplicationSet·관측·platform 정책 Application만 임시 feature ref로 패치했다. 이 때문에 시험 중 root는 의도적으로 OutOfSync이며 원격 파일에는 feature ref를 저장하지 않는다.

KEDA Application의 첫 sync는 `scaledjobs.keda.sh` CRD가 client-side apply의 262144-byte annotation 한도를 넘겨 실패했다. `ServerSideApply=true`만으로는 이 Argo CD 3.5.5 시험에서 해결되지 않았다. KEDA chart의 `crds.additionalAnnotations`에 CRD 전용 `argocd.argoproj.io/sync-options: Replace=true`를 추가하자 같은 전용 클러스터에서 KEDA CRD와 operator 3 Pod가 Synced·Healthy가 됐다. local 전용 설정이며 KEDA 업그레이드 때 CRD 호환성을 별도로 확인해야 한다. platform NetworkPolicy Application은 Synced·Healthy였고 PostgreSQL·RabbitMQ·Redis·MinIO는 정책 적용 후에도 Ready였다.

관측 Application의 Collector·Prometheus는 즉시 Ready였지만 Grafana는 CPU 한도 `250m`에서 cgroup `nr_throttled=2827/2860`으로 거의 매 기간 제한돼 첫 300초 startup probe를 넘기고 재시작했다. local observability values에서 Grafana CPU 요청을 `100m`, 한도를 `1`로 올려 전용 Deployment에 같은 값을 적용하자 새 Pod가 재시작 0회로 Ready가 됐다. 이 수정이 원격 브랜치에 반영되기 전 관측 Application은 OutOfSync·Healthy였다. 반영 후 결과는 아래에 기록한다. Collector·Prometheus·Grafana의 실제 백엔드 저장 지속성이나 Langfuse trace 저장은 이 결과에 포함되지 않는다.

core·learning의 Argo PreSync Flyway Job은 각각 v19·v7에서 Complete, report-api의 Alembic Job은 `20261030_04`에서 Complete였다. core·learning·AI·scoring·report-api 하위 Application은 모두 Synced·Healthy, 실제 API Pod 5개는 각각 1/1 Ready·재시작 0이었다. report-worker Application도 Synced·Healthy이고 KEDA ScaledObject가 Ready였으며 빈 두 큐에서 worker Deployment는 설정대로 0/0이었다. metrics-server도 Synced·Healthy, `kubectl top node`가 CPU 766m·메모리 5630Mi(조회 시점)를 반환했다. 외부 Ingress는 `/api/v1/me`에 인증되지 않은 401, `/internal/model-versions/active`에 nginx 404를 반환했다. 실제 AI Pod에서 core·learning·scoring readiness가 모두 200, report-api의 DB readiness가 200, scoring Pod의 MinIO 버킷 접근이 성공했다. 실제 모델 버킷은 비어 있어 가중치 로딩·추론은 여전히 미검증이고, 실제 사용자 로그인·LLM·PDF 생성·SSE 진행 중 종료도 실행하지 않았다.

KEDA CRD·Grafana local 보완과 기록은 `2e25b7cb7e2efb07d73cc3188e45d69a7d4879af`(`fix: Argo KEDA CRD와 로컬 Grafana 기동 보완`)로 같은 feature 브랜치에 push했다. Argo repo-server가 새 SHA를 읽은 뒤 관측 Application은 수정된 Grafana CPU `1`과 live Deployment가 일치해 Synced·Healthy로 전환됐다. 마지막 조회에서 root 이외의 하위 Application 10개(KEDA·platform 정책·metrics-server·관측·여섯 앱)는 모두 Synced·Healthy였다. Grafana·Collector·Prometheus는 각 1/1 Ready이고 새 Grafana Pod는 재시작 0, core·learning·AI·scoring·report-api도 각 1/1 Ready였다. 세 migration Job은 Complete, report-worker는 빈 큐에서 0/0, ScaledObject는 Ready·Inactive였다. `kubectl top node`의 마지막 값은 CPU 647m·메모리 5486Mi(70%)였다. root만 전용 검증용 하위 targetRevision 패치 때문에 OutOfSync·Healthy이며, 저장소에는 병합 후 사용할 `develop` 참조를 유지한다. PR 생성·원격 CI·EKS 배포·실제 Langfuse 저장 조회는 수행하지 않았다.

## GitOps chart CI (#238)

[이슈 #238](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/238)에 따라 `.github/workflows/ci-gitops.yml`을 추가했다. `infrastructure/gitops/**`, migration 이미지가 복사하는 core·learning의 `db/migration/**`, 워크플로 파일이 바뀐 PR과 `develop`·`main` push에서 실행한다. 기존 chart·values·다른 워크플로는 수정하지 않았다.

### 검사 항목

| job | 검사 | 실패 조건 |
|---|---|---|
| charts | Helm v4.3.1·kubeconform v0.8.0을 공식 배포본에서 받아 SHA256 대조 | 체크섬 불일치 |
| charts | `environments/<env>/*.yaml`마다 `helm lint --strict`와 `helm template` | 렌더 실패, `values.schema.json` 위반, lint 경고 |
| charts | 렌더 결과와 `argocd/`·`policies/` 원본 manifest의 kubeconform `-strict` | 스키마 위반, 정의되지 않은 필드 |
| migrations | `migrations/*.Dockerfile`을 저장소 루트 context로 `docker build`(push 없음) | 빌드 실패 |

렌더 조합은 Argo CD 정의를 그대로 따른다. 환경 파일 이름과 같은 chart가 있으면(`observability`·`platform-data`) 그 chart, 나머지는 ApplicationSet처럼 파일 이름을 릴리스 이름으로 `app-service` chart에 넘긴다. namespace는 app-service `app`, observability `observability`, platform-data `platform`이다. platform-data는 Argo Application이 아니라 #17 README의 Helm 릴리스로 설치하지만 같은 환경 values로 함께 렌더한다. 새 chart를 추가하면 워크플로의 namespace 대응을 함께 넣어야 하며, 빠지면 CI가 오류로 알린다. 의존 chart가 있으면 `helm dependency build`를 먼저 실행한다(현재 세 chart 모두 없음).

`app-service` 기본 values는 `image.repository`가 빈 문자열이라 환경 values 없이 단독 lint하면 자체 스키마의 `minLength`에서 실패한다. 환경별 이미지를 반드시 넣게 한 설계이므로 chart 오류로 보지 않았다. chart lint는 실제 배포 조합으로 하고, 어떤 환경 파일도 쓰지 않는 chart만 기본 values로 lint한다.

### CRD 처리 결정

kubeconform은 기본 Kubernetes 스키마와 공개 CRD 카탈로그를 순서대로 찾고, 둘 다 없는 종류만 `-ignore-missing-schemas`로 건너뛴다. 이 방식은 KEDA·Argo CD 리소스도 실제 필드까지 검사하면서, 아직 카탈로그에 없는 CRD를 추가할 때 CI가 막히지 않는다. CRD 스키마를 저장소에 복사하는 방식은 KEDA·Argo 업그레이드마다 별도 갱신이 필요해 택하지 않았다. 건너뛴 리소스는 `Kind/이름 (파일)` 목록과 경고 annotation으로 남는다.

| 항목 | 고정 값 | 근거 |
|---|---|---|
| Kubernetes 스키마 | [yannh/kubernetes-json-schema](https://github.com/yannh/kubernetes-json-schema) `e0c72a1`의 `v1.35.8-standalone-strict` | kind 노드 이미지 v1.35.8([local-platform](local-platform.md))과 같은 버전 |
| CRD 스키마 | [datreeio/CRDs-catalog](https://github.com/datreeio/CRDs-catalog) `27233a5` | KEDA 2.21.0 CRD 갱신(2026-11-01)을 포함하고 Argo CD `Application`·`ApplicationSet`이 있음 |

두 저장소는 커밋 SHA로 고정했으므로 upstream 변경이 CI 결과를 바꾸지 않는다. KEDA chart 버전을 올리면 카탈로그 커밋도 같은 버전 이후로 갱신한다. 카탈로그의 Argo CD 스키마 버전과 전용 kind에 설치한 v3.5.5의 일치 여부는 확인하지 않았다.

### 로컬 실행

Linux 셸(WSL 또는 컨테이너)에서 위 두 도구를 같은 버전으로 설치한 뒤 저장소 루트에서 실행한다. 워크플로의 run 블록과 같은 명령이다.

```bash
cd infrastructure/gitops
out=/tmp/gitops-rendered; mkdir -p "$out/local"
for values in environments/local/*.yaml; do
  release="$(basename "$values" .yaml)"
  if [ -d "charts/$release" ]; then chart="$release"; else chart=app-service; fi
  case "$chart" in app-service) ns=app ;; observability) ns=observability ;; platform-data) ns=platform ;; esac
  helm lint --strict "charts/$chart" --namespace "$ns" -f "$values"
  helm template "$release" "charts/$chart" --namespace "$ns" --kube-version 1.35.8 -f "$values" > "$out/local/$release.yaml"
done
kubeconform -strict -summary -kubernetes-version 1.35.8 \
  -schema-location 'https://raw.githubusercontent.com/yannh/kubernetes-json-schema/e0c72a1bc5f409d1685c0e1323460c8a98cd7459/{{.NormalizedKubernetesVersion}}-standalone{{.StrictSuffix}}/{{.ResourceKind}}{{.KindSuffix}}.json' \
  -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/27233a506de0085e71c7f9702597806a7f95eb24/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json' \
  -ignore-missing-schemas "$out" argocd policies
```

migration 이미지는 저장소 루트에서 `docker build -f infrastructure/gitops/migrations/core.Dockerfile .`처럼 확인한다.

### 검사하지 않는 항목

- Argo CD가 받는 외부 chart(KEDA 2.21.0, metrics-server 3.14.0)의 렌더링. 외부 저장소 다운로드가 필요하고 저장소 변경으로 바뀌지 않는다.
- 실제 클러스터 적용, Argo sync, admission webhook·NetworkPolicy 동작. 스키마 검사는 필드 형식만 본다.
- migration 이미지의 실행·게시. 빌드만 확인하며 레지스트리 push와 태그 갱신은 #186 범위다.
- `kubeconform -strict`는 manifest의 정의되지 않은 필드를 잡지만, values의 오타는 그 값이 렌더되는 경로에서만 드러난다. 스키마가 있는 `app-service`만 values 단계에서 막는다.

### 검증 (2026-11-02)

워크플로 charts job의 env와 run 블록을 그대로 추출해 전용 `buildpack-deps:noble-curl` 컨테이너(저장소 읽기 전용 mount)에서 실행했다. 두 도구의 SHA256이 일치했고, local 환경 파일 8개의 lint·template가 통과했다. kubeconform은 15개 파일 76개 리소스를 검사해 Valid 76, Skipped 0이었다. `ScaledObject`·`TriggerAuthentication`·`Application`·`ApplicationSet`도 카탈로그 스키마로 실제 검사됐다.

일부러 넣은 값 오류는 `infrastructure/gitops` 복사본에만 넣고 같은 컨테이너 명령을 실행했다. 저장소 파일은 바꾸지 않았다.

| 사례 | 변경 | 결과 |
|---|---|---|
| 스키마 타입 오류 | `ai-service.yaml`의 `replicaCount: "one"` | `helm lint`가 `/replicaCount: got string, want integer`로 실패, 종료 코드 1 |
| 스키마 없는 chart 필드 오타 | `observability.yaml` Grafana `limits` → `limit` | lint·template는 통과, kubeconform이 `additional properties 'limit' not allowed`로 실패, 종료 코드 1 |
| 카탈로그에 없는 CRD | 임의의 `example.invalid/v1` `Widget` 추가 | 통과, `Widget/probe` 건너뜀 목록과 경고 출력 |

migration Dockerfile 2개는 전용 임시 태그로 빌드에 성공했고 태그는 삭제했다. actionlint 1.7.12(shellcheck 포함)는 `ci-gitops.yml`에서 오류가 없었다. 원격 GitHub Actions 결과는 브랜치 push 후 별도로 확인한다.

## kind 클러스터 통합 (#273)

#171은 병합 전 chart를 기존 `sagomungchi-local`의 platform-data·PVC와 분리해 시험하려고 전용 `sagomungchi-issue171` 클러스터와 전용 Secret 원본을 두었다. 두 클러스터는 호스트 포트(80/443 ↔ 18080/18443)와 Pod/Service CIDR만 달랐고 Kubernetes·Calico·Ingress 버전은 같았다. #171 병합 후에도 이 분리가 정식 절차로 남아 앱 배포 경로가 전용 클러스터에만 있었고, Secret 원본도 루트 `.env`와 별도 파일로 나뉘었다. Docker 메모리 한도(약 7.6GiB)에서는 두 클러스터를 동시에 운영하기 어렵다.

로컬 kind는 `sagomungchi-local` 하나로 통합한다.

| 항목 | 변경 |
|---|---|
| 앱 Secret | `create-issue-171-secrets.ps1` → `create-app-secrets.ps1`. 대상 context·노드를 `kind-sagomungchi-local`·`sagomungchi-local-control-plane`으로 고정 검사하고 기본 입력을 루트 `.env`로 한다. UTF-8 stdin 전달, 기존 Secret 값 대조 후 불일치 시 중단은 유지한다 |
| platform Secret | 기존 `create-platform-secret.ps1`이 계속 담당한다. 두 스크립트가 같은 `.env`를 읽어 platform·app 계정 원본이 하나가 된다 |
| 관측 Secret | `.env`에 `GRAFANA_ADMIN_USER`·`GRAFANA_ADMIN_PASSWORD`가 둘 다 있을 때만 만든다. 하나만 있으면 실패한다 |
| 제거 | `issue-171-verification.yaml`, `calico-issue-171-installation.yaml`, `issue-171-secrets.env.example`, `README-issue-171.md`. 유지할 이미지 로드·context 명시·기동 순서는 [kind 안내](../../infrastructure/kind/README.md) 5절로 옮겼다 |
| 적용 대상 문구 | chart·local Argo CD 안내의 "기존 클러스터 적용 금지"를 `sagomungchi-local` 정식 절차로 바꿨다 |

누락 환경값(Google·토스·LLM 공급자 등)과 외부 egress는 #236 범위로 남긴다. 이 절 위의 검증 기록은 당시 전용 클러스터 기준이다. 이미 만들어진 `sagomungchi-issue171` 클러스터·Docker 네트워크 `kind-issue171`은 저장소 변경과 별개이며, 담당자가 직접 `kind delete cluster --name sagomungchi-issue171`과 `docker network rm kind-issue171`로 정리한다.

## kind 환경값·외부 egress 보완 (#236)

kind/GitOps local values가 `compose.yaml`보다 적어 클러스터에서 Google 로그인·토스 결제·LLM 판정이 동작하지 않았다. 위 "외부 LLM·토스 호출을 허용하는 local stub이 아직 저장소에 없으므로" 결정은 이 절로 대체한다.

### compose 대비 환경값 차이 (develop f6250bd 기준)

| 서비스 | compose에만 있던 값 | 처리 |
|---|---|---|
| core | `GOOGLE_CLIENT_ID`·`GOOGLE_CLIENT_SECRET` | 앱 Secret 선택 키 |
| core | `TOSS_TEST_SECRET_KEY`·`TOSSPAYMENTS_SECRET_KEY`·`TOSS_TEST_MID`·`TOSS_TEST_WEBHOOK_SECURITY_KEY`, 빌링 `TOSS_TEST_BILLING_*` 3종 | 앱 Secret 선택 키, `live_` 키 거부 |
| core | `PAYMENT_BILLING_ENCRYPTION_KEY`·`PAYMENT_FREE_PRODUCT_ID` | 앱 Secret 선택 키 (상품 UUID는 환경마다 다름) |
| core | `AUTH_ACCESS_TTL`·`AUTH_STUDENT_ACCESS_TTL`·`AUTH_REAUTH_TTL`·`AUTH_REFRESH_TTL`·`REDIS_PORT`·`STUDENT_DEVICE_TTL`·`STUDENT_DEVICE_ATTEMPT_LIMIT` | values에 compose 기본값 |
| core | `REDIS_PASSWORD` | 추가하지 않음. compose·platform-data Redis 모두 비밀번호 없음 |
| ai | `LLM_PROVIDER`·`OPENAI_MODEL`·`OPENAI_JSON_MODE`·`ANTHROPIC_MODEL`·`ANTHROPIC_EFFORT`·`ANTHROPIC_FALLBACK` | values에 compose 기본값 (`LLM_PROVIDER=openai`) |
| ai | `ANTHROPIC_API_KEY` | 앱 Secret 선택 키 (`OPENAI_API_KEY`는 기존 선택 키) |
| ai | `OPENAI_BASE_URL` | 추가하지 않음. compose 기본값이 빈 값(OpenAI 기본 주소)이고 sLLM 사용 시에만 필요 |
| report-api | `REPORT_DOWNLOAD_TTL_SECONDS` | 추가하지 않음. 앱 기본값 300과 compose 기본값이 같음 |
| report-api | `RABBITMQ_URL` | 추가하지 않음. 메시지 소비는 report-worker만 하며 worker values에 있음 |
| learning·scoring | 없음 | — |

### 결정

- 외부 키는 루트 `.env` 하나를 원본으로 `create-app-secrets.ps1`이 값이 있을 때만 앱 Secret에 복사한다. values는 `optional: true`로 참조해 키가 없으면 환경 변수를 만들지 않는다(compose의 빈 기본값과 같은 동작).
- egress: core·ai에만 `0.0.0.0/0`에서 사설(10/8·172.16/12·192.168/16)·CGNAT(100.64/10)·link-local(169.254/16)·loopback을 뺀 TCP 443을 허용한다. Calico 오픈소스판과 기본 NetworkPolicy는 FQDN 규칙이 없고, 공급자 IP 대역 목록은 자주 바뀌어 유지하기 어렵다. 클러스터 내부·platform 접근은 기존 앱·platform 허용 규칙만 따른다. 운영 EKS의 NAT·도메인 제한은 #185에서 정한다.
- 웹은 호스트 Vite에서 실행하고 `CORE_PROXY_TARGET`·`CORE_PROXY_HOST`로 `/api`를 kind Ingress(`api.sagomungchi.local`)에 보낸다. 지정하지 않으면 기존 compose 대상(`localhost:CORE_HOST_PORT`)을 유지한다. Google 콜백은 `AUTH_WEB_ORIGIN` 기준이라 기존 리디렉션 URI를 그대로 쓴다.
- 토스 웹훅은 외부에서 로컬 kind로 들어올 수 없어 kind 확인 범위가 아니다. 결제 승인은 core가 토스 API를 직접 호출해 확인한다.

### kind 실제 확인 (2026-11-03)

이 브랜치의 values·스크립트로 Windows 11 PC의 새 `sagomungchi-local`(kind v0.33.0, Kubernetes v1.35.8, Calico v3.33.0, ingress-nginx 4.15.1, Docker 메모리 약 30GiB)에서 확인했다. Argo CD 설치는 이 이슈 범위가 아니어서 같은 chart·values를 Helm으로 직접 설치했다. local Argo 정의와 같은 KEDA 2.21.0과 `policies/local`도 적용했다. Helm은 Argo PreSync 훅을 쓰지 않으므로 core·learning·report-api를 먼저 설치하고 migration Job 완료(core v23·learning v8·report)를 기다린 뒤 나머지를 설치했다.

확인용 데이터는 이 PC의 kind DB에만 넣었고 저장소에는 넣지 않았다. 무료(0원)·프리미엄(14,900원) 상품 2개, #235 전까지 가입을 막지 않도록 "Synthetic non-binding notice" 동의 문서 3종, learning `db/seed/demo_missions.sql`이다. 웹은 Node 컨테이너의 Vite를 `CORE_PROXY_TARGET`·`CORE_PROXY_HOST`로 kind Ingress에 연결했다.

| 항목 | 결과 |
|---|---|
| 배포 | platform 4종 Ready·초기화 Job 2개 완료, 앱 6종 Running(report-worker는 큐가 비어 KEDA 0개) |
| Ingress | `/api` 200, 외부 `/internal` 404 |
| egress | core → Google OAuth·토스 API 응답 수신, ai → OpenAI 응답 수신(인증 없이 401). learning의 외부 443과 core의 외부 80은 시간 초과로 차단 |
| Google 로그인 | 학부모 로그인·동의·자녀 등록, PIN 변경용 Google 재인증 콜백 VERIFIED |
| LLM 판정 | 초3 서술형 미션 답변 3건 모두 `method=LLM`·`gpt-6.1-terra`·`judge@2`, `DONE`(CORRECT·RETHINK·PARTIAL), 실패 코드 없음. core `llm_usage`에 JUDGMENT·FOLLOWUP 호출이 성공으로 기록 |
| 토스 결제 승인 | 학부모 프리미엄(14,900원) 테스트 결제 승인. 주문·결제·시도 `APPROVED`, 이용권 `APPLIED`, 구독 `ACTIVE`(PREMIUM, 2026-11-03~12-03) |

토스: 결제위젯 키(`test_gck_`·`test_gsk_`)는 공식 안내상 전자결제 신청 이후에만 개발자센터에 보이고, 신청 전에는 문서의 테스트 키로 연동하도록 되어 있다. 담당자 계정에는 API 개별 연동 키(`test_ck_`·`test_sk_`)만 있어 문서 테스트 키(`test_gck_docs_`·`test_gsk_docs_`)를 사용했다. 이 키의 결제는 공용 문서 상점 `tgen_docs`에 기록된다. 첫 결제는 `TOSS_TEST_MID`가 다른 값이어서 core의 MID 대조에서 `PAYMENT_PG_MISMATCH`가 됐고(토스 결제 키 조회로는 `DONE`·`mId=tgen_docs` 확인), `TOSS_TEST_MID=tgen_docs`로 바꾼 뒤 새 결제가 승인됐다. 문서 테스트 키는 주문번호 조회(`GET /v1/payments/orders/{orderId}`)에 `NOT_FOUND_MERCHANT`를 반환하므로 "결제 상태 다시 확인"·복구·관리자 대조처럼 이 조회를 쓰는 경로는 이 키로 검증할 수 없다. 그래서 확인 중으로 남은 첫 주문은 kind DB에서만 FAILED로 정리해 같은 자녀의 새 결제 차단을 풀었다. 웹훅·빌링·환불은 확인 범위 밖이다.

사용성 관찰(#236 범위 밖): Google 재인증 팝업은 콜백 JSON만 보여 주고 원래 화면으로 돌아오지 않는다. 같은 콜백 주소를 다시 열면 403 `REAUTH_REQUIRED`가 된다. 학생 기기 등록에서 기기 이름이 비어 있으면 어느 칸인지 없이 `VALIDATION_FAILED`만 보인다. 관측 chart를 설치하지 않은 환경에서는 core·learning Java agent가 Collector 주소를 찾지 못한다는 경고를 남기지만 앱 동작에는 영향이 없다.
