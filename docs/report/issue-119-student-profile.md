# #119 리포트 생성용 학생 별명 조회

## 기준과 범위

2026-10-29 원격 fetch 후 기준은 `85bf1079c34a3e713bcf5eedf0cfdfd7822dc5a4`다. 사용자 지정 base는 `feature/core-support-payments-integration`, head는 `feature/core-student-profile`이다. 당시 `origin/develop`은 `c608f52aa0f7b651133603a629a8347be61b3282`이며 base의 조상이다. origin은 SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM, upstream은 없다. 기존 체크아웃과 #47 worktree는 변경하지 않는다.

이슈 본문은 제안 상태였고 댓글은 0개였다. 같은 날 사용자가 이 채팅에서 아래 계약을 확정하고 **core만 구현, report 변경은 담당자에게 인계**를 선택했다. 기존 필터·SQL·스키마·공개 프로필/삭제/로그인·report 제품 코드는 수정하지 않는다. 새 production 의존성도 없다. 설계·OpenAPI를 먼저 추가하고 구현한다.

## 확정 계약과 보안

`GET /internal/students/{studentId}/profile` → `200 {studentId, nickname}`, `Cache-Control: no-store`.

| 조건 | HTTP / code |
|---|---|
| 내부 토큰 누락·불일치, Bearer만 전달 | 401 UNAUTHENTICATED |
| SYSTEM 외·역할 누락·학생 scope 누락/불일치 | 403 FORBIDDEN |
| 잘못된 UUID (유효 내부 토큰 사용) | 400 VALIDATION_FAILED |
| 미존재·ACTIVE 외 상태 | 404 NOT_FOUND |
| 예상하지 못한 조회 실패 | 500 INTERNAL_ERROR |

기존 RFC 9457 Problem Details를 사용한다. 현재 DB에는 ACTIVE·DELETION_REQUESTED·DELETED만 있다. 비활성이라는 이유로 임의 INACTIVE enum을 만들지 않으며 삭제 진행·완료 모두 404다. RECORDS 완료 뒤에도 DELETION_REQUESTED를 유지하는 #45 정책을 그대로 따른다.

호출은 `InternalAuthFilter` → `InternalStudentProfileController` → `InternalStudentProfileService` → `ChildManagementRepository.profile` → `ChildManagementMapper.profile`이다. 서비스가 SYSTEM을 확인하고 `UserContext.requireStudent`로 scope를 검사한 뒤 DB를 조회한다. 기존 LinkedStudent 전체를 노출하지 않고 전용 DTO로 id→studentId·nickname만 변환한다. 필터의 finally가 요청 컨텍스트를 정리한다. 별명·토큰·학생 UUID를 새 로그에 기록하지 않는다.

## report 담당자 인계

현재 `CoreClient`는 삭제 완료 콜백에 사용되고 `worker.run`의 기본 생성기는 `UnconfiguredGenerator`다. #50은 큐·작업 기반, #52는 서술·가림, #53은 렌더링, #55는 삭제를 담당한다. 기존 `internal_client`가 토큰과 SYSTEM/student scope를 붙이므로 이를 재사용한다. 삭제 완료 API·실패 처리는 보존한다.

후속 구현 경로: worker의 기존 컨텍스트 안에서 CoreClient로 위 API 호출 → 응답 UUID 대조·nickname 검증 → 내부 `GenerateReport.display_name`에 보관 → Metrics/Narrative/Rendering 생성기 조립. RenderingGenerator는 이 별명을 HTML/PDF/Markdown 제목에 사용한다. `report.generate.v1`의 여섯 필드 및 additionalProperties=false는 유지한다.

403·404를 생성 실패로 처리하고 UUID·빈 문자열·임의 별명으로 대체하지 않는다. 통신 오류는 기존 작업 실패/재시도 정책 경계에 연결한다. 현재 GenerationService의 종료 FAILED와 메시지 소비자의 재시도는 같은 것이 아니므로, 담당자는 실제 예외 처리 위치를 확인해 정책과 맞춰야 한다. 새 HTTP 재시도를 추가하지 않는다.

