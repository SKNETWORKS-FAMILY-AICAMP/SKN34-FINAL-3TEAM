"""교육과정 지식 판 관리 (#466, api-spec 4.1.3). learning 내부 관리 경로를 직접 부르는 운영 스크립트.

core 프록시·관리자 화면은 없다. learning에 닿는 주소(kind는 포트 포워드)와 내부 토큰(환경 변수 INTERNAL_TOKEN)만 쓰고,
토큰 값은 출력하지 않는다. 표준 라이브러리만 쓴다.

  # kind: kubectl -n app port-forward svc/learning-service 18081:8081
  python scripts/knowledge/manage_datasets.py list
  python scripts/knowledge/manage_datasets.py load --records curriculum.jsonl --reviews relations.csv \\
      --dataset dataset.json [--recheck-out recheck.csv] [--activate]
  python scripts/knowledge/manage_datasets.py show kn-20261111-01
  python scripts/knowledge/manage_datasets.py activate kn-20261111-01
  python scripts/knowledge/manage_datasets.py delete kn-20261111-01   # RETIRED 판만

--dataset은 `scripts/knowledge/samples/dataset.sample.json` 모양(`source` 객체를 씀). 샘플 확인 파일(reviewer SAMPLE)은
learning이 거부하므로 샘플 적재는 --reviews 없이 한다.
"""

import argparse
import csv
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

PATH = "/internal/admin/knowledge/datasets"
REVIEW_COLUMNS = (
    "relationType", "standardCode", "standardStatement", "target", "targetText", "evidence", "similarity",
    "candidateSource", "decision", "modifiedTarget", "reason", "reviewer", "reviewedAt", "datasetVersion",
)
# 실제 추출본 적재는 임베딩 호출 수십 번(1~2분)이라 동기 요청을 넉넉히 기다린다(동섭 결정 2026-11-11)
TIMEOUT_SECONDS = 600


def read_records(path):
    """C1 JSONL: 빈 줄을 뺀 한 줄 = 한 레코드."""
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [json.loads(line) for line in lines if line.strip()]


def read_reviews(path):
    """C4 CSV(UTF-8, 머리줄 = 칸 이름). 칸이 다르면 멈춘다."""
    with Path(path).open(encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if tuple(reader.fieldnames or ()) != REVIEW_COLUMNS:
            raise SystemExit(f"{path}: 머리줄이 C4 칸과 다름: {reader.fieldnames}")
        return [dict(row) for row in reader]


def write_recheck(path, rows):
    with Path(path).open("w", encoding="utf-8", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=REVIEW_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column) or "" for column in REVIEW_COLUMNS})


def load_body(records_path, reviews_path, dataset_path):
    dataset = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    source = dataset.get("source", dataset)
    body = {"source": source, "records": read_records(records_path)}
    if reviews_path:
        body["reviews"] = read_reviews(reviews_path)
    return body


def request(base_url, method, path, token, body=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, method=method)
    req.add_header("X-Internal-Token", token)
    req.add_header("X-User-Role", "SYSTEM")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as response:
            text = response.read().decode("utf-8")
            return response.status, json.loads(text) if text else None
    except urllib.error.HTTPError as error:
        text = error.read().decode("utf-8", "replace")
        try:
            return error.code, json.loads(text)
        except ValueError:
            return error.code, {"detail": text[:500]}


def summary(result):
    """결과서 2·4·5절에 옮길 숫자만."""
    dataset = result["dataset"]
    return {
        "version": dataset["version"],
        "status": dataset["status"],
        "embeddingModel": dataset["embeddingModel"],
        "documents": result["documents"],
        "chunkCount": dataset["chunkCount"],
        "chunks": dataset["chunks"],
        "relationCount": dataset["relationCount"],
        "relations": dataset["relations"],
        "embeddedTexts": result["embeddedTexts"],
        "embeddingRequests": result["embeddingRequests"],
        "reusedEmbeddings": result["reusedEmbeddings"],
        "previousVersion": result.get("previousVersion"),
        "carriedRelations": result["carriedRelations"],
        "recheck": len(result["recheck"]),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--learning-url", default=os.environ.get("LEARNING_URL", "http://127.0.0.1:18081"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list")
    for name in ("show", "activate", "delete"):
        commands.add_parser(name).add_argument("version")
    load = commands.add_parser("load")
    load.add_argument("--records", required=True)
    load.add_argument("--reviews")
    load.add_argument("--dataset", required=True)
    load.add_argument("--recheck-out")
    load.add_argument("--activate", action="store_true")
    args = parser.parse_args(argv)

    token = os.environ.get("INTERNAL_TOKEN")
    if not token:
        raise SystemExit("INTERNAL_TOKEN 환경 변수 필요(값은 출력하지 않음)")
    url = args.learning_url

    if args.command == "list":
        status, body = request(url, "GET", PATH, token)
    elif args.command == "show":
        status, body = request(url, "GET", f"{PATH}/{args.version}", token)
    elif args.command == "activate":
        status, body = request(url, "POST", f"{PATH}/{args.version}/activate", token, {})
    elif args.command == "delete":
        status, body = request(url, "DELETE", f"{PATH}/{args.version}", token)
    else:
        status, body = request(url, "POST", PATH, token, load_body(args.records, args.reviews, args.dataset))
        if status == 201:
            if args.recheck_out:
                write_recheck(args.recheck_out, body["recheck"])
            result = summary(body)
            if args.activate:
                status, activated = request(url, "POST", f"{PATH}/{result['version']}/activate", token, {})
                result["activation"] = activated if status != 200 else activated["status"]
            body = result
    print(json.dumps({"status": status, "body": body}, ensure_ascii=False, indent=2))
    return 0 if 200 <= status < 300 else 1


if __name__ == "__main__":
    sys.exit(main())
