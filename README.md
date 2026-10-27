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


### Google OAuth (#36)
`.env.example`의 `AUTH_JWT_SECRET`(base64 32바이트 이상 난수), `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`를 개인 `.env`에 설정한다. Google web client의 redirect URI는 `AUTH_WEB_ORIGIN` + `/api/v1/auth/google/callback`과 정확히 같아야 한다. 로컬 기본은 `http://localhost:5173`이며 Vite `/api` 프록시를 사용한다. 로컬 HTTP만 `AUTH_COOKIE_SECURE=false`, 배포 HTTPS는 true다. Google 키가 없으면 OAuth는 명시적으로 실패한다.

배포 시 core 환경에 `AUTH_JWT_SECRET`·`GOOGLE_CLIENT_ID`·`GOOGLE_CLIENT_SECRET`을 Kubernetes Secret 참조로 주입하고 `AUTH_WEB_ORIGIN`을 실제 web origin으로 지정한다. 현재 저장소의 platform-data chart는 앱 배포를 소유하지 않으므로 실제 core Deployment의 Secret 주입은 앱 배포 구성 시 적용한다. 키·자격 증명은 Git에 넣지 않는다.

인증 구현은 [#36 결정·검증 보고서](docs/report/issue-36-google-auth.md)를 따른다. 실제 모드의 로그인·가입은 Google을 사용하며 동의 저장·자녀 등록은 [#37 계약·검증 보고서](docs/report/issue-37-consent-children.md)를 따른다. 현재 문서 확인 → 동의 저장 → 자녀 등록을 온보딩에서 진행한다. 운영자가 검토된 TERMS·PRIVACY·GUARDIAN 문서를 게시해야 하며, 미게시 상태는 503 오류로 안내한다. 중요 작업 Google 재인증은 #45 후속 범위다.

개정 P01에 따라 부모·관리자만 refresh를 사용한다. 학생 동석 진입은 부모 쿠키를 폐기하고 access만 발급한다. 학생 TTL은 `AUTH_STUDENT_ACCESS_TTL`(초기 15분)이며 만료·새로고침 시 학생 진입을 다시 진행한다. 등록 기기·PIN 신규 API는 후속 범위다.