`NarrativeGenerator.scrub`는 이름 계열 필드를 제거하고 본문의 알려진 display_name을 가린다. 조회 성공만으로 개인정보 가림이 완료되는 것은 아니다. report 담당자는 실제 worker 실행에서 최종 `AiClient.narrative` HTTP payload를 캡처해 별명·이름이 없는지 확인하고 렌더링 제목에는 실제 조회 별명이 남는지 확인해야 한다. 현재 테스트에서 조립한 생성기나 HTTP 대역은 실제 worker 연결 완료 근거가 아니다.

이 채팅은 다른 채팅·담당자에게 메시지나 GitHub 댓글을 보내지 않는다. report 적용 담당자는 해당 후속 작업의 추적 이슈/브랜치를 기록하고, core 계약과 403·404·통신 오류 처리 및 AI payload 검증 결과를 이슈 #119에 연결할 수 있다.

report 변경을 반영한 브랜치에서 다음 회귀를 실행한다(이번 core 작업에서는 미실행).

```sh
cd backend/report-service
uv sync --frozen
uv run pytest tests/test_worker_broker.py tests/test_narrative.py tests/test_rendering.py tests/test_deletion.py tests/test_deletion_broker.py -q
uv run ruff check .
uv run ruff format --check .
```

위 명령만으로 전체 연결이 입증되지는 않는다. 후속 담당자는 별도 Docker 프로젝트·합성 ACTIVE 학생 DB·실제 core·연결된 worker·브로커·스토리지를 준비하고 공유 compose/DB를 변경하지 않아야 한다. 실제 report.generate를 소비시킨 뒤 core HTTP 조회·세 출력 제목·최종 AI 송신 payload·403/404/통신 오류별 작업 상태와 retry/DLQ를 함께 검증해야 한다. 전용 환경의 실행 명령은 승인된 worker bootstrap과 검증 구성에 맞춰 해당 담당자가 기록한다. 아직 없는 실행 파일/검증 명령이 존재한다고 가정하지 않는다.

## 검증 결과

2026-10-29 최종 소스에서 코드·계약·테스트 작성을 마친 뒤 일괄 실행했다.

| 검증 | 실제 결과 |
|---|---|
| core 전체 `test bootJar` | JDK 21 Docker/Linux, **43개 클래스·270개 테스트 통과**, 실패/오류/생략 0, BUILD SUCCESSFUL (4분 54초) |
| 신규 HTTP 권한 테스트 | 7개 통과. 실제 InternalAuthFilter + 신규 service + mock repository. 토큰 누락/빈 값/오류·Bearer만 전달, 역할 누락/SYSTEM 외, scope 누락/불일치, 2개 응답 필드, no-store, UUID 400, 조회 404/500, 각 요청 뒤 컨텍스트 정리 |
| 신규 실제 HTTP·DB 통합 | 5개 통과. Docker 내 실제 Spring 서버의 임의 포트에 Java HttpClient로 접속. 실제 PostgreSQL/Flyway/Mapper의 ACTIVE·DELETION_REQUESTED·DELETED·미존재, 인증/권한 거부, 후속 요청 scope 독립성 확인 |
| 공개 프로필·삭제·로그인 회귀 | 전체 core test에 기존 AccountManagementTest·AuthFlowIntegrationTest·ConsentChildrenTest·StudentDeviceAuthTest 등 포함. Google/하위 서비스 대역 범위는 기존 테스트를 따르며 실제 Google 로그인/배포 검증이 아님 |
| 공통 계약·스크립트 | `python -O -m unittest discover -s scripts/tests -q`: **69개 통과**, 신규 #119 계약 검사 4개 포함 |
| core OpenAPI | openapi-spec-validator 표준 검사 통과 (3.1) |
| 입력 소스 대조 | 검증 tar와 현재 core 입력 파일 **292개 바이트 일치** |
| 경계·변경 검토 | guardianship 내부 계층·DTO 변환·package/경로 일치, 기존 필터/SQL/스키마/report 제품 코드 불변, secret/.env/임시 산출물 제외, `git diff --check` 통과 |

