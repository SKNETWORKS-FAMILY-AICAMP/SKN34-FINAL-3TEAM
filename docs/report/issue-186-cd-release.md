# #186 CD 배포 승인·이력·이전 앱 버전 복구

## 결정과 구현 기준

2026-11-01 사용자가 운영 배포 승인자를 **김동섭**으로 확정했다. GitHub 계정은 `20220348-kim`(ID `201464527`)이다. Slack의 김동섭 작성 PR #203 안내와 해당 PR 작성자를 대조했다.

롤백은 이전 승인 앱과 **현재 DB 스키마·데이터가 호환된다고 검증한 경우**에 승인 후 앱 이미지를 복귀한다. DB 자동 다운그레이드·백업 복원은 수행하지 않는다. 호환되지 않거나 확인하지 못한 경우 배포를 차단하고 별도 복구안을 승인받는다. DB 버전 번호 일치만으로 호환성을 추정하지 않으며 API·이벤트·현재 설정·진행 중 학습·결제 영향의 근거를 함께 기록한다.

작업 브랜치 `feature/cd-release-186`은 develop `2db122c`에 #171의 원격 `feature/infra-app-deployment` 커밋 `86f627e`를 포함한 상태에서 시작했다. #171 구현은 이 작업의 신규 구현으로 계산하지 않는다. #171이 develop에 병합된 뒤 #186을 병합하는 순서다. 운영 values·EKS·레지스트리·Secret·네트워크는 #185의 책임이며 가상의 운영 설정을 추가하지 않았다. 제품 API·DB 스키마 변경은 없다.

## 실행 흐름

`cd-release.yml`은 **develop에서 수동 실행할 때만** 작동한다. 입력은 환경(local/prod), deploy/rollback, 배포할 소스의 전체 SHA, rollback 대상 배포 ID, 검토 JSON 경로다. workflow rerun은 차단하며 새 실행으로 다시 승인받는다. 환경별 concurrency는 진행 중 배포를 취소하지 않는다. GitHub 기본 concurrency의 대기 실행 교체 동작은 적용되므로 대기 건이 취소되면 새로 요청한다.

1. plan: 현재 배포 ID·values/chart 해시·소스 SHA·24시간 이내 검토 근거를 검증한다. rollback은 같은 환경의 이전 성공 이력에서만 선택한다. source는 develop 이력에 있어야 하고 일반 deploy로 과거 소스로 되돌릴 수 없다.
2. CI: 변경 서비스 경로에 따라 기존 `_spring.yml`·`_python.yml`을 재사용한다. 서비스 간 계약·배포 구성 변경은 전체 서비스 검사 대상으로 삼는다. `_web.yml`로 해당 소스의 웹 lint·test·build도 검사한다. 기존 PR CI 경로 필터와 기본 동작은 유지한다.
3. 승인: `prod` GitHub Environment에서 김동섭의 승인을 받는다. 작업 시작 후 Actions review-history API에서도 승인자 ID·계정·환경·승인 상태를 확인한다. Environment 보호 설정이 빠지거나 우회됐어도 확인되지 않은 운영 승인은 실패한다. local은 수동 실행자를 기록한다.
4. 게시: 변경 서비스 5종(core·learning·ai·scoring·report)과 해당 core/learning migration 이미지를 linux/amd64로 게시한다. local은 GHCR, prod는 AWS OIDC로 ECR에 인증한다. report-api와 report-worker는 같은 report 이미지를 사용한다. 빌드 결과 digest를 읽어 고정하며 변경 없는 이미지는 이전 이력의 digest를 재사용한다. migration Job revision에는 migration 파일과 이미지 digest를 함께 반영해 이전 Job의 불변 pod template과 충돌하지 않게 한다. 웹의 S3/CloudFront 배포는 #185 범위이고 이 워크플로는 웹 배포를 완료했다고 기록하지 않는다.
5. 배포 전 관측: 전용 데모 계정의 진행 중 학습·미정산 테스트 결제 상태를 읽는다. 새 계정이나 실제 결제·환불을 만들지 않는다.
6. GitOps: 승인 대기 중 develop HEAD·현재 배포·설정·검토 유효기간이 달라졌으면 중단한다. 이미지 repository/tag/digest, migration revision, pending 이력을 일반 commit으로 develop에 push한다. 강제 push나 main 변경은 없다. 브랜치 보호가 거부하면 우회하지 않고 실패한다.
7. 검증: Argo 여섯 앱의 두 source revision이 배포 commit과 정확히 같고 Synced·Healthy인지 확인한다. API에서 실제 학생 PIN 로그인 → 미션 시도 시작 → 답변 제출·재조회 → 보호자 리포트 조회를 실행한다. 앞서 읽은 학습 답변 보존·결제 금액·검토된 상태 전이를 비교한다.
8. 기록: 성공/실패와 실행자·승인 확인 시각·버전·범위·근거·run URL·검증 결과를 Git 이력에 남긴다. HTTP 응답 원문·토큰·PIN·쿠키·학생 내용은 저장하지 않는다. 실패 시 자동 롤백하지 않으며 새 검토·승인을 요청한다.

