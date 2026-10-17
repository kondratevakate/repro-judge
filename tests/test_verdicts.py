from repro_judge import verdicts


def test_normalize_orders_by_claim_and_fills_missing():
    raw = {"claims": [{"claim": 2, "verdict": "Falsified", "evidence": "e2"},
                      {"claim": "1", "verdict": "verified", "evidence": "e1"}]}
    rows = verdicts.normalize(raw, 3)
    assert [r["verdict"] for r in rows] == ["verified", "falsified", "inconclusive"]
    assert rows[2]["issue"] == "missing"


def test_unknown_word_is_flagged_not_hidden():
    rows = verdicts.normalize({"claims": [{"claim": 1, "verdict": "partially"}]}, 1)
    assert rows[0]["verdict"] == "inconclusive"
    assert "partially" in rows[0]["issue"]


def test_garbage_claim_index_is_ignored():
    rows = verdicts.normalize({"claims": [{"claim": "one", "verdict": "verified"}, "junk"]}, 1)
    assert rows[0]["issue"] == "missing"


def test_points_follow_the_challenge_scale():
    rows = [{"verdict": v} for v in ("verified", "falsified", "toy", "inconclusive")]
    assert verdicts.points(rows) == 5
