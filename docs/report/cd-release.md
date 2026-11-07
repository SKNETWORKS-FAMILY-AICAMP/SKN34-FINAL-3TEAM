# CD 배포 승인·이력과 이전 버전 복구 (#186)

`cd-release.yml`(main 수동 실행 → GitHub Environment `prod` 승인 → 작업자 PC runner에서 Helm 적용 → 경로 확인 → 이력)의 결정과 실행 기록. 설정·명령은 [운영 배포 문서](../../infrastructure/cd/README.md), AWS 구성은 [aws-deploy](aws-deploy.md).

## 확정 정책

사용자가 전달한 담당자 답변을 기준으로 한다.

- 이전 승인 앱이 현재 DB 스키마·데이터와 호환될 때만 새 승인을 받아 이미지 버전을 복귀한다.
- 비호환 및 미확인은 모두 복귀 차단이다. DB 버전 번호만으로 호환성을 판정하지 않는다.
- API·이벤트 계약, 진행 중 학습·결제 작업 영향과 검증 근거를 함께 기록한다.
- DB 자동 downgrade 및 백업 자동 복원은 구현하지 않는다.
- 비호환은 수정 버전 배포 또는 데이터 복구 등 별도 계획을 작성하고 승인받는다.
- 운영 승인자는 김동섭(`20220348-kim`)과 김태윤(`kty2001`) 2명이다(2026-11-03 담당자 결정). 둘 중 한 명의 GitHub Environment 승인 없이는 실행하지 않는다. 승인자 확정은 실행 허용이 아니며 실행 스위치·환경 보호·인프라 준비는 별도로 확인한다.

## 구성

