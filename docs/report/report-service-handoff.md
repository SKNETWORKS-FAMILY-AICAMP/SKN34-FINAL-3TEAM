# 리포트 #50~#55 구현 및 인계

2026-10-27 로컬 구현 기준. 최초 기반 develop은 `ecd6ecf`이며, 이후 최신 develop `7188b69`를 현재 `feature/report-deletion`에 병합했다(merge `8b76b1f`). 아래 브랜치는 아직 로컬이며 GitHub push·PR 생성·이슈 종료는 수행하지 않았다. 실제 타 서비스까지 연결한 완료와 report 단독 검증 완료를 구분한다.

## 구현 범위

| 이슈 | 브랜치 | 구현 결과 | 남은 완료 조건 |
|---|---|---|---|
| #50 | feature/report-generation | 상태 전이·job 멱등·Outbox·confirm 후 발행 기록·지연 재시도 연계 | #42 공유 메시지 codec 실제 연결 |
| #51 | feature/report-metrics | 기간/포함 규칙·P08 수치/전후 변화·항목과 evidence 저장 | #27 실제 응답 계약·통합 검증 |
| #52 | feature/report-narrative | AI 요청·이름 가림·수치/인용 대조·검증 실패 템플릿·메타데이터 저장 | AI 서술 API와 버전 실제 제공 |
| #53 | feature/report-rendering | HTML/MD/PDF·한글 폰트·S3 저장·full/free 파일·Docker/CI 의존성 | 실제 MinIO/AWS E2E·버킷 정책 |
| #54 | feature/report-query | 목록/판 선택/상세/현재 evidence/권한별 서명 URL·OpenAPI | core의 현재 entitlement 전달·공개 경로 연동 |
| #55 | feature/report-deletion | 학생별 삭제·processed_event·S3 재시도·core 완료 보고·삭제/생성 장벽·worker 조립 | #45 범위/동시성 정책·생성 시각·공유 스키마 확인, 추가 DDL 검토 |

브랜치는 위 순서대로 누적된다. 나중 브랜치를 develop과 바로 비교하면 앞선 이슈 변경도 포함된다. 검토자는 앞 브랜치 대비 차이로 보거나 #50부터 차례로 병합하고 다음 PR base를 갱신해야 한다. 파일별 부분 복사나 초기 migration 수정으로 맞추지 않는다. #55 추가 migration은 기능 코드와 분리한 커밋으로 검토한다.

## 검증 근거

최신 develop `7188b69` 병합 후에도 Ruff check/format, pytest **144개(56.29초)**, 세 DB 전체 migration/ERD 대조·no-op·report rollback/reapply(**12.0초**)를 다시 통과했다. #51~#54 보존 브랜치는 merge-tree 검사에서 모두 충돌이 없었으며, 실제 병합은 누적된 #55 브랜치에만 수행했다. 미션 조회·데모 시드가 추가되었지만 report 코드/스키마의 중복 변경은 없었다. 필요한 자료의 구체적인 요청 목록은 [#51~#55 필요 자료](report-required-inputs.md)를 따른다.

- report 전체 pytest **144 passed, 0 failed, 0 skipped (58.10초)**. 실제 Docker PostgreSQL/RabbitMQ, HTTP 테스트 대역, moto S3, Chromium을 사용했다. AI Hub·실제 학생 데이터는 사용하지 않았다.
- Ruff check·format check 통과. Starlette TestClient/httpx 사용에 대한 기존 deprecation warning 1개는 실패와 구분한다.
- 일회용 PostgreSQL에서 세 DB migration 적용·재적용 no-op·ERD 타입/NULL/제약/인덱스 대조·report 전체 롤백/재적용 통과(12.7초). core 35/318, learning 19/156, report 7/50 테이블/컬럼, 제약 음성 사례 50개·CHECK 값 집합 64개·인덱스 19개. 검증기 회귀 unittest 18개 통과.
- 최종 `sagomungchi/report-service:issue55-local` Docker 빌드 및 UID 10001·읽기 전용 root + 쓰기 가능한 `/tmp`에서 worker import와 HTML/MD/한글 A4 PDF 2페이지 생성을 확인했다. 운영 이미지에 pytest가 없는 것도 확인했다.
- Compose와 MinIO overlay는 실제 `.env` 대신 가짜 검증 값으로 구성 유효성 검사를 통과했다. 이것은 MinIO 업로드/다운로드 E2E 성공을 의미하지 않는다.
- HTML/MD와 PDF 논리 텍스트 스냅샷을 검사한다. PDF 스냅샷은 OS별 한글 줄바꿈 차이를 허용하도록 공백을 정규화하며, 화면 배치 확인은 별도 렌더링 이미지로 수행했다.

## 다른 담당자에게 필요한 작업

