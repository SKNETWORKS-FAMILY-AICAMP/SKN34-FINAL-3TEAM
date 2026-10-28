# #44 앱 내 알림·Redis SSE

## 범위와 기준
- origin/develop 78bbdc1에서 feature/core-notifications 전용 worktree 사용. #42·#45는 PR #98로 반영됨. PR base develop, PR 생성 없음.
- #58 최신 이슈에는 PIN 잠금·새 기기 알림이 미확정이다. 이번 구현에서 해당 유형/발생 연결은 추가하지 않는다.
- #58과 공유할 연결은 Boot 표준 spring.data.redis, REDIS_HOST/REDIS_PORT/REDIS_PASSWORD. 신규 production 의존성은 Boot BOM의 spring-boot-starter-data-redis이며 별도 Redis 서버를 추가하지 않는다. 알림 채널 core:notifications:v1은 페어링 키와 무관하다.
- #45 V9 보존, #58 작업 중 V11을 확인해 알림 CHECK 확장을 V12로 배정했다. 이후 #58이 V10으로 변경된 것도 확인했으며, 이미 검증한 V12는 유지한다. 기존 V1~V9와 번호 충돌이 없다.

## 계약·실패 처리
api-spec 2.7, architecture 1.6, erd 3.3을 먼저 갱신했다. 학생 세션은 보호자 account ID를 공유하므로 전체 알림/설정을 금지한다. 보호자 알림은 서버 인증 계정에만 노출한다.
리포트 실제 상태 전이의 ReportJobFinished를 같은 트랜잭션에서 저장한다. processed_event·상태 전이와 notification UK가 재전달/재처리 중복을 막는다. 실패는 REPORT_FAILED 독립 유형이다.
DB 커밋 이후 Pub/Sub 발행, 실패는 전달 FAILED로 기록하며 DB 원본/리포트 상태를 되돌리지 않는다. Redis 발행 성공은 브라우저 전달 보장이 아니다. 커밋 직후 프로세스 중단에 남은 QUEUED도 목록에 노출된다. 영구 메시징 프레임워크나 추가 재시도 큐는 만들지 않는다.
SSE ready 후 목록 API 재조회 및 주기적 목록 동기화가 유실 복구 계약이다. Last-Event-ID replay 없음.

## 검증
- `python -O -m unittest discover -s scripts/tests -q`: 53개 통과. 최초 OpenAPI 참조 위치 오류는 수정 후 전체 재검증했다.
- 격리 PostgreSQL `issue44-schema-postgres`에서 `python -O scripts/check_db_migrations.py --docker-network issue44-schema-network --flyway-host issue44-schema-postgres` 통과. core 38테이블/337컬럼, learning 19/156, report 6/44; 위반 입력 50건·CHECK 65집합·ERD 인덱스 21개. 재실행 이력 불변·report downgrade/upgrade 통과. 검증 컨테이너/네트워크 정리 완료.
- Windows Gradle은 loopback 연결 오류로 실행 불가. 첫 Linux 실행도 PowerShell의 옵션 분리 때문에 테스트 전 실패했다. 옵션 인용 후 첫 테스트 실행도 Docker Desktop의 Ryuk localhost 연결 오류로 초기화에 실패했다. TESTCONTAINERS_HOST_OVERRIDE=host.docker.internal로 수정하여 최종 실행은 통과했다.

## 남은 연결
#58 PIN 잠금·새 기기 알림 정책 결정. #42 보고서에 명시된 실제 report worker·상품 공급자 E2E는 별도 공급자 연결 범위이며 이번 알림 테스트는 실제 core 상태 전이를 사용한다.

프론트의 현재 유효 경로 `/parent/report`에 childId/reportId query를 제공한다. 기존 프론트는 query로 자녀/상세를 자동 선택하지 않으므로 그 소비는 프론트 연결 후속이며, 상세 조회 API의 기존 권한 검사는 유지한다.

## 최종 검증 (2026-10-28)

