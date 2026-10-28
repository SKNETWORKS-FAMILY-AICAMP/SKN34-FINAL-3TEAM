# 리포트 실제 연동에 남은 입력

2026-10-28 develop `b344797`(PR #105, #27) 기준. 로컬 develop과 누적 작업 브랜치 `feature/report-deletion`에 반영했다. 다른 report 브랜치는 이번에 갱신하지 않았다. 필요한 자료는 API 형식·합성 응답·구현 PR·설정이며 AI Hub 원본이나 운영 자격 증명을 저장소에 올리지 않는다. 이번 확인은 #27 범위이며 아래 다른 담당 항목을 새로 검증한 것은 아니다.

| 대상 | 담당/이슈 | 필요한 내용 |
|---|---|---|
| #51·#52·#54 | report 담당(우리 쪽) | #27 PR·실제 DTO·OpenAPI·테스트를 확보했다. 학생 ID 수신, 학생 작성 칸 기준 수치 계산, nullable followup 처리를 보완하고 실제 연동한다. #27 담당자의 추가 형식 답변을 기다릴 필요는 없다. |
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
- #27 [PR #105](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/pull/105)의 실제 DTO·SQL·OpenAPI·회귀 테스트·[구현 보고서](learning-records.md). 아래 기존 질문은 공급 코드와 문서로 확인했다.

## #27 답변 전 report 사전 정리 기록 (2026-10-28)

다음은 답변 전에 수행한 report 보완 기록이다. 이후 #27 계약 확인은 아래 절에 갱신했다. 실제 서비스 연동 완료를 뜻하지 않는다.

- learning 돌아보기 입력은 `reflection:null`(생략도 허용) 또는 `{difficulty:EASY|NORMAL|HARD,text:string|null,createdAt}`이다. `{written:false}`는 입력 객체가 아니라 report 출력/저장 항목의 표현이다. 난이도만 작성한 경우는 `written:true,text:null`로 구분한다.
- 내부 계산·저장에는 난이도 코드를 유지하고 API 3.4·PDF·HTML·Markdown은 `쉬웠어요`·`보통`·`어려웠어요`를 표시한다. OpenAPI도 동일하며 무료/유료 표시는 같다.
- attempts 삭제 표식은 필수가 아니다. 정상 `NO_RECORD` 빈 목록도 허용한다. evidence 삭제 표시와 #55 삭제 완료 절차는 별개다.
- 도움 열람은 조회 시작일 이전이라도 최초 답변 전 기록을 포함한다. 시간은 오프셋 포함, 페이지는 0부터, 연결어는 확정된 네 개를 유지한다.

## #27 병합 후 확인 결과 (2026-10-28)

| 확인 대상 | 확보한 계약·근거 | 판단 |
|---|---|---|
| 구현 PR·명세 | PR #105 병합, `contracts/openapi/learning-service.yaml`의 기록 조회 스키마, `record/controller`·`service`·MyBatis SQL | 확보. 로컬 develop과 누적 report 브랜치에 반영 |
| evidence 정상 응답 | `{items:[...]}`. 정상 항목은 ID·시도·버전·전체 평문 quote·제목·제출 시각·available을 제공. `quote`는 attempts `text`와 같음 | 원문·버전 확인 완료. 잘린 미리보기 문제 없음 |
| 삭제된 근거 | 요청 ID를 중복 제거한 순서로 정상/삭제 항목 모두 반환. 없는 답변·삭제 학생은 `available:false`, 원문 없음 | 개별 삭제 표시를 확보. attempts의 삭제 표식 항목은 없음. report는 중복 없는 ID를 전송 |
| 평문 없는 답변 | 모든 입력 방식의 `text`는 문자열, 비어 있으면 `""`. evidence SQL도 null을 빈 문자열로 변환 | 정상 available=true/quote=null을 허용하도록 바꿀 필요 없음 |
| 시각·돌아보기 | answers·hintUsages는 시작일 이전 포함, 종료일까지. completedAt 제공, 돌아보기 미작성·기간 밖 null, 작성 시 createdAt 포함. EASY·NORMAL·HARD 유지 | 필요한 입력 확보. 난이도 한글 표시는 기존 report 처리 재사용 |
| P08·페이지 | 기간 내 제출 시도, 미완료·PENDING/RUNNING 포함. 종료일까지 전부 FAILED인 시도만 제외. KST 양 끝 포함. attempts·changes page 0부터, size 최대 100 | 기준 확보. thinking-types는 다섯 유형, 별도 페이지 없음 |
| 합성 응답 자료 | 제공자 테스트의 합성 데이터·JSON 응답 검증과 보고서의 결과 요약은 있음. 네 조회의 완전한 응답을 모은 별도 JSON 파일은 찾지 못함 | 실제 코드·스키마·테스트로 우리 쪽에서 재현 가능. 별도 파일 미제공 때문에 구현을 기다릴 필요는 없음 |

## 우리 쪽에 남은 계약 보완

| 대상 | 현재 차이 | 다음 작업 |
|---|---|---|
| learning_client.py의 ScopeInput·_check_scope | report는 최상위 `childId` 필수, #27은 `studentId` 제공 | learning 입력 검사만 studentId로 변경. report 공개 응답 childId까지 일괄 변경하지 않음 |
| AnswerInput·AnswerRecord·MetricsCalculator | report는 표시용 text로 전후 글자 수 계산. #27의 논술·풀이 text에는 학생이 쓰지 않은 칸 이름이 포함됨 | 이미 제공되는 inputType·content를 받아 학생 작성 칸만 집계. text는 표시·원문 근거 대조에 보존 |
| ChangeInput·변화 출력 | #27 followup은 string 또는 null, report 입력은 문자열만 허용 | null 수신부터 저장·API·파일 표시까지 일관되게 처리하고 문구를 임의로 생성하지 않는지 검증 |

공급자 스키마에 맞는 합성 입력으로 현재 report 수신부를 직접 검사했다. studentId 페이지는 childId 누락 오류, followup:null은 문자열 형식 오류를 재현했다. 논술 기본 칸 이름을 붙인 합성 예에서 표시용 text는 39자지만 학생 작성 내용은 11자여서 현재 집계 차이도 재현했다. 이는 실제 서비스 간 통합 테스트가 아닌 계약 진단이다. 이번에는 수신부 제품 코드를 변경하지 않았다.

병합 후 저장소 계약 검사 **54개 통과**. 과거 report 203개 통과 결과는 당시 고정 입력 기준이며 새 #27 응답과의 연동 성공을 뜻하지 않는다. #27의 학생 기록 삭제 소비자는 별도 미구현이라고 명시되어 있어 #55 전체 삭제 연동 완료로 판단하지 않는다.

[인계 문서](report-service-handoff.md)와 [에픽 점검](report-epic-readiness.md)을 참고한다. Slack·이슈 댓글로 요청을 보내지 않았다.
