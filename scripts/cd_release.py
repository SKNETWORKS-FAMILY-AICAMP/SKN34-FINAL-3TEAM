"""#186 release planning, digest publication and audited GitOps changes.

No cluster writes or DB restore commands. All deployment changes are ordinary Git
commits made by cd-release.yml after its environment approval gate.
"""

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.request import Request, urlopen

import yaml

ROOT = Path(__file__).resolve().parents[1]
SERVICES = (
    "core-service",
    "learning-service",
    "ai-service",
    "scoring-service",
    "report-service",
)
APPS = dict(zip(SERVICES[:4], SERVICES[:4])) | {
    "report-api": "report-service",
    "report-worker": "report-service",
}
MIGRATIONS = {
    "core-service": "core-migrate",
    "learning-service": "learning-migrate",
    "report-api": "report-service",
}
CHECKS = {
    "database",
    "api",
    "events",
    "configuration",
    "inflight_learning",
    "inflight_payments",
}
APPROVER = "20220348-kim"  # 김동섭; user decision, 2026-11-01
APPROVER_ID = 201464527
SHA = re.compile(r"[0-9a-f]{40}")
DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
DEPLOYMENT_ID = re.compile(r"[0-9]+-1")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def now():
    return datetime.now(UTC)


def stamp():
    return now().isoformat()


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, encoding="utf-8"
    ).strip()


def paths(root, environment):
    require(environment in {"local", "prod"}, "Unknown environment")
    base = root / "infrastructure/gitops"
    return base / "environments" / environment, base / "deployments" / environment


def load_current(root, environment):
    values, history = paths(root, environment)
    state = values / "deployment.json"
    if not state.exists():
        return None
    pointer = read_json(state)
    return load_record(history, pointer["id"])


def load_record(history, deployment_id):
    require(bool(DEPLOYMENT_ID.fullmatch(deployment_id)), "Invalid deployment ID")
    record = read_json(history / f"{deployment_id}.json")
    require(record["id"] == deployment_id, "Deployment record ID mismatch")
    return record


def config_hash(root, environment):
    values, _ = paths(root, environment)
    files = [values / f"{app}.yaml" for app in APPS]
    appset = (
        root / f"infrastructure/gitops/argocd/{environment}/apps/applicationset.yaml"
    )
    files.append(appset)
    chart = root / "infrastructure/gitops/charts/app-service"
    require(chart.is_dir(), "Missing #171 application chart")
    files.extend(sorted(p for p in chart.rglob("*") if p.is_file()))
    digest = hashlib.sha256()
    for path in files:
        require(
            path.is_file() and not path.is_symlink(),
            f"Missing #171/#185 configuration: {path.relative_to(root)}",
        )
        digest.update(path.relative_to(root).as_posix().encode())
        digest.update(path.read_bytes())
    spec = yaml.safe_load(appset.read_text(encoding="utf-8"))["spec"]["template"][
        "spec"
    ]
    automated = spec.get("syncPolicy", {}).get("automated")
    require(
        isinstance(automated, dict) and automated.get("enabled") is not False,
        "ApplicationSet automatic sync is not enabled",
    )
    sources = spec.get("sources", [])
    require(
        len(sources) == 2
        and all(s.get("targetRevision") == "develop" for s in sources),
        "Both Argo sources must follow develop",
    )
    return digest.hexdigest()


def validate_review(review, environment, source, current_id, fingerprint, clock=None):
    clock = clock or now()
    require(review.get("environment") == environment, "Review environment mismatch")
    require(
        review.get("target_source_sha") == source,
        "Review does not cover the exact source SHA",
    )
    require(
        review.get("current_deployment") == current_id,
        "Review is stale: current deployment changed",
    )
    require(
        review.get("config_sha256") == fingerprint,
        "Review is stale: deployment configuration changed",
    )
    checked = datetime.fromisoformat(review["checked_at"])
    expires = datetime.fromisoformat(review["expires_at"])
    require(
        checked.tzinfo is not None and expires.tzinfo is not None,
        "Review timestamps require time zones",
    )
    require(
        checked <= clock < expires <= checked + timedelta(hours=24),
        "Review expired or validity exceeds 24 hours",
    )
    require(
        bool(review.get("reviewer")) and bool(review.get("reason")),
        "Reviewer and reason are required",
    )
    require(
        set(review.get("checks", {})) == CHECKS,
        "All compatibility and in-flight impact checks are required",
    )
    for name, check in review["checks"].items():
        require(
            check.get("status") == "compatible",
            f"Blocked: {name} is incompatible or unverified",
        )
        require(
            bool(check.get("summary", "").strip())
            and bool(check.get("evidence", "").strip()),
            f"Missing change analysis/evidence for {name}",
        )
    require(
        review.get("database_restore") is False,
        "Automatic database downgrade/restore is forbidden",
    )


