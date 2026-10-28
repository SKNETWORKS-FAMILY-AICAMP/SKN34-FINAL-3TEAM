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

## 완성을 위한 외부 연결

- core 담당자: 신뢰할 수 있는 표시 이름의 허용된 조회 경로가 필요하다. #42의 확정 `report.generate.v1`에는 닉네임이 없으므로 메시지에 임의로 추가하지 않는다. 내부 모델의 display_name은 조회 결과를 전달할 자리다.
- 인프라 담당: 운영 버킷·IAM/IRSA, S3 endpoint, 공개 다운로드 주소 및 비밀 값 주입. readOnlyRootFilesystem에서는 Chromium이 쓸 `/tmp` writable volume이 필요하다. 실제 AWS 배포 검증은 하지 않았다.
- #50/#42 공통 v1 codec은 연결했다. #27 학습 기록·#64 서술 API와 표시 이름 조회 연결 후 계산→서술→렌더링→완료 이벤트의 전체 서비스 연동 검증이 필요하다. 이 브랜치의 독립 worker 기본 생성기는 아직 `GENERATOR_NOT_CONFIGURED` 실패로 명시한다. 단계별 생성기는 테스트에서 조립해 검증하며 가짜 파일로 운영 완료를 만들지 않는다.

참고: [Playwright Docker 지침](https://playwright.dev/python/docs/docker), [boto3 S3 API](https://docs.aws.amazon.com/boto3/latest/reference/services/s3.html).
