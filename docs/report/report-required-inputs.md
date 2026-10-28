# #51~#55 실제 연동에 필요한 자료

> 최신 정정(2026-10-28): #42/#45는 develop `78bbdc1`에 병합되어 공유 메시지 규격·삭제 완료 API·학생 scope 전달이 확보되었다. 이 자료를 다시 요청할 필요는 없다. 현재 필요한 것은 #27 실제 기록 DTO, 닉네임 공급, 현재 상품 권한 연결, 삭제 재개 정책 정합성 등이며 [에픽 #56 점검](report-epic-readiness.md)을 따른다. 아래 표는 당시 확인 기록이다.

2026-10-27 GitHub 이슈 본문·담당자와 로컬 구현을 다시 대조했다. 여기서 자료는 원본 데이터셋이 아니라 **확정된 API/메시지 형식, 가짜 값으로 만든 요청·응답 예시, 연결할 구현 커밋/PR, 실행 설정**을 뜻한다. AI Hub 자료를 추가로 받거나 저장소에 올릴 필요는 없다.

## GitHub·develop 재조회로 확인한 내용

직접 조회한 #17/#27/#42/#45/#51~#56/#64에는 댓글이 없었다. 원격 develop은 `7188b69`로 직전 병합 기준과 같았다. Open 여부만으로 미구현을 판단하지 않고 develop의 실제 파일도 대조했다.

| 항목 | 이미 확인된 내용 | 실제로 남은 내용 |
|---|---|---|
| #51 입력 (#27) | 조회 경로, 5유형, 답변 버전·도움·돌아보기·원문 제공, 메모 제외, 삭제 available:false, 0/1~4/5건 이상 상태 규칙은 이슈와 설계에 있음 | develop의 learning `record/`에는 .gitkeep만 있음. 실제 DTO·페이지·시간 경계·최초/최신 답변 응답을 API 4.1.1 report 구현안과 맞추기 |
| #52 AI (#64) | POST /internal/report-narratives와 입력 5개 배열, 서술/질문/인용 응답, AI 장애 503, 입력 외 인용 제한은 #64에 있음. #64는 Open·미배정 | develop의 report_narrative에는 __init__.py만 있음. 실제 API와 세부 DTO·versions·timeout 합의. report 단독 테스트는 이 구현을 기다릴 필요 없음 |
| #53 저장소 (#17) | #17 Closed, PR #32 merged. 로컬 구성 확인 및 실제 MinIO 업로드·서명 다운로드·삭제 검증 완료 | 닉네임 공급은 #42와 맞추고 AWS 운영 설정은 별도 작업 |
| #54 권한 (#42) | core가 권한 판단, report가 X-Student-Scope 확인. 무료 수치/프리미엄 전체 정책과 생성 시 narrativeEnabled 전달은 설계에 있음 | 실제 core 프록시와 현재 권한 전달 필드 합의. X-Report-Narrative-Enabled는 아직 report 로컬 제안. 만료 300초도 팀 확정값은 아님 |
| #55 삭제 (#45) | 이벤트 이름·subject=studentId·deletionRequestId/scope, 완료 POST 경로·service:report, 양 서비스 보고 후 완료는 설계에 있음. PROFILE은 학생 삭제, RECORDS는 학생 유지/기록 삭제라는 기본 구분도 있음 | 공유 JSON Schema와 core API 구현, 생성 중 삭제/늦은 명령 처리, 추가 guard 보존·운영 적용 검토. RECORDS 완료 시 student 상태를 바꾸지 않는 조건을 문서·코드에 일관되게 명시해야 함 |

**로컬 MinIO는 추가로 주소·버킷 결정을 요청할 대상이 아니다.** develop의 compose.minio.yaml 및 platform-data README에서 컨테이너 주소 `http://minio:9000`, 호스트 기본 API `http://127.0.0.1:9000`, `MINIO_HOST_PORT` 변경, 버킷 `sagomungchi-local-reports`, `.env`의 MINIO_ROOT_USER/MINIO_ROOT_PASSWORD와 kind Secret `platform-data-credentials` 준비 절차를 확인했다. report용 AWS_ACCESS_KEY_ID/AWS_SECRET_ACCESS_KEY 매핑과 S3_PUBLIC_ENDPOINT_URL은 현재 report 브랜치에 추가된 연결 설정이며 아직 develop 기능으로 표현하지 않는다.

