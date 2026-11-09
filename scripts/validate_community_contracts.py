"""Validate actual community MockMvc JSON (#388, not handcrafted examples) against public schemas."""
from pathlib import Path
import json
import yaml
from jsonschema import Draft202012Validator, FormatChecker

root = Path(__file__).resolve().parents[1]
spec = yaml.safe_load((root / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
snapshots = {
    "settings-default": "CommunitySettings",
    "settings-on": "CommunitySettings",
    "mission-posts": "CommunityPostPage",
    "my-posts": "CommunityOwnPostList",
    "admin-report": "SupportReport",
}
for name, schema in snapshots.items():
    data = json.loads((root / f"backend/core-service/build/generated-contracts/community-{name}.json").read_text(encoding="utf-8"))
    Draft202012Validator({**spec["components"]["schemas"][schema], "components": spec["components"]},
                         format_checker=FormatChecker()).validate(data)
    print(f"{name}: actual HTTP JSON matches {schema}")
# 학생 화면 목록에는 학생 ID가 나가지 않는다(작성자는 별명·꾸미기만).
posts = json.loads((root / "backend/core-service/build/generated-contracts/community-mission-posts.json").read_text(encoding="utf-8"))
assert posts["items"] and all(set(item["author"]) == {"nickname", "look"} for item in posts["items"]), "author must be nickname/look only"
print("mission-posts: no student identifiers in author")
