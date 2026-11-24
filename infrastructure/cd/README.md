# 운영 배포·롤백 (#186, #858)

`.github/workflows/cd-release.yml`은 main 릴리스 SHA만 운영(AWS 데모 EKS)에 배포한다. 2026-11-20 결정(에픽 #859)으로 기본 방식이 **digest PR**로 바뀌었다(#858). workflow가 이미지를 ECR에 게시한 뒤 지금 main 위에 `infrastructure/gitops/environments/prod/images/<release>.json`만 고친 digest 브랜치를 push하고, 실행 요약에 PR 만들기(compare) 링크를 남긴다. 조직 정책상 Actions는 PR을 만들 수 없어(2026-11-24 결정, #986) **PR은 사람이 그 링크로 연다.** **그 PR의 승인·병합이 배포 승인**이다. 병합되면 Argo CD가 main을 읽어 자동 동기화하고(#855~#857), migration은 앱보다 먼저 PreSync Job으로 돈다. 되돌리기는 그 PR의 revert다. 실패해도 자동 롤백하지 않는다.

예전 방식(GitHub Environment `prod` 승인 → 작업자 PC self-hosted runner `cd-prod`에서 migration Job → Helm 적용 → 경로 확인 → 이력)은 실행 입력 `delivery: helm-emergency`로 고르는 **비상용**으로 12/7 시연까지 남긴다([비상용 Helm 경로](#비상용-helm-경로-helm-emergency)). 앱 release가 없는 빈 클러스터의 `currentRelease: "none"`(#760)은 이 비상용 경로에서만 의미가 있다.

```
수동 실행(main, 계획 JSON, delivery)
  → validate  : main 확인, 계획 검증, SHA가 main 이력인지, (digest PR) images 파일 구조 확인     (GitHub 호스팅)
  → publish   : deploy만. main-<SHA 12자리> 앱·migration 이미지를 ECR에 게시(이미 있으면 재사용) (GitHub 호스팅, OIDC)
  → digest-pr : (기본) 최종 게이트 → 지금 main HEAD에서 images 파일 갱신 → 브랜치 push → 실행 요약에 PR 만들기 링크
                → 사람이 링크로 PR 열기(ci-gitops가 pull_request로 자동 실행)                        (사람)
                → PR을 연 사람과 다른 code owner 1명 승인·병합 → Argo CD 동기화(PreSync migration → 앱)
                → 작업자 PC에서 경로 확인, 결과를 PR 댓글로                                       (사람)
  → deploy    : (비상용) prod 승인 대기 → 최종 게이트 → migration·앱 server dry-run → migration Job 완료 → 앱 적용
                → 경로 확인 → 이력 기록 (작업자 PC)
```

| 파일 | 역할 |
|---|---|
| `policy.json` | 승인자, 릴리스 브랜치(main), 실행 스위치·환경 보호·인프라 준비 선언. `delivery`: digest PR이 고치는 폴더(`imagesDir`), 서비스 → release 파일(`imageFiles`, 서비스 5개 → 파일 6개), migration 값을 가진 파일(`migrationFiles`, core·learning·report-api) |
| `release.example.json` | 운영 배포 계획 형식 |
| `plan.example.json` | 후보 CI가 쓰는 합성 계획(local) |
| `scripts/cd_release.py` | 계획 검증과 실행 게이트(`--require-executable`). `--check-images`로 images 파일 구조 확인, `--write-images`로 images 파일 갱신과 PR 본문(`--pr-body`) 생성 |
| `infrastructure/gitops/environments/prod/images/<release>.json` | #857이 만든 prod 이미지 값. 키 `image.repository`·`image.digest`, core·learning·report-api는 `migration.image.repository`·`migration.image.digest`·`migration.revision`. digest PR만 고친다 |
| `.github/CODEOWNERS` | images 폴더 승인자(김동섭·김태윤) |
| `scripts/verify_cd_deployment.py` | 배포 후 로그인 → 학습 제출 → 리포트 조회 |
| `scripts/cd_record.py` | (비상용 Helm 경로) 수행자·승인·시점·버전·결과 이력 |
| `infrastructure/gitops/environments/prod/redeploy-app.ps1` | release 하나 dry-run/적용. 설정 파일 `<release>.json` + `images/<release>.json`을 함께 넘기고 앱 release에는 `migration.enabled=false`. `-ImageDigest`·`-Revision`은 images 파일의 임시 사본만 바꾼다. `-Migration`이면 앱 대신 migration Job만 다룬다(아래 DB migration 절). `-AllowInstall`이면 release가 없을 때 처음 설치한다(아래 빈 클러스터 첫 배포 절) |
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
| Settings → Environments → `prod` | Required reviewers: `20220348-kim`, `kty2001`(GitHub는 이 목록 중 **1명**이 승인하면 job을 시작한다. 필요 승인 수 설정은 없다) / Deployment branches: `main`만 / Allow administrators to bypass: 끔 |
| Environment `prod` 변수 | `CD_BASE_URL` = 시연 웹 https origin(경로 없음). 2026-11-24부터 `https://www.sagomungchi.co.kr`(core `AUTH_WEB_ORIGIN`과 같아야 경로 확인의 로그인이 통과한다) |
| Repository 변수 | `CD_AWS_ROLE_ARN` = `arn:aws:iam::347161580747:role/sagomungchi-demo-github-cd-publish`, `CD_AWS_REGION` = `ap-northeast-2`, `CD_ECR_REGISTRY` = `347161580747.dkr.ecr.ap-northeast-2.amazonaws.com` |
| Settings → Actions → General | Fork pull request workflows: 외부 기여자 승인 필요 |
| OIDC subject (API) | `gh api -X PUT repos/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/actions/oidc/customization/sub -F use_default=false -f "include_claim_keys[]=repo" -f "include_claim_keys[]=context" -f "include_claim_keys[]=job_workflow_ref"` |

2026-11-04 적용 완료(위 표 그대로, 외부 기여자 승인은 `all_external_contributors`). `policy.json`의 `environmentProtectionVerified`를 true로 바꿨다. Environment `prod`는 digest PR 방식에서는 쓰지 않지만 비상용 Helm 경로가 쓰므로 12/7까지 그대로 둔다.

### B2. digest PR 저장소 설정 (#858, 관리자 손 작업, 11/24 예정)

**아직 적용하지 않았다**(저장소 관리자 권한 필요). 11/24 develop → main 릴리스(#623)가 병합된 **뒤에** 적용한다(먼저 켜면 릴리스 PR에도 승인 규칙이 걸린다. 아래 표 참고). 화면 이름은 2026-11 GitHub 기준이다.

| 순서 | 위치 | 값 | 이유 |
|---|---|---|---|
| 1 | Settings → Branches → Add branch ruleset(또는 classic branch protection) → 대상 `main` | Require a pull request before merging: 켬 / Required approvals: **1** / Require review from Code Owners: 켬 / Dismiss stale approvals when new commits are pushed: 켬 / Require status checks: 끔(아래) / Block force pushes·Restrict deletions: 켬 / Bypass list: 비움(관리자 우회 없음) | digest PR 승인 = 배포 승인. 승인자 수는 #760 승인자 수 결정(1명 기본안, 팀장 확인 전)과 같다. 바뀌면 이 값만 고친다 |
| 2 | 저장소 파일 `.github/CODEOWNERS` | `/infrastructure/gitops/environments/prod/images/ @20220348-kim @kty2001` (develop에 있음, 11/24 릴리스로 main에 들어감) | 1의 Code Owners 설정이 있어야 강제된다 |

예전 1단계("Allow GitHub Actions to create and approve pull requests")는 조직 정책이 막아 저장소에서 켤 수 없고, 2026-11-24부터 필요 없다(아래 PR 생성 토큰 표).
| 3 | 확인 | main에 직접 push가 거부되는지(`git push --dry-run`은 판정하지 않으므로 빈 브랜치 PR로 확인), 아래 A 계정 확인 2단계에서 연 digest PR에 "Review required"·Code owner 표시가 뜨는지 | |

- status check를 필수로 두지 않는 이유: `ci-gitops` 등은 경로 필터가 있어 develop → main 릴리스 PR에 항상 돌지 않는다. 필수로 걸면 경로가 맞지 않는 PR이 영원히 대기한다. digest PR은 사람이 열므로 `ci-gitops`가 `pull_request` 이벤트(경로 `infrastructure/gitops/**`)로 바로 돌고 결과가 PR check에 붙는다. 승인자는 그 check를 보고 승인한다.
- 승인 규칙은 develop → main 릴리스 PR에도 걸린다. 릴리스 PR 작성자는 자기 PR을 승인할 수 없으므로 다른 한 명(동섭 ↔ 태윤)이 승인한다. CODEOWNERS는 images 폴더만 지정하므로 릴리스 PR은 쓰기 권한이 있는 팀원 누구든 1명이 승인하면 된다.
- digest PR 작성자는 링크로 PR을 연 사람이다(커밋 작성자는 `github-actions[bot]`). GitHub는 PR 작성자 본인의 승인을 세지 않으므로 **PR을 연 사람과 다른 code owner**(동섭 ↔ 태윤)가 승인한다. 한 명만 있을 때는 다른 사람이 돌아올 때까지 병합하지 않거나, 막히면 비상용 Helm 경로(아래)를 쓴다. revert PR도 Revert를 누른 사람이 작성자라 같은 규칙이다.
- 되돌릴 때(설정 해제): 1을 끄면 예전과 같다. CODEOWNERS 파일은 1이 꺼져 있으면 리뷰 요청만 보낸다.

#### PR 생성 토큰 (2026-11-20 결정, 2026-11-24 변경)

| 방식 | 내용 | 채택 |
|---|---|---|
| 브랜치 push + 사람이 링크로 PR 열기 (11/24) | job 권한 `contents: write`만. 커밋 메시지를 `git commit --cleanup=verbatim -F`(1행 제목 + 빈 줄 + `pr-body.md`)로 만들어, 커밋 1개짜리 compare 화면(`compare/main...<브랜치>?expand=1`)이 PR 제목·본문을 채운다. 사람이 연 PR이라 `ci-gitops` 등 `pull_request` CI가 평소처럼 돈다 | **채택**(2026-11-24 팀장 결정, #986). 조직 정책이 "Actions가 PR을 만들고 승인하는 것"을 막고 있고 조직은 바꿀 수 없다고 답했다. 새 토큰·도구가 필요 없고, 사람 한 단계(링크 클릭)만 늘어난다 |
| `GITHUB_TOKEN` + `ci-gitops` `workflow_dispatch` (11/20) | job 권한 `contents: write`·`pull-requests: write`·`actions: write`로 `gh pr create` 후 PR 브랜치에 `ci-gitops`를 dispatch | 11/20 채택 → 11/24 폐기. `gh pr create` 단계가 조직 정책으로 실패한다 |
| deploy key (조직 제안) | 저장소 SSH 키로 push | 채택하지 않음. git(SSH) clone·push용이라 PR 생성 API를 부를 수 없다. main 직접 push는 사람 승인 단계가 없어지고 main 보호 규칙과 충돌한다 |
| 개인 계정 포크 | 포크에서 Actions 실행·PR 생성 | 채택하지 않음. OIDC 신뢰 정책·Argo CD repoURL·GitHub 변수·문서를 모두 포크 기준으로 바꿔야 하고, 배포 기록이 포크에만 남는다 |
| 개인 토큰(PAT) | 개인 PAT를 비밀 값으로 두고 `gh pr create` | 채택하지 않음. 만료·보안 관리 부담이 있고 조직이 막았을 수도 있다 |
| GitHub App 설치 토큰 | 조직에 앱을 만들고(`contents`·`pull_requests` 쓰기) `actions/create-github-app-token`으로 토큰 발급. 앱이 만든 PR에는 `pull_request` CI가 평소처럼 돈다 | 선택지. 새 GitHub App은 조직 승인이 필요해 이번에는 하지 않음. 조직 정책도 같이 막을 수 있다. 바꾸려면 digest-pr job의 push 자격을 앱 토큰으로 교체하고 `gh pr create` 단계를 다시 넣는다 |
| CI 생략 | PR만 만들고 CI 없음 | 채택하지 않음(렌더링 오류를 병합 뒤 Argo CD에서야 발견) |

### C. 작업자 PC self-hosted runner (비상용 Helm 경로)

digest PR 방식에는 필요 없다(Argo CD가 클러스터 안에서 동기화). 비상용 Helm 경로(`delivery: helm-emergency`)를 쓸 때만 켠다. EKS API 공개 접근이 작업자 공인 IP로 제한돼 있어 적용은 이 PC에서만 된다. 공개 저장소이므로 runner는 **배포할 때만 켜고 끝나면 끈다.** 12/7 시연 뒤 등록을 지운다.

1. Settings → Actions → Runners → New self-hosted runner(Windows x64)의 안내대로 내려받아 등록한다. 라벨에 `cd-prod`를 추가한다. 가능하면 조직 runner group에 넣고 이 저장소·`cd-release.yml@refs/heads/main`만 허용한다.
2. 서비스로 설치하지 않고 작업자 계정으로 `run.cmd`를 실행한다(기존 AWS 프로필·kubeconfig 사용).
3. runner 폴더의 `.env`(또는 사용자 환경 변수)에 둔다. 값은 Git에 넣지 않는다.

| 변수 | 값 |
|---|---|
| `CD_KUBECONFIG` | 데모 EKS 전용 kubeconfig 절대 경로 |
| `CD_AWS_PROFILE` | 생략 시 `sagomungchi-provided` |
| `CD_HELM` | helm 실행 파일(생략 시 PATH의 helm) |
| `CD_SMOKE_FIXTURE_FILE` | 아래 D의 fixture 절대 경로 |

필요 도구: PowerShell 7, Python 3.12, AWS CLI v2, kubectl, Helm 3 또는 4(ci-gitops는 4.3.1), git. 클러스터를 새로 만들 때는 eksctl도 필요하다(11/17 v0.231.0, [AWS README B 계정 전환 런북](../aws/README.md#b-계정-전환-런북-809) 0단계).

### D. 배포 후 경로 확인 fixture (작업자 PC에만)

`verify_cd_deployment.py` 머리말의 형식이다. 시연 전용(`is_demo=true`) 계정·학생·공개 미션만 쓴다. 판정·결제는 호출하지 않는다.

- `studentDeviceCookie`: 그 학생으로 등록한 브라우저의 `student_device` 쿠키(90일)
- 미션 고르기(#387, 2026-11-10 개정 #483·#485·#506): 스크립트는 학생 주간 테마 `GET /api/v1/students/me/weekly-theme`(`pick-mission` 단계)에서 열린(`OPEN`) 요일 문제 중 그 주에 마무리하지 않은 문제(진행 중 우선)를 `context: THEME_DAY`로, 없으면 되돌아보기가 열린 날(토요일, learning #484 전에는 토·일)에 그 주 마무리한 문제를 `THEME_REVIEW`로 시작한다. `context`를 빼면 `EXTRA`(추가 문제)가 되어 무료 학생은 403 `PREMIUM_REQUIRED`(V43), 프리미엄 학생은 배포마다 환불 판정용 프리미엄 사용(`EXTRA_MISSION`)이 남으므로 쓰지 않는다. 그 주 테마가 게시돼 있어야 하며(없으면 learning이 지난 테마를 재사용), 고를 문제가 없으면 `pick-mission`에서 실패한다.
- 다시 확인할 때: 무료 테마 문제는 하루 한도(429)가 없다(core #485). 같은 날 다시 확인하면 진행 중 시도를 `200`으로 돌려받아 답변이 있으면 조회만 한다(`read-answer`). 열린 문제를 모두 마무리한 평일에는 고를 문제가 없어 `pick-mission`에서 실패하므로 다음 날·토요일에 확인한다(마무리한 문제의 새 `THEME_DAY`는 learning #484부터 409라 고르지 않음, #506). learning #484 배포 뒤 무료 시연 학생은 일요일이 닫혀 실패하므로, 일요일 확인은 프리미엄 시연 학생으로 한다.
- `missionId`: 토·일 되돌아보기에서 먼저 고를 테마 미션(마무리한 문제 중 없으면 첫 마무리 문제). 평일에는 쓰지 않는다.
- `answer`·`answers`: 시작 응답 `mission.inputType`에 맞는 답변을 쓴다. 기본 `answer`(예: `NARRATIVE`) 외 입력 방식 테마 문제가 있으면 `answers` 목록에 입력 방식별 답변을 더한다. 맞는 답변이 없으면 `start-attempt` 단계에서 실패하고 답변을 내지 않는다.
- `parentRefreshCookie`: 같은 학부모로 Google 로그인한 브라우저의 `sagomungchi_refresh` 쿠키. **최초 로그인부터 최대 7일**이고 쓸 때마다 회전한다. 스크립트가 새 값을 파일에 바로 저장한다. 배포 전에 7일이 지났으면 다시 로그인해 넣는다. 같은 값을 브라우저와 동시에 쓰면 세션이 폐기되므로 fixture용 로그인은 따로 한다.
- 현행 동의(2026-11-18 #760): 약관·개인정보가 새 버전(core V39, #415의 1.1)이 되면 그 학부모가 다시 동의하기 전까지 자녀 학생 로그인이 `CHILD_NOT_LINKED`로 막힌다. 재가동·새 계정 배포 전에 fixture 학부모로 로그인해 현행 문서에 동의하고, 그 로그인으로 refresh 쿠키를 새로 받는다. B 계정은 A 최종 스냅샷을 복원하므로 계정·자녀는 그대로지만, 새 CloudFront 도메인에서 부모 로그인(refresh 쿠키)과 학생 기기 등록(`student_device` 쿠키)을 다시 해 이 파일을 갱신한다([B 계정 전환 런북](../aws/README.md#b-계정-전환-런북-809) 15단계).
- 주간 테마: 그 주 테마가 게시돼 있어야 `pick-mission`이 문제를 고른다(없으면 learning이 지난 테마를 재사용). 테마가 0건인 새 DB나 시연 주차는 관리자 화면에서 먼저 게시한다(같은 런북 15단계).

### E. 실행 스위치

2026-11-04 A~C 적용 후 `policy.json`의 `environmentProtectionVerified`·`infrastructureReady`·`executionEnabled`를 true로 바꿨다. main에 반영돼야 실행된다. D(fixture)는 플래그와 무관하며 배포 직전에 채운다. 비우면 적용 후 경로 확인 단계가 실패로 기록된다. 배포를 멈춰야 할 때는 `executionEnabled`를 false로 되돌리는 PR을 main에 반영한다.

## digest PR 배포 (기본, #858)

1. develop → main 릴리스 PR을 병합하고 main CI가 통과했는지 본다.
2. `release.example.json`을 복사해 main SHA·서비스·근거를 채운다. 여섯 항목을 모두 `compatible`과 근거로 채워야 진행된다. `compatibility.schema`에는 이번 SHA의 새 migration 목록과 지금 떠 있는 앱·revert 대상 앱이 새 스키마에서 동작하는 근거를 적는다(PreSync migration이 앱보다 먼저 돌고, revert해도 DB는 그대로). `operation`은 `deploy`만 받는다.
3. 실행한다. 작업자 PC runner는 필요 없다.

```powershell
gh workflow run cd-release.yml --ref main -f delivery=pull-request -f plan="$(Get-Content release.json -Raw | ConvertFrom-Json | ConvertTo-Json -Compress -Depth 10)"
```

4. 결과: 실행 요약 "digest PR 열기"에 브랜치와 **PR 만들기** 링크(`compare/main...<브랜치>?expand=1`). 링크를 열면 제목·본문이 채워져 있으니 그대로 **Create pull request**를 누른다(제목·본문은 고치지 않는다). 이전 digest PR이 열려 있으면 닫고 브랜치를 지운다(아래 "열린 digest PR은 하나만"). 브랜치는 `cd/prod-images-main-<SHA 12자리>-<run id>`(자동 브랜치라 `feature/*` 규칙 밖), 바뀐 파일은 `images/<release>.json`뿐이다(workflow가 다른 경로 변경이 있으면 브랜치를 push하지 않음). 본문에 원본 main SHA, PR 기준 main HEAD, release별 digest 전후, migration revision, 호환성 근거, 계획 기록 JSON, 되돌리기 방법이 들어간다. artifact `cd-digest-pr-<run id>`(90일)에 `plan.json`·`plan-record.json`·`pr-body.md`.
5. PR check의 `ci-gitops`(prod 렌더링·kubeconform) 결과를 확인한다. 사람이 연 PR이라 `pull_request` 이벤트로 자동 실행된다. 실패면 원인을 고치기 전에는 병합하지 않는다.
6. PR을 연 사람과 다른 code owner 1명(김동섭 ↔ 김태윤)이 승인하고 **Squash and merge**로 병합한다. 병합 = 배포 승인.
7. Argo CD가 main을 읽어 동기화한다(PreSync migration Job → 앱). Discord 알림(#855)이나 `argocd app list`/UI에서 앱 Application이 Synced/Healthy인지 본다. migration Job 실패면 Application이 Degraded로 멈추고 앱은 바뀌지 않는다(Job 로그는 작업자 PC에서 `kubectl -n app logs job/<Job 이름>`, 공개 로그에 옮기지 않음).
8. 경로 확인: 작업자 PC에서(fixture가 이 PC에만 있음, 위 D) 실행하고 결과를 그 digest PR 댓글로 남긴다.

```powershell
python scripts/verify_cd_deployment.py --base-url 'https://www.sagomungchi.co.kr' --fixture $env:CD_SMOKE_FIXTURE_FILE --output smoke.json
$s = Get-Content smoke.json -Raw | ConvertFrom-Json
gh pr comment <PR 번호> --body "경로 확인: ok=$($s.ok), $(($s.steps | ForEach-Object { $_.step + ':' + $(if ($_.ok) {'ok'} else {'fail'}) }) -join ', ')"
```

댓글에는 단계 이름과 성공 여부만 남긴다(쿠키·응답 본문은 옮기지 않음).

- 열린 digest PR은 하나만 둔다. 같은 파일을 고치므로 앞 PR이 병합되면 뒤 PR은 충돌한다. 새로 실행했으면 이전 PR은 병합하지 말고 닫는다(병합하면 더 오래된 digest로 되돌아감). cd-release는 `concurrency: cd-prod`로 실행만 한 번에 하나다.
- 이력(결정): digest PR(누가·언제 승인·병합, 본문의 digest·계획)과 Argo CD sync 이력이 배포 이력이다. `cd_record.py`의 `history.json` artifact는 비상용 Helm 경로에서만 남기고, 스크립트는 12/7 시연 뒤 정리한다.
- 계정 전환(B 첫 배포): images 파일의 저장소 주소가 A 레지스트리면 게이트가 "게시한 저장소가 images 파일 저장소와 다릅니다"로 멈춘다. 선행 변수(`CD_ECR_REGISTRY` 등)를 B로 바꾼 뒤, 서비스 5개 전부를 넣은 계획으로 `-f allowRepositoryChange=true`를 주고 실행한다. 저장소 주소와 digest를 함께 바꾸며 PR 본문에 "저장소 변경(계정 전환)"이 표시된다. 서비스 일부만이면 계정이 섞이므로 거부한다.

## digest PR 되돌리기 (#858)

1. 되돌릴 digest PR 화면에서 **Revert** → 만들어진 revert PR을 같은 승인 규칙(Revert를 누른 사람과 다른 code owner 1명)으로 병합한다. Argo CD가 이전 digest로 동기화한다.
2. Argo CD UI의 rollback·수동 sync로 이전 revision을 띄우지 않는다(Git과 어긋나 다음 자동 동기화가 되돌림).
3. revert는 앱 이미지·migration 값만 되돌리고 DB는 그대로다. 이전 앱이 새 스키마에서 동작한다는 근거가 그 PR의 schema 근거에 있어야 한다. migration revision도 이전 값으로 돌아가지만 이미 끝난 Job 이름이 같으면 다시 실행해도 Flyway·Alembic은 할 일이 없다.
4. 그 뒤 다른 digest PR이 병합돼 revert가 충돌하면, 되돌릴 digest를 넣은 PR을 손으로 만든다(`images/**`만, 같은 승인 규칙). 경로 확인은 위 8단계와 같다.

## 11/25 A 계정 확인 절차 (#858)

A 재가동(11/25)에서 Argo CD 설치·플랫폼·앱(#855~#857)이 Synced/Healthy가 된 뒤 한 번 확인한다. 11/24 저장소 설정(B2)과 develop → main 릴리스가 먼저다. 결과는 #858 댓글과 infra 9.18.4에 남긴다.

| # | 할 일 | 확인 |
|---|---|---|
| 1 | 위 "digest PR 배포" 2~3단계로 cd-release 실행(서비스는 바뀐 것만, 처음이면 5개) | validate·publish·digest-pr 통과, 실행 요약에 브랜치와 PR 만들기 링크, 바뀐 파일이 `images/**`뿐 |
| 2 | 실행 요약 링크로 PR 열기 → PR check `ci-gitops` | compare 화면에 제목(`chore: prod 이미지 digest main-…`)·본문이 채워져 있음, 본문 digest가 ECR `main-<SHA 12자리>` 태그와 같음. `ci-gitops`가 `pull_request`로 자동 실행돼 성공. 실패면 원인 수정 전 병합하지 않음 |
| 3 | PR을 연 사람과 다른 code owner가 승인 → Squash and merge | "Review required"·Code owner 표시, 연 사람 본인은 승인할 수 없음, 다른 code owner 승인 1명 뒤 병합 가능 |
| 4 | Argo CD 동기화 | 앱 Application Synced/Healthy, migration PreSync Job Complete, Pod 이미지 digest가 PR 값과 같음(`kubectl -n app get pod -o jsonpath='{..image}'`), Discord 알림 |
| 5 | `verify_cd_deployment.py` → PR 댓글 | 6단계 ok |
| 6 | digest PR Revert → 승인·병합 | Argo CD가 이전 digest로 Synced/Healthy, 경로 확인 다시 ok. 확인 뒤 같은 계획으로 다시 실행해 최신 digest로 돌려놓는다 |

- 대체안(에픽 #859): 11/24 저장소 설정(B2)이 늦어지면 1·2·4·5·6은 그대로 하고 3은 승인 없이 병합되는 것만 기록한다.
- 막히면: 비상용 Helm 경로(아래)로 배포하고 Argo CD로 넘긴다.

## 비상용 Helm 경로 (helm-emergency)

12/7 시연까지만 유지한다. Argo CD 경로가 막혔을 때(동기화 실패를 바로 고칠 수 없음, Argo CD 자체 장애) 쓴다. 쓰는 순서:

1. 대상 앱 Application의 자동 동기화를 끈다(`argocd app set <app> --sync-policy none` 또는 UI). 끄지 않으면 Argo CD가 Helm 적용 결과를 main 값으로 되돌린다.
2. 아래 절차로 `-f delivery=helm-emergency` 실행 → `prod` 승인 → 작업자 PC에서 migration·Helm 적용·경로 확인·이력.
3. 적용한 digest를 Git에 맞춘다: `images/**`만 고친 PR을 main에 낸다(같은 승인 규칙).
4. Git과 클러스터가 같은지(`argocd app diff <app>` 차이 없음) 본 뒤 자동 동기화를 다시 켠다.

Argo CD로 넘어가기 전(Argo CD가 없는 클러스터)에는 1·4가 없다.

1. develop → main 릴리스 PR을 병합하고 main CI가 통과했는지 본다.
2. DB migration은 이 workflow가 앱보다 먼저 실행한다(아래 DB migration 절). `compatibility.schema` 근거에는 이번 main SHA의 새 migration 목록과 **지금 떠 있는 앱이 새 스키마에서 계속 동작한다는 근거**(추가만인지, 컬럼·제약 삭제·이름 변경이 없는지)를 적는다. migration과 앱 적용 사이, 그리고 이후 롤백 때 이전 앱이 새 스키마 위에서 돈다.
3. `release.example.json`을 복사해 main SHA·서비스·근거를 채운다. 여섯 항목을 모두 `compatible`과 근거로 채워야 실행된다. 앱 release가 없는 빈 클러스터면 `currentRelease`를 `"none"`으로 둔다(아래 빈 클러스터 첫 배포 절).
4. 작업자 PC에서 runner를 켜고 실행한다.

```powershell
gh workflow run cd-release.yml --ref main -f delivery=helm-emergency -f plan="$(Get-Content release.json -Raw | ConvertFrom-Json | ConvertTo-Json -Compress -Depth 10)"
```

`gh`가 없으면 Actions 화면에서 `cd-release` → Run workflow(main)에 한 줄 JSON을 붙여 넣고 delivery를 고른다.

5. 승인자 한 명이 Actions 화면에서 `prod` 배포를 승인한다. 승인 전에는 deploy job이 시작되지 않는다.
6. 결과: 실행 요약과 artifact `cd-history-<run id>`(90일)에 `history.json`(승인자·migration Job 결과·release 전후 revision·경로 확인), `plan.json`, `plan-record.json`, `migrations.json`이 남는다. 배포가 끝나면 실제 배포값(앱 digest, `migration.image.digest`·`migration.revision`)을 Git에 맞추는 PR을 올린다. #857 뒤에는 이 값이 `images/<release>.json`에 있으므로 그 파일만 고친 PR을 main에 낸다(위 3단계).

## DB migration (2026-11-17)

11/6 이후 core V29~V51, learning V11~V21, report revision 3개가 운영 DB에 쌓이지 않은 채 남아 있었고, 이전에는 배포 전에 작업자가 [prod README 3절](../gitops/environments/prod/README.md#3-rds-초기화와-migration)대로 손으로 Job을 적용했다. 이제 deploy가 같은 절차를 승인 뒤 자동으로 한다.

| 항목 | 정한 것 |
|---|---|
| 대상 | 계획 `services` 중 DB를 가진 서비스만: core-service → release `core-service`, learning-service → `learning-service`, report-service → `report-api`. ai·scoring만 배포하면 migration 없음 |
| 이미지 | 앱과 같은 태그 `main-<SHA 12자리>`. core·learning은 `sagomungchi/{core,learning}-migrate`에 `infrastructure/gitops/migrations/*.Dockerfile`로 빌드, 태그가 이미 있으면 digest만 읽어 재사용(ECR 태그 불변). report는 같은 배포의 `report-service` 앱 이미지(Alembic 포함)를 그대로 쓴다 |
| 게이트 | `cd_release.py --migrations`가 확인: 대상 서비스와 키가 일치, 저장소 이름(`core-migrate`·`learning-migrate`·`report-service`)과 `@sha256` digest, report는 앱 이미지와 동일. rollback 계획에 migration이 있으면 거부 |
| values | 설정 파일과 `images/<release>.json`(#857)을 쓰고, images 파일은 그대로 두고 `migration.image.digest`와 `migration.revision`(=`main-<SHA 12자리>`)만 바꾼 임시 사본을 쓴다. Job 이름은 `<release>-migrate-main-<SHA 12자리>`(11/4·11/5 수동 Job과 같은 규칙) |
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

## 빈 클러스터 첫 배포 (2026-11-18, #760)

11/17 A 계정 재가동에서 새 클러스터에 cd-release를 실행했을 때 "적용 미리보기"가 `release: not found`로 실패해 migration도 돌지 않았다. 앱 경로가 기존 `deployed` release만 받았기 때문이다. 이제 계획이 첫 배포임을 밝히면 같은 흐름(migration → 앱 → 경로 확인)으로 처음 설치한다.

| 항목 | 정한 것 |
|---|---|
| 계획 표시 | `currentRelease: "none"`. `cd_release.py`가 plan-record에 `firstInstall: true`를 남긴다. deploy만 가능(rollback에 `none`이면 계획 오류) |
| 실행기 | deploy job이 `firstInstall`일 때만 `redeploy-app.ps1`에 `-AllowInstall`을 준다. 스크립트는 `helm list`로 그 release를 찾고, **없을 때만** 미리보기 `helm install --dry-run=server`, 적용 `helm upgrade --install --wait`. 있으면(`deployed`) 지금과 같은 `helm upgrade` |
| 안전장치 | `none`이 아닌 계획에서 release가 없으면 "first install needs -AllowInstall"로 미리보기에서 멈춘다(실수로 빈 namespace에 설치하지 않음). `failed`·`pending` release는 계획과 관계없이 덮어쓰지 않는다 |
| 일부만 있을 때 | `none` 계획이면 있는 release는 `upgrade`, 없는 release만 `install`. 11/17처럼 손으로 일부를 올린 뒤에도 같은 계획으로 이어 갈 수 있다 |
| 이력 | 미리보기 요약에 release별 `install`/`upgrade`, `releases.json`·`history.json`에 `action`과 전후 revision(첫 설치는 `previousRevision: null`), 요약에는 "첫 설치→r1" |
| 같은 계획 재실행 | migration은 `already-complete`, 이미 설치된 앱은 같은 digest로 `upgrade`. 첫 설치 중 `failed`가 된 release는 원인을 고친 뒤 승인을 받아 `helm uninstall <release> -n app`으로 지우고 다시 실행한다 |

이 workflow가 하지 않는 것(빈 클러스터·빈 DB에서는 앞뒤에 직접): RDS 초기화 `demo_stack.py rds-bootstrap --execute`(migration 전, 그리고 뒤에 한 번 더), 웹 S3 업로드·CloudFront 무효화, 관리자·동의 문서·시연 계정·주간 테마 같은 운영 데이터. 빈 DB면 fixture 계정이 아직 없고, 스냅샷을 복원해도 부모 refresh 쿠키(7일)와 학생 기기 쿠키(도메인별)를 새로 받아야 해서 첫 실행의 경로 확인은 실패로 남을 수 있다. 쿠키를 갱신한 뒤 같은 계획을 다시 실행한다. 순서와 이유는 [infra 9.16](../../docs/report/infra.md#916-빈-클러스터-첫-배포와-b-계정-부트스트랩-보완-760-2026-11-18).

## 롤백 (비상용 Helm 경로)

digest PR 방식의 되돌리기는 위 "digest PR 되돌리기"(revert)다. 아래 rollback 계획은 `delivery: helm-emergency`에서만 받는다(digest PR 방식에 rollback 계획을 넣으면 validate가 거부).

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

- 실제 승인·게시·적용과 scoring 롤백 리허설은 2026-11-04·05에 실행했다([infra 7.4](../../docs/report/infra.md#74-운영-실행에서-얻은-주의점)).
- migration 단계(2026-11-17)는 AWS에서 아직 실행하지 않았다. 로컬 확인은 시험(`scripts/tests/test_cd_*.py`, 가짜 aws·kubectl과 실제 helm 렌더링)과 kind의 server dry-run·Job 상태 읽기까지다. 첫 실행은 재가동 때 publish 역할 정책 갱신(위 A) 뒤에 한다.
- 적용 단계는 작업자 PC가 켜져 있어야 한다. 노드 여유가 작으므로 dry-run의 Pod 변경을 보고 승인한다(#185 노드그룹 분리 기록).
- 웹(S3/CloudFront) 배포, RDS 초기화(`rds-bootstrap`), 운영 데이터 seed(성취기준 표 등 일회성 Job)는 이 workflow 범위 밖이다.
- 빈 클러스터 첫 배포(2026-11-18)는 AWS에서 아직 실행하지 않았다. 확인은 시험(가짜 aws·kubectl·helm)과 일회용 kind 빈 클러스터의 migration·앱 server dry-run까지다.
- 계정 `347161580747`·클러스터 `sagomungchi-demo-eks`가 `redeploy-app.ps1`·values·IAM 정책에 고정돼 있다. B 계정(시연용)에서 쓰려면 이 값들을 함께 바꿔야 한다.
- digest PR 방식(2026-11-20, 11/24 사람이 PR 열기로 변경)은 GitHub·AWS에서 끝까지 실행하지 않았다. 11/24 첫 실행은 `gh pr create`에서 조직 정책으로 멈췄다. 확인은 시험(`scripts/tests/test_cd_digest_pr.py`, `test_cd_deployment.py`)까지다. 링크로 연 PR의 제목·본문 채움, `pull_request` ci-gitops, 승인 규칙, Argo CD 동기화는 11/25 A에서 처음 확인한다(위 절차).
- PR 열기는 사람 손이다. 링크를 열지 않으면 브랜치만 남고 배포되지 않는다. 오래된 digest 브랜치는 PR을 닫을 때 함께 지운다.
