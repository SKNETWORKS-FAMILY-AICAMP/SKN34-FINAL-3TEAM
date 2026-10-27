# #37 기록 존재 확인 선행 API와 실제 데이터 연동

> 최신 develop 통합·검증과 PR 준비 기준은 [PR 준비 보고서](issue-37-pr-preparation.md)를 따른다. 아래 SHA·미커밋/미푸시 표시는 각 검증 시점의 기록이다.

## 범위와 기준

사용자가 #27 담당자에게 계획을 공유한 뒤 최소 API의 선행 구현을 요청했다. 최신 origin/develop b2441711e12ff949cb2859df058a119f0181032c에는 미션 조회만 구현돼 있고 record/는 .gitkeep 상태다. #27은 별도 담당자의 미완료 이슈다. 기존 feature/core-consent-children(기준 ecd6ecf)에서 기존 변경을 보존하며 작업한다.

## 계약과 구현

공개 GET /children 형태는 유지한다. 기존 임시 attempts 목록 의존을 전용 exists 내부 API로 교체한다. learning에는 Controller·Service·Repository·Mapper만 추가하며 기존 내부 인증과 PostgreSQL 테스트 기반을 사용한다. 새 의존성·마이그레이션·공통 필터 변경은 없다. core learning/IdempotencyService·모델·사용량은 수정하지 않는다.

기록 기준과 오류·범위 계약은 api-spec 5.4과 learning-service OpenAPI를 따른다. EXISTS SQL로 제출 답변이 있는 시도만 확인하며 모든 판정 FAILED 및 삭제 표식 학생을 제외한다. 메모·답변 원문·학생 프로필을 읽거나 반환하지 않는다. 삭제 표식 이후 재학습 정책은 이번에 확장하지 않는다.

## 검증 방식

코드·테스트·설정을 모두 작성한 뒤 일괄 검증한다. core 전체 test·bootJar, learning 전체 test·bootJar, OpenAPI/기존 스크립트, 실제 두 JAR·독립 core/learning DB의 HTTP 연결로 0건 false·1건 이상 true 및 권한/제외 기준을 확인한다. learning은 최신 develop 스냅샷에 신규 record 파일만 적용한 조합도 검증하고, 원본 checkout·다른 worktree는 변경하지 않는다. 실제 데이터는 검증용 합성 값을 DB에 저장한 것이며 운영 사용자 기록이나 HTTP 응답 목업은 사용하지 않는다.


## 최종 검증 결과 (2026-10-27)

| 검증 | 실제 실행 범위와 결과 |
|---|---|
| core | 전용 Temurin JDK 21 Docker에서 `bash gradlew test bootJar --no-daemon --max-workers=2 --no-watch-fs --console=plain`: 58/58 통과, 실패·오류·생략 0, BUILD SUCCESSFUL |
| learning | 최신 develop b2441711e12ff949cb2859df058a119f0181032c의 learning 스냅샷에 신규 record 파일 5개만 적용해 같은 명령 실행: 36/36 통과(신규 RecordExistsTest 12개), 실패·오류·생략 0, BUILD SUCCESSFUL |
| API 계약 | `python -O -m unittest discover -s scripts/tests -v`: 29/29 통과. core/learning OpenAPI 3.1 표준 검사 각각 통과 |
| DB | 전용 PostgreSQL 17.11의 `issue37_core_records`와 `issue37_learning_records`에 기존 core 8개·learning 5개 migration 적용 성공. DDL 변경 없음 |
| 실제 서비스 연결 | 최종 core JAR → HTTP → 최신 learning+record JAR → 독립 learning DB 경로를 `scripts/verify_children_records.py`로 검증: 11개 시나리오 PASS |
| 변경 범위 | production 의존성·공통 필터·core learning/IdempotencyService·모델·사용량·기존 migration 변경 없음. 프론트 구현은 이번 후속 작업에서 변경하지 않아 기존 프론트 검증은 반복하지 않음 |

learning snapshot과 현재 worktree의 신규 record 5개 파일은 바이트 단위로 같고, 실행 JAR의 Mapper도 최종 소스와 같다. 최신 develop을 feature 브랜치에 병합하거나 다른 작업의 파일을 변경한 것은 아니다. 최신 learning 조합과 소비자 core feature의 연동을 검증한 것이며 최신 develop의 core 모델/사용량 기능까지 합친 통합 검증은 아니다.

### 실제 HTTP·DB 확인

검증 스크립트는 검증 전용 DB 이름이 아니면 쓰기를 거부한다. 부모 세션·문서는 합성 fixture로 준비하고, 동의 저장·자녀 3명 등록·자녀 목록·철회는 실제 core 공개 API를 호출한다. 기록은 learning DB에 schema-valid 합성 행으로 저장한다. 기존 학습 작성 API 또는 실제 Google 로그인을 검증한 것은 아니다. 작업 종료 시 fixture는 생성한 ID만으로 제거한다.

