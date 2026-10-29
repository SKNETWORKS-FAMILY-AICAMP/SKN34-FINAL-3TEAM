"""#84 실제 모델 통합 검증: 지정 core 큐 적재와 미학습 M1 계약."""

import argparse
import json
import time
from pathlib import Path

import httpx
import jsonschema
from verify_scoring_models import ROOT, verify


def check_epic(run, endpoint, rabbit, headers, password, request, results, passed):
    # 격리 프로젝트의 core만 멈춰 즉시 소비되는 큐를 관찰한다.
    # 큐·바인딩은 팀 definitions.json 그대로이며 검증용으로 새로 만들지 않는다.
    run(["stop", "core"])
    queue = "core.llm.usage.recorded"
    with httpx.Client(base_url=rabbit, auth=("verify", password), timeout=10) as broker:
        deadline = time.monotonic() + 30
        while True:
            info = broker.get(f"/api/queues/%2F/{queue}")
            info.raise_for_status()
            assert info.json()["durable"]
            if info.json()["consumers"] == 0:
                break
            assert time.monotonic() < deadline, "core consumer did not stop"
            time.sleep(0.5)
        bindings = broker.get("/api/bindings/%2F").json()
        assert any(
            x["source"] == "events.topic"
            and x["destination"] == queue
            and x["destination_type"] == "queue"
            and x["routing_key"] == "llm.usage.recorded"
            for x in bindings
        )

        def drain():
            response = broker.post(
                f"/api/queues/%2F/{queue}/get",
                json={
                    "count": 1000,
                    "ackmode": "ack_requeue_false",
                    "encoding": "auto",
                },
            )
            response.raise_for_status()
            return [json.loads(x["payload"]) for x in response.json()]

        # 기존 채점 이벤트를 비워 이번 두 요청의 수신 수를 별도로 검사한다.
        drain()
        with httpx.Client(base_url=endpoint, headers=headers, timeout=35) as client:
            for kind in ("NARRATIVE", "ESSAY"):
                response = client.post("/internal/m2/scores", json=request(kind))
                response.raise_for_status()
                assert response.json()["active"] is True
            received = []
            deadline = time.monotonic() + 30
            while len(received) < 2 and time.monotonic() < deadline:
                received.extend(drain())
                if len(received) < 2:
                    time.sleep(0.25)
            assert len(received) == 2
            for event in received:
                for name, value in (
                    ("envelope.schema.json", event),
                    ("llm.usage.recorded.v1.schema.json", event["data"]),
                ):
                    jsonschema.validate(
                        value,
                        json.loads(
                            (ROOT / "contracts/events" / name).read_text("utf-8")
                        ),
                    )
                assert event["data"]["service"] == "scoring"
                assert event["data"]["callType"] == "M2"
                assert event["data"]["success"] is True
            assert len({x["id"] for x in received}) == 2
            assert {x["data"]["model"].split("@")[0] for x in received} == {
                "m2-klue-narrative",
                "m2-klue-essay",
            }
            results["core_usage_queue"] = {
                "queue": queue,
                "count": 2,
                "eventIds": [x["id"] for x in received],
                "bindingVerified": True,
                "coreConsumerStoppedForObservation": True,
            }
            passed(
                "both real M2 inferences reached exact core.llm.usage.recorded queue"
            )
            m1 = {
                "problem": "2+3",
                "answerKey": "5",
                "solution": {"steps": ["2에 3을 더함"], "finalAnswer": "5"},
            }
            response = client.post("/internal/m1/checks", json=m1)
            assert response.status_code == 200 and response.json() == {"active": False}
            assert (
                httpx.post(endpoint + "/internal/m1/checks", json=m1).status_code == 401
            )
            assert client.post("/internal/m1/checks", json={}).status_code == 400
            time.sleep(1)
            assert drain() == [], "미학습 M1은 추론 사용량을 발행하면 안 된다"
            results["m1"] = {
                "active": False,
                "missingToken": 401,
                "invalidInput": 400,
                "usageEvents": 0,
                "scope": "untrained exception",
            }
            passed("real M1 HTTP inactive/401/400; no fabricated inference usage")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--core-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--image", default="local/scoring84:20261029")
    args = parser.parse_args()
    verify(
        args.archive.resolve(),
        args.core_root.resolve(),
        args.output.resolve(),
        args.image,
        scores=True,
        epic=True,
    )
