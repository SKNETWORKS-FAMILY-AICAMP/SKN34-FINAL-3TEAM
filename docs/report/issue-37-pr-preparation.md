# #37 PR 준비: 최신 develop 통합

## 기준·보존

사용자가 #37 PR 준비를 위한 commit·push를 요청했다. 기존 전용 worktree의 49개 변경 파일을 ZIP·SHA-256 manifest·전용 stash로 보존한 뒤 feature/core-consent-children만 origin/develop 3e3273152e6a27e60e4febf96aa8749dd21b0d73으로 fast-forward하고 기존 작업을 재적용했다. 원본 checkout·다른 worktree는 전환하지 않는다. 기존 기능 커밋은 없었으며 이력 재작성·squash를 사용하지 않는다.

## 충돌 해결과 영향

- OpenAPI는 최신 #43 모델·사용량 계약을 보존하고 #37의 새 4개 경로/6개 operation·10개 schema를 추가했다.
- API 문서는 최신 #43 구현 계약 5.2를 유지하고 #37 동의 계약을 5.3, learning exists 계약을 5.4로 정리했다. 문서 인덱스는 최신 링크와 #37 보고서를 함께 유지한다.
- 프론트 apiClient는 #59 기기/PIN 진입 오류의 로컬 처리와 #37 동의 철회·재진입 이벤트를 함께 유지한다. 자녀 어댑터는 PIN 확장 메타데이터·동의·기록 상태를 함께 보존한다. #37은 PIN DB나 응답 상태를 선구현하지 않는다.
- 최신 대시보드·기기 화면에서 #37이 제공하지 않는 이용권/PIN 정보를 무료·프리미엄·미설정으로 단정하지 않고 확인 필요로 표시한다. 기존 명시적 PIN 상태와 화면 경로는 보존한다.
- 최신 MSW 경로에 동의 관리 API를 연결한다. 계정별 개발 fixture의 동의 이력·철회/재동의·학생 진입 차단을 구현해 새로운 화면의 요청이 실제 서버로 빠지지 않게 한다. 이 상태는 개발용 메모리 fixture이며 운영 저장·Google 로그인 검증을 대신하지 않는다.
- #38은 별도 열린 작업으로 유지하고 core learning/IdempotencyService를 수정하지 않는다. #27 전체 조회·통계도 이번 PR의 완료 범위가 아니다.

## 최종 검증 계획

충돌 해결·호환성 코드·테스트 작성을 모두 마친 뒤 core/learning 전체 test·bootJar, 프론트 test·lint·build·production mock 제외, OpenAPI/스키마 검사, 실제 두 서비스·독립 DB의 기록 유무·권한 흐름, 실제 브라우저 온보딩/철회를 일괄 검증한다. 최신 develop의 기존 기능을 포함한 회귀 결과와 #37 결과를 구분해 기록한다. 검증이 끝나야 현재 작업 파일만 명시적으로 stage해 commit·push한다. PR은 사용자가 develop 대상으로 직접 생성한다.


## 통합 후 검증 결과 (2026-10-27)

| 항목 | 결과 |
|---|---|
| core | JDK 21 `test bootJar --no-daemon --max-workers=2 --no-watch-fs --console=plain`, 전체 81/81 통과·실패/오류/생략 0 |
| learning | 같은 최종 worktree에서 전체 test·bootJar, 57/57 통과·실패/오류/생략 0. 최신 미션/학습 시도·초안·신규 기록 API 포함 |
| frontend | npm ci 후 npm test 75/75, lint·build·production mock 제외 검사 통과. 기존 500KB chunk 안내는 유지 |
| 계약 | 기존 #36·#43와 신규 #37을 포함한 스크립트 34/34, core/learning OpenAPI 3.1 표준 검사 각각 통과 |
| 스키마 | 전용 PostgreSQL 17.11에서 core/learning/report 전체 migration·ERD 대조, 47개 제약 위반 사례·62개 CHECK 값 집합·19개 인덱스, 무변경 재실행·report downgrade/upgrade 통과 |
| 실제 서비스 | 같은 최종 두 JAR·독립 core/learning DB, 실제 HTTP 11개 시나리오 PASS. 0건 false·1건 이상 true·초안/실패/삭제/타 학생 제외·권한/철회 확인 |
| 실제 브라우저 | production build + 최종 core/learning JAR·독립 DB에서 동의→자녀 등록→READY, 새 대시보드의 기록 없음, 이용권/PIN 정보 미제공의 확인 필요 표시, 계정·자녀 동의 철회→차단→재동의, 실제 동석 발급 200과 학생 화면 전환 확인 |

브라우저는 합성 세션과 비구속 시험 문서로 시작했다. 실제 Google API·운영 배포 검증은 아니다. 대시보드 전체 조회·기기/PIN·꾸미기·학생 미션 공개 API의 미구현 404는 그대로 표시되며 #37 완료로 포함하지 않는다. #38은 아직 별도 열린 작업이고 그 변경을 이번 PR에 가져오지 않았다. MSW 결과와 실제 JAR/DB 결과를 구분한다.

## PR 작성 기준

- 저장소: SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM
- base/default branch: develop. 검증 시 origin/develop=3e3273152e6a27e60e4febf96aa8749dd21b0d73.
- head: feature/core-consent-children. 검증한 변경만 기능 커밋으로 준비하고 이력 재작성·squash 없이 push한다. 최종 commit SHA·원격 반영은 Git log와 대화 결과로 확인한다.
- 제목: feat: 동의·자녀 등록과 실제 기록 유무 연동 구현
- 본문에 Closes #37을 포함한다. 현재 기본 브랜치가 develop이므로 해당 base 병합 시 GitHub 종료 키워드 적용 대상이다. #27 전체와 #38은 완료 이슈로 넣지 않는다.
- 현재 등록·설명을 확인한 라벨 후보: enhancement(New feature or request), area:core(core 영역), area:learning(learning 영역), area:web(web 영역). 기존 이슈 #37의 Type은 미설정이며 별도 등록 Type 후보는 확인되지 않았다. PR 메타데이터 설정·생성은 사용자가 직접 한다.
- 원격 CI는 로컬 검사와 구분한다. PR 생성 후 필수 체크 결과를 확인해야 한다. 운영 동의 문서의 게시와 후속 기능은 별도다.
