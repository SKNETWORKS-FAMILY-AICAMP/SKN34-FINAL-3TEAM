# 이슈 #53 리포트 렌더링·파일 저장

작업 브랜치는 `feature/report-rendering`이다. develop `47e5ffe`와 #50·#52의 검증된 메시지·서술 변경을 병합했다. 프로젝트 설계의 Jinja2·Playwright Chromium과 S3 SDK(boto3)를 사용한다. 운영 의존성은 uv.lock에 고정하며, moto·pypdf는 개발 검증용이다.

## 구현과 저장 규칙

- `rendering/renderer.py`·`templates/weekly.html`: 표시 이름·기간·판·포함 기준·수치/분자/분모/계산식·생각 유형·변화·돌아보기·검증된 인용·서술·저녁 질문을 HTML/PDF/Markdown으로 렌더링한다. 이름과 원문은 escape하며 Chromium의 JavaScript와 외부 네트워크 요청을 차단한다.
- `generation/presentation.py`: 조회와 파일 생성에서 같은 항목 조립 규칙을 사용한다. 검증되지 않은 인용의 원문은 노출하지 않는다.
- `rendering/generator.py`: 계산/서술 다음 단계로 파일을 생성·저장한 뒤 `GenerationResult.files`를 반환한다. 생성·업로드 작업이 취소돼도 진행 중인 blocking 작업이 끝나기 전에 잠금을 반환하지 않는다.
- `clients/storage.py`: S3/MinIO 업로드, 제한 시간 URL, 학생별 정리. 자격증명은 SDK provider chain을 사용하며 소스에 넣지 않는다. 별도 공개 MinIO 주소가 필요하면 `S3_PUBLIC_ENDPOINT_URL`로 서명용 주소를 지정한다.
- 경로는 `reports/{studentId}/{reportId}/r{revision}/{full|free}/{pdf|md|html}`다. 같은 판의 full/free 6개 객체를 만들고, 기존 UK에 맞춰 DB `report_file`에는 full 기준 3개 행을 저장한다. 무료 파생 파일은 같은 경로 규칙으로 조회하며 삭제 시 학생 prefix의 양쪽 파일을 제거한다. 생성 당시 유료였던 리포트도 현재 권한으로 올바른 변형을 다운로드해야 한다.
- AI 서술·생각 유형 summary·저녁 질문을 제외하는 무료 투영을 제공한다. 운영 기본 URL 수명은 300초이며 설정으로 변경한다. 이 값과 세부 무료 정책은 초기 구현 기준으로 기록하며 팀의 운영 확정과 구분한다.
- 업로드 실패 시 부분 객체 정리를 시도하고 리포트를 FAILED로 만든다. 정리 실패는 안정된 report ID로 경고하며, 해당 학생 삭제 시에도 prefix 정리를 수행한다. 중단으로 남은 실패 리포트 prefix의 주기적 운영 점검은 인프라 후속 항목이다.

새 스키마는 추가하지 않는다. 파일 메타데이터는 상태·항목·근거·완료 Outbox와 같은 종료 트랜잭션에 저장한다. DB 저장 전 중단돼도 RUNNING report ID가 있어 prefix를 식별할 수 있다.

## PDF·검증 환경

2026-10-28 병합 후 report 전체 **147개 통과(70.39초)**, Ruff check/format 통과. `sagomungchi/report-service:issue53-20261028` 이미지를 새로 빌드하고 non-root(uid 10001)·read-only root·네트워크 차단·`/tmp` tmpfs 환경에서 고정 합성 데이터의 HTML/PDF/MD를 생성했다. PDF 191,409바이트·2페이지의 논리 텍스트가 검토된 스냅샷과 일치했고 PNG 2페이지에서 한글 깨짐·잘림·중첩이 없음을 확인했다. 운영 이미지에 pytest가 없는 것도 확인했다. 이 실행은 저장 기능의 moto 검사이며, 실제 MinIO+조회 API 결합 검증은 #54가 포함된 후속 누적 브랜치에서 수행한다.

