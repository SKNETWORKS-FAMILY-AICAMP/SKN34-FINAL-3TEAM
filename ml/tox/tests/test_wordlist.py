import wordlist as W


def test_with_wordlist_counts_only_what_the_word_list_passed():
    probs = [0.9, 0.9, 0.1, 0.9, 0.1, 0.1]
    labels = [1, 1, 1, 0, 0, 0]
    flags = [1, 0, 0, 0, 1, 0]  # 단어 목록: 막을 글 1개·정상 글 1개를 막음
    r = W.with_wordlist(probs, labels, flags, 0.5)
    assert r["wordListRecall"] == round(1 / 3, 4)
    assert r["extraCatch"] == 0.5  # 단어 목록이 놓친 막을 글 2개 중 1개
    assert r["extraFalsePositiveRate"] == 0.5  # 단어 목록이 통과시킨 정상 글 2개 중 1개
    assert r["combinedRecall"] == round(2 / 3, 4)
    assert r["combinedFalsePositiveRate"] == round(2 / 3, 4)


def test_pick_respects_must_pass_and_extra_fp():
    probs = [0.95, 0.85, 0.6, 0.7, 0.2, 0.1]
    labels = [1, 1, 1, 0, 0, 0]
    flags = [0, 0, 0, 1, 0, 0]  # 0.7 정상 글은 단어 목록이 이미 막음 → 추가 오탐 아님
    t, r = W.pick(probs, labels, flags, must_pass_max=0.0)
    assert 0.2 < t <= 0.6 and r["extraFalsePositiveRate"] == 0.0
    t, _ = W.pick(probs, labels, flags, must_pass_max=0.9)
    assert t > 0.9
    t, r = W.pick(probs, labels, flags, must_pass_max=0.99)
    assert t is None and "reason" in r