| 대상/담당 | 필요한 결과물 | 연결 위치·이유 | 완료 확인 |
|---|---|---|---|
| #42 김동섭 | report.generate / started / completed / failed 공유 schema와 실제 codec, 표시 이름 공급 경로 | `generation/ports.py`의 ReportEventCodec, `worker.run(codec)`. 공통 메시지를 report에서 중복 정의하지 않는다. 표시 이름은 렌더링·AI 요청 전 이름 가림에 사용한다. | core 발행 → report 소비 → core terminal 반영 계약 테스트 |
| #27 learning 담당(Overlay1010) | API 4.1.1 세 조회의 페이지/시각/최초·최신 답변/도움 요청 및 evidence 원문·버전·삭제 표식 | `LearningClient.records/evidence`. 오류를 빈 기록으로 취급하지 않으므로 실제 응답이 필요하다. | 합성 학생으로 정상/경계 시간/여러 페이지/삭제 evidence 대조 |
| #64 AI 서술 API(현재 assignee 없음) | API 4.2.1 응답, prompt/model 버전, 이름 없는 요청 처리 | `AiClient.narrative`. #64가 새로 발행되어 기존 ‘이슈 미발행’ 인계 내용을 정정한다. API 장애는 FAILED, 대조 실패만 TEMPLATE라는 사용자 결정 적용. | 정상·잘못된 숫자/인용·5xx/timeout 실제 통합 테스트 |
| core 리포트/상품 담당 | 현재 권한으로 계산한 `X-Report-Narrative-Enabled`, 생성 시 narrativeEnabled, 사용자/학생 scope | 무료 전환 후 기존 유료 파일이 새로 노출되지 않도록 core가 권한을 계산해야 한다. 브라우저 제공 헤더를 그대로 신뢰하면 안 된다. | 무료/유료/다운그레이드 상세·다운로드 대조 |
| #45 김동섭·조장 | PROFILE/RECORDS 삭제 범위·진행 중 생성 정책·삭제 표식 보존·student.deleted 스키마 및 멱등 완료 API | `StudentDeletedConsumer`, `CoreClient`, 새 guard migration. 현재 구현 기본안은 팀 확정 전 운영 적용하지 않는다. | 삭제/중복/저장소 장애/완료 API 장애·재시도 E2E |
| #42/#45 core 담당 | 최초 EventEnvelope.time 보존, 삭제 중 신규 요청 차단, 기존 queued job 취소·늦은 상태 이벤트 무시 | report 시간 장벽과 lock만으로 core 작업 상태나 learning 삭제 완료 순서까지 보장할 수 없다. | 오래된 generate/terminal을 삭제 뒤 재전달해 복원·상태 오염이 없는지 확인 |
| 인프라 담당 | S3/MinIO 버킷·IAM/IRSA·서명 endpoint·보존/버전/복제 정책, Chromium `/tmp` writable volume와 종료 유예 | URL 기본안은 설정 가능한 300초. 이미 발급한 URL/외부 캐시·S3 과거 버전은 DB 행 삭제만으로 회수되지 않는다. | 실제 MinIO generate→파일→조회→학생 삭제, 이후 AWS 동작 검증 |

## 확정값과 기본안

사용자 확정: 까닭 연결어 집계는 **왜냐하면·때문·그래서·따라서**, AI API 장애는 **FAILED**, 숫자/인용 대조 실패만 템플릿 대체다.

별도 운영 확인이 남은 구현 기본안: URL 300초(설정 가능), 무료 상세/파일에서 narrative·thinking summary·evening question 제외, PROFILE은 영구 생성 차단/RECORDS는 삭제 후 새 명령 허용. 기본안을 확정 정책으로 보고하지 않는다.

## 다음 진행 순서

1. 로컬 변경 검토 후 이슈별 순서로 push/PR을 준비한다. develop 최신화는 작업 보존·fetch·변경 비교 후 수행하고, 실제 최신 commit에서 재검증한다.
2. #42/#27/AI/core 연결 결과를 받아 production codec과 HTTP 계약을 연결한다. 현재 기본 CLI는 생성 큐를 소비하지 않으므로 이를 통합 완료로 승인하면 안 된다.
3. #55 정책과 추가 DDL을 승인받은 뒤 운영 migration job으로 적용한다. 앱 startup에서 migration하지 않는다.
4. 합성 데이터로 Compose/MinIO 전체 생성→조회→다운로드→삭제를 검증하고, 담당자별 잔여 항목이 닫힌 뒤 #56 에픽 완료 여부를 판단한다.

상세 구현과 재현 기준은 각 이슈 보고서 및 코드 테스트를 따른다. 외부 담당자에게 메시지나 이슈 댓글을 자동 게시하지 않았다.