Dockerfile은 production 의존성만 설치하고 Chromium·Noto CJK 폰트를 준비한다. non-root 사용자로 실제 Linux PDF를 생성했다. 한글 텍스트 추출과 A4 2개 페이지의 PNG 시각 검토에서 글자 깨짐·잘림·중첩을 확인하지 않았다. Windows 출력도 같은 방식으로 확인했다.

HTML·Markdown 스냅샷은 전문을 비교한다. PDF는 OS별 한글 폰트의 줄바꿈 차이를 고려해 공백을 제외한 논리 텍스트를 비교하며 시각 검토를 별도로 수행한다. Windows/Linux PDF의 논리 텍스트가 같음을 확인했다. CI의 report-service에만 Chromium·한글 폰트 준비 단계를 추가했다.

최초 집중 검증은 `test_rendering.py` 6개 통과: 3종 스냅샷, escape, 무료 투영, moto 업로드·서명·다른 학생 파일 보존, 실제 DB의 업로드 성공/실패와 파일 메타데이터 저장. 최종 회귀 결과는 통합 보고서에 기록한다.

## 실제 MinIO 추가 검증 — 2026-10-27

`tests/test_minio_storage.py`의 통합 테스트 3개를 추가했고 **3 passed (26.62초)**를 확인했다. 팀 `compose.minio.yaml`에 고정된 Chainguard MinIO 이미지와 실제 PostgreSQL을 일회용 컨테이너로 실행한다. 저장 데이터는 합성 값이며, 버킷은 `sagomungchi-local-reports`, 포트는 loopback의 임의 포트, 계정은 실행마다 만든 테스트 값이다. `/data`는 tmpfs이고 테스트 종료 시 해당 컨테이너만 제거한다. 기존 MinIO·DB·볼륨·개인 `.env`는 사용하지 않는다.

| 검증 | 확인한 결과 |
|---|---|
| 생성·메타데이터 | 실제 Chromium으로 full/free × HTML/MD/PDF 6개 생성·업로드, COMPLETED와 `report_file` 3개 행 저장 |
| 재생성 | 같은 학생·기간의 2판 생성 시 총 12개 객체, 이전 판 파일 유지 |
| 다운로드 | report 내부 조회 API에서 발급한 URL로 실제 HTTP 다운로드, 6개 파일 모두 200·형식·첨부 파일명·Cache-Control 확인, full 파일 크기와 DB 값 일치 |
| 현재 권한 | 동일 리포트에 무료/유료 요청을 보내 올바른 파일 선택, 무료 파일에 AI 서술·저녁 질문 없음, 다른 학생 범위는 403 |
| 서명 | 공개 endpoint 사용, 300초 TTL 설정, 서명 없는 요청·다른 파일로 변조한 URL은 403, 별도 5초 URL 만료 후 403 |
| 정리 | 특정 판 삭제 시 다른 판 유지, 학생 prefix 삭제 시 다른 학생 파일 유지, 삭제한 파일의 기존 URL은 404, 재발급 요청은 503 |
| 실제 업로드 실패 | 2개 객체 업로드 후 잘못된 테스트 계정으로 MinIO 403 유발 → FAILED, 파일 DB 행 없음, 부분 객체 제거, 다른 리포트 파일 유지 |

재현 명령은 `backend/report-service`에서 실행한다. Docker가 실행 중이어야 하며, 이미지 다운로드 실패나 Docker 미실행을 skip으로 감추지 않는다. 새 테스트는 일반 `uv run pytest`에도 포함된다.

```powershell
uv sync --frozen
uv run playwright install chromium
uv run pytest tests/test_rendering.py tests/test_minio_storage.py -q
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```

