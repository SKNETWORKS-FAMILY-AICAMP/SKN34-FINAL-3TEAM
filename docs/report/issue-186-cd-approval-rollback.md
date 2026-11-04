# #186 CD 배포 승인·이력과 이전 버전 복구

문서 버전: v1.3.0 (2026-11-04). develop `de8e225` 기준, 실행 없는 준비 도구·CI·인계 자료. 현재 #186 담당자는 `20220348-kim`이며 이 브랜치는 부분 작업 인계용이다.

## 확정 정책

사용자가 전달한 담당자 답변을 기준으로 한다.

- 이전 승인 앱이 현재 DB 스키마·데이터와 호환될 때만 새 승인을 받아 이미지 버전을 복귀한다.
- 비호환 및 미확인은 모두 복귀 차단이다. DB 버전 번호만으로 호환성을 판정하지 않는다.
- API·이벤트 계약, 진행 중 학습·결제 작업 영향과 검증 근거를 함께 기록한다.
- DB 자동 downgrade 및 백업 자동 복원은 구현하지 않는다.
- 비호환은 수정 버전 배포 또는 데이터 복구 등 별도 계획을 작성하고 승인받는다.
- 운영 승인자는 김동섭(`20220348-kim`)과 김태윤(`kty2001`) 2명이다(2026-11-03 담당자 결정). 둘 중 한 명의 GitHub Environment 승인 없이는 실행하지 않는다. 승인자 확정은 실행 허용이 아니며 실행 스위치·환경 보호·인프라 준비는 별도로 확인한다.

## 이번 구현

- `scripts/cd_release.py`: 변경 서비스의 불변 이미지 digest, 전체 Git SHA, 대상 버전·사유, 여섯 호환성 검토 항목, 이전 승인 기록의 누락을 검증한다. UTC 시각·계획 해시·차단 사유를 JSON으로 남긴다.
- `infrastructure/cd/policy.json`: 승인자 2명(`20220348-kim`·`kty2001`), 실행 비활성, Environment 보호 설정·인프라 준비 미확인으로 둔다.
- `scripts/tests/test_cd_release.py`: 호환 계획, 비호환·미확인·근거 누락, 승인 기록 불일치, DB 변경 명령 거부, 이미지 digest·레지스트리 검사, 입력의 승인 위조 방어를 검증한다.
- `.github/workflows/cd-candidate.yml`: 기존 `_spring.yml`, `_python.yml`, `_web.yml`을 재사용하는 후보 검사. 이 준비 파일·도구·정책 변경 PR과 수동 실행만 대상으로 한다. 서비스 소스 변경은 기존 서비스별 CI 경로 필터를 유지한다. 배포 시점 전체 후보 검사는 별도로 수행한다.

**계획 입력의 `compatible`이나 이전 승인 기록 문자열은 사람이 작성한 선언이다. 실제 호환성 또는 GitHub 승인 완료를 증명하지 않는다.** 이 도구의 `valid=true`는 필수 입력 형식이 갖춰졌다는 의미뿐이다. `executable`은 항상 false이며, policy 값을 바꿔도 배포되지 않는다. 실제 GitHub 승인·환경 보호 조회·검증 증거 대조 실행기는 후속 연결 대상이다.

## 선행 연결과 구현 순서

