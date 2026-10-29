"""#86 실제 core → RabbitMQ → scoring 2개 → MinIO 모델 교체 검증.

모델 파일은 외부 archive에서만 읽는다. 2.1-check는 교체 검증용 메타데이터이며
가중치는 같은 2.0 artifact를 재사용한다. 모델 품질·새 학습 버전 검증이 아니다.
"""

import argparse
import time
from pathlib import Path

import httpx
from verify_scoring_models import BUCKET, verify, wait


def check_events(run, url, core, access, headers, password, results, passed):
    endpoints = [url(name, 8001) for name in ("scoring", "scoring2")]
    rabbit = url("rabbitmq", 15672)
    name = "m2-klue-narrative"
    scope = "verification/" + name
    original = next(v for v in results["snapshot"]["items"] if v["name"] == name)

    def both(revision, release):
        for endpoint in endpoints:
            wait(
                endpoint + "/internal/versions",
                lambda r: (
                    r.status_code == 200
                    and any(
                        v == {"name": name, "version": release, "revision": revision}
                        for v in r.json()["items"]
                    )
                ),
                headers,
                seconds=300,
            )
            wait(endpoint + "/health/ready", lambda r: r.status_code == 200)

    def queues():
        response = httpx.get(rabbit + "/api/queues/%2F", auth=("verify", password))
        response.raise_for_status()
        return [q for q in response.json() if q["exclusive"] and q["auto_delete"]]

    def bound_queues():
        response = httpx.get(rabbit + "/api/bindings/%2F", auth=("verify", password))
        response.raise_for_status()
        return {
            b["destination"]
            for b in response.json()
            if b["source"] == "events.topic" and b["routing_key"] == "model.version.*"
        }

    both(1, "2.0")
    before = {q["name"] for q in queues()}
    assert len(before) == 2 and before <= bound_queues()
    results["exclusive_queues_before"] = sorted(before)
    passed(
        "two actual scoring replicas own separate exclusive auto-delete bound queues"
    )

    evidence = {
        key: "LOCAL transport test only; NOT quality approval"
        for key in (
            "datasetId",
            "datasetVersion",
            "baselineVersion",
            "comparisonReport",
            "trainingEvaluationSeparation",
            "quoteAccuracy",
            "calculationAccuracy",
            "humanReview",
        )
    }
    evidence["evaluatedScopes"] = [scope]
    with httpx.Client(
        base_url=core, headers={"Authorization": "Bearer " + access}, timeout=30
    ) as client:

        def register(release, uri):
            response = client.post(
                "/api/v1/admin/model-versions",
                json={
                    "kind": "MODEL",
                    "name": name,
                    "version": release,
                    "artifactUri": uri,
                    "evaluation": evidence,
                },
            )
            response.raise_for_status()
            return response.json()["id"]

        def activate(model_id, rollback=False):
            response = client.post(
                f"/api/v1/admin/model-versions/{model_id}/"
                + ("rollback" if rollback else "activate"),
                json={
                    "approved": True,
                    "scopes": [scope],
                    "reason": "LOCAL #86 integration test",
                    "reanalysisPlanned": False,
                },
            )
            response.raise_for_status()

        replacement = register("2.1-check", f"s3://{BUCKET}/models/{name}/2.0/")
        activate(replacement)
        both(2, "2.1-check")
        passed("core activation event replaces real loaded models on both replicas")
        activate(original["id"], rollback=True)
        both(3, "2.0")
        passed("core rollback reloads original MinIO artifact on both replicas")

        missing = register("2.2-missing", f"s3://{BUCKET}/models/missing/2.2/")
        prior_failures = [
            run(["logs", "--no-color", service]).count(
                "Model startup retry error_type="
            )
            for service in ("scoring", "scoring2")
        ]
        activate(missing)
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            logs = [
                run(["logs", "--no-color", service])
                for service in ("scoring", "scoring2")
            ]
            if all(
                log.count("Model startup retry error_type=") > previous
                for log, previous in zip(logs, prior_failures, strict=True)
            ):
                break
            time.sleep(1)
        else:
            raise AssertionError("replacement failure not observed on both replicas")
        both(3, "2.0")
        passed("missing replacement artifact keeps both prior versions available")
        activate(original["id"], rollback=True)
        both(5, "2.0")

        run(["exec", "-T", "rabbitmq", "rabbitmqctl", "stop_app"])
        for endpoint in endpoints:
            wait(endpoint + "/health/ready", lambda r: r.status_code == 503)
        # core commits while the broker is stopped; Outbox + snapshot recover on reconnect.
        activate(replacement, rollback=True)
        run(["exec", "-T", "rabbitmq", "rabbitmqctl", "start_app"])
        both(6, "2.1-check")
        after = {q["name"] for q in queues()}
        assert len(after) == 2 and before.isdisjoint(after) and after <= bound_queues()
        results["exclusive_queues_after"] = sorted(after)
        passed(
            "broker reconnect recreates both queues and reconciles activation during outage"
        )
        results["replica_versions"] = [
            httpx.get(endpoint + "/internal/versions", headers=headers).json()
            for endpoint in endpoints
        ]
        # loaders use TemporaryDirectory: no model weights remain after successful replacement.
        for service in ("scoring", "scoring2"):
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                # 재연결 시 취소된 이전 다운로드 스레드의 정리가 끝날 때까지 확인한다.
                raw = run(
                    [
                        "exec",
                        "-T",
                        service,
                        "python",
                        "-c",
                        (
                            "from pathlib import Path; "
                            "print(len(list(Path('/tmp/scoring-models').iterdir())))"
                        ),
                    ]
                )
                if raw.strip() == "0":
                    break
                time.sleep(1)
            else:
                raise AssertionError(
                    "temporary model downloads were not cleaned within 60s"
                )
        passed("temporary model downloads cleaned on both replicas")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--core-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", default="local/scoring86-events:20261029")
    args = parser.parse_args()
    verify(
        args.archive.resolve(),
        args.core_root.resolve(),
        args.output.resolve(),
        args.image,
        events=True,
    )
