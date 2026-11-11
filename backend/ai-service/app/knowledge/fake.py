"""지식 RAG 가짜 구현 (#464).

샘플로 답하는 가짜 learning 지식 API(C5)와 고정 벡터를 돌려주는 가짜 임베딩(C6).

- 표준 라이브러리만 쓴다. 계약 시험(scripts/tests/test_knowledge_contracts.py)이
  pydantic 없이 불러 쓰기 때문. 응답은 HTTP로 오가는 JSON 모양(camelCase dict) 그대로다
- pydantic 모델(contracts.py)로 받으려면 `as_embedder()`·`as_knowledge_api()`(안에서만 import)
- HTTP로 시험하려면 `mock_transport()`(httpx, 안에서만 import) 또는 `serve()`(표준 HTTP 서버)
- 샘플: scripts/knowledge/samples/ (curriculum·relations-review·dataset).
  확인 파일의 ACCEPT·MODIFY 행만 관계로 쓴다

가짜 벡터(api-spec 4.2.4와 같은 규칙, learning 시험 대역이 같은 값을 만들 수 있게):
NFC·소문자·공백 제거 → 글자 2개씩(한 글자면 그 글자) → 조각마다 SHA-256의
앞 4바이트(big endian) % 차원 = 위치, 5번째 바이트가 짝수면 +1 홀수면 -1을 더함
→ 길이 1로 맞춤(모두 0이면 0번 위치 1.0).
"""

import csv
import hashlib
import json
import math
import re
import threading
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

SAMPLES_DIR = Path(__file__).resolve().parents[4] / "scripts" / "knowledge" / "samples"
FAKE_EMBEDDING_MODEL = "fake-bigram-v1"
DIMENSIONS = 1536  # 기준안(C6)
MAX_TEXTS = 64  # 기준안(C6)
MAX_CHARS = 8000  # 기준안(C6)
MAX_CODES = 10  # 기준안(C5)
MAX_K = 20
MAX_THEME_K = 10
MAX_CONCEPTS = 20
DEFAULT_MIN_SIMILARITY = 0.7
THINKING_TYPES = ("ANALYZE", "EVALUATE", "CREATE", "SOLVE", "REFLECT")
KINDS = ("STANDARD", "DOMAIN", "CONTENT", "SUBJECT_GUIDE", "THINKING_TYPE")
SUBJECTS = ("국어", "도덕", "사회", "수학", "과학")
CATEGORY_NAME = {"K": "지식⋅이해", "P": "과정⋅기능", "V": "가치⋅태도"}
SEMESTER = re.compile(r"^[3-6]-[12]$")


