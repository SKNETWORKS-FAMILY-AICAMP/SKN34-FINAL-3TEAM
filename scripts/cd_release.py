"""#186 배포 계획 검증과 실행 게이트. 네트워크·배포·DB 변경을 실행하지 않는다.

`executable`은 오류·차단 사유가 모두 없을 때만 true다. 실제 승인은 GitHub Environment가
맡으며, 계획 파일의 승인 표시(approved 등)는 읽지 않는다.
"""

import argparse
import hashlib
import json
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

CHECKS = ("schema", "data", "api", "events", "ongoingLearning", "payments")
SERVICES = {
    "core-service",
    "learning-service",
    "ai-service",
    "scoring-service",
    "report-service",
}
# DB를 가진 서비스의 migration 이미지 저장소. report Alembic은 앱 이미지 안에 있다
MIGRATION_REPOSITORIES = {
    "core-service": "core-migrate",
    "learning-service": "learning-migrate",
    "report-service": "report-service",
}
# 앱 release가 하나도 없는 빈 클러스터의 첫 배포(#760). 이 값일 때만 실행기가 release 없는 앱을 설치한다
FIRST_INSTALL = "none"


def image_pattern(environment):
    registry = (
        r"ghcr\.io/[a-z0-9._/-]+"
        if environment == "local"
        else r"[0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com/[a-z0-9._/-]+"
    )
    return registry + r"@sha256:[0-9a-f]{64}"


def validate_migrations(plan, services, images, pending_images):
    """deploy는 앱 적용 전에 DB를 가진 서비스의 migration을 실행한다. rollback은 DB를 건드리지 않는다."""
    errors = []
    migrations = plan.get("migrations")
    if plan.get("operation") == "rollback":
        if migrations:
            errors.append("롤백은 migration을 실행하지 않습니다(DB는 되돌리지 않음)")
        return errors
    if plan.get("operation") != "deploy" or services is None:
        return errors
    if migrations is None and pending_images:
        return errors  # publish가 앱 이미지와 같은 SHA로 게시한 뒤 채운다
    expected = {s for s in services if s in MIGRATION_REPOSITORIES}
    if not isinstance(migrations, dict):
        if expected:
            errors.append("DB를 가진 서비스의 migration 이미지가 필요합니다")
        return errors
    if set(migrations) != expected:
        errors.append(
            "migrations의 서비스가 services 중 DB를 가진 서비스(core·learning·report)와 다릅니다"
        )
    for service, image in migrations.items():
        if service not in MIGRATION_REPOSITORIES:
            continue
        repository = MIGRATION_REPOSITORIES[service]
        if not isinstance(image, str) or not re.fullmatch(
            image_pattern(plan.get("environment")), image
        ):
            errors.append(f"{service} migration: 불변 digest 이미지가 필요합니다")
        elif image.split("@")[0].rsplit("/", 1)[-1] != repository:
            errors.append(f"{service} migration: {repository} 저장소 이미지여야 합니다")
        elif (
            service == "report-service"
            and isinstance(images, dict)
            and image != images.get(service)
        ):
            errors.append(
                "report-service migration은 같은 배포의 앱 이미지(Alembic 포함)여야 합니다"
            )
    return errors


