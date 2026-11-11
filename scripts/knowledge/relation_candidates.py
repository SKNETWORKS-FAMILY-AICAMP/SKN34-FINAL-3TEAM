"""지식 관계 후보 생성 (#468): 맞는 생각 유형(FITS)·선수(PREREQUISITE)·다루는 내용 요소(COVERS).

C1 레코드만 입력으로 쓴다(학생 정보 없음). 결과는 C4 확인 파일(decision 이하 빈 칸)이고, 사람이 확인한
행만 #466이 적재한다. 확인 절차는 review_relations.py 머리말.

- FITS: 성취기준마다 LLM이 유형 0~2개와 근거(요소 코드·원문 인용·이유)를 낸다. 인용이 원문에 없거나
  코드가 틀린 후보는 버린다(근거 없는 유형은 내지 않음). #262: 분류·비교는 '이해'라 분석하기 아님
- COVERS: 같은 교과·같은 고시 학년군의 내용 요소 중 임베딩 유사도 상위 N(기준안 3) + LLM 한 줄 설명
- PREREQUISITE: 같은 교과에서 학기가 앞선 초3~6 성취기준만(3-1은 후보 없음, 사용자 결정 11/11).
  내용 요소가 겹치는 것을 앞에 두고 상위 N(기준안 10)을 LLM에 주어 0~3개를 고르게 한다

실제 LLM은 ai-service 설정(LLM_PROVIDER·OPENAI_*·ANTHROPIC_*)을 그대로 쓰므로 ai-service 환경에서 실행:

    cd backend/ai-service
    uv run python ../../scripts/knowledge/relation_candidates.py --records R --dataset-version kn-YYYYMMDD-NN \\
        --embedding http --out ../../scripts/knowledge/relations-reviewed/kn-YYYYMMDD-NN-candidates.csv

임베딩: --embedding fake(기본, #464 가짜 fake-bigram-v1) | http(ai `POST /internal/embeddings`, 환경 변수
AI_URL(기본 http://localhost:8000)·INTERNAL_TOKEN, #467).
"""

import argparse
import asyncio
import importlib.util
import json
import os
import sys
import urllib.request
from pathlib import Path

import review_relations as review

ROOT = Path(__file__).resolve().parents[2]
AI_SERVICE = ROOT / "backend/ai-service"
FAKE = AI_SERVICE / "app/knowledge/fake.py"
CALL_TYPE = "KNOWLEDGE_RELATION"  # 로컬 기록만(core 사용량 이벤트를 보내지 않음)
PROMPT_VERSION = "relation-candidates-v1"
EMBED_BATCH = 64  # C6 한 요청 상한
MAX_FITS = 2
MAX_PREREQUISITES = 3
COVERS_TOP = 3  # 기준안(이슈)
PREREQUISITE_POOL = 10  # 기준안


