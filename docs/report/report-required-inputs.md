# 리포트 실제 연동에 남은 입력

2026-10-28 develop `47e5ffe` 기준. 과거 미확보 목록을 현재 상태로 교체한다. 필요한 자료는 API 형식·합성 응답·구현 PR·설정이며 AI Hub 원본이나 운영 자격 증명을 저장소에 올리지 않는다.

| 대상 | 담당/이슈 | 필요한 내용 |
|---|---|---|
| #51·#52·#54 | #27, Overlay1010 | 실제 DTO·합성 응답·구현 PR로 API 4.1.1을 대조. 특히 evidence의 원문 범위·answerVersion·삭제된 ID 응답·평문 없는 답변 표현, P08 포함 기준을 확인한다. 아래 협의 상태 참고. |
| #52 | #64, 조회 시 미배정 | 서술 API·API 4.2.1 응답·prompt/model 버전. AI 장애 FAILED, 대조 실패 TEMPLATE 기준 연결. 이슈에서 허용한 가짜 응답 검증은 별도 수행했다. |
| #52·#53 | core 리포트 담당 김동섭 | AI 전송 전 이름 가림과 파일 제목에 쓸 신뢰할 수 있는 닉네임 내부 조회 경로. 확정 report.generate.v1 메시지에는 임의로 추가하지 않는다. |
| 실제 생성·#54 | core 리포트/상품 담당 | 현재 503인 ReportEntitlementService의 실제 상품 판정, 조회 시 X-Report-Narrative-Enabled 전달. 이미 구현된 학생 scope·공개 프록시는 재요청하지 않는다. |
| #55 전체 연동 | #42/#45 core 담당 김동섭 | 삭제 전 queued job 정리·늦은 상태 이벤트 무시. 현재 양 scope 모두 생성 차단. 재개가 필요하면 별도 계약을 확정한다. |
| #55 운영 | 조장·DB/인프라 | 별도 guard migration(20261027_02) 검토·표식 보존·S3 버전/복제본·캐시 처리·종료 유예/DLQ 복구. 운영 DB 미적용. |
| #53 운영 | 인프라 | 운영 S3/IAM/IRSA·공개 endpoint·Chromium /tmp writable volume. 로컬 MinIO 구성과 검증은 확보되어 재요청하지 않는다. |

## 이미 확보·확정된 것

- PR #98의 #42/#45 공유 report.*.v1·student.deleted.v1, core 완료 API·SYSTEM/학생 scope 검사·최초 time 보존.
- 이번 #50의 production codec·worker 구독·Outbox. 다른 담당자에게 report codec 작성을 요청하지 않는다.
- 사용자 확정 연결어(왜냐하면·때문·그래서·따라서), AI 장애 FAILED / 대조 실패 TEMPLATE.
- 구현된 PDF 라이브러리·한글 폰트·S3 키·revision 분리. URL 300초는 설정 가능한 운영 기본값.
- 최신 core와 같은 RECORDS 이후 자동 재개 금지. report도 새 생성 차단으로 수정했다.

## #27 답변 대기 중 report 사전 정리 (2026-10-28)

report 쪽 수신·표시 기준을 코드와 문서에 맞췄다. 아래는 report 구현 기준이며 #27 담당자의 합의나 실제 연동 완료를 뜻하지 않는다.

- learning 돌아보기 입력은 `reflection:null`(생략도 허용) 또는 `{difficulty:EASY|NORMAL|HARD,text:string|null,createdAt}`이다. `{written:false}`는 입력 객체가 아니라 report 출력/저장 항목의 표현이다. 난이도만 작성한 경우는 `written:true,text:null`로 구분한다.
- 내부 계산·저장에는 난이도 코드를 유지하고 API 3.4·PDF·HTML·Markdown은 `쉬웠어요`·`보통`·`어려웠어요`를 표시한다. OpenAPI도 동일하며 무료/유료 표시는 같다.
- attempts 삭제 표식은 필수가 아니다. 정상 `NO_RECORD` 빈 목록도 허용한다. evidence 삭제 표시와 #55 삭제 완료 절차는 별개다.
- 도움 열람은 조회 시작일 이전이라도 최초 답변 전 기록을 포함한다. 시간은 오프셋 포함, 페이지는 0부터, 연결어는 확정된 네 개를 유지한다.

추가 확인할 내용은 다음과 같다. 구현돼 있다면 합성 응답·테스트·PR로 확인한다.

| 확인 대상 | #27에서 필요한 확인 | report 현재 처리 |
|---|---|---|
| evidence 정상 응답 | `{items:[...]}`와 `answerId`, `attemptId`, `answerVersion`, `quote`, 표시용 `missionTitle`, `submittedAt`; quote가 동일 평문 원문인지 미리보기인지 | 50개 ID씩 쉼표로 전달하며 ID·시도·버전 일치를 검사. 현재 인용 후보는 제출 평문이므로 잘린 quote는 검증에 부족할 수 있음 |
| 삭제된 근거 | 요청한 각 ID의 `{answerId,available:false}`; 정상/삭제 혼합 응답과 410 범위 | 요청 ID가 응답에서 빠지면 오류. 410은 그 요청 묶음 전체 이용 불가로 처리하며 저장된 과거 원문을 재사용하지 않음 |
| 평문 없는 답변 | attempts의 `text:null`에 대응하는 evidence가 `available:true,quote:null`일 수 있는지 | attempts의 null은 허용하지만 현재 evidence의 available=true/quote=null은 거부. 답변 확인 후 필요하면 보완 |
| P08 포함/상태 | 기간 내 제출이 있는 미완료 포함, 종료일까지 전부 FAILED인 시도 제외; 개별 PENDING/RUNNING과 조회 전체 PROCESSING/FAILED 구분 | 필수 필드·연속 버전·기간·유형/변화 원문을 대조하며 오류를 빈 기록으로 바꾸지 않음 |
| 실제 계약 확인 | 네 조회의 합성 응답, 기간 경계·100건 초과 페이지·삭제·미작성 사례, 구현 PR | 현재 검증은 고정 응답 기준. 계약 합의 및 #27 병합 뒤 develop 반영·실제 연동 검증 필요 |

[인계 문서](report-service-handoff.md)와 [에픽 점검](report-epic-readiness.md)을 참고한다. Slack·이슈 댓글로 요청을 보내지 않았다.