def rollback_target(root, environment, current, target_id):
    require(
        current is not None,
        "Cannot roll back an environment with no deployment history",
    )
    _, history = paths(root, environment)
    ancestor = current.get("previous")
    seen = set()
    while ancestor and ancestor != target_id:
        require(ancestor not in seen, "Cyclic deployment history")
        seen.add(ancestor)
        ancestor = load_record(history, ancestor).get("previous")
    require(
        ancestor == target_id and ancestor is not None,
        "Target is not a previous deployment of this environment",
    )
    target = load_record(history, target_id)
    require(
        target["environment"] == environment and target["status"] == "success",
        "Rollback target was not successfully verified",
    )
    approval = target.get("approval", {})
    require(bool(approval.get("actor")), "Target has no approval/execution record")
    if environment == "prod":
        require(
            approval.get("approved_by") == APPROVER
            and approval.get("approver_id") == APPROVER_ID,
            "Target has no production approval by 김동섭",
        )
    return target


def changed_services(root, previous_source, source):
    if previous_source is None:
        return list(SERVICES)
    require(bool(SHA.fullmatch(previous_source)), "Invalid previous source SHA")
    changed = git(root, "diff", "--name-only", previous_source, source).splitlines()
    # Release history, review documents and generated image edits must not
    # force every image to rebuild on the next otherwise service-only release.
    relevant = []
    for path in changed:
        if path.startswith(
            ("infrastructure/gitops/deployments/", "infrastructure/gitops/reviews/")
        ):
            continue
        if path.startswith("infrastructure/gitops/environments/"):
            if path.endswith("/deployment.json"):
                continue
            if path.endswith(".yaml"):
                snapshots = []
                try:
                    for revision in (previous_source, source):
                        value = yaml.safe_load(git(root, "show", f"{revision}:{path}"))
                        value.pop("image", None)
                        if isinstance(value.get("migration"), dict):
                            for key in ("image", "revision", "enabled"):
                                value["migration"].pop(key, None)
                        snapshots.append(value)
                except (subprocess.CalledProcessError, AttributeError):
                    pass
                if len(snapshots) == 2 and snapshots[0] == snapshots[1]:
                    continue
        relevant.append(path)
    changed = relevant
    broad = ("contracts/", "scripts/", ".github/workflows/", "infrastructure/")
    if any(p.startswith(broad) for p in changed):
        return list(SERVICES)
    return [
        service
        for service in SERVICES
        if any(p.startswith(f"backend/{service}/") for p in changed)
    ]


def plan(root, environment, operation, source, target_id, review_path, deployment_id):
    require(
        bool(DEPLOYMENT_ID.fullmatch(deployment_id)),
        "Use a new workflow run; reruns are not deployment approvals",
    )
    require(operation in {"deploy", "rollback"}, "Unknown operation")
    current = load_current(root, environment)
    fingerprint = config_hash(root, environment)
    target = (
        rollback_target(root, environment, current, target_id)
        if operation == "rollback"
        else None
    )
    if target:
        source = target["source_sha"]
    require(bool(SHA.fullmatch(source)), "Source must be a full immutable Git SHA")
    require(
        git(root, "rev-parse", f"{source}^{{commit}}") == source,
        "Source is not a commit",
    )
    subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", source, "HEAD"],
        check=True,
    )
    if current and operation == "deploy":
        subprocess.run(
            [
                "git",
                "-C",
                str(root),
                "merge-base",
                "--is-ancestor",
                current["source_sha"],
                source,
            ],
            check=True,
        )
    review_file = (root / review_path).resolve()
    review_root = (root / f"infrastructure/gitops/reviews/{environment}").resolve()
    require(
        review_file.is_relative_to(review_root) and review_file.suffix == ".json",
        "Review must be committed under the environment review directory",
    )
    relative = review_file.relative_to(root).as_posix()
    # Read the committed version, not an untracked or locally edited assertion.
    review = json.loads(git(root, "show", f"HEAD:{relative}"))
    current_id = current["id"] if current else None
    validate_review(review, environment, source, current_id, fingerprint)
    require(
        review.get("rollback_target") == (target_id if target else None),
        "Review rollback target mismatch",
    )
    selected = (
        []
        if target
        else changed_services(
            root,
            current["source_sha"]
            if current and current["status"] == "success"
            else None,
            source,
        )
    )
    images = copy.deepcopy((target or current or {}).get("images", {}))
    return {
        "id": deployment_id,
        "environment": environment,
        "operation": operation,
        "source_sha": source,
        "control_sha": git(root, "rev-parse", "HEAD"),
        "previous": current_id,
        "rollback_target": target_id if target else None,
        "config_sha256": fingerprint,
        "review": review,
        "review_path": relative,
        "services": selected,
        "images": images,
        "created_at": stamp(),
        "recovery_baseline": current.get("impact_before")
        if current and target
        else None,
    }