| 실제 데이터 조건 | GET /children 결과 |
|---|---|
| 자녀 없음 | items=[]·totalElements=0, /me CHILD_REGISTRATION_REQUIRED |
| 기록 0건 | 세 자녀 모두 hasRecords=false, recordState=AVAILABLE |
| 초안만 존재 | false 유지 |
| 다른 학생에만 제출 기록 있음 | 해당 보호자 자녀는 false 유지 |
| 해당 학생 제출 1건(PENDING 판정) | 해당 자녀 true |
| 답변이 있으나 판정이 모두 FAILED | 해당 자녀 false |
| 실패 후 정상 제출 있음 | true |
| 여러 제출 기록 있음 | true |
| 삭제 표식(RECORDS)이 있음 | 남은 물리 행이 있어도 false |
| 내부 API 토큰·역할·범위 | 정상 200, 범위 밖 403, 잘못된 토큰 401, ADMIN 역할 403 |
| 법정대리인 동의 철회 | 해당 자녀 null/CONSENT_REQUIRED, 나머지 자녀의 실제 결과 유지 |

GET /children의 기존 hasRecords nullable/recordState 계약은 유지한다. 정상 조회에서만 false/true이며, DB/HTTP 오류·응답 계약 불일치는 null/UNAVAILABLE다. 이 오류 처리는 core HTTP 클라이언트 대역 테스트에서 404·503·형식 오류·학생 불일치로 확인했고, 실제 0건·1건 이상 결과는 응답 대역이 아닌 두 실행 서비스로 검증했다.

## #27 담당자 인계

- 신규 내부 계약: `GET /internal/records/students/{studentId}/exists` → `{studentId,hasRecords}`.
- 소유 파일: learning `record/controller/RecordExistsController.kt`, `record/service/RecordExistsService.kt`, `record/repository/RecordExistsRepository.kt`, `resources/mybatis/record/RecordExistsMapper.xml`, `src/test/.../record/RecordExistsTest.kt`.
- core 소비자: `guardianship/client/ChildRecordsClient.kt`. 기존 `_common/config/InternalRestClientFactory`가 내부 토큰·검증된 사용자/scope를 전달한다.
- 조회 기준: 제출 답변 존재, 실패만 있는 시도 제외, 삭제 표식 학생 제외. process_status=PENDING/RUNNING/DONE(결과 HELD 포함) 또는 아직 판정 행이 없는 제출은 보존 기록이다. 초안·답변 원문·메모·프로필은 조회/응답 대상이 아니다.
- `deleted_student`에 PROFILE/RECORDS 어느 표식이든 있으면 현재 exists는 false다. 삭제 표식 이후 새 학습 허용/복원 수명주기는 이번에 구현하지 않았다. #27·삭제 기능에서 정책을 확장할 때 이 조건과 테스트를 함께 조정해야 한다.
- #27 전체 summary/thinking-types/attempts/changes/evidence/stats는 미구현 범위로 유지한다. 이 최소 API를 #27 전체 완료로 처리하지 않는다. 전체 조회 구현 시 대상·제외 기준을 검토해 동일하게 적용하고 exists 계약을 변경하면 core 소비자도 함께 맞춘다.
- 새 의존성·migration 없이 구현했다. 현재 브랜치 feature/core-consent-children, 기준 ecd6ecf7880e90341855d2fad6d9e773f3711c67, 새 commit 0개·미푸시다. 담당자에게 메시지/댓글을 자동 전송하지 않았다.


## 종료 상태

전용 core·learning·PostgreSQL 컨테이너와 검증 네트워크를 종료·정리했다. Testcontainers 테스트 실행도 정상 종료했다. 공유 compose·기존 서비스·원본 체크아웃은 그대로다. 원본은 feature/core-google-auth / a2439e6d3d22ad091c1f8e9ec108975c66d5a300이며 깨끗한 작업 트리다. 검증 스냅샷·결과 JSON과 전용 Gradle 캐시는 재현용으로 보존한다.

현재 feature/core-consent-children에는 기존 #37을 포함해 총 49개 변경 파일이 미커밋 상태다. 이전 core 검증 기준 129개 파일과 비교하면 이번 core 후속 수정은 ChildRecordsClient.kt와 ChildRecordsClientTest.kt 두 파일뿐이며 나머지 기존 구현을 보존했다. 실제 .env·비밀키 패턴·기존 migration·core learning/모델/사용량 범위 변경이 없음을 확인했고 최종 git diff --check를 통과했다. commit·push·PR·squash는 수행하지 않았다. 원격 CI·운영 배포·최신 develop 전체 core와의 통합은 미검증이다.


종료 시 origin/develop은 다른 작업의 PR #71 병합으로 526ed245b56c50aa90426bad588ba1394e3d3106까지 진행됐다. 검증 기준 b244171 이후 변경은 프론트와 문서이며 learning 소스는 동일하다. 원격 record/도 여전히 .gitkeep 상태여서 선행 API와 중복 구현은 없음을 확인했다. 새 프론트/기기 화면 전체와 #37 변경의 병합 검증은 이번 범위에 포함하지 않았다.
