# PR #77 추가 리뷰 대응 (2026-10-27)

## 요청과 Git 범위

리뷰 4건과 최신 develop 반영을 요청받았고, 사용자가 이어서 commit·push 금지를 명시했다. feature/core-consent-children의 깨끗한 HEAD/원격 head 114d4a6b91991b3d2f2130d2bbf4479f725f76f3에서 origin/develop 826e4dc71e60ba4d2396d3545f87a41524d6db83을 --no-ff --no-commit으로 병합했다. 충돌은 없고 아직 병합 커밋을 만들지 않았다. 원본 checkout·다른 worktree는 수정하지 않는다.

## 구현 결정

1. 별도 guardianship RestClient를 learning의 기록 전용 client/service로 옮긴다. guardianship은 learning service만 호출하고, 기존 LearningClient.exchange와 동일 learning-json 서킷·LearningHttpProperties read timeout을 공유한다. 학생 전용 LearningProxyService는 그대로 유지한다. 외부 JSON 변환은 client에 두고 service 계약은 Boolean?(null=조회 불가)로 제한한다.
2. 기존 최대 자녀 3명을 병렬 조회한다. 요청 단위의 최대 3개 virtual-thread 작업에 검증된 UserContext를 전달하고 finally에서 정리한다. 순서·동의 차단·기록 상태 계약을 유지하며 DB 트랜잭션 동안 HTTP를 호출하지 않는다. 새 의존성·임의 timeout 값·일반화된 실행 계층을 추가하지 않는다.
3. api-spec 3.7의 #7 초안에 5.3/OpenAPI 우선 및 실제 id·plan 미생성을 표시하고 5.4의 develop 확인 기준을 826e4dc로 갱신한다.
4. PR 본문 수치는 최종 실제 검증 결과로 초안을 준비한다. 현재 원격 PR head는 114d4a6이므로 미푸시 로컬 변경의 결과를 원격 head 검증으로 표시하거나 PR 본문을 임의 갱신하지 않는다. Closes #37은 보존한다.

## 검증 범위

모든 코드·테스트 작성을 마친 뒤 core/learning 전체 test·bootJar, API 계약·OpenAPI·diff 검사와 실제 두 서비스·독립 DB의 기록 유무를 검증한다. 공유 서킷 OPEN·HALF_OPEN·timeout·HTTP 오류·부모 scope 및 학생 전용 프록시 권한 유지, 세 자녀 병렬 실행·컨텍스트·목록 순서·동의 차단을 확인한다. 과거 이력 철회와 LINKED 수 계산은 설계에 부합해 변경하지 않는다. 최신 develop에서 들어온 AI 기본 모델·답변 제출 변경은 이 작업의 신규 설계가 아닌 상위 브랜치 변경이다.

## 최종 로컬 검증 결과

검증 대상은 HEAD 114d4a6에 develop 826e4dc를 병합 적용하고 이번 리뷰 수정까지 포함한 미커밋 최종 소스다. 원격 PR head 자체의 검증 결과와 구분한다.

| 검증 | 결과 |
|---|---|
| core 전체 | Temurin JDK 21.0.12.1 Docker에서 `bash gradlew test bootJar --no-daemon --max-workers=2 --no-watch-fs --console=plain`: 109개 통과, 실패·오류·생략 0, BUILD SUCCESSFUL |
| learning 전체 | 같은 JDK·명령으로 80개 통과, 실패·오류·생략 0, BUILD SUCCESSFUL. 최신 develop의 답변 제출 테스트 포함 |
| 스크립트 | `python -O -m unittest discover -s scripts/tests -v`: 40개 통과 |
| OpenAPI | core·learning OpenAPI 표준 검사 통과 |
| 실제 서비스·DB | 새 core·learning JAR와 전용 PostgreSQL 17.11의 독립 DB에서 `scripts/verify_children_records.py` 11개 시나리오 PASS |
| 이동·참조·산출물 | 이전 client의 활성 package/import/경로 참조 없음. 새 JAR에는 LearningRecordClient·LearningRecordService가 있고 이전 ChildRecordsClient 클래스 없음 |

실제 HTTP 검증에서는 자녀 없음과 `/me` 등록 안내, 기록 0건·초안만·타 학생 기록의 false, 제출 1건 이상 true, FAILED만 있는 시도·삭제 표식 제외, 내부 토큰·역할·범위 차단, 법정대리인 동의 철회 후 null/CONSENT_REQUIRED를 확인했다. DB의 기록 행은 검증용 합성 fixture이며 Google 로그인·실제 사용자의 학습 작성 경로를 실행한 것은 아니다. 검증 스크립트가 생성한 행은 종료 시 제거한다.