상태 파일은 `infrastructure/gitops/environments/<env>/deployment.json`, 변경 불가한 과거 이력은 `infrastructure/gitops/deployments/<env>/<run-id>-1.json`이다. 현재 실행의 pending 이력만 성공/실패로 한 번 전환할 수 있다. 승인 근거와 검증 JSON은 Actions artifact에도 90일 보관한다. 실행 강제 취소나 Git 최종 기록 실패 시 pending이 남을 수 있으며 Actions 결과를 확인해 별도 복구 요청으로 처리한다. pending을 성공으로 간주하지 않는다.

## 환경 연결에 필요한 설정

GitHub 관리자가 `local`, `prod` Environment를 만들고 `prod` required reviewer에 김동섭을 등록해야 한다. 허용 배포 branch는 develop으로 제한하고 관리자 우회도 차단한다. 운영 승인이 사용자 이름 문자열만으로 대체되지 않도록 실제 review-history를 다시 확인한다. 환경 설정 변경은 이 로컬 작업에서 실행하지 않았다.

| 설정 | 위치·용도 |
|---|---|
| `CD_LOCAL_RUNNERS` / `CD_PROD_RUNNERS` | Repository Variables의 JSON runner label 배열. 기본값은 각각 `["self-hosted","linux","cd-local"]`, `["self-hosted","linux","cd-prod"]` |
| `CD_BASE_URL` | Environment Variable. 웹·API 동일 origin. prod는 HTTPS 필수 |
| `ARGOCD_SERVER` | Environment Variable. runner에서 접근 가능한 Argo origin. prod는 HTTPS 필수 |
| `ARGOCD_TOKEN` | Environment Secret. 해당 환경 6개 Application 조회만 가능한 토큰 |
| `CD_SMOKE_FIXTURE` | Environment Secret. 아래 전용 데모 검증 JSON |
| `CD_AWS_ROLE_ARN`, `CD_AWS_REGION`, `CD_ECR_IMAGE_PREFIX` | prod Environment Variables. 예: `<account>.dkr.ecr.<region>.amazonaws.com/sagomungchi` |

runner에는 Docker/buildx·Git·Python 3.12가 필요하다. PR 코드를 실행하는 공용 self-hosted runner와 분리하고 Argo/API에 접근 가능해야 한다. 테스트는 GitHub hosted runner에서, 게시·배포 검증은 신뢰된 전용 runner에서 수행한다. workflow가 요구하는 `contents:write`, `packages:write`, `actions:read`, `id-token:write`를 허용해야 한다. 기본 GITHUB_TOKEN의 일반 GitOps push를 branch 정책이 허용하는지 관리자가 확인해야 하며 보호 규칙을 자동 완화하지 않는다.

AWS IAM OIDC trust는 저장소와 `environment:prod` subject로 한정하고, ECR 쓰기도 해당 서비스·migration repository로 제한한다. 레지스트리는 미리 만들고 Kubernetes image pull 권한을 준비한다. GHCR private 이미지이면 앱 values의 `imagePullSecrets`를 설정한다. #186은 migration Job에도 이 값을 전달하도록 보완했다. ECR pull은 #185의 노드 역할/인증 구성을 사용한다.

local ApplicationSet에는 `automated` sync(selfHeal, prune/allowEmpty false)를 추가했다. #171의 root Application은 여전히 수동 bootstrap이므로 병합 후 root를 한 번 동기화해 자식 자동 동기화 설정을 적용해야 한다. prod도 #185가 동일한 6개 Application 이름(`prod-<app>`), 두 source의 develop ref, 자동 동기화를 준비해야 한다. 없으면 plan에서 차단한다. 현재 실제 클러스터의 자동 동기화 설정을 변경하지 않았다.

