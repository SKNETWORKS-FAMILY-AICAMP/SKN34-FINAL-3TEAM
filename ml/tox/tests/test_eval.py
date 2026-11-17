import eval as E


def test_sql_sentences_keeps_korean_and_unescapes():
    sql = "INSERT INTO m VALUES ('abc', '고양이''s 집', 'x'), ('나무는 자란다');"
    assert E.sql_sentences(sql) == ["고양이's 집", "나무는 자란다"]


def test_kotlin_pass_sentences_reads_only_null_cases():
    kt = """
        assertAll(PROFANITY, listOf("막을 말"))
        assertAll(
            null,
            listOf("죽고 싶다", "3 x 4 = 12",
                "새끼 고양이"),
        )
        assertEquals(null, check("고양이가 새끼를 낳았다", mission))
        assertEquals(PROFANITY, check("막을 말 2"))
    """
    assert E.kotlin_pass_sentences(kt) == ["죽고 싶다", "3 x 4 = 12", "새끼 고양이"]
    assert E.kotlin_context_sentences(kt) == ["고양이가 새끼를 낳았다"]


def test_ts_sentences_keeps_korean_and_drops_template_parts():
    ts = "const a = { t: '안녕', u: \"abc\", v: `${n}번째 답이에요` }"
    assert E.ts_sentences(ts) == ["안녕", "번째 답이에요"]


def test_must_pass_reads_repo_files():
    sets = E.must_pass()
    assert len(sets["demo"]) > 100
    assert len(sets["web"]) > 50
    assert len(sets["trap"]) > 40
    assert "죽고 싶다" in sets["trap"]
    assert "고양이가 새끼를 다섯 마리 낳았다" not in sets["trap"]


def test_pick_threshold_respects_must_pass_and_fpr():
    probs = [0.9, 0.8, 0.6, 0.3, 0.2, 0.1]
    labels = [1, 1, 1, 0, 0, 0]
    t, m = E.pick_threshold(probs, labels, must_pass_max=0.0)
    assert 0.3 < t <= 0.6 and m["f1"] == 1.0
    t, m = E.pick_threshold(probs, labels, must_pass_max=0.7)
    assert t > 0.7 and m["recall"] < 1.0
    t, m = E.pick_threshold(probs, labels, must_pass_max=0.99)
    assert t is None and "reason" in m
