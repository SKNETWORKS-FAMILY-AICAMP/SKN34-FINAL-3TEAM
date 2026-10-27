# #51~#55 실제 연동에 필요한 자료

2026-10-27 GitHub 이슈 본문·담당자와 로컬 구현을 다시 대조했다. 여기서 자료는 원본 데이터셋이 아니라 **확정된 API/메시지 형식, 가짜 값으로 만든 요청·응답 예시, 연결할 구현 커밋/PR, 실행 설정**을 뜻한다. AI Hub 자료를 추가로 받거나 저장소에 올릴 필요는 없다.

| 내 이슈 | 자료가 나와야 하는 이슈·담당 | 구체적으로 받을 내용 | 사용하는 곳 |
|---|---|---|---|
| #51 학습 기록·집계 | #27 learning 학습 기록 조회, Overlay1010 | attempts/thinking-types/changes 실제 JSON 예시와 필드 정의. 학생/기간/state, 페이지 봉투, 답변 ID·버전·제출 시각·원문·처리 상태, 도움 열람 시각, 완료 시각·돌아보기. 주를 걸친 최초/마지막 답변 제공 기준 포함 | API 4.1.1 입력 구현안과 대조, 수치/전후 변화 계산 |
| #52 서술·대조 | #64 AI 리포트 서술 API, 현재 미배정 | POST /internal/report-narratives 입력 배열 형태, narrative 객체, eveningQuestion, citedQuotes의 attemptId/answerId/answerVersion/quote, versions.prompt/model 응답 예시. 서술 길이·질문 말투·timeout도 합의 | API 4.2.1 및 AiClient 계약 연결 |
| #52 서술·대조 | #27, Overlay1010 | GET /internal/records/evidence?answerIds= 응답: 답변/시도 ID·버전·원문 및 삭제 available:false 또는 410 예시 | AI가 쓴 인용과 실제 원문 대조 |
| #53 파일 생성 | #42 core 리포트, 김동섭 | 학생 표시 이름의 신뢰할 수 있는 공급 경로. 메시지에 넣을지 별도 내부 조회로 받을지 합의 | 자녀 닉네임 렌더링, AI 전송 전 이름 가림 |
| #53 파일 생성 | #17 로컬 저장소, 김동섭/인프라 | 기존 reports 버킷을 사용하는 MinIO endpoint·브라우저 접근 주소·환경변수/Secret 주입 방법. AWS는 별도 자원 작업에서 S3/IAM 확정 | S3 업로드·다운로드 실제 연결. #17에 버킷 이름은 이미 sagomungchi-local-reports로 정해져 있음 |
| #54 조회·다운로드 | #42 core 리포트, 김동섭 | 공개 API → report 내부 API 프록시, X-Internal-Token·X-Student-Scope 전달, 현재 유료/무료 권한을 core가 계산해 넘기는 방식 | 자녀 범위 검사, 현재 권한에 따른 full/free 상세·파일 선택 |
| #54 조회·다운로드 | #27 및 #17 | #27 현재 evidence/삭제 응답, #17 브라우저에서 실제 접근 가능한 서명 URL | 근거 열람과 다운로드 |
| #55 삭제 | #45 core 자녀 삭제, 김동섭 | student.deleted.v1 JSON/schema: subject, deletionRequestId, scope, time. 완료 API의 요청/성공/중복 응답 예시와 실제 구현 PR | 삭제 이벤트 해석, 삭제 후 core에 service:report 완료 보고 |
| #55 삭제 | #45·#42, 김동섭 및 조장 정책 확인 | PROFILE/RECORDS 범위, 생성 중 삭제 처리, 삭제 전 queued 작업 취소·늦은 결과 무시, 최초 이벤트 time 보존, 삭제 표식 보존 기준 | 삭제한 자료의 재생성 방지와 새 리포트 허용 시점 결정 |

공통 선행인 #42에서 `contracts/events/`의 report.generate / report.started / report.completed / report.failed 공유 schema와 JSON 예시도 받아야 한다. report 측 codec 구현·연결은 우리가 맡고, 공유 규격 정의를 report에서 중복 작성하지 않는다.

## 이미 결정했거나 구현한 내용

- #51 연결어 네 개(왜냐하면·때문·그래서·따라서)와 API의 표본 상태 기준을 구현했다. 같은 질문을 다시 할 필요는 없다.
- #52 AI 장애 FAILED / 대조 실패 TEMPLATE는 사용자가 확정했다. #64와 이 기준을 공유하면 된다. 템플릿 문구는 report 코드에 구현되어 있으며 문구 변경이 필요하면 검토한다.
- #53 PDF 라이브러리·한글 폰트·파일 키·revision 분리는 report에 구현했다. 새 라이브러리를 다른 담당자가 정해줘야 하는 상태가 아니다.
- #54 URL 300초와 현재 권한에 따른 조회 가림은 구현 기본안이다. 최종 팀 운영값과 권한 전달 계약은 확인해야 한다.
- #55 양 범위의 기존 리포트 물리 삭제, PROFILE 이후 생성 차단/RECORDS 이후 새 명령 허용은 구현 기본안이며 팀 확정 전 운영 적용하지 않는다. 추가 guard migration도 리뷰 대상이다.

## 최신 develop 병합 확인

develop `7188b69`를 누적 브랜치 feature/report-deletion에 병합했다(8b76b1f). #51~#54 개별 브랜치도 merge-tree 검사에서 충돌이 없었다. 개별 브랜치를 모두 최신화한 것은 아니며 실제 병합은 누적 브랜치에 수행했다.

이번 develop은 미션 조회·데모 미션 시드와 인증/설계 문서 정리를 포함한다. report 코드나 report migration의 중복 추가는 없었다. 새 미션 조회 API는 #27 학습 기록 조회 API를 대신하지 않는다. 따라서 #27/#42/#45/#64와의 실제 연동 확인은 여전히 필요하다. 최종 회귀 결과는 통합 인계 문서에 기록한다.