def validate(plan, policy, *, pending_images=False):
    """검토 자료의 완전성과 실행 차단 사유를 분리한다. 선언은 승인 증명이 아니다.

    pending_images=True는 배포 이미지를 아직 빌드하기 전 단계라 images 누락을 허용한다.
    """
    errors = []
    blocks = []
    if not isinstance(plan, dict) or not isinstance(policy, dict):
        return {
            "valid": False,
            "executable": False,
            "errors": ["계획과 정책은 JSON 객체여야 합니다"],
            "blocks": ["입력 오류"],
        }
    compatibility = plan.get("compatibility")
    if not isinstance(compatibility, dict):
        compatibility = {}
    if plan.get("environment") not in ("local", "prod"):
        errors.append("environment는 local 또는 prod여야 합니다")
    if plan.get("operation") not in ("deploy", "rollback"):
        errors.append("operation은 deploy 또는 rollback이어야 합니다")
    for field in ("sourceCommit", "currentRelease", "targetRelease", "reason"):
        if not isinstance(plan.get(field), str) or not plan[field].strip():
            errors.append(f"{field}가 필요합니다")
    if not re.fullmatch(r"[0-9a-f]{40}", str(plan.get("sourceCommit", ""))):
        errors.append("sourceCommit은 전체 Git SHA여야 합니다")
    if (
        not isinstance(plan.get("sourceBranch"), str)
        or not plan["sourceBranch"].strip()
    ):
        errors.append("sourceBranch가 필요합니다")
    # 운영은 develop → main 릴리스 병합 SHA만 배포한다 (#185). 이력 포함 여부는 실행기가 확인
    elif plan.get("environment") == "prod" and plan["sourceBranch"] != policy.get(
        "releaseBranch"
    ):
        errors.append(
            "prod는 정책의 릴리스 브랜치(releaseBranch)에서 나온 커밋만 배포합니다"
        )
    if plan.get("currentRelease") == plan.get("targetRelease"):
        errors.append("현재 버전과 대상 버전이 같습니다")
    if plan.get("currentRelease") == FIRST_INSTALL and plan.get("operation") != "deploy":
        errors.append("첫 배포(currentRelease none)는 deploy만 가능합니다. 되돌릴 이전 버전이 없습니다")
    services = plan.get("services")
    if (
        not isinstance(services, list)
        or not services
        or len(set(map(str, services))) != len(services)
        or not set(services) <= SERVICES
    ):
        errors.append("services는 지원 서비스의 중복 없는 목록이어야 합니다")
        services = None
    images = plan.get("images")
    if images is None and pending_images and plan.get("operation") == "deploy":
        pass  # 배포는 publish 단계가 main SHA로 빌드한 digest를 나중에 넣는다
    elif not isinstance(images, dict) or not images:
        errors.append("변경 서비스 이미지가 필요합니다")
    else:
        if services is not None and set(images) != set(services):
            errors.append("images의 서비스가 services와 다릅니다")
        for service, image in images.items():
            if service not in SERVICES:
                errors.append(f"지원하지 않는 서비스: {service}")
            if not isinstance(image, str) or not re.fullmatch(
                image_pattern(plan.get("environment")), image
            ):
                errors.append(
                    f"{service}: 환경에 맞는 레지스트리와 불변 digest가 필요합니다"
                )
    errors.extend(validate_migrations(plan, services, images, pending_images))
    for name in CHECKS:
        evidence = compatibility.get(name, {})
        if not isinstance(evidence, dict):
            evidence = {}
        if evidence.get("status") != "compatible":
            blocks.append(f"{name}: 비호환 또는 미확인")
        if (
            not isinstance(evidence.get("evidence"), str)
            or not evidence["evidence"].strip()
        ):
            blocks.append(f"{name}: 검증 근거 없음")
    if plan.get("operation") == "rollback":
        previous = plan.get("previousApproval", {})
        if not isinstance(previous, dict):
            previous = {}
        if previous.get("release") != plan.get("targetRelease") or not previous.get(
            "record"
        ):
            blocks.append("대상 버전의 이전 승인 기록 없음")
    if plan.get("databaseAction") != "none":
        errors.append("DB 자동 다운그레이드·백업 복원은 허용하지 않습니다")
    for field in ("approvers", "environmentProtectionVerified", "infrastructureReady"):
        if not policy.get(field):
            blocks.append(f"운영 연결 미완료: {field}")
    if policy.get("executionEnabled") is not True:
        blocks.append("실행 스위치 비활성")
    if pending_images:
        blocks.append("배포 이미지 빌드 전")
    return {
        "valid": not errors,
        "executable": not errors and not blocks,
        "errors": errors,
        "blocks": blocks,
    }


