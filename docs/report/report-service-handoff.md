# 리포트 #50~#55 구현 및 인계

2026-10-28 develop `47e5ffe`를 원래 이슈 브랜치에 순차 병합했다. 개인 에픽 브랜치는 삭제하고 작업은 보존했다. #85 실제 모델 연동은 계속 중단한다.

같은 날 #27 PR #105가 병합된 develop `b344797`을 로컬 develop과 **누적 `feature/report-deletion` 브랜치**에 반영했다. 다른 report 브랜치는 이번에 갱신하지 않았다. API 문서 충돌 한 곳은 최신 공급 계약과 기존 report 설명을 함께 보존해 해결했다. #27의 PR·코드·OpenAPI·테스트 자료는 확보했으며, 아래의 미연결 항목은 외부 답변 대기가 아니라 report 수신부 보완과 실제 연동 검사다. [대조 결과](report-required-inputs.md).

사용자 최신 지시로 **이미 등록한 #50 PR #101은 유지하고 추가 PR 등록은 중단**한다. 코드·문서·검증 결과를 브랜치에 보존하며 develop 병합이나 이슈 종료는 하지 않는다.

| 이슈 | 브랜치 | 이번에 한 일 | 실제 연결에서 남은 것 |
|---|---|---|---|
| #50 | feature/report-generation | 공유 v1 codec·필수값/학생 검사·worker 생성 구독·트랜잭션 밖 Outbox·실제 브로커 검사, PR #101 | 전체 생성기·닉네임·학습/AI·상품 판정 |
| #51 | feature/report-metrics | 최신 #50 기반·돌아보기 입력/출력 구분·난이도 코드 검사·계약 설명 보완 | #27 DTO 확보. 누적 브랜치에서 학생 ID·학생 작성 칸 집계·nullable followup 차이 확인, 수신부 보완 필요 |
| #52 | feature/report-narrative | 최신 기반 병합·timeout FAILED DB 검사·#42 대기 문구 제거·API 표 복구 | #64·닉네임·#27 실제 연결 검사 |
| #53 | feature/report-rendering | 기존 파일 검증에 더해 조회/파일 공통 난이도 표시·저장 코드 보존 | 닉네임·운영 AWS |
| #54 | feature/report-query | 한글 난이도 응답·OpenAPI 일치·무료/유료/미작성 DB 연계 검사 | core 권한 헤더·#27 evidence 실제 연결 검사(원문/삭제 계약 확보) |
| #55 | feature/report-deletion | 공유 삭제 메시지 엄격 검사·기본 worker 삭제 구독·RECORDS 자동 생성 허용 제거·실제 브로커/DB/MinIO 결합 검사 | core queued job/늦은 terminal·전체 E2E·guard 운영 리뷰 |

브랜치는 #50→#51→#52→#53→#54→#55 누적 구조다. 다음 PR 요청 시 선행 병합 여부와 develop diff를 확인한다. #55 guard DDL은 기존 별도 커밋을 보존하고 초기 migration은 수정하지 않는다.

## 실행 경계

기본 worker는 생성·삭제 큐를 v1으로 구독한다. 삭제는 S3 정리와 core 완료 보고를 조립했다. 전체 생성은 닉네임 공급 경로가 없어 기본 생성기로 가짜 성공을 만들지 않고 GENERATOR_NOT_CONFIGURED FAILED를 기록한다. run(generator=...) 주입 지점을 유지한다. #51~#53 조합은 합성 입력으로 검사하며 core·learning·AI 전체 연동 완료와 구분한다.

## #27 협의 전 사전 보완 (2026-10-28)

목적은 learning 입력과 report 결과를 혼용하지 않도록 하고, 리포트 조회와 파일 표시를 API 문서에 맞추는 것이다. 기존 #51→#52→#53→#54→#55 브랜치에 순서대로 로컬 커밋·병합했다. 이 보완은 아직 원격 push·추가 PR 등록을 하지 않았다.

`reflection:null`과 결과 `written:false`, 작성했으나 text가 null인 경우를 구분했다. learning 난이도 입력은 세 코드만 허용하며 내부 저장 코드는 유지한다. 출력 조립의 공통 매핑으로 조회 API·PDF·HTML·MD에 같은 한글 난이도를 표시하고 OpenAPI를 갱신했다. attempts 삭제 표식의 선택성·페이지·도움 시각도 문서에 명시했다.

#55 병합에서 `report-rendering.md`의 같은 위치에 추가된 과거 MinIO 검증과 새 설명이 충돌했으며 두 내용을 모두 보존해 해결했다. 제품 코드 충돌은 없었다. evidence 원문·삭제·평문 없는 답변 처리는 담당자 답변 전 임의로 변경하지 않았다. 확인 목록은 [남은 입력](report-required-inputs.md)에 정리했다. DB 마이그레이션 변경은 없다.

## 검증 기록

- #27 병합 후 저장소 계약 **54개 통과**. 공급자 스키마에 맞는 합성 입력으로 report의 studentId·nullable followup 수신 오류와 표시용 평문 기반 글자 수 차이를 재현했다. 제품 코드는 이번에 수정하지 않았고, 아래 과거 203개 통과 결과를 최신 #27 실제 연동 성공으로 해석하지 않는다.
- **최신 #27 사전 보완 후 누적 전체: 203개 통과(133.01초), 실패·생략 0개.** Ruff check/format 78파일 통과. 일회용 PostgreSQL·RabbitMQ·MinIO, 실제 Chromium 파일 스냅샷과 OpenAPI 대조를 포함한다. 새로 추가한 입력·표시·DB 보존 검사는 21개다. 실제 #27/core/AI 서비스 연동은 아직 별도다.
- 단계별 집중 검사: #51 입력/계산 56개(0.66초), #53 포함 입력/표시/파일 스냅샷 64개(4.86초), #54 조회/실제 DB/OpenAPI 22개(51.33초). 서로 겹치는 검사이므로 이 숫자를 합산하지 않는다.
- #50: 64개 통과 후 브로커 테스트 정리 옵션 오류 2개 수정·해당 2개 재실행 통과. root 계약 53개, Ruff, Docker 검사. [상세](report-generation-foundation.md).
- #52: 전체 **141개 통과(34.71초)**, Ruff. AI timeout·5xx FAILED, 대조 실패 TEMPLATE. [상세](report-narrative.md).
- #53: 전체 **147개 통과(70.39초)**, Ruff. 새 Docker의 UID 10001·read-only root·네트워크 차단 환경에서 3종 파일·한글 PDF 스냅샷/시각 검사. [상세](report-rendering.md).
- 사전 보완 전 #55 누적 전체 **182개 통과(141.69초)**, Ruff 78파일·root 계약 53개·3개 DB migration/ERD/롤백 재검증 통과. 실제 저장소/브로커와 대역 범위 및 최초 오류 수정은 [삭제 보고서](report-deletion.md)에 기록했다.
- AI Hub·실제 학생 자료·운영 자격 증명을 사용하지 않았다. 기존 TestClient deprecation warning은 기능 실패와 구분한다.

[담당자별 남은 입력](report-required-inputs.md)에 후속 연결을 정리했다. 이미 받은 #42/#45 스키마·scope·완료 API는 재요청하지 않는다. 삭제 재개는 별도 계약 전 허용하지 않는다. URL 300초·S3 보존은 운영 검토 항목이다. Slack·이슈 댓글은 보내지 않았다. #56은 실제 하위 기능과 전체 연동 후 완료 판단한다.