def approval_from_reviews(reviews, environment, actor, run_id):
    result = {
        "actor": actor,
        "run_id": run_id,
        "checked_at": stamp(),
        "approved_by": None,
    }
    if environment == "prod":
        matching = [
            r
            for r in reviews
            if any(e.get("name") == "prod" for e in r.get("environments", []))
        ]
        require(
            matching and not any(r.get("state") == "rejected" for r in matching),
            "Production approval absent or rejected",
        )
        valid = [
            r
            for r in matching
            if r.get("state") == "approved"
            and r.get("user", {}).get("login") == APPROVER
            and r["user"].get("id") == APPROVER_ID
        ]
        require(
            bool(valid),
            "Production requires 김동섭's actual GitHub Environment approval",
        )
        result.update(approved_by=APPROVER, approver_id=APPROVER_ID)
    return result


def validate_approval(approval, release):
    require(
        str(approval.get("run_id")) == release["id"].removesuffix("-1"),
        "Approval belongs to a different workflow run",
    )
    require(bool(approval.get("actor")), "Execution actor missing")
    if release["environment"] == "prod":
        require(
            approval.get("approved_by") == APPROVER
            and approval.get("approver_id") == APPROVER_ID,
            "Production approver mismatch",
        )


def validate_images(images, environment):
    require(
        set(images) == set(SERVICES) | {"core-migrate", "learning-migrate"},
        "Release must contain all service and migration images",
    )
    for item in images.values():
        require(
            bool(DIGEST.fullmatch(item.get("digest", ""))),
            "Images must use an immutable digest",
        )
        repository = item.get("repository", "")
        pattern = (
            r"ghcr\.io/[a-z0-9._/-]+"
            if environment == "local"
            else r"[0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com/[a-z0-9._/-]+"
        )
        require(
            bool(re.fullmatch(pattern, repository)),
            "Registry does not match environment",
        )


def publish(release, source_root, prefix, output):
    require(
        git(source_root, "rev-parse", "HEAD") == release["source_sha"],
        "Build checkout differs from reviewed source",
    )
    require(
        not git(source_root, "status", "--porcelain", "--untracked-files=no"),
        "Build source contains local changes",
    )
    # Validate the registry before passing any argument to Docker.
    example = {
        k: {"repository": f"{prefix}/{k}", "digest": "sha256:" + "0" * 64}
        for k in set(SERVICES) | {"core-migrate", "learning-migrate"}
    }
    validate_images(example, release["environment"])
    for service in release["services"]:
        builds = [
            (
                service,
                source_root / "backend" / service,
                source_root / "backend" / service / "Dockerfile",
            )
        ]
        if service in {"core-service", "learning-service"}:
            name = service.replace("-service", "-migrate")
            builds.append(
                (
                    name,
                    source_root,
                    source_root
                    / f"infrastructure/gitops/migrations/{service.split('-')[0]}.Dockerfile",
                )
            )
        for name, context, dockerfile in builds:
            require(dockerfile.is_file(), f"Missing Dockerfile: {dockerfile}")
            metadata = output / f"{name}.json"
            subprocess.run(
                [
                    "docker",
                    "buildx",
                    "build",
                    "--platform",
                    "linux/amd64",
                    "--push",
                    "--file",
                    str(dockerfile),
                    "--tag",
                    f"{prefix}/{name}:{release['source_sha']}",
                    "--metadata-file",
                    str(metadata),
                    "--label",
                    f"org.opencontainers.image.revision={release['source_sha']}",
                    str(context),
                ],
                check=True,
            )
            digest = read_json(metadata).get("containerimage.digest", "")
            require(
                bool(DIGEST.fullmatch(digest)),
                f"No published digest returned for {name}",
            )
            release["images"][name] = {
                "repository": f"{prefix}/{name}",
                "tag": release["source_sha"],
                "digest": digest,
            }
    validate_images(release["images"], release["environment"])
    return release


