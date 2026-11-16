"""Build an offline single-PUT plan from a trusted model preflight request (#493).

No AWS SDK, credentials, network calls, upload, registration or activation.
"""

import argparse
import base64
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

FILES = frozenset(
    {
        "config.json",
        "tokenizer.json",
        "tokenizer_config.json",
        "train_info.json",
        "score_cuts.json",
        "model.safetensors",
    }
)
SMALL = frozenset({"config.json", "train_info.json", "score_cuts.json"})
# Conservative single-PUT limit in decimal bytes; never fall back to multipart.
MAX_SINGLE_PUT_BYTES = 5_000_000_000


def prepare(request: dict, model_dir: Path, expected_bucket: str) -> dict:
    """Verify all six local artifacts before returning any upload parameters."""
    if not isinstance(request, dict) or set(request) != {
        "name",
        "version",
        "artifactUri",
        "files",
    }:
        raise ValueError(
            "Expected a ModelPreflightRequest, not registration or manifest JSON"
        )
    if request["name"] not in ("m2-klue-narrative", "m2-klue-essay"):
        raise ValueError("Unsupported model name")
    if (
        not isinstance(request["version"], str)
        or not 1 <= len(request["version"]) <= 100
    ):
        raise ValueError("Invalid model version")
    uri = request["artifactUri"]
    if not isinstance(uri, str) or len(uri) > 2048:
        raise ValueError("Invalid artifactUri")
    location = urlsplit(uri)
    prefix = location.path.removeprefix("/")
    if (
        not re.fullmatch(r"[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]", expected_bucket)
        or location.scheme != "s3"
        or location.netloc != expected_bucket
        or location.query
        or location.fragment
        or not prefix.startswith("models/")
        or not prefix.endswith("/")
        or any(part in ("", ".", "..") for part in prefix[:-1].split("/"))
        or re.search(r"[\\%<>:\s]", prefix)
        or uri != f"s3://{expected_bucket}/{prefix}"
    ):
        raise ValueError(
            "artifactUri must use the expected bucket and a safe models/ prefix"
        )
    entries = request["files"]
    if not isinstance(entries, list) or len(entries) != len(FILES):
        raise ValueError("Exactly six artifacts are required")
    seen = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"file", "bytes", "sha256"}:
            raise ValueError("Each artifact must contain file, bytes and sha256")
        name = entry["file"]
        if not isinstance(name, str) or name not in FILES or name in seen:
            raise ValueError("Duplicate or unsupported artifact name")
        seen.add(name)
        if (
            type(entry["bytes"]) is not int
            or not 0 <= entry["bytes"] <= MAX_SINGLE_PUT_BYTES
        ):
            raise ValueError(f"{name}: invalid size or exceeds the single-PUT limit")
        if name in SMALL and entry["bytes"] > 1024 * 1024:
            raise ValueError(f"{name}: exceeds the preflight JSON size limit")
        if not isinstance(entry["sha256"], str) or not re.fullmatch(
            r"[0-9a-f]{64}", entry["sha256"]
        ):
            raise ValueError(f"{name}: expected a lowercase hexadecimal SHA-256")

    directory = model_dir.resolve(strict=True)
    artifacts = []
    for entry in sorted(entries, key=lambda item: item["file"]):
        name = entry["file"]
        source = (directory / name).resolve(strict=True)
        if not source.is_file() or source.parent != directory:
            raise ValueError(f"{name}: must be a regular file inside model-dir")
        if source.stat().st_size != entry["bytes"]:
            raise ValueError(f"{name}: SIZE_MISMATCH")
        digest = hashlib.sha256()
        size = 0
        with source.open("rb") as stream:
            while chunk := stream.read(1024 * 1024):
                digest.update(chunk)
                size += len(chunk)
        if size != entry["bytes"] or digest.hexdigest() != entry["sha256"]:
            raise ValueError(f"{name}: HASH_MISMATCH or file changed while reading")
        artifacts.append(
            {
                "file": name,
                "path": str(source),
                "key": prefix + name,
                "bytes": size,
                "sha256": digest.hexdigest(),
                "checksumSHA256": base64.b64encode(digest.digest()).decode("ascii"),
            }
        )
    return {
        "name": request["name"],
        "version": request["version"],
        "bucket": expected_bucket,
        "artifactUri": uri,
        "operation": "PutObject",
        "checksumAlgorithm": "SHA256",
        "files": artifacts,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument("--expected-bucket", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        request = json.loads(args.request.read_text(encoding="utf-8-sig"))
        plan = prepare(request, args.model_dir, args.expected_bucket)
        # Refuse overwriting any existing file, including the trusted input request.
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(plan, stream, ensure_ascii=False, indent=2)
            stream.write("\n")
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Upload preparation failed: {exc}\n")
    print("Verified 6 local artifacts. Offline plan saved; no AWS operation performed.")


if __name__ == "__main__":
    main()