def validate_delivery(policy):
    """digest PR(#858) 대상 파일 정의를 확인한다. 서비스마다 images 파일이 있고 migration 파일은 그중 하나다."""
    delivery = policy.get("delivery") if isinstance(policy, dict) else None
    if not isinstance(delivery, dict):
        return ["정책에 delivery(digest PR 대상)가 없습니다"]
    errors = []
    if not isinstance(delivery.get("imagesDir"), str) or not delivery["imagesDir"]:
        errors.append("delivery.imagesDir가 필요합니다")
    files = delivery.get("imageFiles")
    if not isinstance(files, dict) or set(files) != SERVICES:
        errors.append("delivery.imageFiles는 지원 서비스마다 하나씩 있어야 합니다")
        files = {}
    releases = []
    for service, names in files.items():
        if (
            not isinstance(names, list)
            or not names
            or not all(isinstance(n, str) and re.fullmatch(r"[a-z0-9-]+", n) for n in names)
        ):
            errors.append(f"delivery.imageFiles.{service}: release 이름 목록이 필요합니다")
            continue
        releases.extend(names)
    if len(releases) != len(set(releases)):
        errors.append("delivery.imageFiles에 같은 release가 두 번 있습니다")
    migrations = delivery.get("migrationFiles")
    if not isinstance(migrations, dict) or set(migrations) != set(MIGRATION_REPOSITORIES):
        errors.append("delivery.migrationFiles는 DB를 가진 서비스(core·learning·report)와 같아야 합니다")
    else:
        for service, name in migrations.items():
            if name not in (files.get(service) or []):
                errors.append(f"delivery.migrationFiles.{service}: 그 서비스의 images 파일이어야 합니다")
    return errors


def _split_image(image):
    repository, digest = image.split("@", 1)
    return repository, digest


def _get(data, *keys):
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def _images_path(policy, root, release):
    return Path(root) / policy["delivery"]["imagesDir"] / f"{release}.json"


def check_images_files(policy, root):
    """#857 images 파일이 계약 키를 갖는지 본다. 값이 아닌 구조만 확인한다."""
    errors = validate_delivery(policy)
    if errors:
        return errors
    delivery = policy["delivery"]
    migration_releases = set(delivery["migrationFiles"].values())
    for names in delivery["imageFiles"].values():
        for release in names:
            path = _images_path(policy, root, release)
            try:
                data = json.loads(path.read_bytes())
            except (OSError, ValueError, UnicodeError):
                errors.append(f"{release}: images 파일이 없거나 JSON이 아닙니다 ({path.as_posix()})")
                continue
            keys = [("image", "repository"), ("image", "digest")]
            if release in migration_releases:
                keys += [
                    ("migration", "image", "repository"),
                    ("migration", "image", "digest"),
                    ("migration", "revision"),
                ]
            for key in keys:
                if not isinstance(_get(data, *key), str):
                    errors.append(f"{release}: {'.'.join(key)}가 필요합니다")
    return errors


