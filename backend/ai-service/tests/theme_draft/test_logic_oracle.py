"""정답 논리 판정(check_logic)과 rulesOut 채우기(fill_rules_out)를 따로 짠 판정기와 무작위
5000건으로 대조한다(seed 고정). 절반은 완전 무작위, 절반은 통과에 가까운 사례를 한 곳만 흔들어
경계 사례를 많이 넣는다.

판정기는 ai.md 16절 규칙 문장을 그대로 옮겨 집합 계산으로 따로 구현했다. 단서 문장은 허용 값 낱말만
늘어놓아 CLUE_TEXT는 나오지 않게 하고, 표·조건·RULE/HINT를 무작위로 만든다. rulesOut은 LLM이
쓰지 않으므로 사례에 없고, 코드가 채운 값이 판정기 계산(RULE은 허용 값 밖 후보, HINT는 빈 배열)과
같은지 함께 본다.
"""

import random

from app.theme_draft.checks import DAYS, check_logic, fill_rules_out

VALUES = [
    "사과",
    "포도",
    "귤",
    "배추",
    "당근",
    "오이",
]  # 서로의 일부가 아니고 명사형 끝이 아닌 낱말
CANDS = ["가게", "공원", "다리", "마당"]
CASES = 5000
SEED = 437


def oracle(
    cands: list[str], answer: str, table: dict[str, dict[str, str]], days: list[dict]
) -> bool:
    remaining = set(cands)
    first_out: dict[str, int] = {}
    for i, d in enumerate(days):
        c = d["condition"]
        values = table[c["feature"]]
        allowed = set(c["allowed"])
        if not allowed or not allowed <= set(values.values()):
            return False
        fit = {x for x in cands if values[x] in allowed}
        out = set(cands) - fit
        if answer not in fit:  # 정답은 어떤 단서로도 빠지지 않음
            return False
        if c["kind"] == "RULE":
            # RULE: 빠지는 후보 = 허용 값 밖 후보(비지 않음), 그때 남은 후보를 적어도 하나 새로 뺌
            if not out or not (out & remaining):
                return False
            for x in out:
                first_out.setdefault(x, i)
            remaining -= out
        else:
            # HINT: 후보를 빼지 않음, 그때 남은 후보가 모두 허용 값 안, 월~수는 남은 후보 2개 이상
            if not remaining <= fit:
                return False
            if i <= 2 and len(remaining) < 2:
                return False
    wrong = set(cands) - {answer}
    if not wrong <= set(first_out):  # 틀린 후보는 모두 RULE로 빠짐
        return False
    return max(first_out[x] for x in wrong) >= 3  # 마지막 틀린 후보는 목요일 이후


def random_case(
    rng: random.Random,
) -> tuple[dict, list[str], str, list[dict], dict[str, dict[str, str]]]:
    answer = rng.choice(CANDS)
    names = ["f1", "f2", "f3"]
    table = {n: {c: rng.choice(VALUES[: rng.randint(2, 4)]) for c in CANDS} for n in names}
    theme = {
        "candidates": CANDS,
        "features": [
            {"name": n, "values": [{"candidate": c, "value": v} for c, v in table[n].items()]}
            for n in names
        ],
    }
    days = []
    for d in DAYS:
        feat = rng.choice(names)
        vals = sorted(set(table[feat].values()))
        allowed = rng.sample(vals, rng.randint(1, len(vals)))
        if (
            rng.random() < 0.6 and table[feat][answer] not in allowed
        ):  # 정답이 맞는 조건 쪽으로 기울임
            allowed.append(table[feat][answer])
        kind = rng.choice(["RULE", "HINT"])
        days.append(
            {
                "day": d,
                "clue": " ".join(allowed),
                "condition": {"kind": kind, "feature": feat, "allowed": allowed},
            }
        )
    return theme, CANDS, answer, days, table


def planned_case(
    rng: random.Random,
) -> tuple[dict, list[str], str, list[dict], dict[str, dict[str, str]]]:
    """통과에 가까운 사례: 틀린 후보마다 빠지는 요일을 정해 요일별 특징(d0~d4)을 만든 뒤 한 곳을 "
    "흔든다."""
    answer = rng.choice(CANDS)
    wrong = [c for c in CANDS if c != answer]
    out_day = {c: rng.choice([0, 1, 2, 3, 3, 4, 4]) for c in wrong}
    table: dict[str, dict[str, str]] = {}
    days = []
    gone: set[str] = set()
    for i, d in enumerate(DAYS):
        name = f"d{i}"
        leaving = {c for c in wrong if out_day[c] == i}
        extra = {c for c in gone if rng.random() < 0.5}  # 이미 빠진 후보도 함께 뺄 수 있음
        table[name] = {c: ("포도" if c in leaving | extra else "사과") for c in CANDS}
        kind = "RULE" if leaving else "HINT"
        days.append(
            {
                "day": d,
                "clue": "사과",
                "condition": {"kind": kind, "feature": name, "allowed": ["사과"]},
            }
        )
        gone |= leaving
    k = rng.randrange(5)
    shake = rng.randrange(5)
    day = days[k]
    if shake == 0:
        day["condition"]["kind"] = "HINT" if day["condition"]["kind"] == "RULE" else "RULE"
    elif shake == 1:  # 두 값 모두 허용: RULE이면 빠지는 후보가 없음
        day["condition"]["allowed"] = ["사과", "포도"]
        day["clue"] = "사과 포도"
    elif shake == 2:
        day["condition"]["allowed"] = ["포도"]
        day["clue"] = "포도"
    # 3·4는 그대로(통과 사례)
    theme = {
        "candidates": CANDS,
        "features": [
            {"name": n, "values": [{"candidate": c, "value": v} for c, v in vals.items()]}
            for n, vals in table.items()
        ],
    }
    return theme, CANDS, answer, days, table


def expected_rules_out(table: dict[str, dict[str, str]], day: dict) -> list[str]:
    c = day["condition"]
    if c["kind"] != "RULE":
        return []
    return [x for x in CANDS if table[c["feature"]][x] not in set(c["allowed"])]


def test_check_logic_matches_independent_oracle() -> None:
    rng = random.Random(SEED)
    valid = mismatches = 0
    for _ in range(CASES):
        theme, cands, answer, days, table = (random_case if rng.random() < 0.5 else planned_case)(
            rng
        )
        bad = check_logic(theme, cands, answer, days)
        assert not [r for r in bad if r.startswith("CLUE_TEXT")]  # 문장은 허용 값만 늘어놓음
        filled = fill_rules_out({**theme, "days": days})["days"]
        assert [d["rulesOut"] for d in filled] == [expected_rules_out(table, d) for d in days]
        expected = oracle(cands, answer, table, days)
        valid += expected
        mismatches += expected != (not bad)
    assert mismatches == 0
    assert valid >= CASES // 10, f"통과 사례가 너무 적어 대조가 약함({valid}건)"