- `scripts/cd_release.py`: 변경 서비스의 불변 이미지 digest·전체 Git SHA·대상 버전·사유·여섯 호환성 검토 항목·이전 승인 기록을 검증하고, 오류·차단 사유가 없을 때만 `executable=true`. 계획 입력의 `compatible`·승인 표시는 사람의 선언이며 실제 승인은 GitHub 승인 기록 API로 읽는다
- `infrastructure/cd/policy.json`: 승인자 2명, `releaseBranch: main`, 실행 스위치(`executionEnabled`·`environmentProtectionVerified`·`infrastructureReady`)는 설정 A~C 확인 후 true(2026-11-04)
- `.github/workflows/cd-candidate.yml`: CD 도구 변경 PR·수동 실행의 `policy` 검사만(서비스 코드는 서비스별 CI)
- `infrastructure/cd/plan.example.json`은 합성 입력이라 항상 차단됨
- prod는 Argo CD 없이 수동 Helm(`redeploy-app.ps1`), 배포 소스는 develop → main 릴리스 SHA(#185 결정), 이미지는 ECR `main-<12자리>` 태그·values digest 고정

## 경과

- 10-30~11-03: 계획 검증 도구·정책·후보 CI 준비(실행 비활성), 승인자 확정(11-03)
- 11-04: #185 결정 반영(main 기준·수동 Helm·Pod Identity·노드그룹 2개), 배포 실행기 구현, 운영 설정 A~C 적용 후 실행 스위치 켬, 첫 운영 배포·롤백 리허설
- 11-05: 두 번째 운영 배포(경로 확인 수정 #376·#377)

## DB 호환성 검토 시 반드시 포함할 기존 제약

- #131 `20261030_04`: 기존 report-worker 중지 → migration → 새 worker 순서. 이전 worker와 새 NOT NULL 카운터 스키마의 혼합 실행 미지원. downgrade 시 실패·격리·수동 재처리 메타데이터가 사라진다.
- report 삭제 guard 제거는 삭제된 학생의 재생성 차단을 잃을 수 있어 무조건 롤백 금지.
- core·learning 앱 자동 migration은 꺼져 있다. 운영 DB 초기화·Flyway 이력 수정으로 버전을 맞추지 않는다.
- 기존 모델 버전 rollback 검증은 앱 배포 rollback 검증을 대신하지 않는다.

## 배포 실행기 구현 (2026-11-04)

실행 단계(승인 → 적용 → 경로 확인 → 이력)의 구현 결정. 설정·명령은 [운영 배포 문서](../../infrastructure/cd/README.md)를 따른다.

| 결정 | 내용 | 근거 |
|---|---|---|
| 적용 위치 | 작업자 PC의 전용 self-hosted runner(`cd-prod`) | EKS API 공개 접근이 작업자 공인 IP로 제한돼 GitHub 호스팅 runner에서 접근 불가. 기존 작업자 AWS 프로필·kubeconfig를 써서 EKS 권한을 새로 만들지 않는다 |
| 승인 | GitHub Environment `prod` 필수 승인자 2명, main만 허용 | 승인 전에는 적용 job이 시작되지 않는다. 승인자는 GitHub 승인 기록 API로 읽어 이력에 남기며 계획 파일의 승인 표시는 읽지 않는다 |
| 이미지 | publish job이 main SHA를 `main-<12자리>`로 ECR 게시, 이미 있으면 재사용 | ECR 태그 IMMUTABLE. GitHub OIDC 역할은 ECR 쓰기만, trust는 main의 `cd-release.yml`만 |
| 계획 입력 | 실행 입력 JSON(커밋하지 않음) | 계획의 SHA가 그 계획을 담은 커밋 자신을 가리키는 순환을 피한다. 계획 원문은 artifact로 보관 |
| 실행 게이트 | `cd_release.py`가 오류·차단 사유가 없을 때만 `executable=true`. validate에서 이미지 빌드 전 다른 차단이 있으면 게시 전에 중단, deploy에서 `--require-executable`로 재확인 | 실행 스위치·근거·승인자 미비 상태에서 ECR 게시나 적용을 하지 않는다 |
| 적용 | release별 server dry-run 전체 → 순서대로 `redeploy-app.ps1 -ImageDigest -Apply` | 저장소 values를 바꾸지 않고 digest만 교체. 실패하면 다음 release는 적용하지 않고 자동 롤백도 하지 않는다 |
| 경로 확인 | 학생 PIN 로그인 → 시도 시작 → 답변 제출 → 부모 refresh → 리포트 목록 | 판정(LLM)·결제는 호출하지 않는다. 부모 refresh 쿠키는 회전하므로 새 값을 fixture 파일에 즉시 저장한다 |
| 이력 | 수행자·승인자·run URL·SHA·이미지·release 전후 revision·경로 확인 결과를 `history.json` artifact(90일)와 실행 요약에 기록 | workflow에 저장소 쓰기 권한(`contents: write`)을 주지 않으려고 Git에 직접 push하지 않는다. develop·main에는 현재 브랜치 보호 규칙이 없다(2026-11-04 확인) |
| 롤백 | 이전 승인 digest를 같은 workflow·승인으로 적용. 계획의 SHA는 이전 릴리스(현재 SHA 일치 검사는 배포에만) | DB downgrade·백업 복원은 하지 않는다 |

- 11/01 브랜치 `feature/cd-release-186`의 workflow는 Argo CD·develop push 전제라 가져오지 않았고, 배포 후 확인 단계 구성만 참고했다.
- migration과 웹(S3/CloudFront) 배포는 범위 밖이다. migration은 배포 전 prod README 절차로 적용하고 schema 근거에 적는다.
- 검증: `python -O -m unittest discover -s scripts/tests` **149개 통과**(CD 37개: 실행 게이트·main 이력 확인·롤백 커밋 처리, 경로 확인 단계·쿠키 회전 저장·자격 증명 비노출·실패 중단, 이력 판정·승인 API, workflow 구조), 변경 Python ruff 통과, workflow YAML 파싱과 PowerShell 단계·`redeploy-app.ps1` 문법 검사 통과. actionlint와 실제 Actions 실행·AWS 적용은 하지 않았다.

## 운영 설정 적용과 후보 CI 정리 (2026-11-04)

- 설정 A(AWS): GitHub OIDC 제공자와 ECR 쓰기 전용 역할 `sagomungchi-demo-github-cd-publish`(인라인 `ecr-push`)를 만들었다. 역할은 `demo-stack.json`에 넣어 `demo_stack.py plan` OK=58로 대조한다. OIDC 제공자는 `demo_stack.py` 관리 대상이 아니다.
- 설정 B(GitHub): Environment `prod`(필수 승인자 `20220348-kim`·`kty2001`, 배포 브랜치 `main`만, 관리자 우회 끔), 변수 `CD_BASE_URL`(prod)·`CD_AWS_ROLE_ARN`·`CD_AWS_REGION`·`CD_ECR_REGISTRY`, 외부 기여자 PR workflow 전원 승인(`all_external_contributors`)을 적용했다.
- 설정 C(runner)·D(fixture)·E(실행 스위치)는 남아 있다.
- `cd-candidate.yml` 정리: 처음 구성(`98b3f98`)은 이 브랜치 push와 PR에서 모두 실행되고 서비스 CI(`_spring.yml`·`_python.yml`·`_web.yml`, 6개 대상)를 다시 호출해, CD 도구만 바꾼 PR에도 같은 서비스 검사가 두 번씩 돌았다. 서비스 코드는 서비스별 CI가, 배포 이미지는 `cd-release` publish가 main SHA로 빌드하므로 PR·수동 실행의 CD 도구 검사(`policy` job)만 남겼다. `executionEnabled=false` 고정 검사는 E단계 PR을 막으므로 릴리스 브랜치·승인자 기준 확인으로 바꿨다.

- 검증: `python -O -m unittest discover -s scripts/tests` **150개 통과**(후보 workflow 구조 테스트 1개 추가), ruff 통과, workflow YAML 파싱 통과.
- 브랜치 보호: develop·main 모두 보호 규칙·Ruleset이 없다(2026-11-04 API 확인). 배포 적용은 `prod` 승인으로 막히지만, main 직접 push로 workflow를 바꾸면 승인 전 publish job이 ECR 게시 역할을 쓸 수 있다. main 보호(PR 필수, force push·삭제 금지)는 팀 결정으로 남긴다.
- 설정 C(runner): 작업자 PC runner `DESKTOP-AUHJ0U2`(라벨 `cd-prod`, 서비스 미설치)를 등록했다. 데모 EKS 전용 kubeconfig와 runner `.env`(경로만)를 두었다.
- 실행 스위치: A~C 적용을 확인하고 `policy.json`의 `environmentProtectionVerified`·`infrastructureReady`·`executionEnabled`를 true로 바꿨다. `cd-release`는 main에서만 수동 실행되고 적용은 `prod` 승인 후라 develop 병합만으로는 실행되지 않는다. 근거 없는 계획(합성 예시 포함)은 계속 차단된다. D(fixture)는 배포 직전에 채운다.
- 수정(2026-11-04, main `a47631a` 반영 후 발견): deploy job `env`에서 `${{ runner.temp }}`를 써서 GitHub가 `cd-release.yml`을 파일 오류로 처리했고, 모든 브랜치 push마다 실패 run이 생겼다(배포는 실행되지 않음). 작업 폴더를 첫 step에서 `GITHUB_ENV`로 정하도록 고치고, actionlint 1.7.12(`cd-prod` 라벨 설정)로 전체 workflow를 검사해 오류 0건을 확인했다. job env 컨텍스트 회귀 테스트를 추가해 151개 통과.
- 첫 실행(run 41796499774) publish 실패와 수정: `sts:AssumeRoleWithWebIdentity` 거부. 원인 두 가지로, AWS IAM은 GitHub 토큰의 `job_workflow_ref`를 조건 키로 비교하지 못하고, 이 저장소는 변경 불가 subject라 `sub`가 조직·저장소 ID를 포함한다(`…@169222902/…@1415225916`). 저장소 OIDC subject에 `job_workflow_ref`를 포함하도록 바꾸고 trust를 `sub` 하나(`StringLike`)로 main의 `cd-release.yml`만 허용하게 고쳤다. 제한 범위는 처음 설계와 같다.

## 운영 실행 기록 (2026-11-04)

기준 main `a47a596`(PR #343). 승인자 `20220348-kim`, 작업자 PC runner `DESKTOP-AUHJ0U2`. 이력은 각 run의 artifact `cd-history-<run id>`(90일)에 있다.

| 순서 | run | 작업 | 결과 | 내용 |
|---|---|---|---|---|
| 1 | [41796499774](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/actions/runs/41796499774) | deploy 5개 서비스 | 1차 실패 → 재실행 성공 | publish의 OIDC 역할 거부(trust 수정 후 재실행). 1차 deploy는 6개 release 적용 성공, 경로 확인 답변 제출 400(fixture 미션이 `CHOICE`). fixture를 `NARRATIVE` 미션으로 바꿔 deploy 재실행: learning r2→r3, ai r2→r3, scoring r3→r4, report-api·worker r2→r3, core r6→r7, 경로 확인 5단계 ok |
| 2 | [41800966528](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/actions/runs/41800966528) | rollback scoring → `sha-f6250bd` | 성공 | scoring r4→r5, digest `6fc49256…`, 경로 확인 5단계 ok |
| 3 | [41802823411](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/actions/runs/41802823411) | deploy scoring → `main-a47a596247ad` | 성공 | scoring r5→r6, digest `b2c36e72…`, 경로 확인 5단계 ok |

- 선행: learning V9 migration Job `learning-service-migrate-main-a47a596247ad`(V8→V9).
- 경로 확인 5단계: 학생 PIN 로그인 → 시도 시작 → 답변 제출 → 부모 refresh → 리포트 목록. 판정·결제 미호출.
- 배포 후 prod values의 앱 digest 6개를 실제 배포값으로 맞췄다(렌더링 결과와 Deployment 이미지 일치 확인).
- 완료 조건: 승인 → 배포 → 경로 확인 1회(1), 롤백 리허설과 복귀(2·3) 기록.
- 별도 발견: learning·core의 OTLP trace export가 `otel-collector:4318`에서 404(경고 로그만, 서비스 영향 없음). 해소 여부는 [ops-observability](ops-observability.md) 완료 조건 상태에서 확인 필요
- fixture 점검 보완: 경로 확인 전 미션의 `inputType`이 답변 형식과 같은지 확인한다(README D).

## 운영 실행 기록 (2026-11-05)

승인자 `20220348-kim`, 작업자 PC runner `DESKTOP-AUHJ0U2`. 선행으로 core V26→V28·learning V9→V10 migration Job과 성취기준 시드 765행 Job을 적용했다(Job 이름은 [prod README](../../infrastructure/gitops/environments/prod/README.md)).

| 순서 | run | 기준 | 결과 | 내용 |
|---|---|---|---|---|
| 1 | [42011445646](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/actions/runs/42011445646) | main `c6809dd`(PR #375) | failure | 6개 release 적용 성공(core r9, learning r5, ai r5, scoring r7, report-api·worker r4), 앱 6개 1/1. 경로 확인 `submit-answer` 422: 이전 확인이 남긴 진행 중 시도를 돌려받아 첫 답변을 다시 냄(#376) |
| 2 | [42055199615](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/actions/runs/42055199615) | main `322e797`(PR #378, 경로 확인 수정 #377) | 1차 실패 → 재실행 success | 1차 deploy는 server dry-run에서 작업자 PC AWS 프로필 세션 만료로 중단(적용 없음). `aws login --profile sagomungchi-provided` 후 deploy 재실행: core r10, learning r6, ai r6, scoring r8, report-api·worker r5. 경로 확인 6단계 ok(`read-answer` 경로) |

- 서비스 코드는 1·2가 같다. 2는 경로 확인 스크립트만 바뀐 main으로 다시 롤아웃해 성공 기록을 남겼다.
- 배포 후 prod values의 앱 digest 6개와 migration 값(core·learning)을 실제 적용값으로 맞췄다. 클러스터 Deployment 이미지와 일치 확인.
- 경로 확인은 시연 학생에게 시작 전 미션이 없어 진행 중 시도의 저장된 답변을 조회했다. 답변 쓰기는 이번에 새로 확인하지 않았다(#376 한계).
- 운영 주의: runner가 쓰는 프로필은 `sagomungchi-provided`다. 기본 프로필로 `aws login`하면 배포 dry-run이 계속 실패한다.