- 전용 eclipse-temurin:21-jdk 컨테이너에서 `bash gradlew test bootJar --no-daemon --max-workers=1 --no-watch-fs --console=plain '-Dorg.gradle.jvmargs=-Xmx512m -XX:ActiveProcessorCount=2' '-Pkotlin.compiler.execution.strategy=in-process' --init-script /verify/limits.gradle` 성공. 테스트 179개, 실패/오류/건너뜀 0. 검증 JVM heap 512MiB·CPU 2, test fork 1, #44 전용 Gradle 캐시 사용.
- 알림 통합 6개: 실제 PostgreSQL 저장·리포트 종료 전이, 같은/다른 이벤트 ID 재전달, REPORT_FAILED 독립 설정·수신 거부, 연결 해제/동의 철회 수신 제외, 소유권·학생 제한·읽음 멱등성·설정 입력, 롤백과 커밋 이후 Pub/Sub, 재연결 목록 복구, 발행 장애 기록.
- 다중 구독 검증은 같은 JVM 안에서 **서로 다른 SseEmitters·NotificationStreams·LettuceConnectionFactory·RedisMessageListenerContainer 두 인스턴스**를 만들고 실제 Redis Pub/Sub 수신→각 SSE emitter 버퍼의 NotificationView를 확인했다. 타 계정 구독에는 미전달. 하나의 객체를 재사용한 테스트가 아니며, 실제 두 Pod·브라우저 네트워크 E2E를 검증한 것은 아니다.
- Redis 장애 테스트는 별도 실제 Redis를 기동·연결한 뒤 중단하고 실제 발행기에 그 연결을 전달하여 FAILED/REDIS_PUBLISH_FAILED 기록, 이미 커밋된 리포트·알림 목록 보존을 확인했다. 실제 report worker를 실행한 E2E와 구분한다.
- SseEmitters 구독 등록을 heartbeat보다 먼저 수행하고, 무효화 시 구독/heartbeat 단일 정리를 검사했다. 기존 feedback client·SSE 통합·JFR/연결 정리 회귀 포함.
- `python scripts/validate_notification_contracts.py`: 실제 MockMvc 알림 목록·설정 JSON의 OpenAPI 대조 통과.
- `python scripts/validate_report_contracts.py`: 실제 테스트 RabbitMQ 봉투/데이터 4종과 core HTTP 리포트 상세 계약 통과.
- bootJar에 spring-data-redis·Lettuce 포함, Testcontainers·JUnit·Mockito·Flyway 미포함 확인. 로컬 검증이며 원격 CI·배포·실제 Google 로그인은 검증하지 않았다.
- 설계/소유권/레이어 경계와 변경 범위를 검토하고 `git diff --check` 통과. 기존 checkout 및 다른 작업 worktree는 수정하지 않았다.

## PR 준비

- head: feature/core-notifications, base: develop. GitHub 실제 기본 브랜치도 develop으로 조회 확인했다.
- 시작 기준은 78bbdc1. 검증 도중 develop에 감사 수정 47e5ffe가 추가됐으며 이 작업의 테스트 결과는 78bbdc1 + #44 변경 기준이다. 새 감사 수정은 알림과 독립된 사용량/문서 변경이다.
- 제목: `feat: 앱 내 알림과 Redis 기반 SSE 구현`
- 본문 초안:

```markdown
Closes #44

리포트 완료·실패를 보호자 알림에 저장하고, 커밋 이후 Redis Pub/Sub으로 각 core 구독에 전달합니다.

- 본인 알림 목록·개별/전체 읽음·유형별 수신 설정·SSE 구현, 학생의 보호자 알림 접근 차단
- REPORT_FAILED 독립 유형과 V12 CHECK 확장, 이벤트 중복·롤백·수신 거부 처리
- 15초 heartbeat·5분 구독, 세션 재검사·종료 정리, ready 후 목록 재조회 계약
- core 179개 테스트·bootJar, 실제 Redis 독립 구독 2개, 실제 HTTP/이벤트 계약, 전체 DB 스키마 검사 통과

후속: #58 PIN 잠금·기기 등록 알림 정책, 프론트 상세 링크 query 소비, 실제 report worker·상품 공급자 E2E.
두 Pod 배포·원격 CI 검증 결과는 포함하지 않습니다.
```