실행 명령은 core 디렉터리에서 `bash gradlew test bootJar --no-daemon --max-workers=1 --no-watch-fs --console=plain '-Dorg.gradle.jvmargs=-Xmx512m -XX:ActiveProcessorCount=2' '-Pkotlin.compiler.execution.strategy=in-process' --init-script /verify/limits.gradle`다. 검증 전용 init script는 Test fork 1개·heap 512m·ActiveProcessorCount=2만 제한한다. 기존 캐시는 읽기 전용 원본에서 #119 전용 볼륨으로 복사했으며 #47 캐시/실행 서비스를 사용하거나 수정하지 않았다. 전체 test task를 실행했고 테스트 필터는 없다.

JAR SHA-256: `c0bb716d77abcdd998848132bbe4e76ddae3e49e52edc9dbb1a75c7378f5910f`. 로그·결과 XML/HTML tar·JAR·집계 JSON·검증 입력 tar는 저장소 밖 `issue119-verification`에 보존한다. Kotlin annotation target의 향후 동작 경고와 JVM CDS 경고가 있으나 빌드 실패는 없다. 최초 기본 권한의 fetch/Docker 접근은 권한 부족이었고 필요한 권한으로 재실행해 성공했다. 제품 코드 검증 실패나 테스트 생략은 없다.

**미검증:** 실제 report-worker → core 호출, 조회 별명을 사용한 실제 생성 파일, 최종 AI 전송 payload, report 통신 오류별 FAILED/retry/DLQ, 원격 CI·병합·배포. 사용자가 report 변경을 담당자에게 인계하도록 범위를 제한했으므로 Java 테스트 호출자를 실제 worker 연결로 집계하지 않는다. 위 후속 조건과 회귀 명령은 report 담당자가 실행해야 한다. 현재 core 범위에 허락 대기 사항은 없다.

## PR 준비 정보

- 대상 저장소: SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM
- base: `feature/core-support-payments-integration`, head: `feature/core-student-profile`
- 제목: `feat: 리포트 생성용 학생 별명 조회 내부 API 추가`
- 본문 초안: 리포트 생성에 필요한 활성 학생 UUID·별명 조회 API를 추가했다. 기존 내부 필터를 재사용하고 SYSTEM·학생 scope를 조회 전에 검사하며 ACTIVE 외 상태는 404로 반환한다. 공개 프로필·삭제·로그인과 report 코드는 유지했다. core 270개 및 계약 69개, bootJar·OpenAPI·diff 검사를 통과했다. report-worker 연결·제목·최종 AI payload 검증은 report 담당자 후속 범위다. 연관 이슈는 #119다.
- 추천 Label: 이슈 #119에서 등록·설명을 확인한 `enhancement`(New feature or request), `area:core`(core 영역). Label 목록 전용 조회는 연결 도구의 허용 endpoint에 없어 전체 목록을 재조회하지 못했다. Type 목록도 확인하지 못했으며 설정하지 않았다. PR 메타데이터는 사용자가 생성 화면에서 확인·설정한다.
- #119 전체 완료 조건에는 실제 worker 연결·제목·가림 검증이 남아 있어 이 core 범위 초안에 자동 종료 구문을 넣지 않는다. 전체 조건이 충족된 최종 PR에 `Closes #119`를 포함한다. 원격 저장소 조회로 확인한 기본 브랜치는 `develop`이다. 현재 통합 브랜치 대상 PR은 병합해도 자동 종료되지 않으며, 기본 브랜치 develop으로 통합하는 최종 PR에 종료 구문을 유지해야 한다.
- PR 생성·댓글 전송·병합·이슈 종료·squash/rebase/force push는 수행하지 않는다. 실제 커밋 SHA·push·최종 working tree 상태는 완료 응답에서 보고한다.
