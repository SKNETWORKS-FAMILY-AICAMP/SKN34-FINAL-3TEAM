"""Check the deployed revision and real public API flows using dedicated demo fixtures.

Credentials and response bodies are never written to the result artifact. This
script does not create accounts, charge/refund payments, or delete test records.
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from uuid import NAMESPACE_URL, UUID, uuid5

from cd_release import APPS, now, read_json, require, stamp, write_json


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward credentials to an authentication/other host.


def origin(value, environment):
    parts = urlsplit(value)
    require(
        parts.scheme in {"https", "http"}
        and parts.hostname
        and not parts.username
        and not parts.password,
        "Invalid service origin",
    )
    require(
        parts.path in {"", "/"} and not parts.query and not parts.fragment,
        "Configure an origin without path/query",
    )
    require(
        environment != "prod" or parts.scheme == "https",
        "Production endpoints require HTTPS",
    )
    return value.rstrip("/")


def http_json(
    base, path, *, token=None, headers=None, body=None, allowed=(200,), timeout=30
):
    require(
        path.startswith("/") and not path.startswith("//"), "Invalid relative API path"
    )
    request_headers = {"Accept": "application/json", **(headers or {})}
    if token:
        request_headers["Authorization"] = f"Bearer {token}"
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode()
        request_headers["Content-Type"] = "application/json"
    request = Request(base + path, data=data, headers=request_headers)
    try:
        with build_opener(NoRedirect()).open(request, timeout=timeout) as response:
            require(response.status in allowed, "Unexpected HTTP status")
            require(
                "application/json" in response.headers.get("Content-Type", ""),
                "Expected JSON, not an HTML login page",
            )
            payload = response.read(4 * 1024 * 1024 + 1)
            require(
                len(payload) <= 4 * 1024 * 1024,
                "API response exceeds verification limit",
            )
            return json.loads(payload)
    except HTTPError as exc:
        # No response bodies, cookies, URLs with IDs or server exception strings in logs.
        raise ValueError(f"HTTP check failed with status {exc.code}") from None


def fixture():
    data = json.loads(os.environ["CD_SMOKE_FIXTURE"])
    require(
        data.get("dedicated_demo_fixture") is True
        and data.get("allow_answer_submission") is True,
        "A dedicated demo fixture explicitly allowing answer writes is required",
    )
    for field in ("child_id", "mission_id", "report_id", "inflight_attempt_id"):
        UUID(data[field])
    for field in (
        "student_pin",
        "student_device_cookie",
        "parent_access_token",
        "payment_order_id",
    ):
        require(
            isinstance(data[field], str)
            and bool(data[field])
            and "\n" not in data[field]
            and "\r" not in data[field],
            "Invalid fixture credential or identifier",
        )
    require(
        isinstance(data.get("answer"), dict) and data["answer"].get("inputType"),
        "Answer must match a published demo mission",
    )
    require(
        isinstance(data.get("allowed_payment_states"), list)
        and data["allowed_payment_states"],
        "Reviewed payment state transitions are required",
    )
    return data


def login(base, data):
    session = http_json(
        base,
        "/api/v1/auth/student/login",
        headers={
            "Cookie": "student_device=" + data["student_device_cookie"],
            "Origin": base,
            "X-Requested-With": "XMLHttpRequest",
        },
        body={"childId": data["child_id"], "pin": data["student_pin"]},
    )
    require(
        session.get("role") == "STUDENT"
        and session.get("child", {}).get("childId") == data["child_id"],
        "Login returned a different identity/role",
    )
    require(bool(session.get("accessToken")), "Login did not return an access token")
    return session["accessToken"]


def impact_snapshot(base, data, token):
    attempt = http_json(
        base, "/api/v1/attempts/" + data["inflight_attempt_id"], token=token
    )
    payment = http_json(
        base,
        "/api/v1/payments/" + quote(data["payment_order_id"], safe=""),
        token=data["parent_access_token"],
    )
    require(
        attempt.get("attemptId") == data["inflight_attempt_id"],
        "Existing learning attempt unavailable",
    )
    require(
        payment.get("orderId") == data["payment_order_id"]
        and payment.get("childId") == data["child_id"],
        "Existing payment unavailable or owner changed",
    )
    # Store hashes and status only; never student content, IDs, tokens or payment keys.
    items = attempt.get("answers")
    require(
        isinstance(items, list) and bool(items),
        "Impact fixture must contain a previously submitted answer",
    )
    answers = []
    for item in items:
        require(
            bool(item.get("answerId")) and isinstance(item.get("version"), int),
            "Malformed persisted answer",
        )
        answers.append(
            {
                key: item.get(key)
                for key in (
                    "answerId",
                    "version",
                    "inputType",
                    "text",
                    "content",
                    "submittedAt",
                )
            }
        )
    require(
        type(payment.get("amount")) is int and payment["amount"] >= 0,
        "Invalid payment amount",
    )
    return {
        "fixture_hash": fixture_hash(base, data),
        "attempt_status": attempt.get("status"),
        "answers": [
            hashlib.sha256(json.dumps(a, sort_keys=True).encode()).hexdigest()
            for a in answers
        ],
        "payment_status": payment.get("status"),
        "payment_amount": payment.get("amount"),
        "checked_at": stamp(),
    }


def fixture_hash(base, data):
    return hashlib.sha256(
        json.dumps(
            [
                base,
                data["child_id"],
                data["inflight_attempt_id"],
                data["payment_order_id"],
            ]
        ).encode()
    ).hexdigest()


def recovery_baseline(release, base, data):
    previous = release.get("recovery_baseline")
    require(
        release["operation"] == "rollback" and isinstance(previous, dict),
        "No measured baseline for failed-service recovery",
    )
    require(
        previous.get("fixture_hash") == fixture_hash(base, data),
        "Recovery fixture differs from the original rollout",
    )
    measured = datetime.fromisoformat(previous["checked_at"])
    require(
        measured.tzinfo is not None
        and now() - timedelta(hours=24) <= measured <= now(),
        "Recovery baseline is expired",
    )
    return previous


def compare_impact(before, after, data):
    require(
        before.get("fixture_hash") == after.get("fixture_hash"),
        "Impact fixtures changed",
    )
    require(
        before["attempt_status"] == "IN_PROGRESS",
        "Baseline must include an in-progress learning attempt",
    )
    require(
        after["attempt_status"] in {"IN_PROGRESS", "COMPLETED"},
        "Learning attempt lost its valid state",
    )
    require(
        set(before["answers"]) <= set(after["answers"]),
        "Existing submitted learning answers disappeared",
    )
    require(
        before["payment_status"] == "PENDING",
        "Baseline must include an unsettled test payment",
    )
    require(
        after["payment_status"] in data["allowed_payment_states"],
        "Payment changed outside reviewed transitions",
    )
    require(
        before["payment_amount"] == after["payment_amount"],
        "Payment amount changed during deployment",
    )


def argo_ready(app, commit):
    status = app.get("status", {})
    revisions = status.get("sync", {}).get("revisions", [])
    return (
        status.get("sync", {}).get("status") == "Synced"
        and status.get("health", {}).get("status") == "Healthy"
        and len(revisions) == 2
        and all(rev == commit for rev in revisions)
    )


def wait_argo(environment, commit, deadline_seconds=900):
    server = origin(os.environ["ARGOCD_SERVER"], environment)
    token = os.environ["ARGOCD_TOKEN"]
    deadline = time.monotonic() + deadline_seconds
    pending = set(APPS)
    while pending and time.monotonic() < deadline:
        pending = {
            app
            for app in APPS
            if not argo_ready(
                http_json(
                    server,
                    f"/api/v1/applications/{environment}-{app}?refresh=normal",
                    token=token,
                ),
                commit,
            )
        }
        if pending:
            time.sleep(10)
    require(
        not pending,
        "Argo CD did not become healthy at the exact GitOps commit: "
        + ", ".join(sorted(pending)),
    )


def verify(base, data, token, deployment_id):
    attempt = http_json(
        base,
        "/api/v1/missions/" + data["mission_id"] + "/attempts",
        token=token,
        body={},
        allowed=(200, 201),
    )
    attempt_id = str(UUID(attempt["attemptId"]))
    require(
        attempt_id != data["inflight_attempt_id"],
        "Submission fixture must differ from the in-flight impact fixture",
    )
    answer = http_json(
        base,
        f"/api/v1/attempts/{attempt_id}/answers",
        token=token,
        headers={"Idempotency-Key": str(uuid5(NAMESPACE_URL, "cd:" + deployment_id))},
        body=data["answer"],
        allowed=(201,),
        timeout=120,
    )
    require(
        answer.get("attemptId") == attempt_id and bool(answer.get("answerId")),
        "Answer submission was not persisted",
    )
    saved = http_json(base, f"/api/v1/attempts/{attempt_id}", token=token)
    require(
        any(a.get("answerId") == answer["answerId"] for a in saved.get("answers", [])),
        "Submitted answer not present on subsequent read",
    )
    report = http_json(
        base, "/api/v1/reports/" + data["report_id"], token=data["parent_access_token"]
    )
    require(
        report.get("reportId") == data["report_id"]
        and report.get("childId") == data["child_id"]
        and report.get("status") == "COMPLETED",
        "Report content/ownership mismatch",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["baseline", "verify"])
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--gitops-commit", default="")
    args = parser.parse_args()
    release = read_json(args.output / "release.json")
    data = fixture()
    base = origin(os.environ["CD_BASE_URL"], release["environment"])
    if args.command == "baseline":
        try:
            result = impact_snapshot(base, data, login(base, data))
        except (ValueError, OSError, KeyError):
            # Broken login/API must not make an approved recovery impossible.
            # Reuse only a recent measured baseline from the failed rollout, tied to the same fixtures.
            result = recovery_baseline(release, base, data)
        # A first deployment also requires previously prepared demo fixtures. Do not invent evidence.
        compare_impact(result, result, data)
        write_json(args.output / "baseline.json", result)
        return
    verification = {
        "deployment_id": release["id"],
        "gitops_commit": args.gitops_commit,
        "started_at": stamp(),
        "status": "failed",
        "checks": {},
    }
    try:
        wait_argo(release["environment"], args.gitops_commit)
        verification["checks"]["argo_sync"] = True
        token = login(base, data)
        verification["checks"]["login"] = True
        after = impact_snapshot(base, data, token)
        compare_impact(read_json(args.output / "baseline.json"), after, data)
        verification["checks"].update(inflight_learning=True, inflight_payments=True)
        verification["impact_after"] = after
        verify(base, data, token, release["id"])
        verification["checks"].update(learning_submission=True, report_query=True)
        verification["status"] = "success"
    finally:
        verification["completed_at"] = stamp()
        write_json(args.output / "verification.json", verification)


if __name__ == "__main__":
    try:
        main()
    except (ValueError, OSError, KeyError, TypeError) as exc:
        # Credentials/response bodies must never appear in an Actions log.
        print(
            f"Deployment verification failed ({type(exc).__name__}). See the check results and service logs.",
            file=sys.stderr,
        )
        sys.exit(1)
