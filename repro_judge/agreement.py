"""Agreement statistics between judges, without external dependencies."""
from collections import Counter

from .verdicts import VERDICTS


def confusion(a: list[str], b: list[str], labels=VERDICTS) -> dict:
    if len(a) != len(b):
        raise ValueError("rating lists differ in length")
    counts = Counter(zip(a, b))
    return {x: {y: counts.get((x, y), 0) for y in labels} for x in labels}


def exact_share(a: list[str], b: list[str]) -> float:
    if not a or len(a) != len(b):
        raise ValueError("need two non-empty rating lists of equal length")
    return sum(x == y for x, y in zip(a, b)) / len(a)


def cohen_kappa(a: list[str], b: list[str], labels=VERDICTS) -> float:
    n = len(a)
    p_obs = exact_share(a, b)
    ca, cb = Counter(a), Counter(b)
    p_exp = sum(ca[l] * cb[l] for l in labels) / (n * n)
    if p_exp == 1.0:
        return 1.0 if p_obs == 1.0 else 0.0
    return (p_obs - p_exp) / (1 - p_exp)


def fleiss_kappa(items: list[list[str]], labels=VERDICTS) -> float:
    """items: one list of ratings per item, every item rated the same number of times."""
    if not items:
        raise ValueError("no items")
    m = len(items[0])
    if m < 2 or any(len(r) != m for r in items):
        raise ValueError("each item needs the same number of ratings, at least 2")
    n = len(items)
    per_item = [Counter(r) for r in items]
    p_i = [(sum(c[l] ** 2 for l in labels) - m) / (m * (m - 1)) for c in per_item]
    p_bar = sum(p_i) / n
    p_l = [sum(c[l] for c in per_item) / (n * m) for l in labels]
    p_e = sum(p ** 2 for p in p_l)
    if p_e == 1.0:
        return 1.0 if p_bar == 1.0 else 0.0
    return (p_bar - p_e) / (1 - p_e)
