# 리포트 에픽 #56 현재 진행 범위

2026-10-28 develop `b344797`(#27 PR #105)을 로컬 develop과 누적 `feature/report-deletion`에 반영한 기준. 이 누적 브랜치에서 세 계약 차이 수정과 실제 learning/report HTTP·DB·파일 검증까지 완료했다. 다른 report 브랜치는 이번에 갱신하지 않았다. 다른 담당 항목은 기존 확인 결과이며 이번에 재점검한 범위는 #27 연동이다.

| 이슈 | 이번 결과 | 완료 판단의 경계 |
|---|---|---|
| #50 | 공유 v1 codec·worker·Outbox, 실제 브로커/DB, PR #101 | 생성 기반 범위. 전체 생성기는 닉네임·#64·core 권한 연결 필요 |
| #51 | studentId·학생 작성 칸 집계·nullable followup 정렬 및 #27 실제 API 연동 | 누적 브랜치 검증 완료. 이슈별 PR 반영은 아직 보류 |
| #52 | 가짜 AI 응답 검증·timeout/5xx FAILED·학습 입력 실제 연동 | 실제 AI E2E는 #64·닉네임 연결 이후 |
| #53 | 3종 파일·S3·한글 PDF, 조회/파일 공통 난이도 표시 | 닉네임·운영 AWS 별도 |
| #54 | 난이도·OpenAPI·DB 검사, null 되묻기·실제 evidence 연동 | core 권한 헤더를 포함한 전체 공개 경로 연결 |
| #55 | 삭제 스키마·구독·양 scope 생성 차단·실제 브로커/저장소 결합 검사 | DDL 리뷰·core queued job/늦은 상태 이벤트·양 서비스 E2E |

## 확보와 후속

PR #98의 #42/#45 공유 규격·core scope·내부 헤더·완료 API를 재사용했다. 최초 time도 보존된다. report codec은 이번에 구현했으므로 재요청하지 않는다.

1. #27(Overlay1010): 필요한 자료 확보, 세 report 계약 차이 수정, 실제 learning/report 연동 8개 항목 통과. 실제 합성 응답 JSON도 로컬에 생성했다. 추가 자료 요청 대기는 해소했다. learning 삭제 소비자는 #27 범위 밖이므로 #55 전체 삭제 연동 완료를 뜻하지 않는다. [상세 검증](report-learning-integration.md).
2. #64(조회 시 미배정): 서술 API·prompt/model 버전. #52 가짜 응답 검사와 실제 E2E 구분.
3. core 리포트/상품: 닉네임 내부 조회·실제 생성 entitlement·현재 조회 권한 헤더. 메시지에 닉네임을 추가하지 않는다. 현재 entitlement는 503, 헤더 누락 시 report는 무료 범위 응답.
4. core 삭제: queued job·늦은 terminal 처리. report guard만으로 다른 서비스 상태를 정리할 수 없다. 최신 core와 맞춰 양 scope의 새 생성 차단, 자동 재개는 미구현.
5. 운영: 별도 guard DDL·표식 보존·S3 과거 버전/복제본/캐시 삭제·worker 종료 유예.

[남은 입력](report-required-inputs.md)과 [인계 및 검증](report-service-handoff.md)을 따른다.

## 브랜치·PR

개인 에픽 브랜치는 삭제하고 원래 이슈 브랜치에 보존했다. #85는 계속 중단한다. 사용자 지시로 **PR #101 유지, 추가 PR 등록 중단**. 후속은 코드·문서·검증까지 진행하고 develop 병합/이슈 종료는 하지 않는다. 다음 PR 요청 때 선행 병합·누적 diff를 확인하며 전체 연동이 남은 상태를 에픽 완료로 보고하지 않는다.
