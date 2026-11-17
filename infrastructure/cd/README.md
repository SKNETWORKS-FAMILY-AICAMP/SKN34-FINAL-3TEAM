# 운영 배포·롤백 (#186)

`.github/workflows/cd-release.yml`은 main 릴리스 SHA만 운영(AWS 데모 EKS)에 배포한다. 승인은 GitHub Environment `prod`가 맡고, 실제 Helm 적용은 EKS API 접근이 허용된 작업자 PC의 전용 self-hosted runner(`cd-prod`)에서 한다. 배포(deploy)는 앱보다 먼저 같은 SHA의 DB migration Job을 실행하고 완료를 확인한다. 실패해도 자동 롤백하지 않는다.

```
수동 실행(main, 계획 JSON 입력)
  → validate  : main 확인, 계획 검증, SHA가 main 이력인지 확인          (GitHub 호스팅)
  → publish   : deploy만. main-<SHA 12자리> 앱·migration 이미지를 ECR에 게시(이미 있으면 재사용) (GitHub 호스팅, OIDC)
  → deploy    : prod 승인 대기 → 최종 게이트 → migration·앱 server dry-run → migration Job 완료 → 앱 적용
                → 경로 확인 → 이력 기록 (작업자 PC)
```

| 파일 | 역할 |
|---|---|
| `policy.json` | 승인자, 릴리스 브랜치(main), 실행 스위치·환경 보호·인프라 준비 선언 |
| `release.example.json` | 운영 배포 계획 형식 |
| `plan.example.json` | 후보 CI가 쓰는 합성 계획(local) |
| `scripts/cd_release.py` | 계획 검증과 실행 게이트(`--require-executable`) |
| `scripts/verify_cd_deployment.py` | 배포 후 로그인 → 학습 제출 → 리포트 조회 |
| `scripts/cd_record.py` | 수행자·승인·시점·버전·결과 이력 |
| `infrastructure/gitops/environments/prod/redeploy-app.ps1` | release 하나 dry-run/적용. `-ImageDigest`로 저장소 values를 바꾸지 않고 digest만 교체. `-Migration`이면 앱 대신 `migrations/<release>.json`의 Job만 다룬다(아래 DB migration 절) |
| `infrastructure/gitops/migrations/{core,learning}.Dockerfile` | core·learning Flyway migration 이미지. report는 앱 이미지의 Alembic을 쓴다 |

## 1회 설정

실행 스위치는 아래가 모두 끝난 뒤에만 켠다.

### A. AWS: GitHub OIDC 게시 역할 (AWS 변경)

publish job이 ECR에 이미지를 올릴 때만 쓴다. EKS 권한은 없다. trust는 main의 `cd-release.yml` job만 허용한다.

AWS IAM은 GitHub 토큰의 `aud`·`sub`만 조건으로 비교하므로 workflow 제한은 `sub`에 넣는다. 저장소 OIDC subject를 `repo`·`context`·`job_workflow_ref`로 바꾸고(B 표), 이 저장소는 변경 불가 subject라 `sub`가 `repo:SKNETWORKS-FAMILY-AICAMP@169222902/SKN34-FINAL-3TEAM@1415225916:ref:refs/heads/main:job_workflow_ref:…/cd-release.yml@refs/heads/main` 형식이다. trust는 이 값을 `StringLike`로 맞춘다.

```powershell
$profile = 'sagomungchi-provided'
aws iam list-open-id-connect-providers --profile $profile
# 위 목록에 token.actions.githubusercontent.com이 없을 때만
aws iam create-open-id-connect-provider --profile $profile `
  --url https://token.actions.githubusercontent.com --client-id-list sts.amazonaws.com
aws iam create-role --profile $profile --role-name sagomungchi-demo-github-cd-publish `
  --assume-role-policy-document file://infrastructure/aws/iam/github-cd-publish-role.trust.json
aws iam put-role-policy --profile $profile --role-name sagomungchi-demo-github-cd-publish `
  --policy-name ecr-push --policy-document file://infrastructure/aws/iam/github-cd-publish-role.inline.ecr-push.json
