"""Validate actual learning expression review MockMvc JSON (#727, not handcrafted examples) against the learning OpenAPI.

core #728 proxies the admin list/label responses and the tox retrain job (#729) reads label-count/export,
so the shapes they rely on and the absence of student/answer IDs are checked here too.
"""
from pathlib import Path
import json
import yaml
from jsonschema import Draft202012Validator, FormatChecker

root = Path(__file__).resolve().parents[1]
spec = yaml.safe_load((root / "contracts/openapi/learning-service.yaml").read_text(encoding="utf-8"))
snapshots = {
    "admin-list": ("/admin/expression-reviews", "get", "200"),
    "admin-label": ("/admin/expression-reviews/{reviewId}/label", "put", "200"),
    "label-count": ("/expression-reviews/label-count", "get", "200"),
    "export": ("/expression-reviews/export", "get", "200"),
}
generated = root / "backend/learning-service/build/generated-contracts"


def load(name):
    return json.loads((generated / f"learning-expression-review-{name}.json").read_text(encoding="utf-8"))


for name, (path, method, status) in snapshots.items():
    schema = spec["paths"][path][method]["responses"][status]["content"]["application/json"]["schema"]
    Draft202012Validator({**schema, "components": spec["components"]}, format_checker=FormatChecker()).validate(load(name))
    print(f"{name}: actual HTTP JSON matches {method.upper()} {path} {status}")

# 응답에 학생·답변 ID 없음(api-spec 4.1.5, NFR-SEC-05): 항목 키가 정해진 것뿐이어야 함
item_keys = {"id", "source", "text", "modelVersion", "label", "labeledAt", "createdAt"}
items = load("admin-list")["items"]
assert items and all(set(item) == item_keys for item in items), "admin list items must expose only review fields"
assert set(load("admin-label")) == item_keys
exported = load("export")["items"]
assert exported and all(set(item) == {"text", "label"} for item in exported), "export must carry only text and label"
assert all(item["label"] != "SKIP" for item in exported)
print(f"expression review: {len(items)} admin items and {len(exported)} exported rows carry no student/answer IDs")
