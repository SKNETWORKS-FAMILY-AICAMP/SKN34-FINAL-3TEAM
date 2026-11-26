import json
import sys
from argparse import Namespace
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runners"))
import structured_report_demo as demo


def test_runpod_results_are_cached_for_the_mock_answers(tmp_path, monkeypatch):
    monkeypatch.delenv(demo.RUNPOD_ENDPOINT, raising=False)
    monkeypatch.delenv(demo.RUNPOD_KEY, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "SAGOMUNGCHI_SLLM_SERVERLESS_gemma=https://api.runpod.ai/v2/test\n"
        "SAGOMUNGCHI_SLLM_SERVERLESS_KEY_gemma=mock-key\n",
        encoding="utf-8",
    )

    prompts = []
    detail = {"analysis": "글의 근거를 설명했어요.", "improvement_points": None,
              "next_steps": ["예를 덧붙여 보세요."]}

    def runpod(request):
        assert request.url.host == "api.runpod.ai"
        assert request.headers["Authorization"] == "Bearer mock-key"
        if request.url.path == "/v2/test/run":
            payload = json.loads(request.content)["input"]["openai_input"]
            assert payload["model"] == "explain"
            prompts.append(json.loads(payload["messages"][-1]["content"].split("\n자료:\n")[-1]))
            return httpx.Response(200, json={"id": f"job-{len(prompts)}"})
        assert request.url.path == f"/v2/test/status/job-{len(prompts)}"
        return httpx.Response(200, json={
            "status": "COMPLETED",
            "output": {"choices": [{"message": {"content": json.dumps(detail)}}]},
        })

    create_client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kwargs: create_client(
        transport=httpx.MockTransport(runpod), **kwargs
    ))
    args = Namespace(
        cases=None,
        prompt=demo.DEFAULT_PROMPT,
        env_file=env_file,
        out=tmp_path / "receipts",
        cache=tmp_path / "gemma-explanations.json",
        model="explain",
    )
    demo.run(args)

    fixture = json.loads(demo.MOCK_SAMPLES.read_text(encoding="utf-8"))
    cache = json.loads(args.cache.read_text(encoding="utf-8"))
    assert cache["model"] == "explain"
    assert len(prompts) == len(cache["items"]) == 3
    for sample, prompt, item in zip(fixture["samples"], prompts, cache["items"], strict=True):
        assert prompt == {
            "grade": fixture["grade"], "topic": sample["question"], "answer": sample["texts"][-1]
        }
        assert item["attemptId"] == sample["attemptId"]
        assert item["answerVersion"] == len(sample["texts"])
        assert item["sourceText"] == sample["texts"][-1]
        assert json.loads(item["text"]) == detail

    demo.run(args)
    assert len(prompts) == 3
