"""#186 배포 계획 검증. 네트워크·배포·DB 변경을 실행하지 않는다."""

import argparse
import hashlib
import json
import re
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


def validate(plan, policy):
    """검토 자료의 완전성과 실행 차단 사유를 분리한다. 선언은 승인 증명이 아니다."""
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
    if plan.get("currentRelease") == plan.get("targetRelease"):
        errors.append("현재 버전과 대상 버전이 같습니다")
    images = plan.get("images")
    if not isinstance(images, dict) or not images:
        errors.append("변경 서비스 이미지가 필요합니다")
    else:
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
    # 이 도구는 승인 게이트를 대신할 수 없다. 입력 파일의 approved=true도 신뢰하지 않는다.
    blocks.append("계획 검증 전용: 실제 GitHub 승인 및 배포 실행기 미연결")
    return {
        "valid": not errors,
        "executable": False,
        "errors": errors,
        "blocks": blocks,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True, type=Path)
    parser.add_argument("--policy", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    if args.output.resolve() in {args.plan.resolve(), args.policy.resolve()}:
        parser.error("출력 파일은 계획·정책 입력 파일과 달라야 합니다")
    raw, policy_raw, plan, policy = b"", b"", {}, {}
    try:
        raw = args.plan.read_bytes()
        policy_raw = args.policy.read_bytes()
        plan = json.loads(raw)
        policy = json.loads(policy_raw)
        result = validate(plan, policy)
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
        "mode": "local-plan-only",
        "recordedAt": datetime.now(UTC).isoformat(),
        "planSha256": hashlib.sha256(raw).hexdigest(),
        "policySha256": hashlib.sha256(policy_raw).hexdigest(),
        "environment": plan.get("environment"),
        "operation": plan.get("operation"),
        "sourceCommit": plan.get("sourceCommit"),
        "targetRelease": plan.get("targetRelease"),
        **result,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["valid"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
