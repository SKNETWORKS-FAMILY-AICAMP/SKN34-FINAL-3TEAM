"""#87 합성 글 + 실제 2.0 모델: core/MinIO/RabbitMQ/scoring HTTP 통합.

모델·결과·로컬 자격 증명은 저장소 밖에 둔다. 품질 평가 데이터는 사용하지 않는다.
"""

import argparse
import json
import statistics
import time
from bisect import bisect_right
from pathlib import Path

import httpx
import jsonschema
from verify_scoring_models import BUCKET, ROOT, verify, wait


def check_scores(run, url, core, access, headers, password, results, passed):
    endpoint, rabbit = url("scoring", 8001), url("rabbitmq", 15672)
    queue = "issue87.usage.probe"
    with httpx.Client(
        base_url=rabbit, auth=("verify", password), timeout=10
    ) as management:
        management.put(
            f"/api/queues/%2F/{queue}",
            json={"durable": True, "auto_delete": False, "arguments": {}},
        ).raise_for_status()
        management.post(
            f"/api/bindings/%2F/e/events.topic/q/{queue}",
            json={"routing_key": "llm.usage.recorded", "arguments": {}},
        ).raise_for_status()
    sentence = (
        "친구와 이야기할 때 서로의 생각을 존중하면 오해가 줄어들고 의사소통이 잘 된다. "
    )

    def request(kind="NARRATIVE", chars=200, **changes):
        return {
            "prompt": "글의 통일성이 무엇이며 왜 필요한지 설명하세요.",
            "text": (sentence * (chars // len(sentence) + 1))[:chars],
            "grade": 5,
            "inputType": kind,
            "keywords": ["통일성", "주제"] if kind == "NARRATIVE" else [],
            **changes,
        }

    with httpx.Client(base_url=endpoint, headers=headers, timeout=35) as client:
        assert (
            httpx.post(endpoint + "/internal/m2/scores", json=request()).status_code
            == 401
        )
        assert (
            client.post("/internal/m2/scores", json=request(grade="5")).status_code
            == 400
        )
        for changes in ({"grade": 3}, {"grade": 4}, {"grade": 6}, {"keywords": []}):
            assert client.post(
                "/internal/m2/scores", json=request(**changes)
            ).json() == {"active": False}
        passed("HTTP 401/400 and inactive grade/scope/missing narrative keywords")
        spec = json.loads(
            run(
                [
                    "exec",
                    "-T",
                    "scoring",
                    "python",
                    "-c",
                    "import json; from app.main import app; print(json.dumps(app.openapi()))",
                ]
            )
        )
        results["responses"], results["latency"] = {}, []
        for kind in ("NARRATIVE", "ESSAY"):
            for chars in (200, 650, 1200):
                timings = []
                for i in range(33):
                    before = time.perf_counter()
                    response = client.post(
                        "/internal/m2/scores", json=request(kind, chars)
                    )
                    duration = (time.perf_counter() - before) * 1000
                    response.raise_for_status()
                    data = response.json()
                    schema = {
                        **spec["components"]["schemas"]["M2Active"],
                        "components": spec["components"],
                    }
                    jsonschema.validate(data, schema)
                    assert data["model"]["name"] == "m2-klue-" + (
                        "narrative" if kind == "NARRATIVE" else "essay"
                    )
                    assert data["model"]["version"] == "2.0"
                    cuts = results["cuts"][data["model"]["name"]]
                    assert data["scores"] == {
                        k: bisect_right(cuts[k], v) + 1
                        for k, v in data["rawScores"].items()
                    }
                    if i >= 3:
                        timings.append(duration)
                timings.sort()
                results["latency"].append(
                    {
                        "kind": kind,
                        "chars": chars,
                        "warmup": 3,
                        "runs": 30,
                        "median_ms": round(statistics.median(timings), 2),
                        "p95_ms": round(timings[int(len(timings) * 0.95) - 1], 2),
                        "max_ms": round(max(timings), 2),
                    }
                )
                results["responses"][kind] = data
                passed(f"real {kind} {chars} chars HTTP inference: 30 timed requests")
        assert max(row["max_ms"] for row in results["latency"]) < 35000
        results["runtime"] = run(
            [
                "exec",
                "-T",
                "scoring",
                "python",
                "-c",
                "import torch,platform,json; print(json.dumps({'threads':torch.get_num_threads(),'cpu':platform.machine(),'torch':torch.__version__}))",
            ]
        ).strip()

        # 같은 가중치의 메타데이터 버전만 바꿔 실제 응답 버전 교체·롤백을 검증한다.
        name = "m2-klue-narrative"
        original = next(x for x in results["snapshot"]["items"] if x["name"] == name)
        scope = "judgment/grade-5/narrative"
        evidence = {
            key: "LOCAL synthetic transport test, NOT quality approval"
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
        ) as admin:
            response = admin.post(
                "/api/v1/admin/model-versions",
                json={
                    "kind": "MODEL",
                    "name": name,
                    "version": "2.1-check",
                    "artifactUri": f"s3://{BUCKET}/models/{name}/2.0/",
                    "evaluation": evidence,
                },
            )
            response.raise_for_status()
            replacement = response.json()["id"]
            for model_id, verb, release, revision in (
                (replacement, "activate", "2.1-check", 2),
                (original["id"], "rollback", "2.0", 3),
            ):
                admin.post(
                    f"/api/v1/admin/model-versions/{model_id}/{verb}",
                    json={
                        "approved": True,
                        "scopes": [scope],
                        "reason": "LOCAL #87 response version test",
                        "reanalysisPlanned": False,
                    },
                ).raise_for_status()
                wait(
                    endpoint + "/internal/versions",
                    lambda r, revision=revision: (
                        r.status_code == 200
                        and any(
                            x["name"] == name and x["revision"] == revision
                            for x in r.json()["items"]
                        )
                    ),
                    headers,
                    seconds=300,
                )
                data = client.post("/internal/m2/scores", json=request()).json()
                assert data["model"] == {
                    "name": name,
                    "version": release,
                    "revision": revision,
                }
                passed(
                    f"real core {verb} event reflected in M2 HTTP response: {release}"
                )

        with httpx.Client(base_url=rabbit, auth=("verify", password)) as management:
            response = management.post(
                f"/api/queues/%2F/{queue}/get",
                json={
                    "count": 500,
                    "ackmode": "ack_requeue_false",
                    "encoding": "auto",
                    "truncate": 50000,
                },
            )
            response.raise_for_status()
            events = [json.loads(x["payload"]) for x in response.json()]
        assert len(events) >= 198
        for event in events:
            for schema_name, value in (
                ("envelope.schema.json", event),
                ("llm.usage.recorded.v1.schema.json", event["data"]),
            ):
                jsonschema.validate(
                    value,
                    json.loads(
                        (ROOT / "contracts/events" / schema_name).read_text(
                            encoding="utf-8"
                        )
                    ),
                )
            assert (
                event["data"]["service"] == "scoring"
                and event["data"]["callType"] == "M2"
            )
            assert event["data"]["inputTokens"] is None
            assert "친구" not in json.dumps(event, ensure_ascii=False)
        results["usage_events"] = {"count": len(events), "sample": events[0]}
        passed(
            "actual RabbitMQ M2 usage envelopes validate shared schema and omit raw input"
        )
        # 브로커 장애는 응답 실패로 전파하지 않는다.
        run(["exec", "-T", "rabbitmq", "rabbitmqctl", "stop_app"])
        wait(endpoint + "/health/ready", lambda r: r.status_code == 503)
        response = client.post("/internal/m2/scores", json=request())
        assert response.status_code == 200 and response.json()["active"]
        passed("real disconnected broker does not fail M2 HTTP response")
        logs = run(["logs", "--no-color", "scoring"])
        assert sentence[:20] not in logs and request()["prompt"] not in logs


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--core-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", default="local/scoring87:20261029")
    args = parser.parse_args()
    verify(
        args.archive.resolve(),
        args.core_root.resolve(),
        args.output.resolve(),
        args.image,
        scores=True,
    )
