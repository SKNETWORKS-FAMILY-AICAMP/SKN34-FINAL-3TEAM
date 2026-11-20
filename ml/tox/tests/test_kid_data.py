import json

import kid_data as K


def test_kid_rows_are_pairs_and_never_overlap_the_test_set():
    spec = json.loads(K.TRAIN.read_text(encoding="utf-8"))
    test = json.loads(K.TEST.read_text(encoding="utf-8"))
    rows = K.build(spec)
    texts = [r["text"] for r in rows]
    assert len(texts) == len(set(texts))
    assert {r["label"] for r in rows} == {0, 1}
    assert not K.overlaps(rows, test["block"] + test["pass"])
    assert not set(texts) & set(test["block"] + test["pass"])


def test_overlap_finds_shared_fragment():
    rows = [{"text": "너는 정말 쓰잘데기 없는 애야.", "label": 1}]
    assert K.overlaps(rows, ["걔는 정말 쓰잘데기 없는 애야."])
    assert not K.overlaps(rows, ["너는 정말 친절한 친구야."])
