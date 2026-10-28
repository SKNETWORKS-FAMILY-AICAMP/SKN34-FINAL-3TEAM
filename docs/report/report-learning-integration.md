# report와 #27 학습 기록 API 연동 검증

2026-10-28. develop `b344797`(#27 PR #105)을 병합한 `ac7a601` 이후, 누적 `feature/report-deletion`에서 수행했다. 다른 report 브랜치로 전파하거나 원격 push·PR 등록을 하지 않았다.

## 목적과 완료한 수정

실제 learning 응답을 report가 거부하거나 학생이 쓰지 않은 글자를 집계하는 문제를 해결했다.

| 대상 | 수정 전 | 수정 후 |
|---|---|---|
| `ScopeInput`·학생 범위 검사 | 내부 응답에 `childId` 요구 | #27의 `studentId`를 검사. 공개 report 응답은 기존 `childId` 유지 |
| `AnswerInput`·`AnswerRecord`·`MetricsCalculator` | 표시용 평문의 칸 이름·선택지 이름까지 집계 | inputType별 content의 학생 작성 칸만 읽어 별도 written_text로 정규화. 표시용 text와 근거는 보존 |
| `ChangeInput`·DB·조회·파일 | `followup:null` 거부 또는 파일에 None 표시 가능 | null을 그대로 저장·조회하며 PDF·HTML·MD에서는 질문 문구 생략. OpenAPI와 프론트의 해당 타입·조건부 표시도 정렬 |

서술은 text, 풀이는 steps 후 finalAnswer, 논술은 claim·reasons·rebuttal 순서다. 비어 있지 않은 칸을 줄바꿈으로 연결하며 공백을 임의로 잘라내지 않는다. 고르기·순서·분류는 작성 글이 없으므로 0으로 계산한다. 메모·초안·관련 없는 필드는 집계에 넣지 않는다. 필수 입력 누락·잘못된 형식은 오류이며 표시용 평문으로 대신 계산하지 않는다. 문장 구분자는 learning과 같은 `.?!`·LF다. 연결어는 기존 네 개를 유지한다.

DB 스키마·마이그레이션·공유 이벤트는 변경하지 않았다. 검증용 빈 DB에 기존 Flyway V1~V5와 Alembic head를 적용했다.

## 검증 결과

| 검사 | 결과 |
|---|---|
| report 전체 테스트 | **220개 통과, 실패·생략 0**, 182.59초. 기존 TestClient deprecation warning 1개 |
| 수신·집계 집중 검사 | **70개 통과**. 위 전체 검사에 포함되므로 합산하지 않음 |
| 저장소 계약 검사 | **54개 통과** |
| 프론트 nullable 계약 | build·lint 통과, 학부모 관련 **8개 테스트 통과**. 기존 번들 크기 경고는 빌드 실패가 아님 |
| 실제 learning 빌드 | JDK 21 컨테이너에서 bootJar 성공. production 소스 변경 없음 |
| 실제 learning → report | 아래 **8개 항목 통과**, 임시 컨테이너·네트워크 정리 확인 |

실제 연동은 [재현 스크립트](../../scripts/verify_report_learning.py)로 실행했다. HTTP 응답 대역을 쓰지 않고 최신 learning JAR·PostgreSQL·RabbitMQ와 수정한 report 서버를 실행했다. 학생·미션은 합성 데이터다. 여섯 입력 방식의 시도 시작과 답변 제출은 실제 learning API를 사용했다. 미션/기준표와 판정·되묻기, 과거 제출 시각은 격리 DB에 설정했다. nullable followup은 DB가 허용하는 이전 기록의 경계 사례로 마지막 답변의 연결을 null로 설정했다. 실제 AI 판정이 실행됐다는 뜻은 아니다.

1. 빈 기록의 `NO_RECORD`를 실제 learning HTTP와 report 집계로 확인.
2. 여섯 입력 방식의 답변 제출과 1·4·5건 표본 상태 확인.
3. 각 입력 방식의 글자·문장·연결어 수가 learning의 실제 counts와 일치. 표시용 원문 보존 및 null 되묻기 수신 확인.
4. 실제 attempts·thinking-types·changes 응답이 저장소 OpenAPI에 부합하는지 검증.
5. evidence 전체 원문·버전, 정상/없는 ID 혼합 응답, 범위 밖 학생 403 확인.
6. 계산 결과를 report DB에 저장하고 실제 report HTTP로 무료/유료 상세 조회. 공개 childId·null 되묻기 보존과 HTML·MD·PDF 출력 확인.
7. **시도 101건·변화 101건**에서 각각 0·1페이지를 읽어 누락 없이 집계.
8. 삭제 표식이 생기면 `NO_RECORD`·빈 목록·근거 available:false 확인. 삭제 이벤트 소비자 검증은 아님.

실제 네 API 응답 JSON, report 상세 JSON, PDF·HTML·MD, 결과 요약과 서버 로그는 로컬 `output/report27-live-20261028-final/`에 보관했다. `output/`은 이번 커밋 대상에서 제외한다. 사용한 learning JAR SHA-256은 `9406fc1d6c2326ff714664de1e007b4e4d0917ec7ed82e352561f366ee83dc96`이다.

## 재현

JDK 21로 learning의 현재 소스를 `bootJar --no-daemon --max-workers=2 -Pkotlin.compiler.execution.strategy=in-process`로 먼저 빌드한다. 검증 스크립트는 소스보다 오래된 JAR을 거부한다. Docker 실행 후 저장소 루트에서:

```powershell
& .\backend\report-service\.venv\Scripts\python.exe -X utf8 -u scripts/verify_report_learning.py --output output/report27-live-rerun
```

report 개발 의존성, PyYAML, Playwright Chromium이 있는 기존 .venv를 사용한다. PostgreSQL·RabbitMQ·Flyway·JDK 이미지는 스크립트에 고정되어 있다. 일회용 DB와 loopback 임시 포트를 만들며 종료 시 자원과 DB를 제거한다. 공유 DB·운영 AWS·AI Hub·실제 학생 자료를 사용하지 않는다.

처음 검증 준비에서 PowerShell의 Gradle 옵션 분리와 합성 학생의 논술 학년 조건(3학년)을 수정했다. 옵션을 인용하고 5학년으로 실행해 최종 검증을 통과했다. 스키마 생성용 임시 토큰이 남아 실패한 집중 검사는 기존 테스트 토큰으로 다시 실행해 통과했다. 이는 제품의 정책을 완화한 수정이 아니다.

## 남은 범위

#27 자료 대기와 위 세 가지 report 계약 차이는 해소했다. core 스케줄러·상품 권한·닉네임 공급, 실제 #64 AI 서술, 운영 저장소, learning 삭제 이벤트 소비자를 묶은 전체 서비스 검증은 이번 범위에 포함하지 않았다. 따라서 #50~#55 전체나 에픽 완료를 선언하지 않는다. [남은 입력](report-required-inputs.md)을 따른다.
