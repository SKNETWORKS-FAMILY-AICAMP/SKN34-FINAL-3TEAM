"""#468 지식 관계 후보 생성·확인 파일 시험(가짜 LLM·가짜 임베딩).

CI(ci-contracts)는 PyYAML·jsonschema만 설치하므로 실제 LLM 어댑터(ai-service 환경)는 부르지 않는다.
"""

import contextlib
import copy
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
KNOWLEDGE = ROOT / "scripts/knowledge"
sys.path.insert(0, str(KNOWLEDGE))

import relation_candidates as candidates
import review_relations as review

SAMPLE_CSV = KNOWLEDGE / "samples/relations-review.sample.csv"
VERSION = "kn-20261111-01"
CODE = re.compile(r"^\[([^\]]+)\]")


class FakeLlm:
    """task·성취기준 코드별 정해 둔 답. 정하지 않은 성취기준은 문장 전체를 인용한 분석하기 하나·빈 목록."""

    def __init__(self, records, answers=None):
        self.records = records
        self.answers = answers or {}
        self.calls = []

    def __call__(self, task, system, user):
        code = CODE.match(user)[1]
        self.calls.append((task, code, system, user))
        if (task, code) in self.answers:
            return self.answers[(task, code)]
        if task == "fits":
            statement = self.records.standards[code]["statement"]
            return {"types": [{"type": "ANALYZE", "element": "ANALYZE_RELATION", "quoteSource": "STATEMENT",
                               "quote": statement, "why": "관계를 찾게 할 수 있음"}]}
        if task == "covers":
            ids = re.findall(r"contentId: (.+?) \|", user)  # id에 공백이 있음(영역 이름)
            return {"items": [{"contentId": i, "explanation": f"설명 {n}"} for n, i in enumerate(ids)]}
        return {"items": []}


def schema_validator():
    schema = json.loads((KNOWLEDGE / "schema/relation-review.schema.json").read_text(encoding="utf-8"))
    return Draft202012Validator(schema)


def with_standard(records, code, semesters, base):
    """시험용 성취기준(base 복사, 코드·학기·문장만 바꿈)을 더한 레코드."""
    standards = dict(records.standards)
    standard = copy.deepcopy(records.standards[base])
    standard.update(code=code, semesters=semesters, statement=f"{code} 시험용 문장")
    standards[code] = standard
    return review.Records(standards, records.contents, records.thinking_types)


class RelationCandidatesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = review.load_records()
        cls.schema = schema_validator()

    def assert_c4(self, rows, records=None):
        for row in rows:
            errors = [e.message for e in self.schema.iter_errors(row)]
            self.assertEqual(errors, [], row)
        self.assertEqual(review.validate(rows, records or self.records), [])

    def test_fits_keeps_only_types_with_original_quote(self):
        standard = self.records.standards["4과02-01"]
        explanation_quote = standard["explanation"][:20]
        answers = {("fits", "4과02-01"): {"types": [
            {"type": "ANALYZE", "element": "ANALYZE_RELATION", "quoteSource": "STATEMENT",
             "quote": "특징에 따라 동물을 분류할 수 있다", "why": "특징을 찾음"},
            {"type": "EVALUATE", "element": "EVALUATE_CLAIM", "quoteSource": "STATEMENT",
             "quote": "원문에 없는 구절", "why": "인용 틀림"},
            {"type": "CREATE", "element": "ANALYZE_RELATION", "quoteSource": "STATEMENT",
             "quote": "동물을 관찰하여", "why": "요소 코드가 다른 유형"},
            {"type": "ANALYZE", "element": "ANALYZE_REASON", "quoteSource": "STATEMENT",
             "quote": "동물을 관찰하여", "why": "같은 유형 두 번"},
            {"type": "SOLVE", "element": "SOLVE_DEFINE", "quoteSource": "EXPLANATION",
             "quote": explanation_quote, "why": "해설 인용 | 구분자 섞임"},
            {"type": "REFLECT", "element": "REFLECT_CHANGE", "quoteSource": "STATEMENT",
             "quote": "동물을 관찰하여", "why": "2개 넘음"},
        ]}}
        rows = candidates.fits_candidates(standard, self.records, FakeLlm(self.records, answers), VERSION)
        self.assertEqual([r["target"] for r in rows], ["ANALYZE", "SOLVE"])
        self.assertEqual(rows[0]["evidence"], "ANALYZE_RELATION: 특징을 찾음 | 문장: 특징에 따라 동물을 분류할 수 있다")
        self.assertEqual(rows[1]["evidence"], f"SOLVE_DEFINE: 해설 인용 / 구분자 섞임 | 해설: {explanation_quote}")
        self.assertEqual({r["candidateSource"] for r in rows}, {"LLM"})
        self.assert_c4(rows)

    def test_fits_may_return_no_type(self):
        standard = self.records.standards["4국01-01"]
        llm = FakeLlm(self.records, {("fits", "4국01-01"): {"types": []}})
        self.assertEqual(candidates.fits_candidates(standard, self.records, llm, VERSION), [])

    def test_fits_prompt_uses_curriculum_only_and_262_rule(self):
        llm = FakeLlm(self.records)
        standard = self.records.standards["4과02-01"]
        candidates.fits_candidates(standard, self.records, llm, VERSION)
        _, _, system, user = llm.calls[0]
        self.assertEqual(user, candidates._standard_text(standard))
        self.assertIn("분류하거나 비교하는 것으로 끝나는 활동", system)
        for record in self.records.thinking_types.values():
            self.assertIn(record["name"], system)

    def test_covers_top3_within_subject_and_grade_band(self):
        llm = FakeLlm(self.records)
        rows = candidates.generate(self.records, llm, candidates.fake_embed, VERSION, types=("COVERS",))
        by_code = {}
        for row in rows:
            by_code.setdefault(row["standardCode"], []).append(row)
        self.assertEqual(set(by_code), set(self.records.standards))
        for code, group in by_code.items():
            standard = self.records.standards[code]
            self.assertEqual(len(group), 3)
            similarities = [float(r["similarity"]) for r in group]
            self.assertEqual(similarities, sorted(similarities, reverse=True))
            for row in group:
                content = self.records.contents[row["target"]]
                self.assertEqual((content["subject"], content["noticeGradeBand"]),
                                 (standard["subject"], standard["noticeGradeBand"]))
                self.assertRegex(row["evidence"], r"^임베딩 유사도 [123]위 \| 설명 [012]$")
                self.assertEqual(row["candidateSource"], "EMBEDDING")
        self.assert_c4(rows)

    def test_prerequisite_pool_is_same_subject_earlier_semester_overlap_first(self):
        records = with_standard(self.records, "4수01-90", ["3-2"], base="4수01-06")
        records = with_standard(records, "4과01-90", ["4-1"], base="4과01-01")
        target = records.standards["4수01-90"]
        covers = {"4수01-90": {"a"}, "4수01-05": {"a"}, "4수01-03": set()}
        pool = candidates.prerequisite_pool(target, records, covers)
        self.assertEqual(pool[0]["code"], "4수01-05")
        self.assertEqual({s["subject"] for s in pool}, {"수학"})
        self.assertTrue(all(s["semesters"] == ["3-1"] for s in pool))
        self.assertNotIn("4수01-90", {s["code"] for s in pool})
        self.assertEqual(candidates.prerequisite_pool(records.standards["4수01-06"], records, covers), [])

    def test_prerequisite_keeps_listed_codes_only(self):
        records = with_standard(self.records, "4수01-90", ["3-2"], base="4수01-06")
        answers = {("prerequisite", "4수01-90"): {"items": [
            {"code": "4수01-06", "why": "나눗셈 계산 원리가 먼저 필요"},
            {"code": "4국01-01", "why": "목록 밖"},
            {"code": "4수01-06", "why": "중복"},
        ]}}
        llm = FakeLlm(records, answers)
        rows = candidates.generate(records, llm, candidates.fake_embed, VERSION, types=("PREREQUISITE",),
                                   codes={"4수01-90", "4수01-06"})
        self.assertEqual([(r["standardCode"], r["target"]) for r in rows], [("4수01-90", "4수01-06")])
        self.assertRegex(rows[0]["evidence"], r"^겹치는 내용 요소(: .+| 없음) \| 나눗셈 계산 원리가 먼저 필요$")
        self.assertEqual([c[1] for c in llm.calls], ["4수01-90"])  # 3-1은 앞 학기 후보가 없어 LLM을 부르지 않음
        self.assert_c4(rows, records)
        accepted = [dict(rows[0], decision="ACCEPT", reviewer="검토자", reviewedAt="2026-11-11")]
        self.assertEqual(review.validate(accepted, records), [])

    def test_prerequisite_uses_reviewed_covers_file(self):
        records = with_standard(self.records, "4수01-90", ["3-2"], base="4수01-06")
        content_id = "수학:초3~4:수와 연산:K:cfcd0e59"
        rows = [candidates._row("COVERS", records.standards[code], content_id, records, "확인", "MANUAL", VERSION)
                for code in ("4수01-90", "4수01-05")]
        for row in rows:
            row.update(decision="ACCEPT", reviewer="검토자", reviewedAt="2026-11-11")
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "covers.csv"
            review.write_review_csv(rows, path)
            covers = candidates.reviewed_covers(path)
        self.assertEqual(covers, {"4수01-90": {content_id}, "4수01-05": {content_id}})
        pool = candidates.prerequisite_pool(records.standards["4수01-90"], records, covers)
        self.assertEqual(pool[0]["code"], "4수01-05")

    def test_generate_on_samples_passes_c4(self):
        llm = FakeLlm(self.records)
        rows = candidates.generate(self.records, llm, candidates.fake_embed, VERSION)
        counts = {t: sum(r["relationType"] == t for r in rows) for t in review.RELATION_TYPES}
        self.assertEqual(counts, {"FITS": 15, "PREREQUISITE": 0, "COVERS": 45})  # 샘플은 모두 3-1
        self.assertNotIn("prerequisite", {c[0] for c in llm.calls})
        self.assert_c4(rows)


class ReviewRelationsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = review.load_records()
        cls.sample = review.read_review_csv(SAMPLE_CSV)

    def rows(self):
        return copy.deepcopy(self.sample)

    def assert_error(self, rows, text, final=False):
        errors = review.validate(rows, self.records, final=final)
        self.assertTrue(any(text in e for e in errors), errors)

    def test_sample_passes_and_final_rejects_sample_and_undecided(self):
        self.assertEqual(review.validate(self.sample, self.records), [])
        errors = review.validate(self.sample, self.records, final=True)
        self.assertEqual(sum("SAMPLE" in e for e in errors), 27)
        self.assertEqual(sum("확인하지 않은 행" in e for e in errors), 2)

    def test_validate_errors(self):
        rows = self.rows()
        rows[0]["standardCode"] = "4국99-99"
        self.assert_error(rows, "성취기준이 레코드에 없음")
        rows = self.rows()
        rows.append(dict(rows[0]))
        self.assert_error(rows, "같은 후보가 또 있음")
        rows = self.rows()
        rows[5]["reason"] = ""  # REJECT
        self.assert_error(rows, "REJECT은 reason 필수")
        rows = self.rows()
        rows[27]["modifiedTarget"] = ""  # MODIFY
        self.assert_error(rows, "MODIFY는 modifiedTarget 필수")
        rows = self.rows()
        rows[27]["modifiedTarget"] = rows[21]["target"]  # 이미 수락한 4과02-01 내용 요소로 수정
        self.assert_error(rows, "같은 관계를 두 번 수락")
        rows = self.rows()
        rows[0]["standardStatement"] += " "
        self.assert_error(rows, "standardStatement가 레코드 문장과 다름")
        rows = self.rows()
        rows[0]["evidence"] = "EVALUATE_CLAIM: 이유 | 해설: 원문에 없는 해설"
        self.assert_error(rows, "evidence 인용이 성취기준 해설에 없음")
        rows = self.rows()
        rows[0]["targetText"] = "분석하기"
        self.assert_error(rows, "targetText가 대상 글과 다름")
        rows = self.rows()
        rows[7].update(decision="ACCEPT", reason="")  # 3-1 → 3-1 선수
        self.assert_error(rows, "선수가 앞 학기가 아님")
        rows = self.rows()
        rows[14]["target"] = "국어:초3~4:읽기:P:38b01aa0"  # 국어 내용 요소를 수학 성취기준(4수01-03)에
        self.assert_error(rows, "다른 교과·학년군")
        rows = self.rows()
        rows[6].update(reviewer="검토자")  # 확인 전 행에 확인자
        self.assert_error(rows, "확인 전 행에")
        rows = self.rows()
        rows[0]["datasetVersion"] = "kn-20261112-01"
        self.assert_error(rows, "판이 여러 개")

    def test_csv_round_trip_and_header(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "out.csv"
            review.write_review_csv(self.sample, path)
            self.assertEqual(review.read_review_csv(path), self.sample)
            path.write_bytes(b"\xef\xbb\xbf" + path.read_bytes())  # 엑셀 BOM
            self.assertEqual(review.read_review_csv(path), self.sample)
            path.write_text("relationType,standardCode\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                review.read_review_csv(path)

    def test_compare_lists_different_and_missing_rows(self):
        self.assertEqual(review.compare(self.sample, self.rows()), [])
        cross = self.rows()
        cross[0].update(decision="REJECT", reason="교차 확인자 의견")
        del cross[1]
        differences = review.compare(self.sample, cross)
        self.assertEqual(len(differences), 2)
        self.assertIn("1차 ACCEPT / 교차 REJECT", differences[0])
        self.assertIn("교차 파일에 없음", differences[1])

    def test_stats_rates_and_reasons(self):
        text = review.stats(self.sample, self.records)
        self.assertIn("| FITS | 6 | 5 | 0 | 1 | 1 | 83% |", text)
        self.assertIn("| COVERS | 20 | 20 | 1 | 0 | 1 | 100% |", text)
        self.assertIn("| 분석하기 | 2 | 1 | 0 | 1 | 1 | 50% |", text)
        self.assertIn("| 수학 PREREQUISITE | 1 | 0 | 0 | 1 | 0 | 0% |", text)
        self.assertIn("MODIFY COVERS 4과02-01 → 과학:초3~4:생명:K:a046b0ee ⇒ 과학:초3~4:생명:K:82d3d210", text)

    def test_coverage_table_and_empty_cells(self):
        text = review.coverage(self.sample, self.records)
        self.assertIn("| 3-1 | 1 | 1 | 1 | 1 | 1 |", text)
        self.assertIn("- 3-2 분석하기", text)
        self.assertNotIn("- 3-1", text.split("#### 빈 칸")[1].split("####")[0])
        rows = [r for r in self.rows() if r["target"] != "REFLECT"]
        text = review.coverage(rows, self.records, ("3-1",))
        self.assertIn("| 3-1 | 1 | 1 | 1 | 1 | 0 |", text)
        self.assertIn("- 3-1 돌아보기", text)
        self.assertIn("#### 수락된 내용 요소가 없는 성취기준\n\n- 없음", text)

    def test_cli_validate_exit_codes(self):
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(review.main(["validate", str(SAMPLE_CSV)]), 0)
            self.assertEqual(review.main(["validate", str(SAMPLE_CSV), "--final"]), 1)
            self.assertEqual(review.main(["compare", str(SAMPLE_CSV), str(SAMPLE_CSV)]), 0)
        self.assertIn("통과: 29행", out.getvalue())


if __name__ == "__main__":
    unittest.main()
