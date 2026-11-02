# platform-data 설정

RabbitMQ·Redis와 로컬용 PostgreSQL·MinIO의 설정을 관리한다. 공통 설정은 [values.yaml](values.yaml), kind 로컬 설정은 [environments/local/platform-data.yaml](../../environments/local/platform-data.yaml)에 둔다. [클러스터 기준](../../../kind/README.md)에 맞춰 release 이름은 `platform-data`, namespace는 `platform`, context는 `kind-sagomungchi-local`을 사용한다.

`templates/`에는 저장소별 StatefulSet, 접속용·Headless Service, 초기화 파일·RabbitMQ 설정 ConfigMap과 초기화 Job을 정의한다. Pod의 준비 상태와 큐·DB·버킷의 초기화 결과는 구분한다.

## 환경별 설정

| 항목 | 공통 기본값 | 로컬 환경 |
|---|---|---|
| RabbitMQ·Redis | 활성 | 활성 |
| PostgreSQL·MinIO | 비활성 | 활성 |
| 기존 Secret 이름 | 환경에서 지정 | `platform-data-credentials` |
| StorageClass | 클러스터 기본값 | 클러스터 기본값 |
| CPU·메모리 | 환경에서 지정 | 기준 PC의 저장소·Job별 requests·limits |

운영은 PostgreSQL·MinIO를 비활성화하고 RDS·S3를 사용한다. 운영 자원값·Secret 이름·StorageClass는 운영 환경에서 별도로 지정한다. 로컬은 저장소별 replica 1개를 기준으로 한다.

`storageClassName: null`은 PVC에 StorageClass 이름을 명시하지 않고 클러스터 기본값을 사용한다는 뜻이다. `storageClassName: ""`는 StorageClass 없는 PVC를 요청할 때 사용한다. `gp3` 같은 문자열은 해당 이름으로 준비된 StorageClass를 지정한다.

## 설정 이름과 자격 증명

values 키는 `existingSecret`, `memoryHighWatermark`처럼 lowerCamelCase를 사용한다. 이미지 값은 태그 또는 digest까지 포함한 전체 참조 문자열이다. 환경 values는 공통 기본값에서 달라지는 항목을 덮어쓴다.

설치·렌더링에는 환경 values를 함께 지정한다. 활성 저장소의 `resources.requests`·`resources.limits`, `existingSecret`, RabbitMQ watermark·Redis maxMemory 같은 필수 값이 없으면 템플릿이 명시적 오류로 중단한다.

`existingSecret`은 release와 같은 namespace에 사전 생성하는 Secret 이름이다. chart에는 비밀번호를 넣거나 Secret을 자동 생성하는 값을 두지 않는다. 로컬 Secret은 다음 키를 사용한다.

| 대상 | 사용자명 키 | 비밀번호 키 |
|---|---|---|
| PostgreSQL | `POSTGRES_USER` | `POSTGRES_PASSWORD` |
| RabbitMQ | `RABBITMQ_USER` | `RABBITMQ_PASSWORD` |
| MinIO | `MINIO_ROOT_USER` | `MINIO_ROOT_PASSWORD` |

각 서비스의 `usernameKey`·`passwordKey`는 Secret의 키 이름이며 실제 계정 값이 아니다. 원본 키 이름과 컨테이너가 요구하는 환경 변수 이름은 구분한다. 예를 들어 `RABBITMQ_USER` 키는 RabbitMQ 서버의 `RABBITMQ_DEFAULT_USER` 환경 변수에 연결한다. `.env`와 실제 Secret 내용은 저장소에 포함하지 않는다. 내부 API 토큰·LLM 키는 이 저장소 계정 Secret에 넣지 않는다.

PowerShell 7에서 저장소 루트의 `.env`에 여섯 값을 준비한 뒤 다음 명령을 실행한다. 값은 비어 있지 않은 리터럴 또는 작은따옴표로 감싼 리터럴을 사용한다. 변수 치환·큰따옴표 이스케이프는 Secret 준비 스크립트에서 처리하지 않는다. Compose와 같은 계정을 사용하려면 해당 여섯 값을 다른 셸 환경 변수로 덮어쓰지 않는다.

```powershell
pwsh -File infrastructure/kind/create-platform-secret.ps1
# 다른 로컬 파일을 사용할 때: -EnvFile <파일 경로>
```