```

2026-11-17 저장소 변경: 인라인 `ecr-push`의 대상에 `sagomungchi/core-migrate`·`sagomungchi/learning-migrate`를 더했다(migration 이미지 게시). **AWS에는 아직 넣지 않았다.** 재가동 때 위 `put-role-policy`를 같은 파일로 한 번 더 실행해야 publish가 migration 이미지를 올릴 수 있다. 그 전에는 publish가 migration 게시에서 실패하고 배포로 넘어가지 않는다. `demo_stack.py plan`도 그때까지 이 정책을 차이로 보고한다.

2026-11-04 적용 완료: OIDC 제공자와 역할(인라인 `ecr-push`)을 만들었고, 역할은 `infrastructure/aws/demo-stack.json`에 넣어 `demo_stack.py plan` 대조 대상이다(OK=58). OIDC 제공자는 `demo_stack.py`가 관리하지 않으므로 빈 계정에서 다시 만들 때는 위 명령으로 제공자를 먼저 만든다.

### B. GitHub 저장소 설정 (관리자)

| 위치 | 값 |
|---|---|
| Settings → Environments → `prod` | Required reviewers: `20220348-kim`, `kty2001` / Deployment branches: `main`만 / Allow administrators to bypass: 끔 |
| Environment `prod` 변수 | `CD_BASE_URL` = 데모 CloudFront https origin(경로 없음) |
| Repository 변수 | `CD_AWS_ROLE_ARN` = `arn:aws:iam::347161580747:role/sagomungchi-demo-github-cd-publish`, `CD_AWS_REGION` = `ap-northeast-2`, `CD_ECR_REGISTRY` = `347161580747.dkr.ecr.ap-northeast-2.amazonaws.com` |
| Settings → Actions → General | Fork pull request workflows: 외부 기여자 승인 필요 |
| OIDC subject (API) | `gh api -X PUT repos/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/actions/oidc/customization/sub -F use_default=false -f "include_claim_keys[]=repo" -f "include_claim_keys[]=context" -f "include_claim_keys[]=job_workflow_ref"` |

2026-11-04 적용 완료(위 표 그대로, 외부 기여자 승인은 `all_external_contributors`). `policy.json`의 `environmentProtectionVerified`를 true로 바꿨다.

### C. 작업자 PC self-hosted runner

EKS API 공개 접근이 작업자 공인 IP로 제한돼 있어 적용은 이 PC에서만 된다. 공개 저장소이므로 runner는 **배포할 때만 켜고 끝나면 끈다.**

1. Settings → Actions → Runners → New self-hosted runner(Windows x64)의 안내대로 내려받아 등록한다. 라벨에 `cd-prod`를 추가한다. 가능하면 조직 runner group에 넣고 이 저장소·`cd-release.yml@refs/heads/main`만 허용한다.
2. 서비스로 설치하지 않고 작업자 계정으로 `run.cmd`를 실행한다(기존 AWS 프로필·kubeconfig 사용).
3. runner 폴더의 `.env`(또는 사용자 환경 변수)에 둔다. 값은 Git에 넣지 않는다.

| 변수 | 값 |
|---|---|
| `CD_KUBECONFIG` | 데모 EKS 전용 kubeconfig 절대 경로 |
| `CD_AWS_PROFILE` | 생략 시 `sagomungchi-provided` |
| `CD_HELM` | helm 실행 파일(생략 시 PATH의 helm) |
| `CD_SMOKE_FIXTURE_FILE` | 아래 D의 fixture 절대 경로 |

필요 도구: PowerShell 7, Python 3.12, AWS CLI, kubectl, helm, git.

### D. 배포 후 경로 확인 fixture (작업자 PC에만)

`verify_cd_deployment.py` 머리말의 형식이다. 시연 전용(`is_demo=true`) 계정·학생·공개 미션만 쓴다. 판정·결제는 호출하지 않는다.

- `studentDeviceCookie`: 그 학생으로 등록한 브라우저의 `student_device` 쿠키(90일)
- 미션 고르기(#387, 2026-11-10 개정 #483·#485·#506): 스크립트는 학생 주간 테마 `GET /api/v1/students/me/weekly-theme`(`pick-mission` 단계)에서 열린(`OPEN`) 요일 문제 중 그 주에 마무리하지 않은 문제(진행 중 우선)를 `context: THEME_DAY`로, 없으면 되돌아보기가 열린 날(토요일, learning #484 전에는 토·일)에 그 주 마무리한 문제를 `THEME_REVIEW`로 시작한다. `context`를 빼면 `EXTRA`(추가 문제)가 되어 무료 학생은 403 `PREMIUM_REQUIRED`(V43), 프리미엄 학생은 배포마다 환불 판정용 프리미엄 사용(`EXTRA_MISSION`)이 남으므로 쓰지 않는다. 그 주 테마가 게시돼 있어야 하며(없으면 learning이 지난 테마를 재사용), 고를 문제가 없으면 `pick-mission`에서 실패한다.
- 다시 확인할 때: 무료 테마 문제는 하루 한도(429)가 없다(core #485). 같은 날 다시 확인하면 진행 중 시도를 `200`으로 돌려받아 답변이 있으면 조회만 한다(`read-answer`). 열린 문제를 모두 마무리한 평일에는 고를 문제가 없어 `pick-mission`에서 실패하므로 다음 날·토요일에 확인한다(마무리한 문제의 새 `THEME_DAY`는 learning #484부터 409라 고르지 않음, #506). learning #484 배포 뒤 무료 시연 학생은 일요일이 닫혀 실패하므로, 일요일 확인은 프리미엄 시연 학생으로 한다.
- `missionId`: 토·일 되돌아보기에서 먼저 고를 테마 미션(마무리한 문제 중 없으면 첫 마무리 문제). 평일에는 쓰지 않는다.
- `answer`·`answers`: 시작 응답 `mission.inputType`에 맞는 답변을 쓴다. 기본 `answer`(예: `NARRATIVE`) 외 입력 방식 테마 문제가 있으면 `answers` 목록에 입력 방식별 답변을 더한다. 맞는 답변이 없으면 `start-attempt` 단계에서 실패하고 답변을 내지 않는다.
- `parentRefreshCookie`: 같은 학부모로 Google 로그인한 브라우저의 `sagomungchi_refresh` 쿠키. **최초 로그인부터 최대 7일**이고 쓸 때마다 회전한다. 스크립트가 새 값을 파일에 바로 저장한다. 배포 전에 7일이 지났으면 다시 로그인해 넣는다. 같은 값을 브라우저와 동시에 쓰면 세션이 폐기되므로 fixture용 로그인은 따로 한다.

### E. 실행 스위치

2026-11-04 A~C 적용 후 `policy.json`의 `environmentProtectionVerified`·`infrastructureReady`·`executionEnabled`를 true로 바꿨다. main에 반영돼야 실행된다. D(fixture)는 플래그와 무관하며 배포 직전에 채운다. 비우면 적용 후 경로 확인 단계가 실패로 기록된다. 배포를 멈춰야 할 때는 `executionEnabled`를 false로 되돌리는 PR을 main에 반영한다.

## 배포

1. develop → main 릴리스 PR을 병합하고 main CI가 통과했는지 본다.
2. DB migration은 이 workflow가 앱보다 먼저 실행한다(아래 DB migration 절). `compatibility.schema` 근거에는 이번 main SHA의 새 migration 목록과 **지금 떠 있는 앱이 새 스키마에서 계속 동작한다는 근거**(추가만인지, 컬럼·제약 삭제·이름 변경이 없는지)를 적는다. migration과 앱 적용 사이, 그리고 이후 롤백 때 이전 앱이 새 스키마 위에서 돈다.
3. `release.example.json`을 복사해 main SHA·서비스·근거를 채운다. 여섯 항목을 모두 `compatible`과 근거로 채워야 실행된다.
4. 작업자 PC에서 runner를 켜고 실행한다.

```powershell
gh workflow run cd-release.yml --ref main -f plan="$(Get-Content release.json -Raw | ConvertFrom-Json | ConvertTo-Json -Compress -Depth 10)"
```

`gh`가 없으면 Actions 화면에서 `cd-release` → Run workflow(main)에 한 줄 JSON을 붙여 넣는다.

5. 승인자가 Actions 화면에서 `prod` 배포를 승인한다. 승인 전에는 deploy job이 시작되지 않는다.
6. 결과: 실행 요약과 artifact `cd-history-<run id>`(90일)에 `history.json`(승인자·migration Job 결과·release 전후 revision·경로 확인), `plan.json`, `plan-record.json`, `migrations.json`이 남는다. 배포가 끝나면 앱 values의 digest와 `migrations/*.json`의 `migration.image.digest`·`migration.revision`을 실제 배포값으로 맞추는 PR을 올린다.

## DB migration (2026-11-17)

11/6 이후 core V29~V51, learning V11~V21, report revision 3개가 운영 DB에 쌓이지 않은 채 남아 있었고, 이전에는 배포 전에 작업자가 [prod README 3절](../gitops/environments/prod/README.md#3-rds-초기화와-migration)대로 손으로 Job을 적용했다. 이제 deploy가 같은 절차를 승인 뒤 자동으로 한다.

| 항목 | 정한 것 |
|---|---|
| 대상 | 계획 `services` 중 DB를 가진 서비스만: core-service → release `core-service`, learning-service → `learning-service`, report-service → `report-api`. ai·scoring만 배포하면 migration 없음 |
| 이미지 | 앱과 같은 태그 `main-<SHA 12자리>`. core·learning은 `sagomungchi/{core,learning}-migrate`에 `infrastructure/gitops/migrations/*.Dockerfile`로 빌드, 태그가 이미 있으면 digest만 읽어 재사용(ECR 태그 불변). report는 같은 배포의 `report-service` 앱 이미지(Alembic 포함)를 그대로 쓴다 |
| 게이트 | `cd_release.py --migrations`가 확인: 대상 서비스와 키가 일치, 저장소 이름(`core-migrate`·`learning-migrate`·`report-service`)과 `@sha256` digest, report는 앱 이미지와 동일. rollback 계획에 migration이 있으면 거부 |
| values | 저장소의 `migrations/<release>.json`은 그대로 두고 digest와 `migration.revision`(=`main-<SHA 12자리>`)만 바꾼 임시 사본을 쓴다. Job 이름은 `<release>-migrate-main-<SHA 12자리>`(11/4·11/5 수동 Job과 같은 규칙) |
| 순서 | 승인 → 게이트 → migration server dry-run(core → learning → report) → 앱 server dry-run → migration 적용(core → learning → report, 하나씩 완료 확인) → 앱 적용. 각자 자기 DB라 서로 의존하지 않지만 실패 위치를 분명히 하려고 하나씩 한다 |
| 적용 | NetworkPolicy(`<release>-migration`, DNS·RDS 5432) 다음 Job을 `kubectl apply -n app`. ESO Ready 확인 후. 5초마다 Job 조건을 읽어 `Complete`면 다음, `Failed`·660초 초과면 중단(chart: `backoffLimit: 1`, `activeDeadlineSeconds: 600`) |
| 재실행 | 같은 SHA로 다시 실행하면 이미 `Complete`인 Job은 건너뛴다(`already-complete`). 이미 `Failed`인 Job이 있으면 dry-run부터 멈춘다(Job은 고칠 수 없으므로 원인을 고친 새 main SHA로 배포) |
| 실패 | 그 뒤 migration과 앱 적용을 하지 않는다. DB는 되돌리지 않는다(Flyway·Alembic down 없음). Job 로그는 접속 정보가 섞일 수 있어 공개 Actions 로그에 옮기지 않고, 작업자 PC에서 `kubectl -n app logs job/<Job 이름>`으로 본다 |
| 롤백 | migration을 실행하지 않는다. 이전 앱 이미지만 같은 승인으로 되돌리며, 새 스키마와 호환된다는 근거가 있어야 한다(기존 원칙) |
| 승인 | 별도 승인 지점을 두지 않는다. prod 승인 한 번이 migration과 앱 적용을 함께 허락한다. 승인 화면에서 계획의 `compatibility.schema` 근거를 보고 승인한다 |
| 이력 | `migrations.json`(release·Job·revision·이미지·상태)과 `history.json`의 `migrationJobs`. 계획에 있던 migration이 모두 `complete`·`already-complete`가 아니면 결과는 `failure` |

`redeploy-app.ps1 -Migration`은 앱 release 상태를 보지 않으므로 빈 클러스터에서 앱 설치 전에 손으로 쓸 수도 있다(AWS 계정·EKS endpoint·kubeconfig 확인은 같다).

```powershell
pwsh -File infrastructure/gitops/environments/prod/redeploy-app.ps1 -Service core-service -Migration -Kubeconfig '<kubeconfig>' `
  -ImageDigest 'sha256:<core-migrate digest>' -Revision 'main-<SHA 12자리>'   # 미리보기. -Apply면 적용·완료 대기
```

## 롤백

이전에 승인·배포된 digest로 되돌리는 것도 같은 workflow·승인을 거친다. DB downgrade·백업 복원은 하지 않고, rollback 계획은 migration을 실행하지 않는다(`migrations`를 넣으면 거부).

```jsonc
{
  "environment": "prod", "operation": "rollback",
  "sourceCommit": "<되돌릴 릴리스의 main SHA>", "sourceBranch": "main",
  "services": ["learning-service"],
  "images": {"learning-service": "347161580747.dkr.ecr.ap-northeast-2.amazonaws.com/sagomungchi/learning-service@sha256:<이전 digest>"},
  "currentRelease": "<지금 버전>", "targetRelease": "<되돌릴 버전>",
  "previousApproval": {"release": "<되돌릴 버전>", "record": "<그 버전 배포 run URL>"},
  "reason": "...", "databaseAction": "none",
  "compatibility": { "...": "여섯 항목 모두 현재 DB와 호환되는 근거" }
}
```

이전 digest는 이전 배포 이력(`history.json`의 images)이나 `helm history <release> -n app`에서 찾는다. 현재 DB 스키마와 호환된다는 근거가 없으면 실행되지 않으며, 그때는 수정 버전 배포나 별도 데이터 복구 계획을 승인받는다.

## 한계

- 실제 승인·게시·적용·롤백은 아직 실행하지 않았다(main 반영·D 전).
- migration 단계(2026-11-17)는 AWS에서 아직 실행하지 않았다. 로컬 확인은 시험(`scripts/tests/test_cd_*.py`, 가짜 aws·kubectl과 실제 helm 렌더링)과 kind의 server dry-run·Job 상태 읽기까지다. 첫 실행은 재가동 때 publish 역할 정책 갱신(위 A) 뒤에 한다.
- 적용 단계는 작업자 PC가 켜져 있어야 한다. 노드 여유가 작으므로 dry-run의 Pod 변경을 보고 승인한다(#185 노드그룹 분리 기록).
- 웹(S3/CloudFront) 배포와 운영 데이터 seed(성취기준 표 등 일회성 Job)는 이 workflow 범위 밖이다.
- 계정 `347161580747`·클러스터 `sagomungchi-demo-eks`가 `redeploy-app.ps1`·values·IAM 정책에 고정돼 있다. B 계정(시연용)에서 쓰려면 이 값들을 함께 바꿔야 한다.
