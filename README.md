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

- 포트 충돌(Windows 8000~8099 예약 등) 시 `.env`의 `*_HOST_PORT`로 변경
- 웹: `cd frontend/web && npm install && npm run dev` (`/api` → core-service 프록시)
- 개발 규칙: [docs/README.md](docs/README.md)
