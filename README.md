# SKN34-FINAL-3TEAM

## 로컬 실행
```
cp .env.example .env        # 값 입력
docker compose up --build
```

| 대상 | 주소 |
|---|---|
| core-service (공개 API) | http://localhost:8080 |
| learning-service | http://localhost:8081 |
| ai-service | http://localhost:8000 |
| scoring-service | http://localhost:8001 |
| report-api | http://localhost:8002 |
| RabbitMQ 관리 화면 | http://localhost:15672 |
| MinIO API / 관리 화면 (선택 실행: `compose.minio.yaml` 사용) | http://localhost:9000 / http://localhost:9001 |

- 포트 충돌(Windows 8000~8099 예약 등) 시 `.env`의 `*_HOST_PORT`로 변경
- 웹: `cd frontend/web && npm install && npm run dev` (`/api` → core-service 프록시)
- 개발 규칙: [docs/README.md](docs/README.md)
- 로컬 Kubernetes: [kind 설정·설치](infrastructure/kind/README.md), [저장소·Secret 설정](infrastructure/gitops/charts/platform-data/README.md)

### MinIO 선택 실행

기본 `docker compose up --build`에는 MinIO가 포함되지 않는다. 로컬 파일 저장소가 필요하면 `.env`에 `MINIO_ROOT_USER`(3자 이상)·`MINIO_ROOT_PASSWORD`(8자 이상)를 추가한다. 비밀번호에 `$` 또는 `#`가 있으면 작은따옴표로 감싼 리터럴을 사용한다.

```powershell
docker compose -f compose.yaml -f compose.minio.yaml up -d minio
docker compose -f compose.yaml -f compose.minio.yaml run --rm minio-init
```

첫 명령은 전용 볼륨 소유권 준비 후 서버를 실행하고, 두 번째 명령은 서버 준비 상태를 기다려 `sagomungchi-local-missions`·`sagomungchi-local-reports`·`sagomungchi-local-models` 버킷을 만든다. 같은 초기화 명령을 다시 실행해도 기존 버킷과 데이터를 유지한다. 두 파일은 같은 Compose 프로젝트 이름을 사용해야 하며 기본 프로젝트 이름은 `sagomungchi`다.

MinIO를 포함한 프로젝트를 중단할 때도 `docker compose -f compose.yaml -f compose.minio.yaml down`을 사용한다. 데이터를 보존하려면 `--volumes`를 붙이지 않는다. 기본 파일과 함께 실행하는 명령이므로 기존 PostgreSQL·RabbitMQ·내부 토큰 환경 변수도 필요하다.
