"""#464 지식 RAG 계약 시험: 샘플이 스키마를 통과하고, OpenAPI와 api-spec이 맞고, 가짜 구현이 계약대로 답한다.

CI(ci-contracts)는 PyYAML·jsonschema만 설치하므로 pydantic을 쓰지 않는다. 가짜 구현(fake.py)은
표준 라이브러리만 쓰므로 파일 경로로 불러온다. pydantic 모델(contracts.py)과 OpenAPI 대조는 ai 시험
(backend/ai-service/tests/knowledge)이 한다.
"""

import csv
import hashlib
import importlib.util
import json
import re
import unicodedata
import unittest
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE = ROOT / "scripts/knowledge"
SAMPLES = KNOWLEDGE / "samples"
LEARNING = ROOT / "contracts/openapi/learning-service.yaml"
AI = ROOT / "contracts/openapi/ai-service.yaml"
API_SPEC = ROOT / "docs/design/api-spec.md"
ERD = ROOT / "docs/design/erd.md"
SEED = ROOT / "backend/learning-service/db/seed/achievement_standards.sql"
FAKE = ROOT / "backend/ai-service/app/knowledge/fake.py"
REVIEW_COLUMNS = ["relationType", "standardCode", "standardStatement", "target", "targetText", "evidence",
                  "similarity", "candidateSource", "decision", "modifiedTarget", "reason", "reviewer",
                  "reviewedAt", "datasetVersion"]
