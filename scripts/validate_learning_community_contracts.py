"""Validate actual learning community MockMvc JSON (#386, not handcrafted examples) against the learning OpenAPI.

core #388 CommunityClient reads these internal responses, so the shapes it relies on are checked here too.
"""
from pathlib import Path
import json
import yaml
from jsonschema import Draft202012Validator, FormatChecker

root = Path(__file__).resolve().parents[1]
spec = yaml.safe_load((root / "contracts/openapi/learning-service.yaml").read_text(encoding="utf-8"))
snapshots = {
    "share-created": ("/community/posts", "post", "201"),
    "share-existing": ("/community/posts", "post", "200"),
    "post-detail": ("/community/posts/{postId}", "get", "200"),
    "post-author": ("/community/posts/{postId}/author", "get", "200"),
    "mission-posts": ("/community/missions/{missionId}/posts", "get", "200"),
    "student-posts-student": ("/community/students/{studentId}/posts", "get", "200"),
    "student-posts-parent": ("/community/students/{studentId}/posts", "get", "200"),
    "reaction-created": ("/community/posts/{postId}/reactions/{reaction}", "put", "200"),
    "reaction-deleted": ("/community/posts/{postId}/reactions/{reaction}", "delete", "200"),
    "moderation": ("/community/posts/{postId}/moderation", "put", "200"),
    "visibility": ("/students/{studentId}/community-visibility", "put", "200"),
}
generated = root / "backend/learning-service/build/generated-contracts"


def load(name):
    return json.loads((generated / f"learning-community-{name}.json").read_text(encoding="utf-8"))


for name, (path, method, status) in snapshots.items():
    schema = spec["paths"][path][method]["responses"][status]["content"]["application/json"]["schema"]
    Draft202012Validator({**schema, "components": spec["components"]}, format_checker=FormatChecker()).validate(load(name))
    print(f"{name}: actual HTTP JSON matches {method.upper()} {path} {status}")

# core CommunityClient가 읽는 필드: 공유 postId, 목록 items[].postId·studentId·answer·myReactions, 원문 postId·studentId·status
assert load("share-created")["created"] is True and load("share-existing")["created"] is False
items = load("mission-posts")["items"]
assert items and all({"postId", "studentId", "answer", "myReactions"} <= set(item) for item in items)
assert all("reactions" not in item for item in items), "mission list must not expose reaction counts"
assert all(set(item["answer"]) == {"inputType", "text", "content"} for item in items), "answer must not carry memo/judgment"
assert {"postId", "studentId", "status"} <= set(load("post-detail"))
# 친구 방 구경(#707·#708): 작성자 확인은 postId·studentId만(답변·미션·상태·반응 없음)
assert set(load("post-author")) == {"postId", "studentId"}, "post author check must expose only postId and studentId"
print("community: fields read by core CommunityClient are present; no reaction counts in mission list")

# #825: core 공개 계약 CommunityAnswer(입력 방식별 content oneOf)는 learning 실제 공유 답변을 그대로 받아야 한다.
core_spec = yaml.safe_load((root / "contracts/openapi/core-service.yaml").read_text(encoding="utf-8"))
core_answer = Draft202012Validator({**core_spec["components"]["schemas"]["CommunityAnswer"], "components": core_spec["components"]},
                                   format_checker=FormatChecker())
answers = [item["answer"] for item in items] + [load("post-detail")["answer"]]
answers += [item["answer"] for name in ("student-posts-student", "student-posts-parent") for item in load(name)["items"]]
for answer in answers:
    core_answer.validate(answer)
print(f"community: {len(answers)} learning shared answers match core CommunityAnswer "
      f"({', '.join(sorted({a['inputType'] for a in answers}))})")