def _load_fake():
    spec = importlib.util.spec_from_file_location("knowledge_fake", FAKE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fake = _load_fake()


def _clean(text):
    """LLM 글에 칸 구분자가 섞이면 인용 검사가 잘못 나뉘므로 바꾼다."""
    return " ".join(str(text).replace(review.SEPARATOR, " / ").split())


def _row(relation_type, standard, target, records, evidence, source, version, similarity=""):
    return {
        "relationType": relation_type,
        "standardCode": standard["code"],
        "standardStatement": standard["statement"],
        "target": target,
        "targetText": review.target_text(relation_type, target, records),
        "evidence": evidence,
        "similarity": similarity,
        "candidateSource": source,
        "decision": "",
        "modifiedTarget": "",
        "reason": "",
        "reviewer": "",
        "reviewedAt": "",
        "datasetVersion": version,
    }


def _standard_text(standard):
    grades = "·".join(f"초{g}" for g in standard["grades"])
    semesters = "·".join(standard["semesters"]) or "학기 정보 없음"
    return (f"[{standard['code']}] {standard['subject']} {grades} ({semesters})\n"
            f"문장: {standard['statement']}\n해설: {standard['explanation'] or '(원문에 없음)'}")


# ---- FITS
FITS_SYSTEM = """너는 초등 교육과정 성취기준을 보고, 그 성취기준으로 어떤 생각 유형 미션을 만들기 좋은지 후보를 내는 검토 보조다.
사람이 후보를 하나씩 확인하므로 근거가 분명한 것만 낸다.
규칙
- 맞는 유형은 0~2개. 근거가 약하면 내지 않는다(빈 배열 허용).
- 유형마다 element(그 유형의 요소 코드 하나), quote(성취기준 문장이나 해설에서 글자 그대로 옮긴 구절, 고치거나 줄이지 말 것),
  quoteSource(문장이면 STATEMENT, 해설이면 EXPLANATION), why(그 구절이 왜 이 유형 요소에 맞는지 한 문장)를 쓴다.
- 분류하거나 비교하는 것으로 끝나는 활동은 블룸 개정 분류의 '이해'라 분석하기로 보지 않는다. 분석하기는 부분 사이의 관계·원인까지 찾는 활동이다(#262).
- 다짐이나 계획만 있는 활동은 돌아보기로 보지 않는다(#262).
- 성취기준 글과 아래 유형 지침만 근거로 쓴다.
생각 유형 지침
{guides}"""


def _type_guides(records):
    blocks = []
    for code in review.THINKING_TYPES:
        record = records.thinking_types[code]
        elements = "; ".join(f"{e['code']}({e['label']}: {e['description']})" for e in record["elements"])
        blocks.append(f"{code} {record['name']}\n요소: {elements}\n질문에 꼭: {' '.join(record['questionMust'])}\n"
                      f"피할 것: {' '.join(record['questionMustNot'])}")
    return "\n\n".join(blocks)


def fits_candidates(standard, records, llm, version):
    data = llm("fits", FITS_SYSTEM.format(guides=_type_guides(records)), _standard_text(standard))
    rows, seen = [], set()
    for item in data.get("types", []):
        thinking_type, quote = item.get("type"), item.get("quote") or ""
        if thinking_type not in records.thinking_types or thinking_type in seen:
            continue
        if item.get("element") not in {e["code"] for e in records.thinking_types[thinking_type]["elements"]}:
            continue
        label, source = {"STATEMENT": ("문장", standard["statement"]),
                         "EXPLANATION": ("해설", standard["explanation"] or "")}.get(item.get("quoteSource"), ("", ""))
        if not quote.strip() or review.SEPARATOR in quote or quote not in source:
            continue
        seen.add(thinking_type)
        evidence = f"{item['element']}: {_clean(item.get('why', ''))}{review.SEPARATOR}{label}: {quote}"
        rows.append(_row("FITS", standard, thinking_type, records, evidence, "LLM", version))
        if len(rows) == MAX_FITS:
            break
    return rows


# ---- COVERS
COVERS_SYSTEM = """너는 성취기준이 교육과정 내용 체계의 어떤 내용 요소를 다루는지 사람이 확인하도록 돕는 검토 보조다.
후보 내용 요소마다 이 성취기준과 어떻게 이어지는지 한 문장으로 쓴다. 관련이 약하면 약하다고 쓴다.
contentId는 받은 그대로 쓴다. 성취기준 글과 내용 요소 글만 근거로 쓴다."""


def _embed_all(embed, texts):
    vectors = []
    for start in range(0, len(texts), EMBED_BATCH):
        vectors += embed(texts[start : start + EMBED_BATCH])
    if len(vectors) != len(texts):
        raise RuntimeError(f"임베딩 개수가 다름: {len(vectors)} != {len(texts)}")
    return vectors


def covers_matches(standards, records, embed, top=COVERS_TOP):
    """성취기준 코드 → [(내용 요소 id, 유사도)] 상위 top. 같은 교과·같은 고시 학년군 안에서만."""
    contents = list(records.contents.values())
    vectors = _embed_all(embed, [fake.chunk_text(s) for s in standards] + [fake.chunk_text(c) for c in contents])
    content_vectors = dict(zip((c["id"] for c in contents), vectors[len(standards) :], strict=True))
    matches = {}
    for standard, vector in zip(standards, vectors[: len(standards)], strict=True):
        pool = [c for c in contents
                if (c["subject"], c["noticeGradeBand"]) == (standard["subject"], standard["noticeGradeBand"])]
        scored = sorted(((c["id"], fake.cosine(vector, content_vectors[c["id"]])) for c in pool),
                        key=lambda pair: (-pair[1], pair[0]))
        matches[standard["code"]] = scored[:top]
    return matches


def covers_candidates(standard, matched, records, llm, version):
    if not matched:
        return []
    listing = "\n".join(
        f"- contentId: {content_id} | {fake.CATEGORY_NAME[records.contents[content_id]['category']]} | "
        f"{records.contents[content_id]['area']} | {records.contents[content_id]['text']}"
        for content_id, _ in matched)
    data = llm("covers", COVERS_SYSTEM, f"{_standard_text(standard)}\n\n후보 내용 요소\n{listing}")
    explanations = {item.get("contentId"): _clean(item.get("explanation", "")) for item in data.get("items", [])}
    rows = []
    for rank, (content_id, similarity) in enumerate(matched, start=1):
        evidence = f"임베딩 유사도 {rank}위"
        if explanations.get(content_id):
            evidence += f"{review.SEPARATOR}{explanations[content_id]}"
        rows.append(_row("COVERS", standard, content_id, records, evidence, "EMBEDDING", version, f"{similarity:.4f}"))
    return rows


# ---- PREREQUISITE
PREREQUISITE_SYSTEM = """너는 성취기준을 배우기 전에 먼저 배워야 하는 성취기준(선수) 후보를 내는 검토 보조다.
받은 목록(같은 교과, 앞 학기)에서만 0~3개를 고른다. 목록 밖 코드는 쓰지 않는다.
이 성취기준을 배우는 데 그 개념이나 기능이 꼭 필요할 때만 고르고, 고른 까닭(why)을 한 문장으로 쓴다.
겹치는 내용 요소는 참고일 뿐이며, 같은 주제라도 먼저 알아야 하는 관계가 아니면 고르지 않는다."""


def prerequisite_pool(standard, records, covers, size=PREREQUISITE_POOL):
    """같은 교과·앞 학기 성취기준을 (겹치는 내용 요소 많은 순, 가까운 학기 순, 코드 순)으로 size개."""
    own = covers.get(standard["code"], set())
    pool = [s for s in records.standards.values()
            if s["subject"] == standard["subject"] and review.is_earlier(s, standard)]
    pool.sort(key=lambda s: (-len(own & covers.get(s["code"], set())),
                             tuple(-n for n in max(map(review.semester_key, s["semesters"]))), s["code"]))
    return pool[:size]


def prerequisite_candidates(standard, records, covers, llm, version):
    pool = prerequisite_pool(standard, records, covers)
    if not pool:
        return []
    own = covers.get(standard["code"], set())
    overlaps = {s["code"]: sorted(own & covers.get(s["code"], set())) for s in pool}
    listing = "\n".join(
        f"- [{s['code']}] ({'·'.join(s['semesters'])}) {s['statement']}"
        + (f" | 겹치는 내용 요소: {'; '.join(records.contents[i]['text'] for i in overlaps[s['code']])}"
           if overlaps[s["code"]] else "")
        for s in pool)
    data = llm("prerequisite", PREREQUISITE_SYSTEM, f"{_standard_text(standard)}\n\n앞 학기 성취기준 목록\n{listing}")
    rows, seen = [], set()
    for item in data.get("items", []):
        code = item.get("code")
        if code not in overlaps or code in seen:
            continue
        seen.add(code)
        shared = "·".join(records.contents[i]["text"] for i in overlaps[code])
        evidence = (f"겹치는 내용 요소: {shared}" if shared else "겹치는 내용 요소 없음") + \
            f"{review.SEPARATOR}{_clean(item.get('why', ''))}"
        rows.append(_row("PREREQUISITE", standard, code, records, evidence, "LLM", version))
        if len(rows) == MAX_PREREQUISITES:
            break
    return rows


def reviewed_covers(path):
    """확인된 COVERS 파일(수락·수정 행)에서 성취기준 코드 → 내용 요소 id 묶음."""
    covers = {}
    for row in review.read_review_csv(path):
        if row["relationType"] == "COVERS" and row["decision"] in review.ACCEPTED:
            covers.setdefault(row["standardCode"], set()).add(review.effective_target(row))
    return covers


def generate(records, llm, embed, version, types=review.RELATION_TYPES, codes=None, covers_file=None,
             top=COVERS_TOP):
    """C4 확인 파일 행 목록. 선수의 내용 요소 겹침은 확인된 COVERS 파일, 없으면 이번 COVERS 유사도 상위를 쓴다."""
    standards = [s for code, s in sorted(records.standards.items()) if codes is None or code in codes]
    rows = []
    if "FITS" in types:
        for standard in standards:
            rows += fits_candidates(standard, records, llm, version)
    matches = {}
    if "COVERS" in types or ("PREREQUISITE" in types and covers_file is None):
        # 선수 겹침은 대상 성취기준의 내용 요소도 필요하므로 같은 교과 전체를 임베딩
        subjects = {s["subject"] for s in standards}
        matches = covers_matches([s for s in records.standards.values() if s["subject"] in subjects],
                                 records, embed, top)
    if "COVERS" in types:
        for standard in standards:
            rows += covers_candidates(standard, matches[standard["code"]], records, llm, version)
    if "PREREQUISITE" in types:
        covers = reviewed_covers(covers_file) if covers_file else \
            {code: {content_id for content_id, _ in pairs} for code, pairs in matches.items()}
        for standard in standards:
            rows += prerequisite_candidates(standard, records, covers, llm, version)
    return rows


# ---- 실제 임베딩·LLM 어댑터
def fake_embed(texts):
    return fake.FakeEmbedder().embed_sync(texts)["vectors"]


def http_embed(texts):
    """ai `POST /internal/embeddings`(C6). 성취기준·내용 요소 글만 보낸다."""
    request = urllib.request.Request(
        os.environ.get("AI_URL", "http://localhost:8000").rstrip("/") + "/internal/embeddings",
        data=json.dumps({"texts": texts}, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Internal-Token": os.environ["INTERNAL_TOKEN"]},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        body = json.loads(response.read().decode("utf-8"))
    print(f"임베딩 모델 {body['model']} {body['dimensions']}차원", file=sys.stderr)
    return body["vectors"]


def ai_service_llm(timeout=60.0):
    """ai-service LLM 설정을 쓰는 llm(task, system, user) -> dict. ai-service 환경에서만 import된다."""
    from typing import Literal

    sys.path.insert(0, str(AI_SERVICE))  # 스크립트 폴더가 sys.path[0]이라 ai-service 패키지(app)를 직접 넣음
    from app.config import Settings
    from app.llm.providers import create_llm
    from pydantic import BaseModel

    class FitItem(BaseModel):
        type: Literal["ANALYZE", "EVALUATE", "CREATE", "SOLVE", "REFLECT"]
        element: str
        quoteSource: Literal["STATEMENT", "EXPLANATION"]
        quote: str
        why: str

    class FitsOutput(BaseModel):
        types: list[FitItem]

    class CoverItem(BaseModel):
        contentId: str
        explanation: str

    class CoversOutput(BaseModel):
        items: list[CoverItem]

    class PrerequisiteItem(BaseModel):
        code: str
        why: str

    class PrerequisitesOutput(BaseModel):
        items: list[PrerequisiteItem]

    outputs = {"fits": FitsOutput, "covers": CoversOutput, "prerequisite": PrerequisitesOutput}

    def record(usage):
        print(f"LLM {usage.model} 입력 {usage.input_tokens} 출력 {usage.output_tokens} "
              f"{'성공' if usage.success else usage.error_code}", file=sys.stderr)

    # 내부 토큰은 LLM 호출에 쓰지 않지만 Settings 필수 칸
    client = create_llm(Settings(internal_token=os.environ.get("INTERNAL_TOKEN") or "relation-candidates"), record)
    # SDK 연결이 루프에 묶이므로 호출마다 asyncio.run(새 루프) 대신 루프 하나를 계속 씀
    loop = asyncio.new_event_loop()

    def llm(task, system, user):
        result = loop.run_until_complete(client.generate(
            system=system, user=user, output=outputs[task], call_type=CALL_TYPE, prompt_version=PROMPT_VERSION,
            timeout=timeout))
        return result.data.model_dump()

    return llm


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):  # Windows 콘솔(cp949)에서 한글 출력
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--records", type=Path, default=review.DEFAULT_RECORDS)
    parser.add_argument("--dataset-version", required=True, help="C9 판 이름 kn-YYYYMMDD-NN")
    parser.add_argument("--types", default=",".join(review.RELATION_TYPES))
    parser.add_argument("--codes", help="쉼표로 나눈 성취기준 코드(없으면 레코드 전체)")
    parser.add_argument("--covers", type=Path, help="확인된 COVERS 파일(선수 겹침 계산에 씀)")
    parser.add_argument("--top", type=int, default=COVERS_TOP)
    parser.add_argument("--embedding", choices=("fake", "http"), default="fake")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    if not review.VERSION.match(args.dataset_version):
        parser.error("--dataset-version은 kn-YYYYMMDD-NN")
    types = tuple(args.types.split(","))
    if set(types) - set(review.RELATION_TYPES):
        parser.error(f"--types는 {','.join(review.RELATION_TYPES)} 중에서")
    records = review.load_records(args.records)
    codes = set(args.codes.split(",")) if args.codes else None
    rows = generate(records, ai_service_llm(), fake_embed if args.embedding == "fake" else http_embed,
                    args.dataset_version, types, codes, args.covers, args.top)
    errors = review.validate(rows, records)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    review.write_review_csv(rows, args.out)
    print(f"후보 {len(rows)}행 → {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