Linux/CI에서는 기존 workflow처럼 Chromium 시스템 의존성과 Noto CJK 폰트도 준비한다. 별도의 production 이미지 검사에서는 `sagomungchi/report-service:issue55-local`을 UID 10001·읽기 전용 root·writable `/tmp`로 실행했다. Docker 네트워크의 `http://minio:9000`으로 업로드하고 `http://localhost:<임의 포트>`로 서명한 6개 파일을 호스트에서 다운로드했다. 학생 prefix 삭제 후 기존 URL 6개 모두 404를 확인했다. 다운로드한 한글 A4 PDF 2페이지를 PNG로 변환해 글자 깨짐·잘림·중첩이 없음을 확인했다.

이번 보강은 테스트와 검증 문서이며 제품 코드·스키마·API 계약 변경은 없다. 실제 MinIO 저장소 연결은 완료했지만 입력 학습 기록·AI 응답·메시지 codec은 여전히 합성 대역이다. core 공개 프록시/브라우저를 포함한 전체 서비스 연동이나 #45 삭제 완료 보고까지 검증한 것으로 해석하지 않는다.

## #27 협의 전 표시 계약 정리 (2026-10-28)

난이도는 learning 입력·report 저장에서 `EASY`·`NORMAL`·`HARD` 코드를 유지하고, 공통 출력 조립 함수 `generation/presentation.py`에서 `쉬웠어요`·`보통`·`어려웠어요`로 변환한다. API 3.4와 파일 출력이 같은 매핑을 쓰도록 렌더러도 이 상수를 재사용한다. 무료/유료 출력에 동일하게 적용하며 저장한 payload나 AI 요청용 계산 결과는 바꾸지 않는다. 미작성의 null은 유지한다. #27 evidence 응답·실제 연동은 아직 확인 대기다.

사전 정리 검증: learning 입력·수치 계산·evidence 기존 검사·세 난이도 표시·실제 PDF/HTML/MD 스냅샷 **64개 통과(4.86초)**. 합성 응답으로 검증했으며 실제 #27 서비스 호출은 아니다. 기존 파일 스냅샷은 수정하지 않았다.

## 완성을 위한 외부 연결

- core 담당자: 신뢰할 수 있는 표시 이름의 허용된 조회 경로가 필요하다. #42의 확정 `report.generate.v1`에는 닉네임이 없으므로 메시지에 임의로 추가하지 않는다. 내부 모델의 display_name은 조회 결과를 전달할 자리다.
- 인프라 담당: 운영 버킷·IAM/IRSA, S3 endpoint, 공개 다운로드 주소 및 비밀 값 주입. readOnlyRootFilesystem에서는 Chromium이 쓸 `/tmp` writable volume이 필요하다. 실제 AWS 배포 검증은 하지 않았다.
- #50/#42 공통 v1 codec은 연결했다. #27 학습 기록·#64 서술 API와 표시 이름 조회 연결 후 계산→서술→렌더링→완료 이벤트의 전체 서비스 연동 검증이 필요하다. 이 브랜치의 독립 worker 기본 생성기는 아직 `GENERATOR_NOT_CONFIGURED` 실패로 명시한다. 단계별 생성기는 테스트에서 조립해 검증하며 가짜 파일로 운영 완료를 만들지 않는다.

