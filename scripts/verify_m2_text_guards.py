"""#549 실제 로컬 가중치·토크나이저 검증. 합성 글만 사용하고 원본 artifact는 수정하지 않는다.

scoring venv Python으로 실행: --artifacts <model/version 폴더의 상위> --output <검증 폴더>
"""

import argparse
import gc
import hashlib
import json
import shutil
import sys
import time
from bisect import bisect_right
from contextlib import contextmanager
from pathlib import Path
from uuid import NAMESPACE_DNS, uuid5

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend/scoring-service"))

from app.m2.m2_long_input import encode_head_tail
from app.m2.models import M2Request, M2Skipped
from app.m2.service import infer
from app.model_loader import ModelLoader
from app.model_versions import ActiveModelVersion


class LocalArtifacts:
    def __init__(self, directory):
        self.directory = directory

    @contextmanager
    def download(self, _):
        yield self.directory


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifacts", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    import torch

    torch.set_num_threads(2)
    report = {"torchThreads": 2, "data": "synthetic only", "models": []}
    args.output.mkdir(parents=True, exist_ok=True)
    for kind, release in (("essay", "3.1"), ("narrative", "3.0")):
        name = f"m2-klue-{kind}"
        source = args.artifacts / name / release
        target = args.output / name / release
        if source.resolve() == target.resolve():
            raise ValueError("output must not overwrite source")
        shutil.copytree(source, target, dirs_exist_ok=True)
        cuts_path = target / "score_cuts.json"
        old_cuts = cuts_path.read_bytes()
        new_cuts = (
            ROOT
            / "backend/scoring-service/metadata/1112b"
            / name
            / release
            / "score_cuts.json"
        ).read_bytes()
        cuts_path.write_bytes(new_cuts)
        meta = ActiveModelVersion.model_validate(
            {
                "id": str(uuid5(NAMESPACE_DNS, name + release)),
                "kind": "MODEL",
                "name": name,
                "version": release,
                "artifactUri": "s3://local-test/models/",
                "revision": 1,
                "refId": None,
                "scopes": [f"judgment/grade-{g}/{kind}" for g in (4, 5, 6)],
                "activatedAt": "2026-11-12T00:00:00Z",
            }
        )
        loader = ModelLoader(LocalArtifacts(target))
        loaded = loader(meta)
        body = {
            "prompt": "우리 동네에 필요한 시설과 그 이유를 설명해 보세요.",
            "grade": 5,
            "inputType": kind.upper(),
            "keywords": ["도서관", "책"],
            "essayType": "주장",
        }
        text = (
            "우리 동네에는 도서관이 필요하다. 지금은 책을 빌리려면 버스를 타고 멀리 가야 한다. "
            "가까운 도서관이 생기면 친구들과 자료를 찾아 숙제를 하고 새로운 지식을 배울 수 있다. "
            "어른들도 신문을 읽거나 필요한 정보를 찾아 생활에 도움을 받을 수 있다. "
            "모두가 조용히 이용하도록 규칙을 정하고 함께 책을 아끼면 좋겠다."
        )
        request = M2Request(**body, text=text)
        started = time.perf_counter()
        result = infer(loaded, request)
        elapsed = time.perf_counter() - started
        assert not isinstance(result, M2Skipped)
        assert result.preparation.copied == 0 and not result.preparation.repeated
        first = "[학년] 초5 " + (
            "[글 종류] 주장" if kind == "essay" else "[핵심어] 도서관, 책"
        )
        original = loaded.tokenizer(
            first, text, truncation="only_second", max_length=512, return_tensors="pt"
        )
        encoded, truncated = encode_head_tail(loaded.tokenizer, first, text)
        assert not truncated
        assert torch.equal(original["input_ids"], encoded["input_ids"])
        assert loaded.predict(original)[0][
            : len(result.rawScores.model_dump())
        ] == list(result.rawScores.model_dump().values())
        cuts = json.loads(new_cuts)
        offset = 0 if kind == "essay" else 1
        assert result.scores.model_dump() == {
            k: bisect_right(cuts[k], v) + offset
            for k, v in result.rawScores.model_dump().items()
        }
        # 정리로 제거되는 복사·반복·칸 이름을 실제 모델에서도 동일 점수로 확인한다.
        copied = infer(loaded, M2Request(**body, text=body["prompt"] + "\n" + text))
        assert copied.rawScores == result.rawScores and copied.preparation.copied == 1
        repeated = infer(loaded, M2Request(**body, text=(text + " ") * 3))
        assert repeated.preparation.repeated and repeated.rawScores == result.rawScores
        if kind == "essay":
            labels = infer(
                loaded,
                M2Request(**body, text="내 생각: " + text, essayLabels=["내 생각"]),
            )
            assert (
                labels.rawScores == result.rawScores
                and labels.preparation.labelsRemoved == 1
            )
        # 서로 다른 문장을 사용하여 반복 제거 때문에 긴 글 검증이 무효가 되지 않게 한다.
        long_text = " ".join(
            f"도서관에서 {i}번째로 발견한 책에는 새로운 지식과 다양한 이야기가 담겨 있다."
            for i in range(90)
        )
        long_request = M2Request(**body, text=long_text)
        long_result = infer(loaded, long_request)
        assert long_result.preparation.truncated
        encoded, truncated = encode_head_tail(loaded.tokenizer, first, long_text)
        assert truncated and encoded["input_ids"].shape[1] == 512
        tail = loaded.tokenizer(long_text, add_special_tokens=False)["input_ids"][-20:]
        assert encoded["input_ids"][0].tolist()[-21:-1] == tail
        threshold = 100 if kind == "essay" else 10
        short = infer(loaded, M2Request(**body, text="가" * (threshold - 1)))
        assert isinstance(short, M2Skipped)
        boundary = infer(loaded, M2Request(**body, text="가" * threshold))
        assert not isinstance(boundary, M2Skipped)
        # 기존 가중치를 다시 읽어 b 경계 재로딩, 이전 경계 복구까지 수행한다.
        before_raw = result.rawScores
        del loaded
        gc.collect()
        reloaded = loader(meta.model_copy(update={"revision": 2}))
        assert infer(reloaded, request).rawScores == before_raw
        del reloaded
        gc.collect()
        cuts_path.write_bytes(old_cuts)
        rollback = loader(meta.model_copy(update={"revision": 3}))
        rolled = infer(rollback, request)
        assert rolled.rawScores == before_raw
        old = json.loads(old_cuts)
        assert rolled.scores.model_dump() == {
            k: bisect_right(old[k], v) + offset
            for k, v in rolled.rawScores.model_dump().items()
        }
        del rollback
        gc.collect()
        cuts_path.write_bytes(new_cuts)
        report["models"].append(
            {
                "name": name,
                "version": release,
                "weightSha256": hashlib.file_digest(
                    (source / "model.safetensors").open("rb"), "sha256"
                ).hexdigest(),
                "cutsSha256": hashlib.sha256(new_cuts).hexdigest(),
                "singleInferenceSeconds": round(elapsed, 4),
                "scores": result.scores.model_dump(),
                "rawScores": before_raw.model_dump(),
                "checks": [
                    "short-token-identity",
                    "new-cuts",
                    "copy-removal",
                    "repeat-removal",
                    "head-tail-512",
                    "short-boundary",
                    "reload",
                    "rollback",
                ],
            }
        )
        print(name, "PASS", flush=True)
    (args.output / "result.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
