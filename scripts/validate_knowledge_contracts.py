"""Validate #469 HTTP responses generated against a real, disposable pgvector database."""

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACTS = ROOT / "backend/learning-service/build/contracts/knowledge"
OPERATIONS = {
    "standards": ("/knowledge/standards", "get"),
    "thinking-type": ("/knowledge/thinking-types/{type}", "get"),
    "search": ("/knowledge/search", "post"),
    "theme-candidates": ("/knowledge/theme-candidates", "post"),
    "learned": ("/knowledge/learned", "post"),
}
SNAPSHOTS = {name: (name, "200") for name in OPERATIONS}
SNAPSHOTS.update({
    "standards-missing": ("standards", "200"),
    "search-below-threshold": ("search", "200"),
    "theme-candidates-empty": ("theme-candidates", "200"),
    "learned-hold": ("learned", "200"),
    **{f"no-active-{name}": (name, "200") for name in OPERATIONS},
    "unauthenticated": ("standards", "401"),
    "forbidden": ("standards", "403"),
    "invalid-request": ("search", "400"),
    "embedding-mismatch": ("search", "409"),
})


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_coverage(payloads):
    """Empty successes cannot silently remove the real producer's schema coverage."""
    for name in ("standards", "search"):
        require(bool(payloads[name]["items"]), f"{name}: expected a non-empty actual result")
    require(payloads["thinking-type"]["guide"] is not None, "thinking-type: expected an actual guide")
    types = payloads["theme-candidates"]["types"]
    require({item["thinkingType"] for item in types} ==
            {"ANALYZE", "EVALUATE", "CREATE", "SOLVE", "REFLECT"}, "theme: missing thinking type")
    require(any(item["candidates"] for item in types), "theme: expected actual candidates")
    require({item["verdict"] for item in payloads["learned"]["items"]} ==
            {"LEARNED", "NOT_YET", "HOLD"}, "learned: all three verdicts must be exercised")
    for name in OPERATIONS:
        inactive = payloads[f"no-active-{name}"]
        require(inactive["datasetVersion"] is None and inactive["reason"] == "NO_ACTIVE_DATASET",
                f"{name}: no-active response must be explicit")
    require(payloads["standards-missing"]["reason"] == "CODE_NOT_FOUND", "missing code coverage")
    require(payloads["search-below-threshold"]["reason"] == "BELOW_THRESHOLD", "threshold coverage")
    require(all(not item["candidates"] and item["reason"] == "NO_CANDIDATE"
                for item in payloads["theme-candidates-empty"]["types"]), "empty theme coverage")
    hold = payloads["learned-hold"]["items"]
    require(bool(hold) and all(item["verdict"] == "HOLD" for item in hold), "hold coverage")
    for name, status, code in (
        ("unauthenticated", 401, "UNAUTHENTICATED"),
        ("forbidden", 403, "FORBIDDEN"),
        ("invalid-request", 400, "VALIDATION_FAILED"),
        ("embedding-mismatch", 409, "KNOWLEDGE_EMBEDDING_MISMATCH"),
    ):
        require(payloads[name]["status"] == status and payloads[name]["code"] == code,
                f"{name}: error status/code differ from contract")


def validate(directory=DEFAULT_ARTIFACTS):
    spec = yaml.safe_load((ROOT / "contracts/openapi/learning-service.yaml").read_text(encoding="utf-8"))
    payloads = {}
    for name, (operation, status) in SNAPSHOTS.items():
        path, method = OPERATIONS[operation]
        response = spec["paths"][path][method]["responses"][status]
        if "$ref" in response:
            target = spec
            for part in response["$ref"].removeprefix("#/").split("/"):
                target = target[part]
            response = target
        content = response["content"]
        media_type = "application/json" if status == "200" else "application/problem+json"
        schema = content[media_type]["schema"]
        payload = json.loads((Path(directory) / f"{name}.json").read_text(encoding="utf-8"))
        Draft202012Validator({**schema, "components": spec["components"]},
                            format_checker=FormatChecker()).validate(payload)
        payloads[name] = payload
        print(f"PASS: {name}: actual HTTP JSON matches {method.upper()} {path} {status}")
    check_coverage(payloads)
    print("PASS: all five knowledge APIs, fallback states and authentication/error contracts")


if __name__ == "__main__":
    validate(Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ARTIFACTS)