스크립트는 `kind-sagomungchi-local` context의 `platform` namespace에만 접근하며 namespace가 없으면 생성한다. 자격 증명은 kubectl의 UTF-8 stdin으로 전달하고 명령 인자·로그·임시 파일에 넣지 않는다. 기존 Secret이 같으면 유지하고 다르면 오류로 중단한다. Secret·컨테이너 환경 변수를 바꾸는 것만으로 기존 DB·RabbitMQ 계정의 비밀번호가 회전되지는 않는다.

## 서비스와 데이터

| 서비스 이름 | 포트 | 데이터 용도 |
|---|---|---|
| `postgres` | 5432 | `core_db`·`learning_db`·`report_db` |
| `rabbitmq` | 5672 / 15672 / 15692 | AMQP / 관리 API / Prometheus |
| `redis` | 6379 | 캐시·실시간 알림 중계 |
| `minio` | 9000 / 9001 | S3 API / 관리 화면 |

앱 namespace에서는 `postgres.platform`·`rabbitmq.platform`·`redis.platform`·`minio.platform`으로 접속한다. 고정된 Service 이름을 사용하므로 같은 namespace에 이 chart를 여러 release로 중복 배포하지 않는다.

저장소마다 `<서비스명>-headless`가 StatefulSet의 `serviceName`과 연결된다. 앱은 접속용 일반 Service를 사용한다. StatefulSet은 replica 1개이며 삭제·축소 시 PVC를 보존하도록 설정한다. kind 클러스터 자체의 삭제에 따른 노드 내부 데이터 보존은 별도다.

- PostgreSQL: `settings`에서 메모리·연결 수를 지정한다. DB 생성 파일은 기존 `files/postgres/init.sql`을 사용하며, 테이블 변경은 서비스별 migration이 담당한다.
- RabbitMQ: `memoryHighWatermark`는 절대 바이트 수 문자열이다. 로컬은 `1073741824`(1GiB)로 지정하며 컨테이너 메모리 limit과 구분한다. 큐·exchange·binding은 기존 `files/rabbitmq/definitions.json`만 기준으로 하고 계정은 파일에 추가하지 않는다.
- Redis: `maxMemory`는 데이터 메모리 기준, `maxMemoryPolicy`는 한도 도달 시 처리 방식이다. 로컬은 `128mb`·`noeviction`을 사용하고 AOF를 활성화한다. `noeviction`에서는 메모리 한도를 넘는 쓰기를 오류로 처리한다.
- MinIO: 단일 저장 공간에 `missions`·`reports`·`models` 세 버킷을 만든다. `buckets`의 키는 용도이고 값은 실제 버킷 이름이다. 로컬 버킷명은 환경 values에 지정한다.

RabbitMQ의 `rabbitmq-config`는 management·Prometheus 플러그인을 활성화하고 `rabbitmq-definitions`는 기존 JSON을 그대로 담는다. JSON에는 1·5·15분 재시도 큐·DLQ가 포함된다. 기본 큐 타입을 전역 quorum으로 강제하지 않고 JSON의 큐별 선언을 따른다. 이는 앱이 선언하는 Pod별 exclusive 브로드캐스트 큐와 구분하기 위한 설정이다.

각 컨테이너는 이미지의 사용자 ID로 실행하고 root filesystem을 읽기 전용으로 둔다. PostgreSQL(70:70), RabbitMQ(100:101), Redis(999:1000), MinIO(65532:65532)의 쓰기 경로는 PVC·임시 볼륨에 연결한다. `startupProbe`가 최초 기동을 기다리고 `readinessProbe`가 접속 준비 상태를 확인하며 `livenessProbe`는 프로세스 상태를 확인한다.

## MinIO 이미지

MinIO 서버는 Chainguard의 공개 배포본을 linux/amd64 digest로 고정한다. 초기화에는 기존 curl 배포 이미지의 고정 버전을 사용하며 S3 SigV4 요청으로 버킷을 생성한다. 이미지 참조는 공통 values의 `minio.image`, `minio.initialization.image`에서 관리한다. MinIO는 로컬 S3 호환 저장소로 사용하고 운영 파일 저장소는 AWS S3를 사용한다.