## 검토 파일과 실행

최신 develop checkout에서 다음 명령으로 현재 배포와 설정 fingerprint를 확인한다.

```sh
python -m pip install PyYAML==6.0.3
python scripts/cd_release.py inspect --environment local
```

`infrastructure/gitops/reviews/review.example.json`을 `reviews/local/<요청명>.json` 또는 `reviews/prod/<요청명>.json`으로 복사한다. 예제는 unknown과 빈 근거로 **실행 불가능한 초기값**이다. 근거가 있을 때만 각 check를 compatible로 바꾼다.

- `target_source_sha`: 테스트할/복구할 소스 전체 SHA. 검토 JSON을 넣은 commit SHA가 아니라 앞서 검토한 코드 SHA다.
- `current_deployment`, `config_sha256`: inspect 결과. 최초 이력이 없으면 current_deployment는 null이다.
- `rollback_target`: deploy는 null, rollback은 이전 성공 배포 ID다.
- `checked_at`, `expires_at`: timezone 포함 ISO 시각, 검토 후 최대 24시간. 승인·빌드가 끝나기 전에 만료되면 새 검토를 작성한다.
- `database`, `api`, `events`, `configuration`, `inflight_learning`, `inflight_payments`: 변경 분석 summary와 검증 로그/문서 evidence를 반드시 작성한다. DB version 번호만 쓰고 데이터/API 호환성 검증을 생략하지 않는다.
- `database_restore`: 반드시 false다. 비호환/미확인에는 수정 앱 배포나 별도 승인 복구 절차가 필요하다.

검토 파일을 develop에 반영한 후 workflow_dispatch를 실행한다. 배포 직전에 develop이 다시 바뀌면 보수적으로 중단한다. 동시에 다른 GitOps 변경이 생겨도 non-fast-forward push는 실패하므로 상태를 덮어쓰지 않는다.

## 데모 경로·진행 중 작업 검증

`CD_SMOKE_FIXTURE`는 다음 구조로 Secret에만 저장한다. 실제 토큰·PIN·쿠키·계정 UUID를 저장소에 커밋하지 않는다.

```json
{
  "dedicated_demo_fixture": true,
  "allow_answer_submission": true,
  "child_id": "<demo student UUID>",
  "mission_id": "<published demo mission UUID>",
  "report_id": "<completed demo report UUID>",
  "inflight_attempt_id": "<different IN_PROGRESS attempt UUID>",
  "payment_order_id": "<unsettled test order number>",
  "student_pin": "<secret>",
  "student_device_cookie": "<paired student_device cookie value>",
  "parent_access_token": "<valid guardian access token>",
  "allowed_payment_states": ["PENDING", "APPROVED"],
  "answer": {"inputType": "NARRATIVE", "text": "<dedicated demo answer>"}
}
```

시도 시작은 기존 진행 시도를 반환할 수 있으므로 제출용 mission과 영향 관측용 진행 중 시도를 분리한다. 답변 입력은 실제 미션 유형·기준에 맞춘다. 동일 run의 UUID idempotency key로 제출하고 재조회에서 저장을 확인한다. 제출 답변은 자동 삭제하지 않는다. 운영 학생 대신 #185에서 분리한 데모 계정·토스 테스트 주문을 사용해야 한다. 보호자 토큰/기기 cookie는 유효기간을 확인한다.

이 검증은 실제 학생 PIN 로그인과 보호자 권한 리포트 조회를 다룬다. Google OAuth 브라우저 재인증, 전체 UI 클릭, LLM 품질, report 새 생성, 실제 결제 승인/환불 테스트를 대체하지 않는다. 진행 중 학습은 기존 답변 ID·버전·내용 해시 보존, 결제는 조회 가능성·금액·허용 상태 전이를 관측한다. 배포 전 결제는 core API 기준 PENDING이어야 하며 승인 후 상태는 APPROVED다(PG 응답의 DONE과 구분). 전체 작업 영향 판단에는 검토 파일의 별도 근거도 필요하다.

## 롤백 리허설