def migration_revision(source_root, app, image_digest):
    folder = source_root / (
        "backend/report-service/migrations/versions"
        if app == "report-api"
        else f"backend/{app}/src/main/resources/db/migration"
    )
    files = sorted(
        p for p in folder.rglob("*") if p.is_file() and p.suffix in {".sql", ".py"}
    )
    require(bool(files), f"Migration files absent: {app}")
    digest = hashlib.sha256()
    # A completed Job has an immutable pod template. A different migration
    # image must use a new Job name even when its migration files are unchanged.
    digest.update(image_digest.encode())
    for path in files:
        digest.update(path.relative_to(folder).as_posix().encode())
        digest.update(path.read_bytes())
    return "r" + digest.hexdigest()[:16]


def apply_release(root, source_root, release, approval, baseline):
    environment = release["environment"]
    validate_approval(approval, release)
    validate_images(release["images"], environment)
    require(
        git(root, "rev-parse", "HEAD") == release["control_sha"],
        "GitOps branch advanced; create a fresh reviewed plan",
    )
    fingerprint = config_hash(root, environment)
    current = load_current(root, environment)
    current_id = current["id"] if current else None
    validate_review(
        release["review"], environment, release["source_sha"], current_id, fingerprint
    )
    if release["operation"] == "rollback":
        target = rollback_target(root, environment, current, release["rollback_target"])
        require(
            target["images"] == release["images"],
            "Rollback image set differs from approved history",
        )
    else:
        require(
            git(source_root, "rev-parse", "HEAD") == release["source_sha"],
            "Migration checkout mismatch",
        )
    values, history = paths(root, environment)
    require(
        not (history / f"{release['id']}.json").exists(), "Deployment ID already used"
    )
    updates = {}
    for app, service in APPS.items():
        path = values / f"{app}.yaml"
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        value["image"].update(release["images"][service], pullPolicy="IfNotPresent")
        if app in MIGRATIONS:
            if release["operation"] == "rollback":
                # Keep the current schema revision and migration image; never run old migrations.
                value["migration"]["enabled"] = False
            else:
                value["migration"]["enabled"] = True
                value["migration"]["revision"] = migration_revision(
                    source_root, app, release["images"][MIGRATIONS[app]]["digest"]
                )
                value["migration"]["image"].update(
                    release["images"][MIGRATIONS[app]], pullPolicy="IfNotPresent"
                )
        updates[path] = value
    record = copy.deepcopy(release)
    record.update(
        approval=approval,
        status="pending",
        started_at=stamp(),
        impact_before=baseline,
        run_url=os.environ.get("CD_RUN_URL", ""),
    )
    # All validation happens before any file is rewritten.
    for path, value in updates.items():
        path.write_text(
            yaml.safe_dump(value, sort_keys=False, allow_unicode=True), encoding="utf-8"
        )
    write_json(history / f"{release['id']}.json", record)
    write_json(values / "deployment.json", {"id": release["id"]})
    return record


