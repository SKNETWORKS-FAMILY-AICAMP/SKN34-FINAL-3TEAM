"""학습 산출물의 입력·출력·경계를 로딩과 추론에서 같은 기준으로 검증한다."""

import math

from app.m2.models import ESSAY_ITEMS, ITEMS


def flag(value):
    if value is True or value == "True":
        return True
    if value is False or value == "False":
        return False
    raise ValueError("invalid training flag")


def validate_metadata(name, config, cuts):
    if name not in ("m2-klue-narrative", "m2-klue-essay"):
        raise ValueError("unsupported M2 model")
    narrative = name == "m2-klue-narrative"
    modern_essay = not narrative and config.get("dataset") == "essay545"
    no_prompt = flag(config.get("no_prompt", False))
    if (
        config.get("head") != "reg"
        or config.get("dataset")
        != ("descriptive" if narrative else "essay545" if modern_essay else "essay")
        or flag(config.get("with_keyword")) != narrative
        or flag(config.get("with_purpose"))
        or flag(config.get("with_exemplar"))
        or (not narrative and no_prompt != modern_essay)
    ):
        raise ValueError("unsupported training configuration")
    if modern_essay and (
        config.get("num_outputs") != 14
        or config.get("use_outputs") != list(ESSAY_ITEMS)
        or config.get("outputs")
        != [
            "org",
            "cont",
            "exp",
            "org_0",
            "org_1",
            "org_2",
            "org_3",
            "cont_0",
            "cont_1",
            "cont_2",
            "cont_3",
            "exp_0",
            "exp_1",
            "exp_2",
        ]
    ):
        raise ValueError("invalid essay output order")
    length = int(config["max_length"])
    items = ESSAY_ITEMS if modern_essay else ITEMS
    if not 8 <= length <= 512 or not isinstance(cuts, dict) or set(cuts) != set(items):
        raise ValueError("invalid scoring metadata")
    for item in items:
        edges = cuts[item]
        if (
            not isinstance(edges, list)
            or len(edges) != (3 if modern_essay or item == "hol" else 4)
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in edges)
            or any(a >= b for a, b in zip(edges, edges[1:], strict=False))
        ):
            raise ValueError("invalid score cuts")
    return items, 14 if modern_essay else 9, no_prompt, length