class FakeError(Exception):
    """계약의 4xx 응답. status·code는 api-spec 4.1.2·4.2.4 오류 표와 같다."""

    def __init__(self, status: int, code: str, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.code = code
        self.detail = detail

    def problem(self, path: str) -> dict[str, Any]:
        return {
            "type": "about:blank",
            "title": self.code,
            "status": self.status,
            "code": self.code,
            "detail": self.detail,
            "instance": path,
            "traceId": "fake",
        }


def _bad(detail: str) -> FakeError:
    return FakeError(400, "VALIDATION_FAILED", detail)


# ---- C6 가짜 임베딩
def fake_vector(text: str, dimensions: int = DIMENSIONS) -> list[float]:
    normalized = re.sub(r"\s+", "", unicodedata.normalize("NFC", text).lower())
    pieces = [normalized[i : i + 2] for i in range(len(normalized) - 1)] or [normalized]
    vector = [0.0] * dimensions
    for piece in pieces:
        digest = hashlib.sha256(piece.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        vector[index] += 1.0 if digest[4] % 2 == 0 else -1.0
    norm = math.sqrt(sum(v * v for v in vector))
    if norm == 0:
        vector[0] = 1.0
        return vector
    return [v / norm for v in vector]


def cosine(a: list[float], b: list[float]) -> float:
    """길이 1인 벡터끼리 코사인 유사도(0~1로 자름)."""
    return max(0.0, min(1.0, sum(x * y for x, y in zip(a, b, strict=True))))


class FakeEmbedder:
    """C6 `POST /internal/embeddings`의 가짜. 같은 글은 언제나 같은 벡터."""

    def __init__(self, dimensions: int = DIMENSIONS, model: str = FAKE_EMBEDDING_MODEL) -> None:
        self.dimensions = dimensions
        self.model = model

    def embed_sync(self, texts: Any) -> dict[str, Any]:
        if not isinstance(texts, list) or not 1 <= len(texts) <= MAX_TEXTS:
            raise _bad(f"texts는 1~{MAX_TEXTS}개")
        for text in texts:
            if not isinstance(text, str) or not text.strip() or len(text) > MAX_CHARS:
                raise _bad(f"texts 항목은 공백 아닌 1~{MAX_CHARS}자")
        vectors = [fake_vector(text, self.dimensions) for text in texts]
        return {"model": self.model, "dimensions": self.dimensions, "vectors": vectors}

    async def embed(self, texts: list[str]) -> dict[str, Any]:
        return self.embed_sync(texts)

    def handle(self, body: Any) -> dict[str, Any]:
        if not isinstance(body, dict) or set(body) != {"texts"}:
            raise _bad("본문은 {texts}")
        return self.embed_sync(body["texts"])

    def as_embedder(self) -> Any:
        """contracts.Embedder를 만족하는 객체(EmbeddingResponse를 돌려줌)."""
        from app.knowledge.contracts import EmbeddingResponse

        fake = self

        class _Embedder:
            async def embed(self, texts: list[str]) -> EmbeddingResponse:
                return EmbeddingResponse.model_validate(fake.embed_sync(texts))

        return _Embedder()


# ---- C2 조각 본문 규칙(erd 4.5): learning 적재(#466)와 같은 글을 만든다
def chunk_text(record: dict[str, Any]) -> str:
    kind = record["kind"]
    if kind == "standard":
        text = f"[{record['code']}] {record['statement']}"
        if record["explanation"]:
            text += f"\n해설: {record['explanation']}"
        return text
    if kind == "domain":
        lines = [f"{record['subject']} {record['noticeGradeBand']} {record['area']}"]
        if record["coreIdeas"]:
            lines.append("핵심 아이디어: " + " ".join(record["coreIdeas"]))
        for key, name in (
            ("knowledge", "지식⋅이해"),
            ("process", "과정⋅기능"),
            ("values", "가치⋅태도"),
        ):
            if record[key]:
                lines.append(f"{name}: " + "; ".join(item["text"] for item in record[key]))
        if record["considerations"]:
            lines.append("적용 시 고려 사항: " + " ".join(record["considerations"]))
        if record.get("activities"):
            lines.append("탐구 활동: " + "; ".join(record["activities"]))
        return "\n".join(lines)
    if kind == "content":
        group = f"{record['group']} - " if record["group"] else ""
        head = f"{record['subject']} {record['noticeGradeBand']} {record['area']}"
        return f"{head} {CATEGORY_NAME[record['category']]}: {group}{record['text']}"
    if kind == "subject_guide":
        return "\n".join(
            [f"{record['subject']} 교수⋅학습:", *record["teaching"], "평가:", *record["assessment"]]
        )
    if kind == "thinking_type":
        lines = [f"{record['name']}({record['type']})"]
        lines.append("근거: " + " ".join(b["attribution"] for b in record["basis"]))
        lines.append(
            "요소: " + "; ".join(f"{e['label']}: {e['description']}" for e in record["elements"])
        )
        lines.append("질문에 꼭: " + " ".join(record["questionMust"]))
        lines.append("피할 것: " + " ".join(record["questionMustNot"]))
        return "\n".join(lines)
    raise ValueError(f"모르는 kind: {kind}")


def content_hash(text: str) -> str:
    """C2 knowledge_chunk.content_hash: NFC 본문의 SHA-256 16진수."""
    return hashlib.sha256(unicodedata.normalize("NFC", text).encode("utf-8")).hexdigest()


def _band_grades(band: str) -> list[int]:
    start, end = re.match(r"^초(\d)~(\d)$", band).groups()
    return list(range(int(start), int(end) + 1))


def _semester_key(semester: str) -> tuple[int, int]:
    grade, term = semester.split("-")
    return int(grade), int(term)


# ---- C5 가짜 learning 지식 API
class FakeKnowledgeApi:
    """샘플을 활성 판 하나로 올린 learning 지식 API의 가짜. 다섯 경로 모두 계약대로 답한다.

    active=False면 활성 판이 없는 learning(모든 응답 reason NO_ACTIVE_DATASET)을 흉내 낸다.
    """

    def __init__(
        self,
        samples_dir: Path | None = None,
        embedder: FakeEmbedder | None = None,
        active: bool = True,
    ) -> None:
        directory = samples_dir or SAMPLES_DIR
        self.embedder = embedder or FakeEmbedder()
        self.active = active
        dataset = json.loads((directory / "dataset.sample.json").read_text(encoding="utf-8"))
        self.version: str = dataset["version"]
        self.embedding_model: str = self.embedder.model
        records = [
            json.loads(line)
            for line in (directory / "curriculum.sample.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        ]
        with (directory / "relations-review.sample.csv").open(encoding="utf-8", newline="") as file:
            rows = list(csv.DictReader(file))
        self._load(records, rows)

    # -- 적재(learning #466 규칙을 메모리에서 흉내 냄)
    def _load(self, records: list[dict[str, Any]], rows: list[dict[str, str]]) -> None:
        self.standards = {r["code"]: r for r in records if r["kind"] == "standard"}
        self.domains = {r["id"]: r for r in records if r["kind"] == "domain"}
        self.contents = {r["id"]: r for r in records if r["kind"] == "content"}
        self.guides = {r["subject"]: r for r in records if r["kind"] == "subject_guide"}
        self.types = {r["type"]: r for r in records if r["kind"] == "thinking_type"}
        self.fits: dict[str, list[tuple[str, str]]] = {}
        self.covers: dict[str, list[str]] = {}
        self.covered_by: dict[str, list[str]] = {}
        for row in rows:
            if row["decision"] not in ("ACCEPT", "MODIFY"):
                continue
            target = row["modifiedTarget"] if row["decision"] == "MODIFY" else row["target"]
            code = row["standardCode"]
            if row["relationType"] == "FITS":
                self.fits.setdefault(code, []).append((target, row["reason"]))
            elif row["relationType"] == "COVERS":
                self.covers.setdefault(code, []).append(target)
                self.covered_by.setdefault(target, []).append(code)
        self.chunks: dict[tuple[str, str], dict[str, Any]] = {}
        for code, record in self.standards.items():
            self._chunk(
                "STANDARD",
                code,
                record,
                grades=record["grades"],
                semesters=record["semesters"],
                subject=record["subject"],
                area=record["area"],
                standard_code=code,
                domain_id=record["domainId"],
            )
        for content_id, record in self.contents.items():
            linked = [self.standards[c] for c in self.covered_by.get(content_id, [])]
            self._chunk(
                "CONTENT",
                content_id,
                record,
                grades=sorted({g for s in linked for g in s["grades"]}),
                semesters=sorted({m for s in linked for m in s["semesters"]}, key=_semester_key),
                subject=record["subject"],
                area=record["area"],
                domain_id=record["domainId"],
            )
        for domain_id, record in self.domains.items():
            if record["scope"] == "CONTENT_SYSTEM":
                linked_codes = {
                    c
                    for cid, r in self.contents.items()
                    if r["domainId"] == domain_id
                    for c in self.covered_by.get(cid, [])
                }
            else:
                linked_codes = {c for c, s in self.standards.items() if s["domainId"] == domain_id}
            semesters = {m for c in linked_codes for m in self.standards[c]["semesters"]}
            self._chunk(
                "DOMAIN",
                domain_id,
                record,
                grades=_band_grades(record["noticeGradeBand"]),
                semesters=sorted(semesters, key=_semester_key),
                subject=record["subject"],
                area=record["area"],
                domain_id=domain_id,
            )
        for subject, record in self.guides.items():
            self._chunk(
                "SUBJECT_GUIDE", record["id"], record, grades=[], semesters=[], subject=subject
            )
        for type_code, record in self.types.items():
            self._chunk(
                "THINKING_TYPE", type_code, record, grades=[], semesters=[], thinking_type=type_code
            )

    def _chunk(
        self,
        kind: str,
        chunk_id: str,
        record: dict[str, Any],
        *,
        grades: list[int],
        semesters: list[str],
        subject: str | None = None,
        area: str | None = None,
        standard_code: str | None = None,
        domain_id: str | None = None,
        thinking_type: str | None = None,
    ) -> None:
        text = chunk_text(record)
        self.chunks[(kind, chunk_id)] = {
            "kind": kind,
            "id": chunk_id,
            "subject": subject,
            "area": area,
            "standardCode": standard_code,
            "domainId": domain_id,
            "thinkingType": thinking_type,
            "grades": grades,
            "semesters": semesters,
            "text": text,
            "contentHash": content_hash(text),
            "record": record,
            "embedding": fake_vector(text, self.embedder.dimensions),
        }

    # -- 보기 모양(api-spec 4.1.2 응답 칸)
    def ref(self, kind: str, chunk_id: str) -> dict[str, str]:
        return {"kind": kind, "id": chunk_id, "datasetVersion": self.version}

    def _standard_view(self, code: str) -> dict[str, Any]:
        r = self.standards[code]
        return {
            "code": code,
            "subject": r["subject"],
            "grades": r["grades"],
            "semesters": r["semesters"],
            "noticeGradeBand": r["noticeGradeBand"],
            "area": r["area"],
            "statement": r["statement"],
            "explanation": r["explanation"],
            "ref": self.ref("STANDARD", code),
        }

    def _domain_view(self, domain_id: str) -> dict[str, Any]:
        r = self.domains[domain_id]
        return {
            "id": domain_id,
            "subject": r["subject"],
            "area": r["area"],
            "scope": r["scope"],
            "coreIdeas": r["coreIdeas"],
            "knowledge": r["knowledge"],
            "process": r["process"],
            "values": r["values"],
            "considerations": r["considerations"],
            "activities": r.get("activities", []),
            "ref": self.ref("DOMAIN", domain_id),
        }

    def _content_view(self, content_id: str) -> dict[str, Any]:
        r = self.contents[content_id]
        return {
            "id": content_id,
            "domainId": r["domainId"],
            "category": r["category"],
            "group": r["group"],
            "text": r["text"],
            "ref": self.ref("CONTENT", content_id),
        }

    def _guide_view(self, subject: str) -> dict[str, Any]:
        r = self.guides[subject]
        return {
            "subject": subject,
            "teaching": r["teaching"],
            "assessment": r["assessment"],
            "ref": self.ref("SUBJECT_GUIDE", r["id"]),
        }

    def _type_view(self, type_code: str) -> dict[str, Any]:
        r = self.types[type_code]
        return {
            "type": type_code,
            "name": r["name"],
            "basis": r["basis"],
            "elements": [
                {"code": e["code"], "label": e["label"], "description": e["description"]}
                for e in r["elements"]
            ],
            "questionMust": r["questionMust"],
            "questionMustNot": r["questionMustNot"],
            "ref": self.ref("THINKING_TYPE", type_code),
        }

    # -- 다섯 경로
    def standards_sync(
        self, codes: list[str], grade: int | None = None, thinking_type: str | None = None
    ) -> dict[str, Any]:
        if not 1 <= len(codes) <= MAX_CODES:
            raise _bad(f"codes는 1~{MAX_CODES}개")
        if grade is not None and not 3 <= grade <= 6:
            raise _bad("grade는 3~6")
        if thinking_type is not None and thinking_type not in THINKING_TYPES:
            raise _bad("thinkingType 값 밖")
        if not self.active:
            return {
                "datasetVersion": None,
                "items": [],
                "missingCodes": codes,
                "subjectGuides": [],
                "thinkingType": None,
                "reason": "NO_ACTIVE_DATASET",
            }
        items, missing, subjects = [], [], []
        for code in codes:
            record = self.standards.get(code)
            if record is None:
                missing.append(code)
                continue
            if record["subject"] not in subjects:
                subjects.append(record["subject"])
            items.append(
                {
                    "standard": self._standard_view(code),
                    "domain": self._domain_view(record["domainId"])
                    if record["domainId"] in self.domains
                    else None,
                    "covers": [self._content_view(c) for c in self.covers.get(code, [])],
                    "fits": [
                        {"thinkingType": t, "reason": reason}
                        for t, reason in self.fits.get(code, [])
                    ],
                    "gradeMatch": None if grade is None else grade in record["grades"],
                }
            )
        return {
            "datasetVersion": self.version,
            "items": items,
            "missingCodes": missing,
            "subjectGuides": [self._guide_view(s) for s in subjects if s in self.guides],
            "thinkingType": self._type_view(thinking_type) if thinking_type in self.types else None,
            "reason": None if items else "CODE_NOT_FOUND",
        }

    def thinking_type_sync(self, type_code: str) -> dict[str, Any]:
        if type_code not in THINKING_TYPES:
            raise _bad("type 값 밖")
        if not self.active:
            return {"datasetVersion": None, "guide": None, "reason": "NO_ACTIVE_DATASET"}
        return {"datasetVersion": self.version, "guide": self._type_view(type_code), "reason": None}

    def _check_vector(self, body: dict[str, Any]) -> list[float]:
        vector, model = body.get("vector"), body.get("embeddingModel")
        if not isinstance(vector, list) or not vector or not isinstance(model, str) or not model:
            raise _bad("vector·embeddingModel 필수")
        if model != self.embedding_model or len(vector) != self.embedder.dimensions:
            raise FakeError(
                409,
                "KNOWLEDGE_EMBEDDING_MISMATCH",
                f"활성 판 임베딩은 {self.embedding_model}·{self.embedder.dimensions}차원",
            )
        return vector

    @staticmethod
    def _min_similarity(body: dict[str, Any]) -> float:
        value = body.get("minSimilarity", DEFAULT_MIN_SIMILARITY)
        if not isinstance(value, int | float) or not 0 <= value <= 1:
            raise _bad("minSimilarity는 0~1")
        return float(value)

    @staticmethod
    def _grade_semester(body: dict[str, Any]) -> tuple[int, str]:
        grade, semester = body.get("grade"), body.get("semester")
        if not isinstance(grade, int) or not 3 <= grade <= 6:
            raise _bad("grade는 3~6")
        if (
            not isinstance(semester, str)
            or not SEMESTER.match(semester)
            or not semester.startswith(f"{grade}-")
        ):
            raise _bad("semester는 그 학년의 학기(예: 3-1)")
        return grade, semester

    def search_sync(self, body: dict[str, Any]) -> dict[str, Any]:
        k = body.get("k", 5)
        if not isinstance(k, int) or not 1 <= k <= MAX_K:
            raise _bad(f"k는 1~{MAX_K}")
        minimum = self._min_similarity(body)
        filters = body.get("filters") or {}
        if not self.active:
            return {"datasetVersion": None, "items": [], "reason": "NO_ACTIVE_DATASET"}
        vector = self._check_vector(body)
        hits = []
        for chunk in self.chunks.values():
            if not self._passes(chunk, filters):
                continue
            similarity = cosine(vector, chunk["embedding"])
            if similarity >= minimum:
                hits.append((similarity, chunk))
        hits.sort(key=lambda pair: (-pair[0], pair[1]["kind"], pair[1]["id"]))
        items = [
            {
                "ref": self.ref(c["kind"], c["id"]),
                "kind": c["kind"],
                "subject": c["subject"],
                "area": c["area"],
                "standardCode": c["standardCode"],
                "domainId": c["domainId"],
                "thinkingType": c["thinkingType"],
                "grades": c["grades"],
                "semesters": c["semesters"],
                "text": c["text"],
                "similarity": round(s, 6),
            }
            for s, c in hits[:k]
        ]
        return {
            "datasetVersion": self.version,
            "items": items,
            "reason": None if items else "BELOW_THRESHOLD",
        }

    @staticmethod
    def _passes(chunk: dict[str, Any], filters: dict[str, Any]) -> bool:
        if filters.get("kinds") and chunk["kind"] not in filters["kinds"]:
            return False
        if filters.get("subjects") and chunk["subject"] not in filters["subjects"]:
            return False
        if filters.get("thinkingTypes") and chunk["thinkingType"] not in filters["thinkingTypes"]:
            return False
        if chunk["kind"] in ("SUBJECT_GUIDE", "THINKING_TYPE"):
            return True  # 학년·학기와 무관한 조각은 학년·학기 거르기를 받지 않음(api-spec 4.1.2)
        if filters.get("grades") and not set(filters["grades"]) & set(chunk["grades"]):
            return False
        return not (
            filters.get("semesters") and not set(filters["semesters"]) & set(chunk["semesters"])
        )

    def theme_candidates_sync(self, body: dict[str, Any]) -> dict[str, Any]:
        grade, semester = self._grade_semester(body)
        k = body.get("k", 3)
        if not isinstance(k, int) or not 1 <= k <= MAX_THEME_K:
            raise _bad(f"k는 1~{MAX_THEME_K}")
        minimum = self._min_similarity(body)
        if not self.active:
            return {
                "datasetVersion": None,
                "grade": grade,
                "semester": semester,
                "types": [],
                "reason": "NO_ACTIVE_DATASET",
            }
        vector = self._check_vector(body)
        scored: dict[str, tuple[float, dict[str, str]]] = {}
        for code, record in self.standards.items():
            if semester not in record["semesters"]:
                continue
            options = [
                (
                    cosine(vector, self.chunks[("STANDARD", code)]["embedding"]),
                    self.ref("STANDARD", code),
                )
            ]
            options += [
                (cosine(vector, self.chunks[("CONTENT", c)]["embedding"]), self.ref("CONTENT", c))
                for c in self.covers.get(code, [])
            ]
            best = max(options, key=lambda pair: pair[0])
            if best[0] >= minimum:
                scored[code] = best
        types = []
        for type_code in THINKING_TYPES:
            candidates = []
            for code, (similarity, matched) in scored.items():
                for fit_type, reason in self.fits.get(code, []):
                    if fit_type == type_code:
                        record = self.standards[code]
                        candidates.append(
                            {
                                "code": code,
                                "statement": record["statement"],
                                "subject": record["subject"],
                                "area": record["area"],
                                "similarity": round(similarity, 6),
                                "matchedBy": matched,
                                "fitReason": reason,
                                "ref": self.ref("STANDARD", code),
                            }
                        )
            candidates.sort(key=lambda c: (-c["similarity"], c["code"]))
            types.append(
                {
                    "thinkingType": type_code,
                    "candidates": candidates[:k],
                    "reason": None if candidates else "NO_CANDIDATE",
                }
            )
        return {
            "datasetVersion": self.version,
            "grade": grade,
            "semester": semester,
            "types": types,
            "reason": None if scored else "BELOW_THRESHOLD",
        }

    def learned_sync(self, body: dict[str, Any]) -> dict[str, Any]:
        grade, semester = self._grade_semester(body)
        concepts = body.get("concepts")
        if not isinstance(concepts, list) or not 1 <= len(concepts) <= MAX_CONCEPTS:
            raise _bad(f"concepts는 1~{MAX_CONCEPTS}개")
        minimum = self._min_similarity(body)
        if not self.active:
            return {
                "datasetVersion": None,
                "grade": grade,
                "semester": semester,
                "items": [],
                "reason": "NO_ACTIVE_DATASET",
            }
        items = []
        for concept in concepts:
            if not isinstance(concept, dict) or not concept.get("text"):
                raise _bad("concepts 항목은 {text, vector}")
            vector = self._check_vector({**body, "vector": concept.get("vector")})
            best = max(
                (
                    (cosine(vector, self.chunks[("CONTENT", cid)]["embedding"]), cid)
                    for cid in self.contents
                ),
                default=(0.0, None),
            )
            item: dict[str, Any] = {
                "text": concept["text"],
                "verdict": "HOLD",
                "matched": None,
                "learnedIn": [],
                "reason": "BELOW_THRESHOLD",
            }
            if best[1] is not None and best[0] >= minimum:
                content_id = best[1]
                item["matched"] = {
                    "contentId": content_id,
                    "text": self.contents[content_id]["text"],
                    "similarity": round(best[0], 6),
                    "ref": self.ref("CONTENT", content_id),
                }
                learned_in = [
                    {"standardCode": code, "semester": m}
                    for code in self.covered_by.get(content_id, [])
                    for m in self.standards[code]["semesters"]
                ]
                item["learnedIn"] = learned_in
                if not learned_in:
                    item["reason"] = "NO_REVIEWED_RELATION"
                elif any(
                    _semester_key(x["semester"]) <= _semester_key(semester) for x in learned_in
                ):
                    item.update(verdict="LEARNED", reason=None)
                else:
                    item.update(verdict="NOT_YET", reason=None)
            items.append(item)
        return {
            "datasetVersion": self.version,
            "grade": grade,
            "semester": semester,
            "items": items,
            "reason": None,
        }

    # -- HTTP 모양
    def handle(
        self, method: str, path: str, query: dict[str, str], body: Any, headers: dict[str, str]
    ) -> tuple[int, dict[str, Any]]:
        """한 요청을 처리해 (상태, JSON 본문). 내부 토큰·SYSTEM 역할 확인은 learning과 같다."""
        lowered = {k.lower(): v for k, v in headers.items()}
        try:
            if not lowered.get("x-internal-token"):
                raise FakeError(401, "UNAUTHENTICATED", "내부 토큰 없음")
            if lowered.get("x-user-role") != "SYSTEM":
                raise FakeError(403, "FORBIDDEN", "SYSTEM 역할만")
            if method == "GET" and path == "/internal/knowledge/standards":
                codes = [c for c in query.get("codes", "").split(",") if c]
                grade = query.get("grade")
                if grade is not None and not grade.isdigit():
                    raise _bad("grade는 정수")
                return 200, self.standards_sync(
                    codes, int(grade) if grade else None, query.get("thinkingType")
                )
            match = re.match(r"^/internal/knowledge/thinking-types/([A-Z]+)$", path)
            if method == "GET" and match:
                return 200, self.thinking_type_sync(match[1])
            routes = {
                "/internal/knowledge/search": self.search_sync,
                "/internal/knowledge/theme-candidates": self.theme_candidates_sync,
                "/internal/knowledge/learned": self.learned_sync,
            }
            if method == "POST" and path in routes:
                if not isinstance(body, dict):
                    raise _bad("JSON 객체 본문 필요")
                return 200, routes[path](body)
            raise FakeError(404, "NOT_FOUND", "없는 경로")
        except FakeError as error:
            return error.status, error.problem(path)

    def as_knowledge_api(self) -> Any:
        """contracts.KnowledgeApi를 만족하는 객체(pydantic 응답 모델을 돌려줌)."""
        from app.knowledge import contracts as c

        fake = self

        class _Api:
            async def standards(
                self, codes: list[str], grade: int | None, thinking_type: str | None
            ) -> Any:
                return c.KnowledgeBundle.model_validate(
                    fake.standards_sync(codes, grade, thinking_type)
                )

            async def thinking_type(self, thinking_type: str) -> Any:
                return c.ThinkingTypeResponse.model_validate(fake.thinking_type_sync(thinking_type))

            async def search(self, request: Any) -> Any:
                return c.SearchResponse.model_validate(
                    fake.search_sync(request.model_dump(by_alias=True))
                )

            async def theme_candidates(self, request: Any) -> Any:
                body = request.model_dump(by_alias=True)
                return c.ThemeCandidatesResponse.model_validate(fake.theme_candidates_sync(body))

            async def learned(self, request: Any) -> Any:
                return c.LearnedResponse.model_validate(
                    fake.learned_sync(request.model_dump(by_alias=True))
                )

        return _Api()


def _dispatch(
    api: FakeKnowledgeApi,
    embedder: FakeEmbedder,
    method: str,
    url: str,
    raw: bytes,
    headers: dict[str, str],
) -> tuple[int, dict[str, Any]]:
    parsed = urlparse(url)
    path = unquote(parsed.path)
    query = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
    try:
        body = json.loads(raw) if raw else None
    except ValueError:
        return 400, _bad("JSON 아님").problem(path)
    if path == "/internal/embeddings" and method == "POST":
        if not {k.lower(): v for k, v in headers.items()}.get("x-internal-token"):
            return 401, FakeError(401, "UNAUTHENTICATED", "내부 토큰 없음").problem(path)
        try:
            return 200, embedder.handle(body)
        except FakeError as error:
            return error.status, error.problem(path)
    return api.handle(method, path, query, body, headers)


def mock_transport(
    api: FakeKnowledgeApi | None = None, embedder: FakeEmbedder | None = None
) -> Any:
    """httpx.MockTransport: learning 지식 API(C5)와 ai 임베딩 API(C6) 경로를 가짜로 답한다."""
    import httpx

    knowledge = api or FakeKnowledgeApi()
    embeddings = embedder or knowledge.embedder

    def handler(request: httpx.Request) -> httpx.Response:
        status, payload = _dispatch(
            knowledge,
            embeddings,
            request.method,
            str(request.url),
            request.content,
            dict(request.headers),
        )
        media = "application/json" if status == 200 else "application/problem+json"
        return httpx.Response(status, json=payload, headers={"content-type": media})

    return httpx.MockTransport(handler)


def serve(
    host: str = "127.0.0.1",
    port: int = 0,
    api: FakeKnowledgeApi | None = None,
    embedder: FakeEmbedder | None = None,
) -> ThreadingHTTPServer:
    """가짜 HTTP 서버를 뒤에서 띄운다(learning Kotlin 개발·로컬 연동용). 끝낼 때 shutdown()."""
    knowledge = api or FakeKnowledgeApi()
    embeddings = embedder or knowledge.embedder

    class Handler(BaseHTTPRequestHandler):
        def _reply(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            status, payload = _dispatch(
                knowledge,
                embeddings,
                self.command,
                self.path,
                self.rfile.read(length),
                dict(self.headers),
            )
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header(
                "Content-Type", "application/json" if status == 200 else "application/problem+json"
            )
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        do_GET = _reply  # noqa: N815
        do_POST = _reply  # noqa: N815

        def log_message(self, *args: Any) -> None:
            return

    server = ThreadingHTTPServer((host, port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


if __name__ == "__main__":
    running = serve(port=8099)
    print(f"가짜 지식 API·임베딩: http://127.0.0.1:{running.server_address[1]} (Ctrl+C로 끝냄)")
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        running.shutdown()