def image_file_updates(record, policy, root, *, allow_repository_change=False):
    """계획 기록(images·migrations) → images 파일 새 내용. (changes, errors).

    저장소 주소가 파일과 다르면(계정·레지스트리 전환) 기본은 고치지 않고 오류로 둔다.
    allow_repository_change는 B 계정 첫 digest PR처럼 저장소를 함께 바꿀 때만 쓰며,
    계정이 섞이지 않도록 지원 서비스 전부를 한 PR에서 바꾸는 계획만 받는다.
    """
    errors = check_images_files(policy, root)
    if errors:
        return [], errors
    if record.get("environment") != "prod" or record.get("operation") != "deploy":
        return [], ["digest PR은 prod deploy만 만듭니다. 되돌리기는 digest PR revert로 합니다"]
    if allow_repository_change and set(record.get("services") or []) != SERVICES:
        return [], ["저장소 변경은 지원 서비스 전부(5개)를 한 PR에서 바꿀 때만 허용합니다(계정 혼재 방지)"]
    commit = record.get("sourceCommit") or ""
    revision = "main-" + commit[:12]
    delivery = policy["delivery"]
    images = record.get("images") or {}
    migrations = record.get("migrations") or {}
    changes = []

    def swap(target, new_repository, label):
        """target(image 또는 migration.image)의 저장소가 다르면 허용 여부에 따라 바꾸거나 오류."""
        old = target["repository"]
        if old == new_repository:
            return None
        if not allow_repository_change:
            errors.append(
                f"{label}: 게시한 저장소({new_repository})가 images 파일 저장소({old})와 다릅니다. "
                "계정 전환이면 allowRepositoryChange로 다시 실행하세요"
            )
            return False
        target["repository"] = new_repository
        return old

    for service in record.get("services") or []:
        repository, digest = _split_image(images[service])
        for release in delivery["imageFiles"][service]:
            path = _images_path(policy, root, release)
            data = json.loads(path.read_bytes())
            before = {"image": data["image"]["digest"]}
            old = swap(data["image"], repository, release)
            if old is False:
                continue
            data["image"]["digest"] = digest
            after = {"image": digest}
            if old:
                before["repository"], after["repository"] = old, repository
            if delivery["migrationFiles"].get(service) == release:
                m_repository, m_digest = _split_image(migrations[service])
                migration = data["migration"]
                before |= {"migration": migration["image"]["digest"], "revision": migration["revision"]}
                m_old = swap(migration["image"], m_repository, f"{release} migration")
                if m_old is False:
                    continue
                migration["image"]["digest"] = m_digest
                migration["revision"] = revision
                after |= {"migration": m_digest, "revision": revision}
                if m_old:
                    before["migrationRepository"], after["migrationRepository"] = m_old, m_repository
            if before == after:
                continue
            changes.append(
                {
                    "service": service,
                    "release": release,
                    "file": Path(delivery["imagesDir"], f"{release}.json").as_posix(),
                    "before": before,
                    "after": after,
                    "content": json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                }
            )
    if not errors and not changes:
        errors.append("바꿀 digest가 없습니다(이미 main images 파일과 같음)")
    return changes, errors


def _short(digest):
    return digest.split(":", 1)[-1][:12] if digest else "-"


def render_pr_body(record, changes, *, run_url="", base_sha=""):
    """digest PR 본문: 원본 SHA, 서비스별 digest, 계획 근거, 승인·확인·되돌리기 방법."""
    commit = record.get("sourceCommit") or ""
    lines = [
        "## prod 이미지 digest 갱신 (#858)",
        "",
        "이 PR을 승인·병합하면 Argo CD가 main의 `environments/prod/images`를 읽어 자동 동기화한다(배포 승인).",
        "",
        f"- 원본 main SHA: `{commit}` (이미지 태그 `main-{commit[:12]}`)",
        f"- PR 기준 main HEAD: `{base_sha or '-'}`",
        f"- cd-release 실행: {run_url or '-'}",
        f"- 사유: {record.get('reason') or '-'}",
        f"- 버전: {record.get('currentRelease')} → {record.get('targetRelease')}",
        "",
        "| 서비스 | release 파일 | 앱 digest (전 → 후) | migration digest (전 → 후) | migration revision |",
        "|---|---|---|---|---|",
    ]
    for c in changes:
        b, a = c["before"], c["after"]
        migration = f"`{_short(b['migration'])}` → `{_short(a['migration'])}`" if "migration" in a else "-"
        revision = f"{b['revision']} → {a['revision']}" if "revision" in a else "-"
        lines.append(
            f"| {c['service']} | `{c['file']}` | `{_short(b['image'])}` → `{_short(a['image'])}` | {migration} | {revision} |"
        )
    moved = sorted(
        {f"`{c['before'][k]}` → `{c['after'][k]}`" for c in changes for k in ("repository", "migrationRepository") if k in c["after"]}
    )
    if moved:
        lines += ["", "**저장소 변경(계정 전환)**: 아래 저장소로 바꾼다. 계정 값 교체(#809 6a)와 같은 계정인지 확인하고 승인한다.", ""]
        lines += [f"- {m}" for m in moved]
    compatibility = record.get("compatibility") or {}
    lines += ["", "### 호환성 근거 (계획)", "", "| 항목 | 상태 | 근거 |", "|---|---|---|"]
    for name in CHECKS:
        item = compatibility.get(name) or {}
        evidence = str(item.get("evidence") or "").replace("|", "\\|").replace("\n", " ")
        lines.append(f"| {name} | {item.get('status')} | {evidence} |")
    plan = {k: record.get(k) for k in ("environment", "operation", "sourceCommit", "sourceBranch",
                                         "services", "currentRelease", "targetRelease", "reason",
                                         "databaseAction", "images", "migrations")}
    lines += [
        "",
        "<details><summary>계획 기록 JSON</summary>",
        "",
        "```json",
        json.dumps(plan | {"planSha256": record.get("planSha256")}, ensure_ascii=False, indent=2),
        "```",
        "",
        "</details>",
        "",
        "### 승인·확인",
        "",
        "- 승인: CODEOWNERS(김동섭·김태윤) 중 이 PR을 연 사람과 다른 1명. 이 PR은 `images/**`만 바꾼다(브랜치 규칙 예외, `docs/README.md`)",
        "- migration: core·learning·report-api는 Argo CD PreSync Job이 앱보다 먼저 실행한다. DB는 되돌리지 않는다",
        "- 병합 뒤: Argo CD Synced/Healthy(Discord 알림) → 작업자 PC에서 `python scripts/verify_cd_deployment.py` 결과를 이 PR 댓글로 남긴다(절차: `infrastructure/cd/README.md` digest PR 배포 절)",
        "",
        "### 되돌리기",
        "",
        "- 이 PR을 GitHub에서 Revert → 같은 승인 규칙으로 병합. Argo CD UI rollback은 쓰지 않는다(Git과 어긋남)",
        "- revert는 앱 이미지와 migration 값만 되돌리고 DB는 그대로다. 이전 앱이 새 스키마에서 동작한다는 근거(위 schema)가 있어야 한다",
    ]
    return "\n".join(lines) + "\n"


