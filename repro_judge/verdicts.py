"""Verdict vocabulary, normalisation of judge output, and points."""

VERDICTS = ("verified", "falsified", "toy", "inconclusive")
POINTS = {"verified": 2, "falsified": 2, "toy": 1, "inconclusive": 0}
MAX_EVIDENCE_CHARS = 600


def normalize(raw: dict, n_claims: int) -> list[dict]:
    """One verdict per claim, in claim order.

    A claim the judge skipped or labelled with an unknown word becomes
    "inconclusive", and the row says why, so nothing is coerced silently.
    """
    by_index = {}
    for item in raw.get("claims") or []:
        try:
            by_index[int(item.get("claim"))] = item
        except (TypeError, ValueError, AttributeError):
            continue
    rows = []
    for i in range(1, n_claims + 1):
        item = by_index.get(i)
        if item is None:
            rows.append({"claim": i, "verdict": "inconclusive", "evidence": "", "issue": "missing"})
            continue
        word = str(item.get("verdict", "")).strip().lower()
        row = {"claim": i, "verdict": word, "evidence": str(item.get("evidence", ""))[:MAX_EVIDENCE_CHARS]}
        if word not in POINTS:
            row.update(verdict="inconclusive", issue=f"unknown verdict {word!r}")
        rows.append(row)
    return rows


def points(rows: list[dict]) -> int:
    return sum(POINTS[r["verdict"]] for r in rows)