1. 같은 환경에 검증 성공한 승인 배포 A, 이후 배포 B를 준비한다. 이전 성공 이력이 없으면 자동으로 후보를 만들지 않는다.
2. B의 **현재 DB·데이터**에 A 앱을 적용해도 되는지 검증한다. 운영과 같은 API·이벤트·설정 계약, 진행 중 학습·결제 영향을 근거와 함께 기록한다.
3. rollback 검토 파일에 current=B, target=A를 고정하고 김동섭의 운영 승인을 받는다.
4. workflow는 A의 app image digest만 복구한다. 현재 migration 이미지·revision은 보존하고 세 migration Job은 disabled로 바꾼다. DB backup restore/down 명령은 없다.
5. B에서 login/API가 망가져 배포 직전 관측이 불가능하면 B 배포 전에 측정한 같은 fixture의 24시간 이내 baseline만 사용한다. 다른 fixture·만료·누락은 차단한다. 복구 후에는 실제 API 검증을 반드시 수행한다.
6. A 복귀 후 동일한 Argo·기능·영향 검증을 수행하고 실행 ID·배포 commit·시각·결과를 기록한다. 다음 정상 deploy에서는 그 소스의 migration 이미지를 사용해 forward migration을 다시 활성화한다.
7. 별도로 database 또는 API check를 incompatible/unknown으로 둔 요청을 실행해 게시·GitOps 변경 전에 차단됨을 기록한다. 성공 리허설과 차단 검증을 모두 #186 근거로 첨부한다.

## 검증 결과와 완료 상태

2026-11-01 로컬 구현 검증:

- 저장소 전체 회귀 테스트 116개 통과(`python -O -m unittest discover -s scripts/tests -v`). 마지막 게시·migration revision 보완 후 CD 테스트 22개도 일반 Python 실행으로 재검증했다(`python -m unittest discover -s scripts/tests -p 'test_cd_*.py' -v`). 승인 누락/다른 사람/다른 환경, 비호환·미확인, 만료/변경된 검토, 이전 성공 이력만 복구, DB migration 비실행, 이미지 digest·registry, 부분 검증의 성공 오판 방지, 로그인·제출·재조회·리포트·진행 중 작업 계약을 포함한다.
- 신규 Python 네 파일의 Ruff lint·format 검사 통과.
- 공식 checksum/digest를 검증한 actionlint 1.7.12와 ShellCheck 0.11.0으로 전체 워크플로 표현식·구문·shell 검사 통과.
- Helm 4.3.1 lint 및 여섯 앱의 배포/롤백 렌더링 12건 통과. 이미지 digest 고정·migration pull secret 전달·롤백 시 migration Job 미생성을 확인했다.
- 합성 서버 통과는 실제 서비스·AWS·GitHub 승인·Argo 검증으로 계산하지 않는다.

| #186 요건 | 이 변경에서 제공한 것 | 실제 환경 검증 |
|---|---|---|
| 서비스 이미지 빌드·게시 | GHCR/ECR·OIDC·서비스별 경로 선택·digest | 미실행 |
| 태그 갱신·Argo 동기화 | 기존 values 갱신·local 자동 sync 설정·정확한 revision 검사 | 미실행 |
| 운영 승인·배포 이력 | 실제 GitHub 승인 재확인·Git/Actions 기록 | 미실행 |
| 로그인·학습 제출·리포트 조회 | 실제 공개 API 검증 스크립트 | 합성 HTTP 계약 검사만 실행 |
| 롤백·마이그레이션 호환성 | 근거 필수·미확인 차단·앱 digest만 복귀 | 임시 Git 회귀 검사만 실행 |
| 롤백 리허설·학습/결제 영향 | 전후 관측·복구 절차·결과 기록 | 실제 리허설 미실행 |
| 완료: 승인→배포→경로 확인 1회 | 실행 흐름 구현 | **미충족** |
| 완료: 롤백 리허설 기록 | 실행 흐름 구현 | **미충족** |

실제 완료에는 #171 병합, #185 운영 환경, 관리자 Environment/OIDC/runner 설정, 전용 데모 fixture가 필요하다. 코드 구현과 로컬 회귀 검사만으로 이슈를 닫거나 체크박스 전체를 완료로 바꾸지 않는다.

## 공식 참고

- [GitHub Environment 배포 보호](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/control-deployments)
- [Actions 실행 승인 이력 API](https://docs.github.com/en/rest/actions/workflow-runs#get-the-review-history-for-a-workflow-run)
- [AWS OIDC 연동](https://docs.github.com/en/actions/how-tos/secure-your-work/security-harden-deployments/oidc-in-aws)
- [ECR login action](https://github.com/aws-actions/amazon-ecr-login)