[MinIO 커뮤니티 배포 안내](https://github.com/minio/minio#source-only-distribution)의 소스 전용 배포 전환을 고려해 로컬 서버는 사전 빌드된 [공개 배포본](https://images.chainguard.dev/directory/image/minio/overview)을 사용한다. 이미지 갱신은 선택한 digest를 명시적으로 변경하는 방식으로 수행한다.

서버는 이미지의 기본 entrypoint를 사용하며 서버에 shell·curl이 포함돼 있다고 가정하지 않는다. 초기화 스크립트는 별도의 curl 컨테이너에서 실행한다. 앱·Job의 계정과 데이터는 FINAL 전용 Secret·볼륨·버킷을 사용한다.

## 초기화와 자원

`rabbitmq.initialization`·`minio.initialization`에서 작업 이미지·재시도 횟수·전체 제한 시간·접속 대기 시간·자원을 설정한다. 각 Job의 `waitTimeoutSeconds`는 `activeDeadlineSeconds`보다 짧게 지정한다. 초기화는 재실행 가능한 방식으로 구성하고 인증·설정 적용 실패를 성공으로 처리하지 않는다.

Job 이름에는 설정·스크립트·초기화 데이터의 hash가 포함되어 변경 시 새 Job을 생성한다. RabbitMQ 스크립트는 준비 대기 후 관리 API로 기존 JSON을 반영하고, MinIO 스크립트는 준비 대기 후 세 버킷을 생성한다. 이미 소유한 버킷만 재실행 성공으로 처리하며 다른 인증·충돌 오류는 실패한다. 두 스크립트는 `files/`에서 Helm ConfigMap과 Compose에 함께 제공한다.

활성 저장소와 초기화 Job의 `resources.requests`·`resources.limits`는 환경 values에서 지정한다. 로컬 PVC 요청 합계는 6.5Gi이며 MinIO의 2Gi는 버킷 세 개가 공유한다. 로컬 provisioner에 따라 PVC 요청량이 실제 디스크 사용 상한을 강제하지 않을 수 있다. Ingress controller 자원은 이 chart가 아닌 별도 [kind 설치값](../../../kind/ingress-nginx-values.yaml)에서 관리한다.

## 설치와 확인

클러스터·CNI·Ingress 및 Secret을 준비한 뒤 저장소 루트에서 실행한다.

```powershell
helm lint infrastructure/gitops/charts/platform-data -f infrastructure/gitops/environments/local/platform-data.yaml
helm upgrade --install platform-data infrastructure/gitops/charts/platform-data --namespace platform --kube-context kind-sagomungchi-local -f infrastructure/gitops/environments/local/platform-data.yaml --wait --wait-for-jobs --timeout 10m
kubectl --context kind-sagomungchi-local -n platform get pods,jobs,pvc,services
```

Pod Ready 외에 Job Complete, PostgreSQL DB 세 개, RabbitMQ의 기존 definitions와 실제 topology 일치, MinIO 버킷 세 개를 확인한다. 관리 화면은 `kubectl --context kind-sagomungchi-local -n platform port-forward svc/rabbitmq 15672:15672` 또는 `svc/minio 9001:9001`로 연결한다.

Compose의 기본 앱은 같은 `.env`를 사용해 `docker compose up --build`로 실행하며 MinIO 계정은 필요하지 않다. PostgreSQL·RabbitMQ·Redis만 확인할 때는 `docker compose up -d postgres rabbitmq redis` 후 `docker compose run --rm rabbitmq-init`을 실행한다. MinIO는 [선택 실행 절차](../../../../README.md#minio-선택-실행)에 따라 별도 파일을 추가한다.

```powershell
docker compose -f compose.yaml -f compose.minio.yaml up -d minio
docker compose -f compose.yaml -f compose.minio.yaml run --rm minio-init
```

MinIO API·콘솔은 기본 `127.0.0.1:9000`·`:9001`이며 포트 충돌 시 `.env`의 `MINIO_HOST_PORT`·`MINIO_CONSOLE_HOST_PORT`로 변경한다. 최소 서버 이미지에는 실행형 healthcheck 도구가 없으므로 Compose의 `minio-init`이 HTTP 준비 상태를 기다린다. kind 배포에서는 계속 여섯 계정 키와 로컬 values의 MinIO 설정을 사용한다.
