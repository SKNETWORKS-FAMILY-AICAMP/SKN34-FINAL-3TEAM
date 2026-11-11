"""Record 13 C5 query observations plus ACTIVE discovery and one C6 embedding batch.

Uses INTERNAL_TOKEN and SYSTEM; never prints credentials. Results are observations,
not evidence that curriculum reviews or answer quality have been approved.
"""

import argparse
import json
import math
import os
import sys
import time
import urllib.error
from collections import Counter
from datetime import UTC, datetime
from http.client import HTTPException
from pathlib import Path
from urllib.parse import urlencode, urlsplit

if __package__:
    from .manage_datasets import PATH, request
else:
    from manage_datasets import PATH, request


NOTICE = "user-supplied classification, does not certify reviews"


class ObservationError(Exception):
    """Only fixed, credential-free codes may be shown to the caller."""


def require(condition, code):
    if not condition:
        raise ObservationError(code)


def read_cases(path):
    cases = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    require(isinstance(cases, dict), "invalid_cases_object")
    require(isinstance(cases.get("label"), str) and 0 < len(cases["label"].strip()) <= 200, "invalid_label")
    require(cases.get("dataClassification") in ("sample", "reviewed"), "invalid_classification")
    grade = cases.get("grade")
    require(type(grade) is int and 3 <= grade <= 6, "invalid_grade")
    require(cases.get("semester") in (f"{grade}-1", f"{grade}-2"), "invalid_semester")
    for field, count, limit in (("codes", 5, 300), ("topics", 3, 8000), ("concepts", 5, 8000)):
        values = cases.get(field)
        require(isinstance(values, list) and len(values) == count, f"invalid_{field}_count")
        require(all(isinstance(v, str) and 0 < len(v.strip()) <= limit for v in values), f"invalid_{field}_text")
        require(len(set(values)) == count, f"duplicate_{field}")
    return {key: cases[key] for key in ("label", "dataClassification", "grade", "semester", "codes", "topics", "concepts")}


def valid_url(url):
    parsed = urlsplit(url)
    require(parsed.scheme in ("http", "https") and bool(parsed.hostname), "invalid_service_url")
    require(not (parsed.username or parsed.password or parsed.query or parsed.fragment), "invalid_service_url")
    _ = parsed.port  # Validate a supplied port without printing the URL.
    return url.rstrip("/")


def inspect_response(value, version, reasons, verdicts):
    if isinstance(value, dict):
        if "datasetVersion" in value:
            require(value["datasetVersion"] == version, "dataset_changed_during_collection")
        if isinstance(value.get("reason"), str):
            reasons[value["reason"]] += 1
        if isinstance(value.get("verdict"), str):
            verdicts[value["verdict"]] += 1
        for child in value.values():
            inspect_response(child, version, reasons, verdicts)
    elif isinstance(value, list):
        for child in value:
            inspect_response(child, version, reasons, verdicts)


