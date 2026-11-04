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
            registry = (
                r"ghcr\.io/[a-z0-9._/-]+"
                if plan.get("environment") == "local"
                else r"[0-9]{12}\.dkr\.ecr\.[a-z0-9-]+\.amazonaws\.com/[a-z0-9._/-]+"
            )
            if not isinstance(image, str) or not re.fullmatch(
                registry + r"@sha256:[0-9a-f]{64}", image
            ):
                errors.append(
                    f"{service}: 환경에 맞는 레지스트리와 불변 digest가 필요합니다"
                )
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
    args = parser.parse_args()
    inputs = {args.plan.resolve(), args.policy.resolve()}
    if args.images:
        inputs.add(args.images.resolve())
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
        "targetRelease": plan.get("targetRelease"),
        "services": plan.get("services"),
        "images": plan.get("images"),
        **result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    if not result["valid"]:
        return 2
    return 3 if args.require_executable and not result["executable"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