def finish(root, release, verification, gitops_commit):
    values, history = paths(root, release["environment"])
    require(
        read_json(values / "deployment.json")["id"] == release["id"],
        "A newer deployment started; do not overwrite its result",
    )
    record = load_record(history, release["id"])
    require(record["status"] == "pending", "Deployment has already been finalized")
    require(
        verification.get("deployment_id") == release["id"]
        and verification.get("gitops_commit") == gitops_commit,
        "Verification does not belong to this deployment commit",
    )
    checks = verification.get("checks", {})
    passed = verification.get("status") == "success" and all(
        checks.get(k) is True
        for k in (
            "argo_sync",
            "login",
            "learning_submission",
            "report_query",
            "inflight_learning",
            "inflight_payments",
        )
    )
    record.update(
        status="success" if passed else "failed",
        completed_at=stamp(),
        gitops_commit=gitops_commit,
        verification=verification,
    )
    write_json(history / f"{release['id']}.json", record)
    return passed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command", choices=["inspect", "plan", "approve", "publish", "apply", "finish"]
    )
    parser.add_argument("--environment", choices=["local", "prod"], default="local")
    parser.add_argument("--operation", choices=["deploy", "rollback"], default="deploy")
    parser.add_argument("--source-sha", default="")
    parser.add_argument("--target-deployment", default="")
    parser.add_argument("--review", default="")
    parser.add_argument("--deployment-id", default="")
    parser.add_argument("--source-dir", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "local_data/cd")
    parser.add_argument("--gitops-commit", default="")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    release_file = args.output / "release.json"
    if args.command == "inspect":
        current = load_current(ROOT, args.environment)
        print(
            json.dumps(
                {
                    "current_deployment": current["id"] if current else None,
                    "config_sha256": config_hash(ROOT, args.environment),
                },
                indent=2,
            )
        )
    elif args.command == "plan":
        release = plan(
            ROOT,
            args.environment,
            args.operation,
            args.source_sha,
            args.target_deployment,
            args.review,
            args.deployment_id,
        )
        write_json(release_file, release)
        outputs = {
            "source": release["source_sha"],
            "spring": json.dumps([s for s in release["services"] if s in SERVICES[:2]]),
            "python": json.dumps([s for s in release["services"] if s in SERVICES[2:]]),
        }
        if os.environ.get("GITHUB_OUTPUT"):
            with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as out:
                out.writelines(f"{key}={value}\n" for key, value in outputs.items())
        print(
            json.dumps(
                {
                    k: release[k]
                    for k in (
                        "id",
                        "environment",
                        "operation",
                        "source_sha",
                        "previous",
                        "services",
                    )
                },
                indent=2,
            )
        )
    elif args.command == "approve":
        require(
            os.environ.get("GITHUB_RUN_ATTEMPT") == "1",
            "Use a fresh workflow dispatch for each approval",
        )
        release = read_json(release_file)
        reviews = []
        if release["environment"] == "prod":
            url = f"https://api.github.com/repos/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}/approvals"
            request = Request(
                url,
                headers={
                    "Authorization": "Bearer " + os.environ["GH_TOKEN"],
                    "Accept": "application/vnd.github+json",
                },
            )
            with urlopen(request, timeout=30) as response:
                reviews = json.load(response)
        write_json(
            args.output / "approval.json",
            approval_from_reviews(
                reviews,
                release["environment"],
                os.environ["GITHUB_ACTOR"],
                os.environ["GITHUB_RUN_ID"],
            ),
        )
    elif args.command == "publish":
        release = read_json(release_file)
        validate_approval(read_json(args.output / "approval.json"), release)
        write_json(
            release_file,
            publish(
                release, args.source_dir, os.environ["CD_IMAGE_PREFIX"], args.output
            ),
        )
    elif args.command == "apply":
        apply_release(
            ROOT,
            args.source_dir,
            read_json(release_file),
            read_json(args.output / "approval.json"),
            read_json(args.output / "baseline.json"),
        )
    else:
        release = read_json(release_file)
        verification_file = args.output / "verification.json"
        verification = (
            read_json(verification_file)
            if verification_file.exists()
            else {
                "deployment_id": release["id"],
                "gitops_commit": args.gitops_commit,
                "status": "failed",
                "checks": {},
                "reason": "Verification did not produce a complete result",
            }
        )
        passed = finish(ROOT, release, verification, args.gitops_commit)
        print(
            "Verification passed"
            if passed
            else "Verification failed; deployment requires investigation or an approved rollback"
        )


if __name__ == "__main__":
    try:
        main()
    except (
        ValueError,
        KeyError,
        TypeError,
        OSError,
        subprocess.CalledProcessError,
    ) as exc:
        print(f"CD blocked: {type(exc).__name__}: {exc}", file=sys.stderr)
        sys.exit(1)
