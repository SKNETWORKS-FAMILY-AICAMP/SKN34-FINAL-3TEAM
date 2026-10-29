"""Read-only probe using the real #85 loader and local core/MinIO, never model quality approval."""

import asyncio
import json
import os
import resource
import time

import torch
from app.clients.base import internal_client
from app.clients.core_client import CoreClient
from app.clients.model_artifacts import S3ModelArtifacts
from app.config import get_settings
from app.model_loader import ModelLoader
from app.model_registry import ModelRegistry
from starlette.concurrency import run_in_threadpool


async def main():
    settings = get_settings()
    async with internal_client(settings.core_url) as http:
        versions = await CoreClient(http).active_versions()
    registry = ModelRegistry(ModelLoader(S3ModelArtifacts(settings)))
    started = time.perf_counter()
    await registry.replace(versions)
    load_seconds = time.perf_counter() - started
    outputs = []
    for version in versions:
        loaded = registry.get(version.name, version.scopes[0])
        assert loaded is not None and not registry.is_active(version.name, "unapproved/scope")
        # Synthetic smoke input only. #87 must separately confirm the exact keyword format.
        prompt = "[학년] 초5 [지시문] 친구를 도운 경험을 써 보세요."
        if loaded.training_config.get("with_keyword") == "True":
            prompt += " [핵심어] 친구, 도움"
        encoded = loaded.tokenizer(
            prompt,
            "친구가 어려워해서 함께 문제를 풀었습니다.",
            return_tensors="pt",
            max_length=int(loaded.training_config["max_length"]),
            truncation="only_second",
        )
        started = time.perf_counter()
        raw = await run_in_threadpool(loaded.predict, encoded)
        seconds = time.perf_counter() - started
        assert len(raw) == 1 and len(raw[0]) == 9
        assert torch.isfinite(torch.tensor(raw)).all()
        assert loaded.score_cuts == loaded.training_config["score_cuts"]
        outputs.append(
            {
                "name": version.name,
                "version": version.version,
                "shape": [1, 9],
                "raw": raw,
                "single_smoke_seconds": seconds,
                "max_length": loaded.training_config["max_length"],
                "with_keyword": loaded.training_config["with_keyword"],
                "score_cut_items": sorted(loaded.score_cuts),
            }
        )
    assert not list(settings.model_cache_dir.iterdir())
    assert torch.version.cuda is None and os.getuid() == 10001
    print(
        "PROBE_JSON="
        + json.dumps(
            {
                "uid": os.getuid(),
                "torch": torch.__version__,
                "cuda": torch.version.cuda,
                "real_team_weights": True,
                "synthetic_input_only": True,
                "load_seconds": load_seconds,
                "outputs": outputs,
                "versions": registry.versions(),
                "peak_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    asyncio.run(main())