1. #171은 병합·종료되었다. 아래 실제 chart 연결표를 사용한다. prod values는 #185가 제공한 `infrastructure/gitops/environments/prod/`를 사용하며 없는 운영 구조를 임의 생성하지 않는다.
2. 운영 배포 소스는 develop → main 릴리스 병합 SHA뿐이다(#185 결정). 그 SHA로 빌드한 이미지를 ECR에 `main-<SHA 12자리>` 태그로 올리고 values에는 digest를 고정한다. 로컬 K8s 이미지는 GHCR을 사용한다. 비밀 키를 JSON·문서에 적지 않는다.
3. GitHub Environment `prod`의 필수 승인자(김동섭·김태윤)·허용 ref(main)·관리자 우회 차단을 확인한다. 현재 prod는 Argo CD 없이 수동 Helm(`redeploy-app.ps1`)이므로 승인 게이트 **뒤에서** Helm 적용을 수행한다. 승인자가 없는 Environment 자동 생성에 의존하지 않는다.
4. 배포 계획은 대상 SHA·이미지 digest·현재 배포 버전·DB 상태·증거에 묶어 승인한다. 실행 직전 현재 상태가 달라졌다면 재검토한다. 환경 단위 직렬화로 배포/복귀의 경합을 막는다.
5. 배포 이력에 수행자·승인 근거·UTC 시각·소스 SHA·전후 이미지 digest·Helm revision(Argo 사용 시 GitOps 커밋·동기화 결과)·기능 확인 결과를 남긴다. 현재 로컬 계획 JSON은 이 실제 배포 이력을 대체하지 않는다.
6. 실제 시연 URL에서 로그인·학습 제출·리포트 조회를 확인한다. health 응답만으로 완료 처리하지 않는다. 합성 계정·토스 테스트 거래를 사용하고 원문·토큰은 증거에 남기지 않는다.
7. 승인된 이전 버전 복귀, 비호환 차단, 미확인 차단을 실행 환경에서 검증한다. DB 복구가 필요하면 일반 롤백과 분리된 승인 계획으로 진행한다.

## DB 호환성 검토 시 반드시 포함할 기존 제약

- #131 `20261030_04`: 기존 report-worker 중지 → migration → 새 worker 순서. 이전 worker와 새 NOT NULL 카운터 스키마의 혼합 실행 미지원. downgrade 시 실패·격리·수동 재처리 메타데이터가 사라진다.
- report 삭제 guard 제거는 삭제된 학생의 재생성 차단을 잃을 수 있어 무조건 롤백 금지.
- core·learning 앱 자동 migration은 꺼져 있다. 운영 DB 초기화·Flyway 이력 수정으로 버전을 맞추지 않는다.
- 기존 모델 버전 rollback 검증은 앱 배포 rollback 검증을 대신하지 않는다.

## 완료 조건 추적

| #186 요구사항 | 현재 상태 |
|---|---|
| 서비스별 이미지 빌드·푸시 | 기존 빌드 CI 재사용 준비, GHCR/ECR 실제 푸시 미구현·미실행 |
| GitOps 태그 갱신 → Argo CD | local은 #171 구조. prod는 #185 기준 Argo CD 없이 수동 Helm·digest 고정 values. 승인 뒤 적용 실행기는 미구현 |
| 운영 승인 게이트·배포 이력 | 정책·계획 기록 준비, 실제 승인자·보호 설정·배포 기록 미완료 |
| 배포 후 로그인·제출·조회 | 미실행 |
| 롤백 절차·호환성 기준 | 정책 문서화·계획 검증 구현, 실행기 미연결 |
| 정상 롤백·차단 리허설 | 합성 계획 단위 테스트만, 실제 환경 리허설 미실행 |

#186의 승인→배포→기능 확인 1회 및 롤백 리허설 완료 조건은 아직 충족하지 않는다. 사용자 요청으로 부분 작업 브랜치만 푸시한다. PR 생성·이슈 종료·레지스트리 업로드·실제 배포·DB 변경은 수행하지 않는다.

## 로컬 검증 기록 (2026-10-30)

- 기준: develop `d651aa1`, 작업 브랜치 `feature/cd-approval-rollback`.
- 저장소 계약·검증 테스트 94개 통과(기존 83개 + 이번 계획 검증 11개). 실제 배포 테스트가 아니다.
- CLI를 별도 Python 프로세스로 실행해 UTC 시각·계획 해시·실행 차단 기록 생성 확인.
- YAML 파싱·기존 reusable workflow 참조 경로·read-only 권한 확인. GitHub Actions 실행 및 actionlint 검증은 아직 수행하지 않았다.
- Windows sandbox의 기본 임시 폴더 권한 오류가 있어 테스트 실행에만 TMP/TEMP를 쓰기 가능한 작업 폴더로 지정한 뒤 재실행했다. 제품 코드의 테스트 생략은 추가하지 않았다.
- 재현: `python -m unittest discover -s scripts/tests -v`. Python 3.12 및 기존 계약 테스트 의존성 필요. Windows 임시 폴더 오류 시 쓰기 가능한 TMP/TEMP를 지정한다.


## #171 실제 연결 구조와 #185 인계 항목

| 대상 | 확인한 저장소 계약 | 후속 실행기에서 할 일 |
|---|---|---|
| 앱 이미지 | `infrastructure/gitops/charts/app-service`: `image.repository` + `image.digest` 또는 `image.tag` | GHCR/ECR에 게시한 실제 digest로 연결 |
| report 공유 이미지 | `environments/local/report-api.yaml`, `report-worker.yaml` 모두 report-service 이미지 | 두 Deployment를 같은 릴리스 digest로 함께 갱신. worker는 `python -m app.worker` |
| core·learning migration | `infrastructure/gitops/migrations/{core,learning}.Dockerfile` 및 chart `migration.image`, `migration.revision` | 앱 SHA와 대응하는 migration 이미지 확인. 이전 앱 복귀 때 migration Job을 함께 되돌리거나 DB downgrade하지 않음 |
| report migration | chart의 PreSync migration Job, Alembic | #131 worker 정지/순차 배포 제약 검토. 같은 report 이미지에 포함된 migration 경로 확인 |
| Argo CD | `infrastructure/gitops/argocd/local/`, local 서비스별 values | 승인 이후 GitOps 커밋, 실제 동기화/상태 기록. 현재 파일은 변경하지 않음 |
| 웹 | Vite 정적 빌드, 운영 S3/CloudFront는 #185 범위 | 이번 5개 backend 이미지 목록과 구분하여 웹 배포·복구 정책 연결 |
| prod | #185 병합: `environments/prod/` values·`redeploy-app.ps1`(기본 server dry-run, `-Apply` 명시), ECR 7개, EKS Pod Identity, 노드그룹 2개 On-Demand | main 릴리스 SHA 이미지 빌드·게시 경로(현재 CodeBuild→ECR) 자동화, 승인 뒤 Helm 적용, 배포 이력 기록 |

승인자와 GitHub Environment 보호 설정이 확정되기 전에는 실행 게이트를 연결하지 않는다. 실행 가능한 배포 워크플로를 미리 켜거나 AWS 리소스를 생성하지 않는다.

## 계획 예시와 재현

`infrastructure/cd/plan.example.json`은 **합성 입력**이다. SHA/digest/릴리스는 실제 아티팩트가 아니며 호환성은 unknown, 승인 근거는 공란이다. 실제 계획 작성 시 검증 근거를 채우되 선언만으로 실행 승인이 성립하지 않는다.

```sh
python -m unittest discover -s scripts/tests -p test_cd_release.py -v
python scripts/cd_release.py --plan infrastructure/cd/plan.example.json --policy infrastructure/cd/policy.json --output /tmp/cd-plan-record.json
```

CLI 종료 코드 0은 JSON 계획의 형식 유효성만 뜻한다. 호환 여부는 `blocks`를 읽어야 하며 `executable`은 항상 false다. 입력 오류는 코드 2와 차단 기록을 남긴다. 출력과 입력 경로가 같으면 입력을 덮어쓰지 않고 거부한다. 기록에는 계획·정책 SHA-256, UTC 시각과 차단 사유가 포함되며 수행자·실제 승인·배포 이력을 대신하지 않는다.

`cd-candidate.yml`은 해당 브랜치의 준비 파일 push, 준비 파일 변경 PR, 수동 실행에서 검사한다. 기존 `_spring.yml`·`_python.yml`·`_web.yml`을 재사용하고 합성 계획 차단 기록을 7일 artifact로 보관한다. `contents: read`이며 packages/id-token 쓰기 권한이나 deploy 명령은 없다.


## 최신 검증 기록 (2026-11-02)

- 기준 `4410007`, 브랜치 `feature/cd-release-preparation`. #209 병합을 포함한 최신 develop을 반영했다.
- `python -O -m unittest discover -s scripts/tests -q`: **107개 통과**(기존 계약 검사 94 + CD 계획 검사 13), 실패·생략 없음.
- 변경 Python Ruff check/format 및 `git diff --check` 통과.
- workflow YAML 파싱, 기존 재사용 workflow 입력 이름, policy 선행 의존성, contents 읽기 전용 권한 대조 통과. actionlint 및 실제 원격 Actions 전체 실행 결과는 이번 로컬 검증에 포함하지 않는다.
- 예시 CLI 실행은 valid=true, executable=false, 비호환/미확인·근거 누락·승인 미연결 차단 사유를 기록했다. JSON 형식 오류와 JSON 배열/null 입력도 코드 2로 차단 기록을 남기는 테스트를 통과했다.
- 최초 Windows sandbox 임시 폴더 권한으로 CLI 테스트가 실패했으나 정상 권한에서 전체 재실행해 통과했다. 테스트를 생략하지 않았다.
- 실제 이미지 build/push, GitHub Environment 승인, GitOps 커밋, Argo CD sync, 운영 DB 변경, 실제 로그인·학습·리포트 동작 및 롤백 리허설은 실행하지 않았다. #186 원격 체크박스와 종료 상태는 변경하지 않는다.

## 최신 develop 반영 (2026-11-03)

- 담당자(`20220348-kim`)가 이 인계 브랜치를 기준으로 이어서 작업하기로 했다. 다른 브랜치 `feature/cd-release-186`(11/01, 승인자 확정본)은 기준으로 삼지 않으며 변경하지 않는다. 승인자는 아래 결정에 따라 2명으로 확정했다.
- `origin/develop` `e65c972`를 merge commit `761f127`로 반영했다(rebase·force push 없음). 충돌 2건은 문서 목록 줄이며 양쪽 내용을 모두 유지했다: `docs/README.md`(#186·#246 보고서 줄), `docs/design/architecture.md` 4.5(#171 병합 문장 + #186 로컬 준비 문장).
- 전제 재대조 결과 변경 필요 없음:
  - `cd-candidate.yml`의 재사용 workflow 입력(`_spring.yml`·`_python.yml`의 `service-path`, `_web.yml`의 `app-path`)과 서비스 목록(core·learning·ai·scoring·report·web)이 기존 서비스별 CI와 같다.
  - app-service chart의 `image.tag`/`image.digest`, `migration.image`·필수 `migration.revision`, `infrastructure/gitops/migrations/{core,learning}.Dockerfile`, `argocd/local/` 경로가 그대로다. 현재 local migration revision은 core `v26`, learning `v8`, report `20261102-05`다.
- 그사이 develop에 들어온 관련 변경: #238 `ci-gitops.yml`(chart lint·렌더·스키마, migration 이미지 빌드 확인), #273 kind 단일 클러스터 `sagomungchi-local`, #236 kind 환경값·외부 443 egress, #246 `e2e.yml`. 이후 실행기 연결 때 #238의 migration 이미지 빌드 확인과 #246 E2E를 배포 후 기능 확인 후보로 검토한다. 이번에는 연결하지 않았다.
- 검증: `python -O -m unittest discover -s scripts/tests` **113개 통과**(CD 계획 검사 13개 포함), 전체 workflow YAML 파싱 통과, 예시 CLI 종료 코드 0·`valid=true`·`executable=false`·차단 사유 18개 기록. 실제 이미지 게시·승인·GitOps 커밋·Argo CD 동기화·롤백 리허설은 실행하지 않았다.

## 승인자 확정과 #185 대기 (2026-11-03)

- 담당자 결정: 운영 배포 승인자는 김동섭(`20220348-kim`)·김태윤(`kty2001`) 2명. 한 명이 자리를 비워도 승인할 수 있도록 예비 승인자를 둔다. `policy.json`의 `approvers`에 반영했고 `executionEnabled`·`environmentProtectionVerified`·`infrastructureReady`는 계속 false다.
- GitHub Environment `prod`의 필수 승인자 등록·허용 ref·관리자 우회 차단은 저장소 관리자 설정이며 이번에 변경하지 않았다. 등록 후 `environmentProtectionVerified`를 실제 조회 결과로 바꾼다.
- 11/01 브랜치 `feature/cd-release-186`의 실제 배포 workflow(self-hosted runner·develop 직접 push·Argo CD 토큰 필요)는 가져오지 않았다. #185 PR(ECR·OIDC·prod 환경)이 먼저 병합된 뒤 필요한 부분(배포 후 기능 확인·배포 이력 형식)을 골라 옮긴다. 그때까지 실제 게시·배포·롤백 리허설은 대기한다.

## #185 결정 반영 (2026-11-04)

- `origin/develop` `de8e225`(#185 PR #333 포함)를 merge commit으로 반영했다. 충돌 2건은 문서 목록 줄이며, develop의 통합 보고서 표를 따르고 #186 줄만 추가했다(`docs/README.md`), architecture 4.5는 develop 문장 + #186 준비 문장으로 정리했다.
- #185 결정과의 대조:

| #185 결정 | #186 설계 영향 | 반영 |
|---|---|---|
| 배포 기준 main. develop → main 릴리스 병합 후 그 SHA 이미지만 배포 | prod 계획은 main에서 나온 커밋이어야 함 | `policy.json` `releaseBranch: "main"`, 계획 필수 필드 `sourceBranch`, prod는 둘이 같아야 `valid`. SHA가 실제 main 이력에 있는지는 실행기가 `git merge-base --is-ancestor`로 확인할 후속 |
| prod는 수동 Helm(`redeploy-app.ps1`), Argo CD prod 없음 | 승인 뒤 적용 대상이 GitOps 커밋이 아니라 Helm upgrade | 선행 연결 절·인계 표 갱신. 롤백도 이전 승인 digest values로 Helm upgrade하며 DB downgrade는 하지 않는다 |
| IRSA 대신 EKS Pod Identity | CD는 앱 Pod 권한을 바꾸지 않음. 영향 없음 | 이미지 게시 자격(현재 CodeBuild)은 Pod Identity와 별개로 정한다 |
| 노드그룹 2개(application 2대·최대 3, platform-observability 2대) 모두 On-Demand | rolling update·롤백 때 application 노드 여유가 작음(scoring 예약 1Gi로 조정됨) | 적용 전 `redeploy-app.ps1` dry-run의 용량·Pod 변경 확인을 계획 근거로 남긴다 |

- 승인자는 김동섭(`20220348-kim`)·김태윤(`kty2001`) 2명 그대로이며 `executionEnabled`·`environmentProtectionVerified`·`infrastructureReady`는 false다.
- 실제 EKS 배포·롤백 시험·GitHub Environment 설정은 하지 않았다. learning·ai·scoring·report의 main 기준 재배포는 #186 병합 후 이 절차로 진행한다.
- 검증: `python -O -m unittest discover -s scripts/tests` **127개 통과**(CD 계획 검사 15개: main 릴리스 기준·저장소 정책 확인 포함), 변경 Python ruff check·format 통과, 전체 workflow YAML 파싱 통과, 예시 CLI 종료 코드 0·`valid=true`·`executable=false`·차단 사유 17개.

## 배포 실행기 구현 (2026-11-04)

실행 단계(승인 → 적용 → 경로 확인 → 이력)를 코드로 구현했다. AWS·GitHub 설정은 바꾸지 않았고 실제 실행은 하지 않았다. 설정·명령은 [운영 배포 문서](../../infrastructure/cd/README.md)를 따른다.

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
- 이슈 완료 조건(승인 → 배포 → 경로 확인 1회, 롤백 리허설 기록)은 설정 A~E 후 실제 실행으로 채운다.

## 운영 설정 적용과 후보 CI 정리 (2026-11-04)

- 설정 A(AWS): GitHub OIDC 제공자와 ECR 쓰기 전용 역할 `sagomungchi-demo-github-cd-publish`(인라인 `ecr-push`)를 만들었다. 역할은 `demo-stack.json`에 넣어 `demo_stack.py plan` OK=58로 대조한다. OIDC 제공자는 `demo_stack.py` 관리 대상이 아니다.
- 설정 B(GitHub): Environment `prod`(필수 승인자 `20220348-kim`·`kty2001`, 배포 브랜치 `main`만, 관리자 우회 끔), 변수 `CD_BASE_URL`(prod)·`CD_AWS_ROLE_ARN`·`CD_AWS_REGION`·`CD_ECR_REGISTRY`, 외부 기여자 PR workflow 전원 승인(`all_external_contributors`)을 적용했다.
- 설정 C(runner)·D(fixture)·E(실행 스위치)는 남아 있다.
- `cd-candidate.yml` 정리: 처음 구성(`98b3f98`)은 이 브랜치 push와 PR에서 모두 실행되고 서비스 CI(`_spring.yml`·`_python.yml`·`_web.yml`, 6개 대상)를 다시 호출해, CD 도구만 바꾼 PR에도 같은 서비스 검사가 두 번씩 돌았다. 서비스 코드는 서비스별 CI가, 배포 이미지는 `cd-release` publish가 main SHA로 빌드하므로 PR·수동 실행의 CD 도구 검사(`policy` job)만 남겼다. `executionEnabled=false` 고정 검사는 E단계 PR을 막으므로 릴리스 브랜치·승인자 기준 확인으로 바꿨다. 위 2026-11-02·11-03 기록의 재사용 workflow 설명은 당시 구성이다.

- 검증: `python -O -m unittest discover -s scripts/tests` **150개 통과**(후보 workflow 구조 테스트 1개 추가), ruff 통과, workflow YAML 파싱 통과.
- 브랜치 보호: develop·main 모두 보호 규칙·Ruleset이 없다(2026-11-04 API 확인). 배포 적용은 `prod` 승인으로 막히지만, main 직접 push로 workflow를 바꾸면 승인 전 publish job이 ECR 게시 역할을 쓸 수 있다. main 보호(PR 필수, force push·삭제 금지)는 팀 결정으로 남긴다.
