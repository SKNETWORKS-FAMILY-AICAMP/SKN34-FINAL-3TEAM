# 이슈 #17 로컬 플랫폼 자원 설계

[이슈 #17](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/17)의 kind·platform-data 자원 설정이다. 2026-10-26에 확인한 기준 PC와 Docker 환경을 바탕으로 하며, 저장소·초기화 Job의 설정값은 [로컬 values](../../infrastructure/gitops/environments/local/platform-data.yaml)에서 관리한다.

## 확인한 환경

| 항목 | 조회 결과 |
|---|---|
| OS | Windows 11 Pro, x86_64 |
| CPU | Intel Core i5-1135G7, 물리 4코어·논리 8개 |
| 메모리 | 16GB급, Windows 인식 약 15.73GiB |
| 조회 시 여유 메모리 | 약 4.98GiB. 실행 중인 다른 프로그램에 따라 변동 |
| C: 용량 / 여유 | 약 222.33GiB / 23.31GiB |
| Docker | Docker Desktop, Linux Engine 29.7.2, WSL 2 |
| Docker 인식 CPU / 메모리 | 논리 CPU 8개 / 메모리 상한 약 7.62GiB |
| 실행 중 컨테이너 | 0개 |
| 기존 Docker 저장 공간 | 이미지 10.8GB, 로컬 볼륨 12.82GB. Docker 표시 단위이며 위 GiB와 구분 |
| 사용자 `.wslconfig` | 없음 |
| PATH에서 확인한 도구 | Docker·WSL·kubectl 있음. kind·Helm은 찾지 못함 |

WSL 2 메모리는 동적으로 사용되므로 Docker의 7.62GiB는 현재 점유량이 아니다. 기존 Docker 이미지·컨테이너·볼륨은 보존한다. Docker·WSL 설정 변경, 종료, 설치 및 정리는 수행하지 않았다.

## 확정한 구성과 적용 범위

- 팀 개발 PC가 기준 PC와 같다는 사용자 확인을 전제로 설계한다.
- 로컬 Ingress는 이슈의 ingress-nginx를 유지한다는 사용자 결정을 따른다. 고정 버전과 IP·포트 기준은 [kind 설정·설치 절차](../../infrastructure/kind/README.md)를, 선택의 기술 근거는 [설계 변경 근거](local-platform-design-decisions.md)를 따른다.
- kind 단일 노드, Calico, 저장소별 replica 1개를 사용한다. 운영용 HA·확장 설정으로 사용하지 않는다.
- MinIO 버킷은 `sagomungchi-local-missions`, `sagomungchi-local-reports`, `sagomungchi-local-models` 세 개로 구분한다. 버킷 세 개가 MinIO Pod나 볼륨 세 개를 의미하지는 않는다.
- 다음 예산은 이슈 #17의 저장소·로컬 Ingress·초기화 작업을 대상으로 한다. 앱 서비스·scoring 모델 추론·Argo CD·관측 구성·동시 이미지 빌드는 포함하지 않는다.

## CPU·메모리 시작 설정

다음 값을 local values에 사용한다. requests는 스케줄링 기준이고 limits는 컨테이너별 상한이며, 둘 다 실제 사용량 측정값이 아니다.

| 대상 | CPU request | CPU limit | 메모리 request | 메모리 limit |
|---|---:|---:|---:|---:|
| PostgreSQL | 100m | 500m | 256Mi | 512Mi |
| RabbitMQ | 250m | 1000m | 512Mi | 2Gi |
| Redis | 50m | 250m | 64Mi | 256Mi |
| MinIO | 100m | 500m | 256Mi | 1Gi |
| ingress-nginx controller | 100m | 500m | 128Mi | 512Mi |
| **상시 구성 합계** | **600m** | **2750m** | **1216Mi** | **4352Mi (4.25Gi)** |
| RabbitMQ 초기화 Job, 1개 | 50m | 250m | 64Mi | 128Mi |
| MinIO 초기화 Job, 1개 | 50m | 250m | 64Mi | 128Mi |
| **두 Job 동시 실행 시 합계** | **700m** | **3250m** | **1344Mi** | **4608Mi (4.5Gi)** |

Ingress admission 등 chart가 추가 생성하는 일회성 작업이 있으면 별도 합산한다. Kubernetes control plane·etcd·CoreDNS·Calico·Linux/Docker 기반 구성에는 메모리 1.5GiB를 계획 여유분으로 잡아, 초기 플랫폼 전체를 약 6GiB 예산으로 시작한다. 기반 구성 1.5GiB는 실측치나 강제 제한이 아니다. 컨테이너 외 메모리와 실제 노드 allocatable도 최종 검증에서 확인한다.

Docker의 현재 CPU·메모리 상한은 우선 유지한다. 상한을 늘려 해결하는 방식으로 시작하지 않는다. 현재 Windows 여유 메모리 4.98GiB만으로 6GiB 예산의 동시 점유를 보장할 수 없으므로, 기동 전 불필요한 앱을 사용자가 정리해 호스트 여유를 확보한다. WSL은 다른 배포판과도 자원을 공유할 수 있다. Compose 전체와 kind를 동시에 실행하지 않고 각각 검증한다.

### 저장소 내부 설정과 한계

- PostgreSQL: `shared_buffers=64MB`, `max_connections=40`, `work_mem=2MB`, `maintenance_work_mem=32MB`를 로컬 시작값으로 제안한다. `work_mem`은 연결 하나당 고정 총량이 아니라 정렬·해시 작업 등에 사용되므로 동시 작업 수에 따라 사용량이 증가한다. 앱 연결 시 생산자·소비자의 연결 풀 합계와 관리자·마이그레이션 접속 여유를 함께 검증한다. 운영 튜닝 값으로 전용하지 않는다.
- RabbitMQ: 기본 quorum WAL 512MiB와 WAL 크기의 최소 3배 메모리 권장 사항을 고려해 limit을 2Gi로 잡는다. 고급 WAL 튜닝은 추가하지 않는다. 컨테이너 환경에서는 메모리 자동 감지에만 의존하지 않고 `vm_memory_high_watermark.absolute=1073741824`(1GiB)를 시작값으로 제안한다. watermark는 발행 제한 기준이고 프로세스의 강제 상한이나 OOM 방지 보장이 아니다. 큐 적체·메모리·디스크 alarm을 확인한다.
- Redis: 데이터용 `maxmemory=128mb`, `maxmemory-policy=noeviction`을 제안해 256Mi limit 안에 부가 메모리 여유를 둔다. 한도 초과 쓰기는 명시적 오류로 드러내며, 내부 버퍼·영속화 작업까지 256Mi 안에 들어오는지는 검증한다. 영속화 방식은 별도 구현 설정과 일치시킨다.
- MinIO: 소규모 파일 업로드·다운로드와 버킷 생성 검증의 시작 limit은 1Gi다. 대형 모델 파일, 다수 동시 업로드, 실제 모델 추론까지 이 예산으로 검증됐다는 뜻은 아니다.

## 볼륨 시작 용량

| 저장소 | PVC 요청량 | 범위 |
|---|---:|---|
| PostgreSQL | 2Gi | DB 세 개의 소규모 로컬 데이터와 WAL |
| RabbitMQ | 2Gi | quorum queue·DLQ의 소규모 메시지와 로그 데이터 |
| Redis | 512Mi | 선택한 로컬 영속화 설정의 저장 공간 |
| MinIO | 2Gi | 세 버킷이 공유하는 소규모 테스트 파일 공간 |
| **합계** | **6.5Gi** | 이미지·컨테이너 로그·Kubernetes 시스템 데이터 제외 |

버킷마다 2Gi를 배정하는 것이 아니라 MinIO 전체에 2Gi를 요청한다. 본격적인 모델 가중치 적재 전에는 파일 크기를 확인하고 예산을 다시 계산한다.

로컬은 kind의 실제 StorageClass와 provisioner를 확인해서 연결하고, chart는 `storageClassName`을 지정 가능하게 작성한다. 로컬 경로 기반 provisioner에서는 PVC의 요청량이 실제 디스크 사용량의 강제 quota가 아닐 수 있다. PVC 합계를 호스트 디스크 사용 상한으로 해석하지 않는다. kind 클러스터 삭제 시 로컬 볼륨 보존 여부도 별도로 문서화한다.

현재 C: 여유는 약 23.31GiB다. PVC 요청 합계 6.5Gi 외에 kind 노드 이미지·Calico·Ingress·MinIO 등의 이미지와 로그가 추가된다. 전체 검증 전 여유 공간 30GiB 이상을 확보하는 것을 설계상 권장 목표로 잡되, 실제 이미지 크기를 아직 측정하지 않았으므로 설치 가능 여부를 단정하지 않는다. 기존 Docker 볼륨 12.82GB는 현재 호스트 여유 공간에 이미 반영된 사용량이며 다시 차감하지 않는다. 불특정 이미지·볼륨 정리는 수행하지 않는다.

## 구현과 최종 검증 순서

1. 고정 버전과 호환성을 확인하고 kind·Calico·ingress-nginx 설치 절차, chart·local values, Secret 준비 절차, Compose MinIO 구성을 모두 작성한다.
2. 작성 완료 후 Helm lint·렌더링, Compose 설정 검사, 비밀 값 포함 여부와 `git diff --check`를 모아서 수행한다.
3. kind를 실제 생성하고 노드 capacity·allocatable·시스템 Pod requests, 모든 저장소 Pod Ready와 초기화 Job 성공을 확인한다. DB 세 개·버킷 세 개·RabbitMQ topology와 지표 노출을 확인한다.
4. CPU·메모리·디스크와 OOMKilled·재시작·CPU throttling·저장소 alarm을 확인한다. 대표 데이터는 합성 데이터로 DB 쓰기·조회, AMQP 발행·소비, Redis 쓰기·읽기, MinIO 업로드·다운로드를 수행한다. CPU throttling을 수집할 지표가 없으면 미검증으로 보고한다. 기본 플랫폼 검증에 운영 모델·실제 학습 기록을 사용하지 않는다.
5. kind와 별도로 기본 Compose가 MinIO 계정 없이 해석되는지 확인하고, `-f compose.yaml -f compose.minio.yaml` 선택 실행으로 MinIO 기동·버킷 준비를 검증한다. 기존 사용자 데이터를 삭제하거나 클러스터 종료를 자동 수행하지 않는다.
6. 실제 사용량에 맞춰 필요한 항목만 조정하고 실패 항목·수정 영향 범위를 재검증한다. 앱 연결과 운영 EKS·실제 부하 검증은 후속 범위로 구분한다.

## 근거

- [WSL 자원 설정](https://learn.microsoft.com/en-us/windows/wsl/wsl-config), [Docker Desktop WSL 2의 동적 자원 사용](https://docs.docker.com/desktop/features/wsl/)
- [Kubernetes requests·limits](https://kubernetes.io/docs/concepts/configuration/manage-resources-containers/)
- [PostgreSQL 17 메모리 설정](https://www.postgresql.org/docs/17/runtime-config-resource.html)
- [RabbitMQ 메모리 watermark](https://www.rabbitmq.com/docs/memory), [quorum WAL과 메모리](https://www.rabbitmq.com/docs/quorum-queues#resource-use)
- [Redis maxmemory와 정책](https://redis.io/docs/latest/develop/reference/eviction/)
