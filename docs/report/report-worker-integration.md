# #56 리포트 worker 통합 및 완료 조건 검증

## 목적과 기준

develop `f9df2d3`에서 분기한 `feature/report-worker-integration`에서 #50~55의 생성·조회 모듈을 기본 worker에 연결한다. core #119의 학생 별명 API를 사용하며 공유 이벤트와 DB 스키마는 변경하지 않는다.

## 구현

- 기본 `python -m app.worker`가 `CoreClient.lookup` → `RecordGenerator` → `NarrativeGenerator` → `RenderingGenerator`를 실행한다.
- core `GET /internal/students/{studentId}/profile`에는 기존 내부 클라이언트로 내부 토큰·SYSTEM 역할·해당 학생 scope를 전달한다. 응답의 `studentId`·`nickname`을 사용한다.
- `NamedGenerator`는 ID 일치와 비어 있지 않은 문자열 별명을 검사한다. core에서 조회한 값을 AI 입력 가림과 파일 표시에 동일하게 사용한다.
- 403·404·시간 초과·잘못된 응답은 기존 생성 서비스의 `FAILED / GENERATION_FAILED`와 `report.failed`로 처리한다. 가짜 별명·NO_RECORD로 대체하거나 HTTP 재시도를 추가하지 않는다. DB/메시지 실패의 기존 재시도 정책은 유지한다.
- worker가 HTTP·S3 클라이언트 수명을 관리한다. 테스트용 생성기·별명 공급자 주입은 유지하지만 운영 기본 경로는 실제 core 클라이언트다.

## 검증 구성과 범위

`scripts/report_integration/compose.yaml`은 고유 프로젝트·일회용 DB/볼륨에서 다음을 실행한다.

| 구성 | 사용 범위 |
|---|---|
| core | 최신 소스의 Spring JAR, 실제 마이그레이션·학생 별명 HTTP API |
| learning | 최신 소스의 Spring JAR, 실제 제출·기록 조회 API |
| report | 운영 Docker 이미지의 기본 worker·API·Outbox·렌더러 |
| 저장소·메시지 | 실제 PostgreSQL·RabbitMQ·MinIO, 내부 Redis |
| 데이터 | core DB에 넣은 합성 학생과 learning 합성 학습 기록 |
| AI | #56이 허용하는 HTTP 대역. 정상·숫자 불일치·503 재현 |

팀 `.env`, AWS, 실제 학생 데이터는 사용하지 않는다. 호스트 포트는 공개하지 않는다. 종료 시 해당 테스트 프로젝트 자원만 정리한다. 저장 장애를 위한 버킷 삭제도 전용 `report56-synthetic`에 한정한다.

## 완료 조건과 증거

| #56 완료 조건 | 확인 방법 |
|---|---|
| #50~55 전체 종료 | GitHub 하위 이슈 상태 확인 |
| 직접 발행 → COMPLETED·report.completed | 실제 RabbitMQ 입력·출력 이벤트, report DB 상태 확인 |
| PDF·Markdown 저장 및 조회 | HTML/PDF/MD 메타데이터 3개와 서명 URL 다운로드 확인 |
| 상세 API 3.4 | 실제 응답을 `ReportDetail`로 검증, 목록·타 학생 403 검사 |
| 기록 없는 학생 | 실제 learning 빈 기록으로 COMPLETED + NO_RECORD, AI 호출 0회 |
| 서술 경로 | 대역 정상 LLM·대조 실패 TEMPLATE·AI 503 FAILED 검사 |

추가로 core 내부 API의 401·역할/학생 scope 403·no-store 응답, 파일의 실제 별명 표시와 AI 최종 payload의 별명/학생 ID 제거, 중복 메시지의 단일 행, 삭제/미등록 학생의 생성 실패, 저장 장애의 파일 행 0개를 검사한다.

전체 report pytest와 Ruff 검사에 더해 Compose 결과의 생성 명령·started/completed/failed 이벤트를 저장소 JSON Schema로 검증한다. 최종 실행 결과는 검증 후 아래에 기록한다.

## 재현

Java 21에서 core-service와 learning-service 각각 `./gradlew bootJar --no-daemon`을 실행한다. runner는 JAR보다 소스가 최신이면 중단한다. Docker 실행 후 저장소 루트에서 다음을 실행한다.

```powershell
& backend/report-service/.venv/Scripts/python.exe -X utf8 scripts/verify_report_compose.py --output C:/Users/playdata2/Desktop/final/tmp/report56-final-compose
```

출력 폴더에 `results.json`과 빌드·기동·검증·서비스·정리 로그를 보관한다. 모델 파일이나 데이터셋은 필요하지 않다.

## 별도 후속 범위

#56이 허용한 직접 메시지 발행·AI 대역 검증을 대상으로 한다. 실제 #64 AI 품질·core 스케줄/작업 상태/알림·학부모 공개 조회·운영 AWS 전체 E2E를 완료했다는 의미는 아니다. 특히 core `ReportClient`의 현재 상품 권한 헤더 전달은 별도 연동 확인 사항이다. PDF는 생성·다운로드·헤더를 검사하며 모든 페이지 시각 검수를 수행한 것으로 보고하지 않는다.

## 최종 실행 결과 (2026-10-29)

- report 전체 회귀: **255 passed**, 101.97초. 기존 Starlette/httpx 폐기 예정 경고 1개, 실패·생략 없음.
- 공통 검증 스크립트 회귀: **74 passed, 34 subtests passed**, 18.16초.
- report Ruff check·format: 통과(81개 파일). 신규 Compose Python 스크립트 린트·포맷 통과.
- 최신 core·learning Java 21 bootJar 및 운영 report Docker 이미지 빌드 통과.
- 실제 Compose **8개 시나리오 모두 통과**: 유료·중복·개인정보·파일·scope 조회 / 무료 AI 생략 / NO_RECORD AI 생략 / 삭제 학생 실패 / 미등록 학생 실패 / 숫자 불일치 TEMPLATE / AI 503 FAILED / MinIO 장애 FAILED.
- 입력 및 출력 이벤트의 공유 JSON Schema 검사 통과. core 실제 API의 인증·scope·no-store 검사 통과.
- 변경 문서 8개의 로컬 링크 59개 정상. `git diff --check`와 미해결 충돌 검사 통과.
- 최초 Compose 시도는 합성 학생 데이터의 `pin_failed_count` 누락으로 실패했다. 합성 초기값 0을 넣어 전체를 재실행했으며 운영 DB 제약은 수정하지 않았다.

로컬 증거: 저장소 밖 `C:/Users/playdata2/Desktop/final/tmp/report56-final-pytest.xml`, `report56-final-compose-v2/results.json` 및 같은 폴더의 로그. 테스트 컨테이너·네트워크·볼륨은 runner의 finally에서 정리한다.

**판정: #56에 명시된 구현·완료 조건을 로컬 검증으로 충족했다. 원격 PR CI·검토·병합은 별도 단계다.** GitHub 이슈의 체크박스와 상태는 이 문서 작성만으로 변경되지 않는다.