2026-10-27 추가 작업으로 실제 MinIO 통합 테스트 3개와 production Linux 이미지의 업로드·호스트 다운로드·삭제 검증을 완료했다. 로컬 저장소 연결 검증을 다시 대기 항목으로 잡지 않는다. 검증 범위와 재현 명령은 [#53 검증 보고서](report-rendering.md)에 기록했다. core·learning·AI의 실제 연결 완료를 뜻하지는 않는다.

**삭제 문서의 구체적인 정합성 확인점:** develop state-diagram 2.2의 note는 RECORDS에 대해 student 상태 유지라고 명시하지만, 같은 절 완료 전이 표와 sequence-diagram 10.1의 마지막 설명은 student DELETED를 scope 조건 없이 적는다. 따라서 삭제 전체 정책을 새로 정할 필요는 없고, #45 구현 시 PROFILE에만 DELETED를 적용한다는 조건을 일치시키는 검토가 필요하다. RUNNING 동시성·삭제 후 새 생성 시각 규칙은 별도 미확정 사항이다.

공유 schema는 develop의 contracts/events에 envelope·llm.usage.recorded만 있고 report.*·student.deleted는 아직 없다. #42/#45 실제 구현 PR은 검색 결과에서 확인되지 않았으며, 최근 PR #73은 #43 모델 레지스트리, #71은 #59 프론트 PIN/테마로 이 계약을 대신하지 않는다.

새 #72 ‘학부모 보고서 화면 챗봇 기능 추가 회의’는 회의 제안이며 확정 요구나 #51~#55 선행 작업으로 추가하지 않는다. #52/#56의 ‘AI 이슈 미발행’과 #56의 ‘#14 미병합’은 현재 상태와 맞지 않는 과거 설명이다. 각각 #64와 병합된 PR #60을 기준으로 확인한다.

근거: [#17](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/17), [PR #32](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/pull/32), [#27](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/27), [#42](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/42), [#45](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/45), [#64](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/64), [#72](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/72). 실제 기능의 실행 성공까지 확인한 것은 아니다.

## 담당자와 맞출 세부 입력

| 내 이슈 | 자료가 나와야 하는 이슈·담당 | 구체적으로 받을 내용 | 사용하는 곳 |
|---|---|---|---|
| #51 학습 기록·집계 | #27 learning 학습 기록 조회, Overlay1010 | attempts/thinking-types/changes 실제 JSON 예시와 필드 정의. 학생/기간/state, 페이지 봉투, 답변 ID·버전·제출 시각·원문·처리 상태, 도움 열람 시각, 완료 시각·돌아보기. 주를 걸친 최초/마지막 답변 제공 기준 포함 | API 4.1.1 입력 구현안과 대조, 수치/전후 변화 계산 |
| #52 서술·대조 | #64 AI 리포트 서술 API, 현재 미배정 | POST /internal/report-narratives 입력 배열 형태, narrative 객체, eveningQuestion, citedQuotes의 attemptId/answerId/answerVersion/quote, versions.prompt/model 응답 예시. 서술 길이·질문 말투·timeout도 합의 | API 4.2.1 및 AiClient 계약 연결 |
| #52 서술·대조 | #27, Overlay1010 | GET /internal/records/evidence?answerIds= 응답: 답변/시도 ID·버전·원문 및 삭제 available:false 또는 410 예시 | AI가 쓴 인용과 실제 원문 대조 |
| #53 파일 생성 | #42 core 리포트, 김동섭 | 학생 표시 이름의 신뢰할 수 있는 공급 경로. 메시지에 넣을지 별도 내부 조회로 받을지 합의 | 자녀 닉네임 렌더링, AI 전송 전 이름 가림 |
| #53 파일 생성 | 운영 인프라 후속 | #17 로컬 구성과 실제 MinIO 연결 검증은 완료. AWS는 별도 자원 작업에서 S3/IAM·버킷 정책 확정 | 로컬 정보 제공·저장소 단독 검증은 남은 작업에서 제외 |
| #54 조회·다운로드 | #42 core 리포트, 김동섭 | 공개 API → report 내부 API 프록시, X-Internal-Token·X-Student-Scope 전달, 현재 유료/무료 권한을 core가 계산해 넘기는 방식 | 자녀 범위 검사, 현재 권한에 따른 full/free 상세·파일 선택 |
| #54 조회·다운로드 | #27 | 현재 evidence/삭제 응답은 연동 대기. 실제 MinIO 서명 URL 다운로드는 검증 완료 | 실제 학습 기록 근거 열람 |
| #55 삭제 | #45 core 자녀 삭제, 김동섭 | student.deleted.v1 JSON/schema: subject, deletionRequestId, scope, time. 완료 API의 요청/성공/중복 응답 예시와 실제 구현 PR | 삭제 이벤트 해석, 삭제 후 core에 service:report 완료 보고 |
| #55 삭제 | #45·#42, 김동섭 및 조장 정책 확인 | PROFILE/RECORDS 기본 의미는 확인됨. RECORDS 완료 시 학생 상태 유지 조건의 문서 일치, 생성 중 삭제 처리, 삭제 전 queued 작업 취소·늦은 결과 무시, 최초 이벤트 time 보존, 삭제 표식 보존 기준 확인 | 삭제한 자료의 재생성 방지와 새 리포트 허용 시점 결정 |

공통 선행인 #42에서 `contracts/events/`의 report.generate / report.started / report.completed / report.failed 공유 schema와 JSON 예시도 받아야 한다. report 측 codec 구현·연결은 우리가 맡고, 공유 규격 정의를 report에서 중복 작성하지 않는다.

## 이미 결정했거나 구현한 내용

- #51 연결어 네 개(왜냐하면·때문·그래서·따라서)와 API의 표본 상태 기준을 구현했다. 같은 질문을 다시 할 필요는 없다.
- #52 AI 장애 FAILED / 대조 실패 TEMPLATE는 사용자가 확정했다. #64와 이 기준을 공유하면 된다. 템플릿 문구는 report 코드에 구현되어 있으며 문구 변경이 필요하면 검토한다.
- #53 PDF 라이브러리·한글 폰트·파일 키·revision 분리는 report에 구현했다. 새 라이브러리를 다른 담당자가 정해줘야 하는 상태가 아니다.
- #54 URL 300초와 현재 권한에 따른 조회 가림은 구현 기본안이다. 최종 팀 운영값과 권한 전달 계약은 확인해야 한다.
- #55 양 범위의 기존 리포트 물리 삭제, PROFILE 이후 생성 차단/RECORDS 이후 새 명령 허용은 구현 기본안이며 팀 확정 전 운영 적용하지 않는다. 추가 guard migration도 리뷰 대상이다.

## 최신 develop 병합 확인 — 2026-10-28

develop `826e4dc`를 누적 브랜치 `feature/report-deletion`에 충돌 없이 병합했다(`9a91fb0`). 이전 `7188b69` 이후 36개 커밋을 반영했다. 개별 #50~#54 보존 브랜치를 모두 최신화한 것은 아니다.

이번 반영에는 PR #73 모델 레지스트리, #71 학생 기기/PIN 화면, #74 학습 시도·초안·생각 열기, #75 core 학습 프록시, #76 답변 제출·버전 저장이 포함된다. report 코드와 세 서비스 migration 파일은 변경되지 않았다. ai Compose 기본 provider/model 변경도 포함되지만 report 서술 API 구현 추가를 뜻하지 않는다.

10월 28일 재조회에서도 #27/#42/#45/#64는 Open이며 댓글이 없었다. develop의 learning `record`와 core `report`는 여전히 빈 폴더이고 AI `report_narrative`에는 초기 파일만 있다. 공유 report.* / student.deleted schema도 아직 없다. 별도 열린 PR #77은 기록 존재 여부의 최소 exists API만 포함하며, #78은 피드백 처리이므로 #27의 전체 기록 조회를 대신하지 않는다. 따라서 기존 외부 연동 대기 항목은 유지한다. 이번 재검증 결과는 [통합 인계 문서](report-service-handoff.md)에 기록한다.