def collect(learning_url, ai_url, cases, token):
    report = {
        "schemaVersion": 1,
        "recordedAt": datetime.now(UTC).isoformat(),
        "cases": cases,
        "classificationNotice": NOTICE,
        "qualityAssessment": "not_evaluated",
        "interpretation": "NO_CANDIDATE, HOLD and other missing evidence are observations, not quality passes.",
        "expectedRequests": {"preparation": 2, "queries": 13, "total": 15},
        "collectionComplete": False,
        "technicalChecks": {"httpSuccess": None, "embeddingMatchesDataset": None, "datasetConsistent": None},
        "requests": [],
    }
    reasons, verdicts = Counter(), Counter()

    def call(operation, url, method, path, body=None, input_value=None):
        entry = {"operation": operation, "method": method, "path": path, "input": input_value}
        report["requests"].append(entry)
        started = time.perf_counter()
        try:
            status, response = request(url, method, path, token, body)
            entry.update(status=status, response=response)
        except (OSError, ValueError, urllib.error.URLError, HTTPException):
            report["technicalChecks"]["httpSuccess"] = False
            entry["transportError"] = "request_failed"
            raise ObservationError("request_failed") from None
        finally:
            entry["latencyMs"] = round((time.perf_counter() - started) * 1000, 3)
        if status != 200:
            report["technicalChecks"]["httpSuccess"] = False
            raise ObservationError("unexpected_http_status")
        return response

    def query(operation, method, path, body, input_value):
        response = call(operation, learning_url, method, path, body, input_value)
        require(isinstance(response, dict) and response.get("datasetVersion") == version, "dataset_changed_during_collection")
        inspect_response(response, version, reasons, verdicts)

    try:
        listing = call("active_dataset", learning_url, "GET", PATH)
        require(isinstance(listing, dict) and isinstance(listing.get("items"), list), "invalid_dataset_listing")
        active = [item for item in listing["items"] if isinstance(item, dict) and item.get("status") == "ACTIVE"]
        require(len(active) == 1, "expected_one_active_dataset")
        dataset = active[0]
        version, model, dimensions = dataset.get("version"), dataset.get("embeddingModel"), dataset.get("embeddingDimensions")
        require(isinstance(version, str) and bool(version.strip()), "invalid_dataset_version")
        require(isinstance(model, str) and bool(model.strip()) and type(dimensions) is int and dimensions == 1536, "invalid_dataset_embedding")
        report["dataset"] = {"version": version, "embeddingModel": model, "embeddingDimensions": dimensions}
        texts = cases["topics"] + cases["concepts"]
        embedding = call("embeddings", ai_url, "POST", "/internal/embeddings", {"texts": texts}, texts)
        report["technicalChecks"]["embeddingMatchesDataset"] = False
        require(isinstance(embedding, dict) and embedding.get("model") == model and embedding.get("dimensions") == dimensions,
                "embedding_metadata_mismatch")
        vectors = embedding.get("vectors")
        require(isinstance(vectors, list) and len(vectors) == len(texts), "invalid_embedding_count")
        for vector in vectors:
            require(isinstance(vector, list) and len(vector) == dimensions, "embedding_dimension_mismatch")
            require(all(type(n) in (int, float) and -1e308 <= n <= 1e308 and math.isfinite(n) for n in vector) and any(n != 0 for n in vector),
                    "invalid_embedding_vector")
        report["technicalChecks"]["embeddingMatchesDataset"] = True
        report["technicalChecks"]["datasetConsistent"] = False
        for code in cases["codes"]:
            path = "/internal/knowledge/standards?" + urlencode({"codes": code, "grade": cases["grade"]})
            query("standard", "GET", path, None, code)
        common = {"embeddingModel": model, "grade": cases["grade"], "semester": cases["semester"]}
        for index, topic in enumerate(cases["topics"]):
            query("theme_candidates", "POST", "/internal/knowledge/theme-candidates", {**common, "vector": vectors[index]}, topic)
        for index, concept in enumerate(cases["concepts"], start=len(cases["topics"])):
            query("learned", "POST", "/internal/knowledge/learned",
                  {**common, "concepts": [{"text": concept, "vector": vectors[index]}]}, concept)
        report["technicalChecks"].update(httpSuccess=True, datasetConsistent=True)
        report["collectionComplete"] = True
    except ObservationError as error:
        report["error"] = str(error)
    report["observations"] = {"reasonCounts": dict(reasons), "verdictCounts": dict(verdicts)}
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--learning-url", required=True)
    parser.add_argument("--ai-url", required=True)
    parser.add_argument("--cases", type=Path, default=Path(__file__).parent / "samples/query-examples.sample.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        token = os.environ.get("INTERNAL_TOKEN", "")
        require(bool(token.strip()) and "\r" not in token and "\n" not in token, "INTERNAL_TOKEN_required")
        cases = read_cases(args.cases)
        report = collect(valid_url(args.learning_url), valid_url(args.ai_url), cases, token)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    except ObservationError as error:
        print(f"Input error: {error}", file=sys.stderr)
        return 2
    except (OSError, ValueError, OverflowError):
        print("Cannot read inputs or write the observation report.", file=sys.stderr)
        return 2
    print("Observation report written; quality and review approval were not evaluated.")
    return 0 if report["collectionComplete"] else 1


if __name__ == "__main__":
    sys.exit(main())
