import pytest

from repro_judge import agreement


def test_cohen_kappa_hand_computed():
    # p_obs = 3/4, p_exp = (2*1 + 2*3) / 16 = 1/2, kappa = 1/2
    a = ["verified", "verified", "toy", "toy"]
    b = ["verified", "toy", "toy", "toy"]
    assert agreement.cohen_kappa(a, b) == pytest.approx(0.5)


def test_cohen_kappa_perfect_and_constant():
    a = ["verified", "toy", "inconclusive"]
    assert agreement.cohen_kappa(a, a) == pytest.approx(1.0)
    same = ["toy"] * 4
    assert agreement.cohen_kappa(same, same) == 1.0


def test_fleiss_kappa_hand_computed():
    # P_bar = 1/2, P_e = (3/4)^2 + (1/4)^2 = 5/8, kappa = -1/3
    items = [["verified", "verified"], ["verified", "toy"]]
    assert agreement.fleiss_kappa(items) == pytest.approx(-1 / 3)


def test_fleiss_kappa_identical_runs():
    items = [["toy"] * 3, ["verified"] * 3, ["inconclusive"] * 3]
    assert agreement.fleiss_kappa(items) == pytest.approx(1.0)


def test_confusion_counts():
    c = agreement.confusion(["verified", "toy"], ["toy", "toy"])
    assert c["verified"]["toy"] == 1 and c["toy"]["toy"] == 1 and c["toy"]["verified"] == 0


def test_length_mismatch_raises():
    with pytest.raises(ValueError):
        agreement.exact_share(["toy"], ["toy", "toy"])
    with pytest.raises(ValueError):
        agreement.fleiss_kappa([["toy", "toy"], ["toy"]])
