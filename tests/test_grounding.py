import pytest

from repro_judge import grounding


def values(text):
    return [v for v, _, _ in grounding.parse_numbers(text)]


def test_parse_handles_separators_signs_percent_and_exponents():
    assert values("30,000 points, −0.023 bias, 92% power, 1.11e-16 error") == [30000, -0.023, 92, 1.11e-16]


def test_identifiers_are_not_numbers_but_dates_are_visible_numbers():
    assert values("sha256 v1.0 build x2") == []
    assert values("run on 2026-07-29") == [2026, 7, 29]  # the hyphen is a separator, not a minus


def test_rounded_citation_is_grounded():
    r = grounding.check_verdict("bias 0.0866 at 30,000 points", "verified", "bias = 0.086612, n = 30000")
    assert r == {"cited": 2, "grounded": 2, "share": 1.0, "flagged": False, "ungrounded": []}


def test_percent_and_fraction_cross_match():
    assert grounding.check_verdict("power 68.9%", "verified", "power 0.68929")["grounded"] == 1
    assert grounding.check_verdict("power 0.689", "verified", "power 68.9%")["grounded"] == 1


def test_small_integers_are_ignored():
    r = grounding.check_verdict("claims 1, 2 and 3 over 5 seeds", "verified", "nothing numeric here")
    assert r["cited"] == 0 and r["flagged"] is False


def test_invented_numbers_flag_a_point_verdict_only():
    evidence = "coverage 0.951 and width 3.7 on 12,000 points"
    seen = "coverage 0.903 width 4.2 on 500 points"
    assert grounding.check_verdict(evidence, "verified", seen)["flagged"] is True
    assert grounding.check_verdict(evidence, "inconclusive", seen)["flagged"] is False


def test_half_grounded_is_not_flagged():
    r = grounding.check_verdict("values 0.25 and 0.75", "toy", "only 0.25 is reported")
    assert r["share"] == pytest.approx(0.5) and r["flagged"] is False