def git_ancestor(commit, ref):
    """commit이 ref 이력에 있으면 True. git 실패는 확인 불가(False)로 본다."""
    run = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, ref],
        capture_output=True,
        check=False,
    )
    return run.returncode == 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--images",
        type=Path,
        help="publish가 만든 서비스별 이미지 JSON (plan.images 대체)",
    )
    parser.add_argument(
        "--migrations",
        type=Path,
        help="publish가 만든 서비스별 migration 이미지 JSON (plan.migrations 대체)",
    )
    parser.add_argument(
        "--expect-commit", help="실행 중인 SHA. deploy 계획의 sourceCommit과 같아야 함"
    )
    parser.add_argument(
        "--require-ancestor-of", help="sourceCommit이 이력에 있어야 하는 Git ref"
    )
    parser.add_argument(
        "--pending-images", action="store_true", help="배포 이미지 빌드 전 검증"
    )
    parser.add_argument(
        "--require-executable",
        action="store_true",
        help="executable이 아니면 종료 코드 3 (배포 직전 게이트)",
    )
    parser.add_argument(
        "--check-images",
        action="store_true",
        help="digest PR 대상 images 파일 구조를 확인 (#858, 이미지 빌드 전)",
    )
    parser.add_argument(
        "--write-images",
        action="store_true",
        help="실행 가능한 deploy 계획이면 images 파일을 새 digest로 고친다 (#858 digest PR)",
    )
    parser.add_argument(
        "--allow-repository-change",
        action="store_true",
        help="images 파일 저장소 주소도 게시한 저장소로 바꾼다(계정 전환 첫 digest PR, 서비스 전부일 때만)",
    )
    parser.add_argument("--repo-root", type=Path, default=Path("."), help="images 파일 기준 폴더")
    parser.add_argument("--pr-body", type=Path, help="--write-images 때 PR 본문 Markdown 출력")
    parser.add_argument("--run-url", default="", help="PR 본문에 남길 cd-release 실행 URL")
    parser.add_argument("--base-sha", default="", help="PR 기준 main HEAD SHA")
    args = parser.parse_args()
    if args.write_images and not args.require_executable:
        parser.error("--write-images는 --require-executable과 함께 씁니다")
    inputs = {args.plan.resolve(), args.policy.resolve()}
    for extra in (args.images, args.migrations):
        if extra:
            inputs.add(extra.resolve())
    if args.output.resolve() in inputs:
        parser.error("출력 파일은 입력 파일과 달라야 합니다")
    raw, policy_raw, plan, policy = b"", b"", {}, {}
    try:
        raw = args.plan.read_bytes()
        policy_raw = args.policy.read_bytes()
        plan = json.loads(raw)
        policy = json.loads(policy_raw)
        if args.images and isinstance(plan, dict):
            plan["images"] = json.loads(args.images.read_bytes())
        if args.migrations and isinstance(plan, dict):
            plan["migrations"] = json.loads(args.migrations.read_bytes())
        result = validate(plan, policy, pending_images=args.pending_images)
        commit = plan.get("sourceCommit") if isinstance(plan, dict) else None
        # 배포는 지금 실행 중인 main SHA만. 롤백은 이전 릴리스 digest를 현재 chart로 되돌린다
        if (
            args.expect_commit
            and isinstance(plan, dict)
            and plan.get("operation") == "deploy"
            and commit != args.expect_commit
        ):
            result["errors"].append("계획의 sourceCommit이 실행 중인 커밋과 다릅니다")
        if args.require_ancestor_of and not (
            isinstance(commit, str)
            and re.fullmatch(r"[0-9a-f]{40}", commit)
            and git_ancestor(commit, args.require_ancestor_of)
        ):
            result["errors"].append(
                f"sourceCommit이 {args.require_ancestor_of} 이력에 없거나 확인할 수 없습니다"
            )
        if args.check_images or args.write_images:
            if isinstance(plan, dict) and plan.get("operation") != "deploy":
                result["errors"].append(
                    "digest PR 방식은 deploy만 받습니다. 되돌리기는 digest PR revert(비상용 Helm은 rollback 계획)"
                )
            else:
                result["errors"].extend(check_images_files(policy, args.repo_root))
        result["valid"] = not result["errors"]
        result["executable"] = result["valid"] and not result["blocks"]
    except (OSError, ValueError, UnicodeError) as exc:
        result = {
            "valid": False,
            "executable": False,
            "errors": [f"입력 파일 읽기/JSON 형식 오류: {type(exc).__name__}"],
            "blocks": ["입력 오류"],
        }
    if not isinstance(plan, dict):
        plan = {}
    record = {
        "mode": "plan-validation",
        "recordedAt": datetime.now(UTC).isoformat(),
        "planSha256": hashlib.sha256(raw).hexdigest(),
        "policySha256": hashlib.sha256(policy_raw).hexdigest(),
        "environment": plan.get("environment"),
        "operation": plan.get("operation"),
        "sourceCommit": plan.get("sourceCommit"),
        "sourceBranch": plan.get("sourceBranch"),
        "currentRelease": plan.get("currentRelease"),
        "targetRelease": plan.get("targetRelease"),
        "reason": plan.get("reason"),
        "databaseAction": plan.get("databaseAction"),
        "compatibility": plan.get("compatibility"),
        # 실행기는 이 값이 true일 때만 release가 없는 앱을 helm install로 올린다
        "firstInstall": plan.get("currentRelease") == FIRST_INSTALL,
        "services": plan.get("services"),
        "images": plan.get("images"),
        "migrations": plan.get("migrations"),
        **result,
    }
    changes = []
    if args.write_images and result["executable"]:
        # 게이트를 통과한 계획만 파일을 고친다. 하나라도 맞지 않으면 아무 파일도 쓰지 않는다
        changes, change_errors = image_file_updates(
            record, policy, args.repo_root, allow_repository_change=args.allow_repository_change
        )
        if change_errors:
            changes = []
            result["errors"].extend(change_errors)
            result["valid"] = record["valid"] = False
            result["executable"] = record["executable"] = False
        record["imageFileChanges"] = [
            {k: c[k] for k in ("service", "release", "file", "before", "after")} for c in changes
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    for change in changes:
        (args.repo_root / change["file"]).write_text(change["content"], encoding="utf-8", newline="\n")
    if changes and args.pr_body:
        args.pr_body.parent.mkdir(parents=True, exist_ok=True)
        args.pr_body.write_text(
            render_pr_body(record, changes, run_url=args.run_url, base_sha=args.base_sha),
            encoding="utf-8",
        )
    print(json.dumps(result, ensure_ascii=False))
    if not result["valid"]:
        return 2
    return 3 if args.require_executable and not result["executable"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