DATASET_VERSION = re.compile(r"^kn-\d{8}-\d{2}$")
KNOWLEDGE_PATHS = {("get", "/knowledge/standards"), ("get", "/knowledge/thinking-types/{type}")}
AI_KNOWLEDGE_SCHEMAS = ["KnowledgeThinkingType", "KnowledgeKind", "KnowledgeSubject", "KnowledgeFallbackReason",
                        "KnowledgeRef", "KnowledgeContentItem", "KnowledgeStandard", "KnowledgeDomain",
                        "KnowledgeContent", "KnowledgeFit", "KnowledgeStandardBundle", "KnowledgeSubjectGuide",
                        "KnowledgeThinkingTypeGuide", "KnowledgeBundle"]


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def load_schema(name):
    schema = json.loads((KNOWLEDGE / "schema" / name).read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def seed_statements():
    text = SEED.read_text(encoding="utf-8")
    return dict(re.findall(r"\('([0-9가-힣()]+-\d\d)', '[^']*', '[^']*', '[^']*', '([^']*)'", text))


def section(text, start, end):
    """문서에서 start 제목 줄부터 end 제목 줄 전까지."""
    begin = text.index(start)
    return text[begin:text.index(end, begin + len(start))]


def openapi_validator(spec, name):
    resource = Resource.from_contents(spec, default_specification=DRAFT202012)
    registry = Registry().with_resource("urn:spec", resource)
    return Draft202012Validator({"$ref": f"urn:spec#/components/schemas/{name}"}, registry=registry)


def load_fake():
    spec = importlib.util.spec_from_file_location("knowledge_fake", FAKE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SampleSchemaTests(unittest.TestCase):
    """C1·C4·C8 샘플이 JSON Schema와 원문 규칙을 지킨다."""

    @classmethod
    def setUpClass(cls):
        cls.records = load_jsonl(SAMPLES / "curriculum.sample.jsonl")
        with (SAMPLES / "relations-review.sample.csv").open(encoding="utf-8", newline="") as file:
            reader = csv.DictReader(file)
            cls.header = reader.fieldnames
            cls.rows = list(reader)
        cls.evals = load_jsonl(SAMPLES / "eval.sample.jsonl")
        cls.dataset = json.loads((SAMPLES / "dataset.sample.json").read_text(encoding="utf-8"))
        cls.by_kind = {}
        for record in cls.records:
            cls.by_kind.setdefault(record["kind"], []).append(record)

    def assert_valid(self, validator, items):
        for index, item in enumerate(items):
            errors = [e.message for e in validator.iter_errors(item)]
            self.assertEqual(errors, [], f"{index}: {item.get('id') or item.get('code') or item}")

    def test_records_pass_c1_schema(self):
        self.assert_valid(load_schema("curriculum-record.schema.json"), self.records)

    def test_sample_scope_matches_issue(self):
        standards = self.by_kind["standard"]
        self.assertTrue(13 <= len(standards) <= 17)  # 초3 1학기 15개 안팎
        self.assertEqual({s["subject"] for s in standards}, {"국어", "수학", "과학", "사회", "도덕"})
        self.assertTrue(all(s["grades"] == [3] and s["semesters"] == ["3-1"] for s in standards))
        self.assertTrue(all(s["noticeGradeBand"] == "초3~4" for s in standards))
        explained = [s for s in standards if s["explanation"]]
        self.assertTrue(explained and len(explained) < len(standards))  # 해설 있는·없는 성취기준 둘 다
        self.assertEqual({t["type"] for t in self.by_kind["thinking_type"]},
                         {"ANALYZE", "EVALUATE", "CREATE", "SOLVE", "REFLECT"})
        self.assertEqual({g["subject"] for g in self.by_kind["subject_guide"]}, {"국어", "수학", "과학", "사회", "도덕"})
        self.assertTrue(all(r["reviewed"] is False for r in self.records))  # 사람 확인 전 표시

    def test_standard_statements_match_seed_and_explanations_quote_code(self):
        seed = seed_statements()
        for standard in self.by_kind["standard"]:
            self.assertEqual(standard["statement"], seed[standard["code"]], standard["code"])
            if standard["explanation"]:
                self.assertTrue(standard["explanation"].startswith(f"[{standard['code']}]"), standard["code"])
            else:
                self.assertTrue(any("해설" in note for note in standard.get("notes", [])), standard["code"])

    def test_ids_links_and_content_hash(self):
        ids = [r.get("id") or r.get("code") or r.get("type") for r in self.records]
        self.assertEqual(len(ids), len(set(ids)))
        domains = {d["id"]: d for d in self.by_kind["domain"]}
        for standard in self.by_kind["standard"]:
            self.assertIn(domains[standard["domainId"]]["scope"], ("BOTH", "STANDARD_GROUP"))
        expected = set()
        for domain in domains.values():
            for key, category in (("knowledge", "K"), ("process", "P"), ("values", "V")):
                for item in domain[key]:
                    digest = hashlib.sha256(unicodedata.normalize("NFC", item["text"]).encode()).hexdigest()[:8]
                    expected.add((f"{domain['id']}:{category}:{digest}", item["text"], item["group"]))
        actual = {(c["id"], c["text"], c["group"]) for c in self.by_kind["content"]}
        self.assertEqual(actual, expected)
        for content in self.by_kind["content"]:
            self.assertIn(domains[content["domainId"]]["scope"], ("BOTH", "CONTENT_SYSTEM"))

    def test_excluded_sources_are_absent(self):
        """평가원 성취수준·교육청(서울특별시·경기도) 자료 문장은 넣지 않는다(교육청 자료는 학기 대응
        출처 표기만)."""
        for record in self.records:
            doc = record["source"]["doc"]
            for word in ("성취수준", "평가원", "경기도", "교육청"):
                self.assertNotIn(word, doc)
        for standard in self.by_kind["standard"]:
            self.assertIn("코드↔학기만", standard["semesterSource"])

    def test_thinking_types_are_our_words_with_attribution(self):
        for record in self.by_kind["thinking_type"]:
            texts = record["questionMust"] + record["questionMustNot"] + [e["description"] for e in record["elements"]]
            for text in texts:
                self.assertIsNone(re.search(r"[A-Za-z]{4,}", text), text)  # 영어 원문 문장을 옮기지 않음
            for basis in record["basis"]:
                if "블룸" in basis["framework"] or "AAC&U" in basis["framework"]:
                    self.assertIn("참고", basis["attribution"])
                if "AAC&U" in basis["framework"]:
                    self.assertIn("보증을 받은 내용이 아님", basis["attribution"])
                    self.assertIn("원문", basis["attribution"])

    def test_review_file_passes_c4_schema_and_points_to_samples(self):
        self.assertEqual(self.header, REVIEW_COLUMNS)
        self.assert_valid(load_schema("relation-review.schema.json"), self.rows)
        codes = {s["code"]: s for s in self.by_kind["standard"]}
        contents = {c["id"] for c in self.by_kind["content"]}
        self.assertEqual({r["decision"] for r in self.rows}, {"", "ACCEPT", "REJECT", "MODIFY"})
        for row in self.rows:
            standard = codes[row["standardCode"]]
            self.assertEqual(row["standardStatement"], standard["statement"])
            self.assertEqual(row["datasetVersion"], self.dataset["version"])
            for target in filter(None, (row["target"], row["modifiedTarget"])):
                if row["relationType"] == "COVERS":
                    self.assertIn(target, contents)
                elif row["relationType"] == "PREREQUISITE":
                    self.assertIn(target, seed_statements())
            quote = re.match(r"^(문장|해설): (.+)$", row["evidence"])
            if quote:
                source = standard["statement"] if quote[1] == "문장" else standard["explanation"] or ""
                self.assertIn(quote[2], source, row["evidence"])

    def test_eval_set_passes_c8_schema(self):
        self.assert_valid(load_schema("eval-record.schema.json"), self.evals)
        self.assertEqual({e["kind"] for e in self.evals}, {"PARAPHRASE", "THEME", "RELATION"})
        seed = seed_statements()
        for record in self.evals:
            expected = record["expected"]
            codes = expected.get("codes", []) + [c for v in expected.get("byType", {}).values() for c in v]
            for code in codes:
                self.assertIn(code, seed)

    def test_dataset_version_follows_c9(self):
        self.assertRegex(self.dataset["version"], DATASET_VERSION)
        erd = section(ERD.read_text(encoding="utf-8"), "### 4.5 교육과정 지식 RAG", "\n---\n")
        self.assertIn("`kn-YYYYMMDD-NN`", erd)
        for table in ("knowledge_dataset", "knowledge_chunk", "knowledge_standard_semester", "knowledge_fits",
                      "knowledge_prerequisite", "knowledge_covers"):
            self.assertIn(f"`{table}`", erd)


class OpenApiSpecTests(unittest.TestCase):
    """C5·C6·C7: OpenAPI와 api-spec이 같은 경로·사유·상한을 말한다."""

    @classmethod
    def setUpClass(cls):
        cls.learning = yaml.safe_load(LEARNING.read_text(encoding="utf-8"))
        cls.ai = yaml.safe_load(AI.read_text(encoding="utf-8"))
        text = API_SPEC.read_text(encoding="utf-8")
        cls.spec_412 = section(text, "#### 4.1.2 교육과정 지식 내부 API", "### 4.2 ai-service")
        cls.spec_424 = section(text, "#### 4.2.4 지식 임베딩", "#### 4.2.5")
        cls.spec_425 = section(text, "#### 4.2.5 미션 초안 근거 칸", "### 4.3 scoring-service")
        cls.spec_42 = section(text, "### 4.2 ai-service", "#### 4.2.2")

    @staticmethod
    def planned(spec):
        return {(method, path): operation["x-implementation-status"]
                for path, methods in spec["paths"].items() for method, operation in methods.items()
                if isinstance(operation, dict) and operation.get("x-implementation-status")}

    def test_learning_knowledge_paths_match_api_spec(self):
        self.assertEqual(self.planned(self.learning), {})
        actual = {(method, path) for path, methods in self.learning["paths"].items()
                  if path.startswith("/knowledge/") for method in methods}
        self.assertEqual(actual, KNOWLEDGE_PATHS)
        rows = set()
        for method, path in re.findall(r"^\| (GET|POST) \| `(/internal/knowledge/[^`?]+)", self.spec_412, re.M):
            rows.add((method.lower(), path.removeprefix("/internal")))
        self.assertEqual(rows, KNOWLEDGE_PATHS)
        for method, path in KNOWLEDGE_PATHS:
            operation = self.learning["paths"][path][method]
            self.assertEqual(operation["parameters"][0], {"$ref": "#/components/parameters/SystemRole"})
            self.assertTrue({"200", "400", "401", "403"} <= set(operation["responses"]))
            if method == "post":
                self.assertIn("409", operation["responses"])
        names = {p["name"] for p in self.learning["paths"]["/knowledge/standards"]["get"]["parameters"] if "name" in p}
        self.assertEqual(names, {"codes", "grade", "thinkingType"})

    def test_fallback_reasons_match_everywhere(self):
        learning = self.learning["components"]["schemas"]["KnowledgeFallbackReason"]["enum"]
        ai = self.ai["components"]["schemas"]["KnowledgeFallbackReason"]["enum"]
        line = next(line for line in self.spec_412.splitlines() if line.startswith("- 대체 사유(`reason`)"))
        documented = [code for code in re.findall(r"`([A-Z_]+)`", line)]
        self.assertEqual(learning, ai)
        self.assertEqual(documented, learning)
        self.assertEqual(learning, ["NO_ACTIVE_DATASET", "CODE_NOT_FOUND"])
        for spec in (self.learning, self.ai):
            description = spec["components"]["schemas"]["KnowledgeFallbackReason"]["description"]
            for removed in ("BELOW_THRESHOLD", "NO_CANDIDATE", "NO_REVIEWED_RELATION"):
                self.assertNotIn(removed, description)

    def test_ai_knowledge_schemas_are_copies_of_learning(self):
        for name in AI_KNOWLEDGE_SCHEMAS:
            self.assertEqual(self.ai["components"]["schemas"][name], self.learning["components"]["schemas"][name], name)

    def test_embedding_contract_c6(self):
        # #467에서 구현해 planned 표시를 뗐다(남은 ai 구현 전 항목은 C7 칸뿐)
        self.assertEqual(self.planned(self.ai), {})
        self.assertNotIn("x-implementation-status", self.ai["paths"]["/embeddings"]["post"])
        self.assertIn("`/internal/embeddings`", self.spec_42)
        texts = self.ai["components"]["schemas"]["EmbeddingRequest"]["properties"]["texts"]
        fake = load_fake()
        self.assertEqual((texts["minItems"], texts["maxItems"], texts["items"]["maxLength"]),
                         (1, fake.MAX_TEXTS, fake.MAX_CHARS))
        self.assertEqual((fake.MAX_TEXTS, fake.MAX_CHARS, fake.DIMENSIONS), (64, 8000, 1536))
        for phrase in ("1~64개", "1~8,000자", "1536차원", "`KNOWLEDGE_EMBEDDING`", f"`{fake.FAKE_EMBEDDING_MODEL}`"):
            self.assertIn(phrase, self.spec_424)
        responses = self.ai["paths"]["/embeddings"]["post"]["responses"]
        self.assertTrue({"200", "400", "401", "502", "503"} <= set(responses))
        self.assertNotIn("422", responses)

    def test_mission_draft_knowledge_fields_c7(self):
        schemas = self.ai["components"]["schemas"]
        knowledge = schemas["MissionDraftRequest"]["properties"]["knowledge"]
        sources = schemas["MissionDraftResponse"]["properties"]["sources"]
        self.assertIn({"$ref": "#/components/schemas/KnowledgeBundle"}, knowledge["anyOf"])
        self.assertEqual(sources["items"], {"$ref": "#/components/schemas/KnowledgeRef"})
        for field in (knowledge, sources):
            self.assertEqual(field["x-implementation-status"], "planned-issue-470")
        self.assertNotIn("knowledge", schemas["MissionDraftRequest"]["required"])
        self.assertNotIn("sources", schemas["MissionDraftResponse"]["required"])
        self.assertIn("응답 본문 그대로", self.spec_425)
        self.assertIn("sources:[{kind, id, datasetVersion}]", self.spec_425)

    def test_all_references_resolve(self):
        for spec in (self.learning, self.ai):
            def visit(node, spec=spec):
                if isinstance(node, dict):
                    if "$ref" in node:
                        target = spec
                        for part in node["$ref"][2:].split("/"):
                            target = target[part]
                        self.assertIsInstance(target, dict)
                    for value in node.values():
                        visit(value)
                elif isinstance(node, list):
                    for value in node:
                        visit(value)
            visit(spec)


class FakeFollowsContractTests(unittest.TestCase):
    """가짜 learning 지식 API·가짜 임베딩의 응답이 OpenAPI 스키마를 통과한다."""

    @classmethod
    def setUpClass(cls):
        cls.fake = load_fake()
        cls.api = cls.fake.FakeKnowledgeApi()
        cls.embedder = cls.api.embedder
        cls.learning = yaml.safe_load(LEARNING.read_text(encoding="utf-8"))
        cls.ai = yaml.safe_load(AI.read_text(encoding="utf-8"))
        cls.headers = {"X-Internal-Token": "t", "X-User-Role": "SYSTEM"}

    def assert_schema(self, spec, name, payload):
        errors = [e.message for e in openapi_validator(spec, name).iter_errors(payload)]
        self.assertEqual(errors, [], name)

    def vector(self, text):
        return self.embedder.embed_sync([text])["vectors"][0]

    def call(self, method, path, body=None, query=None, headers=None):
        return self.api.handle(method, path, query or {}, body, self.headers if headers is None else headers)

    def test_embedder_keeps_order_and_limits(self):
        response = self.embedder.embed_sync(["가", "나눗셈", "가"])
        self.assert_schema(self.ai, "EmbeddingResponse", response)
        self.assertEqual((response["model"], response["dimensions"]), ("fake-bigram-v1", 1536))
        first, second, third = response["vectors"]
        self.assertEqual(first, third)
        self.assertNotEqual(first, second)
        self.assertAlmostEqual(sum(v * v for v in second), 1.0, places=9)
        for bad in ([], ["x"] * 65, ["x" * 8001], ["   "]):
            with self.assertRaises(self.fake.FakeError) as raised:
                self.embedder.embed_sync(bad)
            self.assertEqual((raised.exception.status, raised.exception.code), (400, "VALIDATION_FAILED"))

    def test_standards_bundle(self):
        status, body = self.call("GET", "/internal/knowledge/standards",
                                 query={"codes": "4수01-06,4국02-04,4수99-99", "grade": "3", "thinkingType": "SOLVE"})
        self.assertEqual(status, 200)
        self.assert_schema(self.learning, "KnowledgeBundle", body)
        self.assert_schema(self.ai, "KnowledgeBundle", body)  # C7 knowledge 칸에 그대로 넣을 수 있음
        self.assertEqual([i["standard"]["code"] for i in body["items"]], ["4수01-06", "4국02-04"])
        self.assertEqual(body["missingCodes"], ["4수99-99"])
        self.assertIsNone(body["reason"])
        self.assertEqual({g["subject"] for g in body["subjectGuides"]}, {"수학", "국어"})
        self.assertEqual(body["thinkingType"]["type"], "SOLVE")
        solve = body["items"][0]
        self.assertTrue(solve["gradeMatch"])
        self.assertIn({"thinkingType": "SOLVE", "reason": solve["fits"][0]["reason"]}, solve["fits"])
        self.assertTrue(all(c["ref"]["kind"] == "CONTENT" for c in solve["covers"]))
        self.assertTrue(solve["standard"]["explanation"].startswith("[4수01-06]"))
        _, none = self.call("GET", "/internal/knowledge/standards", query={"codes": "4수99-99"})
        self.assertEqual((none["reason"], none["items"]), ("CODE_NOT_FOUND", []))

    def test_thinking_type_and_inactive_dataset(self):
        status, body = self.call("GET", "/internal/knowledge/thinking-types/ANALYZE")
        self.assertEqual(status, 200)
        self.assert_schema(self.learning, "KnowledgeThinkingTypeResponse", body)
        inactive = self.fake.FakeKnowledgeApi(active=False)
        for method, path, query, body_, schema in [
            ("GET", "/internal/knowledge/standards", {"codes": "4수01-06"}, None, "KnowledgeBundle"),
            ("GET", "/internal/knowledge/thinking-types/SOLVE", {}, None, "KnowledgeThinkingTypeResponse"),
        ]:
            status, payload = inactive.handle(method, path, query, body_, self.headers)
            self.assertEqual(status, 200)
            self.assert_schema(self.learning, schema, payload)
            self.assertEqual((payload["reason"], payload["datasetVersion"]), ("NO_ACTIVE_DATASET", None))

    def test_auth_and_removed_vector_routes_return_problem(self):
        cases = [({}, 401, "UNAUTHENTICATED"), ({"X-Internal-Token": "t", "X-User-Role": "PARENT"}, 403, "FORBIDDEN")]
        for headers, status_code, code in cases:
            status, problem = self.call("GET", "/internal/knowledge/thinking-types/SOLVE", headers=headers)
            self.assertEqual((status, problem["code"]), (status_code, code))
            self.assert_schema(self.learning, "Problem", problem)
        for endpoint in ("search", "theme-candidates", "learned"):
            status, problem = self.call("POST", f"/internal/knowledge/{endpoint}", {})
            self.assertEqual((status, problem["code"]), (404, "NOT_FOUND"))


    def test_chunk_text_follows_erd_rule(self):
        chunk = self.api.chunks[("STANDARD", "4수01-06")]
        record = chunk["record"]
        self.assertEqual(chunk["text"], f"[4수01-06] {record['statement']}\n해설: {record['explanation']}")
        self.assertEqual(chunk["contentHash"], hashlib.sha256(chunk["text"].encode("utf-8")).hexdigest())
        guide = self.api.chunks[("SUBJECT_GUIDE", "국어:guide")]
        self.assertEqual((guide["grades"], guide["semesters"]), ([], []))
        uncovered = next(c for c in self.api.chunks.values() if c["kind"] == "CONTENT" and not c["semesters"])
        self.assertEqual(uncovered["grades"], [])  # 확인된 covers가 없으면 학년·학기 없음


if __name__ == "__main__":
    unittest.main()
