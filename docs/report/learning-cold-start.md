# learning 초기 무응답과 JDK 21 실행 모델

## 원인과 수정 범위

#201 실제 스케줄 검증에서 learning이 cold start 후 기록 요청·health에 응답하지 않아 리포트 생성이 실패했다. 기존 `feature/issue-35-integration-verification`에서 원인을 분석하고 learning 설정만 수정한다.

- JDK 21, `ActiveProcessorCount=2`, 가상 스레드 활성 상태의 기존 JAR에서 기록 API 16개 동시 첫 요청이 모두 12초 시간 초과했고, 이후 readiness도 응답하지 않았다.
- CPU·DB 잠금 부족은 관측되지 않았다. 스레드 덤프의 carrier 2개는 Jackson `SerializerCache.addAndResolveNonTypedSerializer` 및 Kotlin reflection 저장소 잠금에서 진행하지 못했다. 후자는 `VirtualThread.parkOnCarrierThread`를 포함한다. DB에는 미완료 읽기 트랜잭션이 남았다.
- 이는 애플리케이션 SQL 교착으로 확인된 것이 아니라, JDK 21의 monitor pinning과 라이브러리 초기화 잠금이 carrier를 소진하는 형태다. [Oracle 설명](https://inside.java/2024/02/21/quality-heads-up/)도 synchronized 진입·대기 시 carrier가 반환되지 않아 starvation/deadlock이 생길 수 있음을 명시한다.

learning의 `spring.threads.virtual.enabled`를 false로 바꿔 기존 Tomcat의 제한된 플랫폼 스레드 풀을 사용한다. 캐리어 수 증가·순차 예열·가짜 정상 응답을 사용하지 않는다. core virtual threads, JDK 21 버전, 라이브러리 의존성, API/DTO/DB 및 서비스 경계는 변경하지 않는다. 이는 처리량 개선 주장이 아니라 콜드 초기화 시 서비스 전체 진행 정지를 피하는 변경이다.

## 검증

2026-11-01, 최신 develop `2db122c2b4a973e1d9c8b267893cf45b03d2c3d6`에 이 변경만 적용한 feature 브랜치에서 확인했다. MSW OFF, 실제 Compose PostgreSQL·RabbitMQ·core·learning·ai·report·MinIO와 사전에 승인된 가상 기록 2건을 사용했다.

| 검증 | 실제 결과 |
|---|---|
| learning `gradle test bootJar` (JDK 21, PostgreSQL Testcontainers) | 42 suite, 250 test, 실패·오류·skip 0, JAR 생성 성공 |
| `RecordColdStartHttpTest` | 실제 내장 Tomcat에 4종 기록 API 16개 동시 HTTP 요청 모두 200, 요청 처리 스레드가 platform임을 확인, 직후 readiness 200 |
| 수정 전 JAR, 2 CPU, 첫 기록 API 16개 동시 요청 | 16개 모두 12초 ReadTimeout, 직후 readiness도 시간 초과 |
| 수정 JAR, 동일 2 CPU, 새 JVM 3회 | 매회 첫 동시 요청 16/16 성공 및 readiness 200. 회차별 최대 응답 2.487 / 3.034 / 2.143초 |

회귀 테스트는 새 실행 모델과 병렬 HTTP 응답을 검사한다. 빈 기록 DTO를 쓰는 자동 테스트와 별도로, 실제 기록이 있는 JAR 프로세스를 매회 새로 시작해 콜드 상태를 확인했다. 수치는 이 로컬 표본의 관측값이며 일반 처리량·성능 개선율을 의미하지 않는다.

### #201: 예열 없는 원본 스케줄과 리포트

- learning을 다시 시작하고 기록 API 순차 예열 없이 스케줄을 기다렸다. 테스트 전용 core 프로세스 두 대에 시계 Bean만 주입했다. 원본 `@Scheduled`의 `0 0 7 * * MON`, `Asia/Seoul`, 서비스 호출 및 ShedLock 코드는 변경하거나 직접 호출하지 않았다.
- 테스트 scheduler 시계가 2026-10-05 월요일 07:00 KST에 도달하도록 하고, 집계 시계는 같은 시각으로 고정했다. 실제 OS·DB 시계는 바꾸지 않았다. 따라서 실제 cron 실행·공유 DB 잠금 검증이며, 실제 월요일 벽시계 시각까지 기다린 운영 검증은 아니다.
- 두 프로세스 모두 원본 cron을 등록했다. 한 프로세스만 `LockAssert.assertLocked()` 이후 지점에 진입했고, 공유 DB의 `core-weekly-reports` 잠금 및 해당 기간 작업 1건을 확인했다.
- 기간 `2026-09-28 ~ 2026-10-04`, 작업 `9d481a6f-b045-4ddd-be41-032b10cf2119`, 리포트 `f33879fb-e61c-442e-a4c2-7e7c8df800e9`: `COMPLETED`.
- 실제 OpenAI `gpt-6-luna`, `report@1`, `narrative.source=LLM`. `numbersMatched`, `quotesMatched`, `contentAllowed` 모두 true. 돌아보기 2건·검증된 답변 인용 2건·저녁 질문을 확인했다.
- 실제 보호자 대시보드 학습 2건·완료 2건과 리포트 집계가 일치했다. 보호자 화면에서 해당 기간 리포트 상세·LLM 서술·돌아보기·인용·저녁 질문이 표시됐다. 2건 표본에 대해 비율을 숨기는 `INSUFFICIENT_SAMPLE`도 유지됐다.
- 해당 주간 검증을 위해 가상 기록의 timestamp 10행만 백업·이동했고 조회 확인 후 원래 값으로 복원했다. 기존 실패 리포트는 실패 근거로 보존했다.

### 분석 연동과 #35 종료 판단

같은 수정 서비스에서 보호자 분석 세션 생성·실제 OpenAI SSE 확정 응답도 확인했다. 메시지 `b214d052-50e6-4f46-993d-8a16ec7f90bd`는 학습 2개·완료 2개, 출처 LLM·조회 기록 2건을 표시했다. #202의 학생 종료→Google 보호자 재로그인→대시보드·분석 경로는 앞선 `2db122c` 검증에서 통과했으며, 이번 변경은 core/web 인증 코드를 변경하지 않는다. 이번 분석 재확인은 PIN 전환을 다시 수행한 결과와 구분한다.

#35의 M1/M3 선행 통합 검증과 #202 결과에 이번 #201 콜드 경로 성공을 합치면 Compose 기준 완료 근거가 충족된다. 다만 develop 자체는 수정 전이므로 **이 수정의 develop 병합과 원격 CI 통과 후** #201·#202 완료 근거를 반영하고 #35를 종료한다. #35의 #41·#47 체크박스는 실제 Closed 상태와 동기화가 필요하다. 이 보고서 작성만으로 원격 이슈를 수정·종료하지 않는다.

실제 AWS 배포 검증(#171·#185)과 이용권 화면 계약(#134)은 별도 범위다. 로컬 실제 API 검증을 원격 CI 통과나 운영 배포 성공으로 표현하지 않는다.