참고: [Playwright Docker 지침](https://playwright.dev/python/docs/docker), [boto3 S3 API](https://docs.aws.amazon.com/boto3/latest/reference/services/s3.html).

## 최신 develop 통합·재검증 (2026-10-28)

`feature/report-rendering`의 `733f8ead`에 로컬 develop `b644b56f`를 통합했다. 이 기준에는 #52 PR #109, 대시보드 PR #111, CI 개선 PR #115가 포함된다. 별도 `local/issue53-integration` 브랜치에서 작업했으며 GitHub push·PR 변경은 하지 않았다.

충돌 3개를 해결했다. `narrative_generator.py`는 develop의 #52 원문 보존/삭제 처리 기준을 유지했다. 파일 출력에서는 `presentation.assemble`의 verified 검사로 미검증 인용을 가린다. `report-narrative.md`는 develop의 최신 검증·계약 기록을 보존하고, `docs/README.md`에는 최신 목록과 #53 링크를 함께 유지했다. learning 수신 모델의 studentId·학생 작성 내용 집계·nullable followup도 develop과 동일하게 유지했다.

nullable followup이 HTML/PDF/Markdown에 `None`으로 표시되는 결함을 수정했다. 질문이 없으면 빈 문자열로 표시하고 최초/최종 답변은 유지한다. 세 출력 형식을 확인하는 회귀 테스트를 추가했다.

| 이번 검사 | 결과 |
|---|---|
| Python 3.12 Docker, uv sync --frozen | 성공 |
| Ruff check / format | 통과, 66개 파일 포맷 일치 |
| report 전체 pytest | **184 passed, 46.57초**, 실패·건너뜀 없음 |
| 공통 계약·스키마 unittest | **58개 통과**, `python -O -m unittest discover -s scripts/tests -q` |
| 운영 Dockerfile 빌드 | `local/issue53-report:20261028` 성공 |
| 운영 이미지 실행 조건 | uid 10001, read-only root, network none, /tmp tmpfs, pytest 미포함 확인 |
| 고정 데이터 출력 | 일반 PDF 191,409바이트·2쪽, nullable PDF 190,311바이트·2쪽. HTML·Markdown도 생성 |
| PDF 검증 | 한글 텍스트 및 None 미출력 확인. 총 4쪽 PNG에서 한글 깨짐·잘림·겹침 없음 |

전체 pytest에는 실제 PostgreSQL·RabbitMQ, moto S3 업로드·서명, 업로드 실패의 FAILED 저장, report_file 저장 검사가 포함된다. 기존 Starlette/httpx 폐기 예정 경고 1개는 테스트 실패가 아니다. Docker 호스트는 host.docker.internal로 연결했다. 최초 검증 이미지 빌드는 운영 dockerignore의 tests 제외 때문에 실패했으며, 저장소 밖 검증용 Dockerfile의 별도 ignore 설정으로 해결했다. 호스트 Python의 공통 검사는 PyYAML 누락으로 실패했고, 잠긴 Docker 환경에서 위 58개를 재실행했다. 실패한 실행은 통과 수치에 포함하지 않는다.

### 이슈 요구사항 대조

| 요구사항 | 확인 근거 |
|---|---|
| 닉네임·기간·포함 기준·수치 근거·생각 유형·전후 변화·돌아보기·인용·저녁 질문 | HTML/Markdown 조립과 고정 데이터 스냅샷 |
| PDF·Markdown 변환 | 실제 Chromium PDF와 Markdown 생성·스냅샷 통과 |
| S3 업로드·presigned URL | ObjectStorage 및 moto 테스트 통과 |
| report_file 저장·실패 시 FAILED | PostgreSQL 성공/실패 회귀 테스트, 기존 유일성 제약 사용 |
| 3종 렌더링 스냅샷 | 전체 pytest에 포함하여 통과 |
| MinIO 또는 moto | moto로 충족 |
| Docker 한글 PDF | 운영 이미지 생성·텍스트·PNG 시각 검증으로 충족 |
| Ruff·pytest | 통합한 코드에서 통과 |

#53 모듈 범위의 구현·검증 조건을 확인했다. 실제 생성기 bootstrap 연결, 신뢰 가능한 닉네임 공급, #64 실제 AI API와 전체 서비스 E2E는 별도 후속 사항이다. 이번 실행은 실제 AWS/MinIO 접속 검증이 아니다. 앞선 절의 #27 확인 대기 기록은 당시 상태이며 이번 통합에서는 develop에 병합된 #27/#51 계약을 유지했다. 이후 원격 develop 변경은 새 기준으로 충돌·검증을 다시 확인해야 한다.
