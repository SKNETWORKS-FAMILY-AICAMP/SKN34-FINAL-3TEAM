"""#186 배포 이력 기록: 수행자·승인·시점·버전·결과를 한 파일로 남긴다 (NFR-OPS-02·03).

승인자는 계획 파일이 아니라 GitHub Actions 승인 기록 API에서 읽는다. 토큰·응답 원문·Secret은
기록하지 않는다. 기록은 Actions artifact(90일)와 실행 요약에 남기며 Git에 커밋하지 않는다.
"""

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen


def read_json(path):
    if not path or not Path(path).is_file():
        return None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def approvals(repo, run_id, token, opener=urlopen):
    """GitHub Environment 승인 기록. 조회 실패는 빈 목록이 아니라 None(확인 불가)으로 남긴다."""
    if not (repo and run_id and token):
        return None
    request = Request(
        f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/approvals",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    try:
        with opener(request, timeout=30) as response:
            items = json.loads(response.read())
    except (URLError, ValueError, OSError):
        return None
    return [
        {
            "user": (item.get("user") or {}).get("login"),
            "state": item.get("state"),
            "environments": [env.get("name") for env in item.get("environments") or []],
            "comment": bool(item.get("comment")),
        }
        for item in items
        if isinstance(item, dict)
    ]


def build(plan_record, releases, smoke, env, approved_by):
    deployed = bool(releases) and all(
        item.get("status") == "deployed" for item in releases
    )
    smoke_ok = bool(smoke and smoke.get("ok"))
    return {
        "recordedAt": datetime.now(UTC).isoformat(),
        "environment": (plan_record or {}).get("environment"),
        "operation": (plan_record or {}).get("operation"),
        "sourceCommit": (plan_record or {}).get("sourceCommit"),
        "targetRelease": (plan_record or {}).get("targetRelease"),
        "planSha256": (plan_record or {}).get("planSha256"),
        "policySha256": (plan_record or {}).get("policySha256"),
        "images": (plan_record or {}).get("images"),
        "actor": env.get("GITHUB_ACTOR"),
        "run": {
            "id": env.get("GITHUB_RUN_ID"),
            "attempt": env.get("GITHUB_RUN_ATTEMPT"),
            "url": (
                f"{env.get('GITHUB_SERVER_URL')}/{env.get('GITHUB_REPOSITORY')}/actions/runs/{env.get('GITHUB_RUN_ID')}"
                if env.get("GITHUB_RUN_ID")
                else None
            ),
        },
        "approvals": approved_by,
        "releases": releases or [],
        "smoke": smoke,
        # 자동 롤백은 하지 않는다. 실패하면 새 계획·승인으로 복구한다
        "result": "success" if deployed and smoke_ok else "failure",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--plan-record", required=True, type=Path)
    parser.add_argument(
        "--releases", type=Path, help="배포 단계가 남긴 release별 결과 JSON 목록"
    )
    parser.add_argument("--smoke", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    env = dict(os.environ)
    record = build(
        read_json(args.plan_record),
        read_json(args.releases),
        read_json(args.smoke),
        env,
        approvals(
            env.get("GITHUB_REPOSITORY"),
            env.get("GITHUB_RUN_ID"),
            env.get("GITHUB_TOKEN"),
        ),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {"result": record["result"], "approvals": record["approvals"]},
            ensure_ascii=False,
        )
    )
    return 0 if record["result"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())