공유 서킷·timeout·HTTP 오류·세 자녀 병렬 실행은 로컬 HTTP 대역을 사용하는 자동 테스트다. 다른 learning 요청이 연 서킷을 기록 조회도 공유하고 그 역방향도 성립하며, HALF_OPEN 복구와 재시도 없는 timeout 처리를 확인했다. 병렬 테스트는 세 요청이 모두 도착해야 응답하도록 해 중첩 실행과 인증 헤더·결과 순서를 확인했다. 운영 성능을 측정하거나 전체 요청의 엄격한 30초 상한을 보장한 것은 아니다.

프론트 소스는 이번 리뷰에서 변경하지 않아 이전 75개 test·lint·build·브라우저 검증을 반복하지 않았다. 상위 develop에서 가져온 AI 기본 모델 변경의 Python 테스트·실제 모델 호출, 원격 CI·배포는 이번 검증 범위가 아니다. 기존 마이그레이션·production 의존성·학생 전용 프록시·공통 필터는 이번 리뷰에서 변경하지 않았다.

## 커밋·푸시 승인 전 Git 상태 (2026-10-27)

당시 사용자 지시에 따라 commit·push·PR 본문 수정·리뷰 코멘트 전송은 하지 않았다. HEAD와 원격 feature head는 114d4a6이었으며 MERGE_HEAD=826e4dc인 미완료 병합 상태로 보존했다. 상위 develop 변경은 Git 병합으로 index에 올라가 있고, 리뷰 수정은 미스테이징·신규·이동 파일로 남아 있었다. 충돌은 없었다.

## 커밋·푸시 승인과 반영 범위 (2026-10-28)

사용자가 커밋·푸시를 명시적으로 요청해 앞선 금지를 해제했다. origin/develop이 검증 기준 826e4dc와 같고 원격 feature head가 114d4a6임을 재확인했다. develop 병합은 `810be13819a2fc2bfbe1ff75a11d6dcfd580829e` (`chore: 최신 develop 답변 제출 기능 병합`)으로 확정했다. 이번 리뷰 수정은 별도 fix 커밋으로 정리하며 `feature/core-consent-children`만 일반 push하는 범위다. 기존 이력 재작성·main/develop push·PR 본문 원격 편집·외부 코멘트 전송은 포함하지 않는다.

최종 검증 후 기능 코드·설정·테스트는 추가로 변경하지 않았다. 이번 커밋 준비에서는 Git 이력·포함 파일·충돌·공백 검사를 하고, 보고서의 승인 이력만 갱신한다. 앞서 통과한 전체 테스트와 실제 연동 검증은 반복하지 않는다.

## PR 본문 초안

원격 PR의 기존 81개/34개 표기는 게시 당시 최종 검증인 core 102개/스크립트 38개보다 오래된 수치다. 아래는 이번 리뷰 변경을 포함한 최종 검증 결과를 반영한 초안이며, 해당 수정분을 원격에 반영한 뒤 사용한다.

```markdown
Google 로그인 이후 필수 문서 버전 동의와 자녀 등록을 연결하고, 동의 철회 시 계정·자녀 접근을 차단합니다. 보호자별 최대 3명과 학년 3~6을 검증하며 동시 등록도 보호자 행 잠금으로 제한합니다.

- 자녀 기록 유무는 learning의 최소 exists API와 실제 저장 기록으로 조회합니다. 정상 0건은 false, 제출 기록이 있으면 true이며 조회 장애는 null/UNAVAILABLE로 구분합니다.
- 기록 조회는 learning service 경계와 기존 공통 서킷·timeout을 사용하고 최대 3명을 병렬 조회합니다. 부모 컨텍스트를 전달하며 학생 전용 프록시 권한을 유지합니다.
- api-spec의 목업 초안보다 5.3·OpenAPI 확정 계약이 우선함을 명시하고 최신 develop(#76 포함)을 반영했습니다.

검증: JDK 21 core 전체 test 109개·learning 전체 test 80개와 두 bootJar 통과, 스크립트 40개·core/learning OpenAPI 통과. 격리된 실제 두 서비스·독립 PostgreSQL DB에서 기록 0건/1건 이상과 권한·철회 등 11개 시나리오 통과.

프론트는 이번 리뷰에서 변경하지 않았으며 이전 test 75개·lint·build·브라우저 검증을 재실행하지 않았습니다. 원격 CI·배포와 실제 Google 로그인·AI 호출은 이번 검증 범위가 아닙니다. #27 전체 기록 목록·상세·통계와 #58·#59 PIN/기기 기능은 후속 범위입니다.

Closes #37
```

#27 담당자에게는 공개 children 계약·learning exists 경로·제출/실패/삭제 판정 기준은 유지되며 core 소비자 위치만 learning/service와 learning/client로 이동했고 공유 서킷·병렬 호출로 바뀌었다고 전달하면 된다.
