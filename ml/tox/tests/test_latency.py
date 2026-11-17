import latency as L


def test_make_text_exact_length():
    s = ["가나다", "라마"]
    for n in (1, 5, 200, 1500):
        assert len(L.make_text(s, n)) == n
    assert L.make_text(s, 7) == "가나다 라마 "


def test_percentile_matches_linear_interpolation():
    xs = [float(i) for i in range(1, 11)]
    assert L.percentile(xs, 0.5) == 5.5
    assert round(L.percentile(xs, 0.95), 2) == 9.55
    assert L.percentile([3.0], 0.95) == 3.0
