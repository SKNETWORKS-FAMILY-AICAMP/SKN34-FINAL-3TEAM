# 로컬 플랫폼 (#17)

통합 원본: local-platform-design-decisions, local-platform-resource-plan

[아키텍처 4.1](../design/architecture.md#41-환경-구분)의 로컬 Kubernetes 환경을 구체화한 설정과 근거. 실행 절차는 [kind](../../infrastructure/kind/README.md)·[platform-data](../../infrastructure/gitops/charts/platform-data/README.md), 설정값은 [local values](../../infrastructure/gitops/environments/local/platform-data.yaml).

## 1. 환경 경계

- 로컬은 kind 단일 노드에 PostgreSQL·RabbitMQ·Redis·MinIO, 운영은 RDS·S3와 RabbitMQ·Redis StatefulSet 설계 유지
- 저장소 구성은 `platform-data` chart 하나로 관리하고 PostgreSQL·MinIO는 로컬 values에서 활성화. 앱 배포·Argo CD·관측·AWS 자원은 범위 밖
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

- Compose MinIO는 [compose.minio.yaml](../../compose.minio.yaml)로 분리. Compose는 병합 전에 각 파일의 변수를 해석하므로 profile만으로는 `${VAR:?}` 검사를 피할 수 없음. 기본 실행에는 MinIO 이미지·포트·메모리를 추가하지 않음. 실행 절차는 [루트 README](../../README.md#minio-선택-실행)
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

## 근거

- [ingress-nginx 지원 버전](https://github.com/kubernetes/ingress-nginx#supported-versions-table), [종료 공지](https://kubernetes.io/blog/2025/11/11/ingress-nginx-retirement/), [kind v0.33.0](https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0)
- [Calico 요구사항](https://docs.tigera.io/calico/latest/getting-started/kubernetes/requirements), [native v3 CRD](https://docs.tigera.io/calico/latest/operations/native-v3-crds)
- [MinIO 배포 방식](https://github.com/minio/minio#source-only-distribution), [Chainguard MinIO](https://images.chainguard.dev/directory/image/minio/overview), [curl SigV4](https://curl.se/docs/manpage.html#--aws-sigv4)
- [Compose 변수 해석](https://docs.docker.com/reference/compose-file/interpolation/), [Compose 파일 병합](https://docs.docker.com/compose/how-tos/multiple-compose-files/merge/), [PowerShell 7](https://learn.microsoft.com/en-us/powershell/scripting/install/install-powershell-on-windows)
- [WSL 자원](https://learn.microsoft.com/en-us/windows/wsl/wsl-config), [Kubernetes requests·limits](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/), [PostgreSQL 17 메모리](https://www.postgresql.org/docs/17/runtime-config-resource.html), [RabbitMQ 메모리](https://www.rabbitmq.com/docs/memory), [quorum WAL](https://www.rabbitmq.com/docs/quorum-queues#resource-use), [Redis eviction](https://redis.io/docs/latest/develop/reference/eviction/)
