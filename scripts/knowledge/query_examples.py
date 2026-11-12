"""Collect #469 code/type lookup results and HTTP latency from a running learning service.

Only reads data; never calls AI, activates datasets, or certifies human reviews.
"""

import argparse
import json
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
    require(cases.get("dataClassification") in ("sample", "extracted", "reviewed"), "invalid_classification")
    grade = cases.get("grade")
    require(type(grade) is int and 3 <= grade <= 6, "invalid_grade")
    for field, count, limit in (("codes", 5, 300), ("thinkingTypes", 5, 20)):
        values = cases.get(field)
        require(isinstance(values, list) and len(values) == count, f"invalid_{field}_count")
        require(all(isinstance(v, str) and 0 < len(v.strip()) <= limit for v in values), f"invalid_{field}_text")
        require(len(set(values)) == count, f"duplicate_{field}")
    require(set(cases["thinkingTypes"]) == {"ANALYZE", "EVALUATE", "CREATE", "SOLVE", "REFLECT"}, "invalid_thinking_types")
    return {key: cases[key] for key in ("label", "dataClassification", "grade", "codes", "thinkingTypes")}


def valid_url(url):
    parsed = urlsplit(url)
    require(parsed.scheme in ("http", "https") and bool(parsed.hostname), "invalid_service_url")
    require(not (parsed.username or parsed.password or parsed.query or parsed.fragment), "invalid_service_url")
    _ = parsed.port  # Validate a supplied port without printing the URL.
    return url.rstrip("/")


def inspect_response(value, version, reasons):
    if isinstance(value, dict):
        if "datasetVersion" in value:
            require(value["datasetVersion"] == version, "dataset_changed_during_collection")
        if isinstance(value.get("reason"), str):
            reasons[value["reason"]] += 1
        for child in value.values():
            inspect_response(child, version, reasons)
    elif isinstance(value, list):
        for child in value:
            inspect_response(child, version, reasons)


def collect(learning_url, cases, token):
    report = {
        "schemaVersion": 1,
        "recordedAt": datetime.now(UTC).isoformat(),
        "cases": cases,
        "classificationNotice": NOTICE,
        "qualityAssessment": "not_evaluated",
        "interpretation": "Empty reviewed relations are valid; this does not approve generation quality.",
        "expectedRequests": {"preparation": 1, "queries": 10, "total": 11},
        "collectionComplete": False,
        "technicalChecks": {"httpSuccess": None, "datasetConsistent": None},
        "requests": [],
    }
    reasons = Counter()

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
        inspect_response(response, version, reasons)

    try:
        listing = call("active_dataset", learning_url, "GET", PATH)
        require(isinstance(listing, dict) and isinstance(listing.get("items"), list), "invalid_dataset_listing")
        active = [item for item in listing["items"] if isinstance(item, dict) and item.get("status") == "ACTIVE"]
        require(len(active) == 1, "expected_one_active_dataset")
        dataset = active[0]
        version = dataset.get("version")
        require(isinstance(version, str) and bool(version.strip()), "invalid_dataset_version")
        report["dataset"] = {"version": version}
        report["technicalChecks"]["datasetConsistent"] = False
        for code in cases["codes"]:
            path = "/internal/knowledge/standards?" + urlencode({"codes": code, "grade": cases["grade"]})
            query("standard", "GET", path, None, code)
        for thinking_type in cases["thinkingTypes"]:
            query("thinking_type", "GET", f"/internal/knowledge/thinking-types/{thinking_type}", None, thinking_type)
        report["technicalChecks"]["httpSuccess"] = True
        report["technicalChecks"]["datasetConsistent"] = True
        report["collectionComplete"] = True
    except ObservationError as error:
        report["error"] = str(error)
    report["observations"] = {"reasonCounts": dict(reasons)}
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--learning-url", required=True)
    parser.add_argument("--cases", type=Path, default=Path(__file__).parent / "samples/query-examples.sample.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        token = os.environ.get("INTERNAL_TOKEN", "")
        require(bool(token.strip()) and "\r" not in token and "\n" not in token, "INTERNAL_TOKEN_required")
        cases = read_cases(args.cases)
        report = collect(valid_url(args.learning_url), cases, token)
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
