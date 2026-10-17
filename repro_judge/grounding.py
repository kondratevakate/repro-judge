"""Diagnostic: are the numbers a verdict cites actually present in what the judge saw?

A cited number is grounded when some visible number rounds to it at the precision it
is written with, or when it is a percentage of a visible fraction. Integers from 0 to
10 are ignored because they are everywhere (claim numbers, small sizes). The check
flags verdicts for manual review and never changes them.
"""
import re

# A number may not continue into a hex digit or underscore, so hashes such as
# "199e996c..." are not read as 199e996. Units like "1.89x" or "12ms" still parse.
_NUMBER = re.compile(r"(?<![\w.])[-−+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-−+]?\d+)?%?(?![0-9a-fA-F_])")
POINT_VERDICTS = {"verified", "falsified", "toy"}
MIN_GROUNDED_SHARE = 0.5


def parse_numbers(text: str) -> list[tuple[float, float, bool]]:
    """Return (value, half of the last written digit, written as percent) for each number."""
    out = []
    for token in _NUMBER.findall(text):
        pct = token.endswith("%")
        t = token.rstrip("%").replace("−", "-").replace(",", "").lstrip("+")
        try:
            value = float(t)
        except ValueError:
            continue
        mantissa = re.split(r"[eE]", t)[0]
        decimals = len(mantissa.split(".")[1]) if "." in mantissa else 0
        exponent = int(re.split(r"[eE]", t)[1]) if re.search(r"[eE]", t) else 0
        # parsed from text so an extreme exponent gives inf or 0.0 instead of OverflowError
        half_step = float(f"5e{exponent - decimals - 1}")
        out.append((value, half_step, pct))
    return out


def eligible(value: float, pct: bool) -> bool:
    return pct or not (value.is_integer() and 0 <= value <= 10)


def grounded(cited: tuple[float, float, bool], visible: list[float]) -> bool:
    value, half_step, pct = cited
    tol = half_step * (1 + 1e-9)
    candidates = [value] + ([value / 100] if pct else [])
    for v in visible:
        for c in candidates:
            if abs(v - c) <= (tol if c == value else tol / 100):
                return True
    return False


def visible_values(text: str) -> list[float]:
    """Every visible number, plus its fraction when it is written as a percentage."""
    out = []
    for v, _, pct in parse_numbers(text):
        out.append(v)
        if pct:
            out.append(v / 100)
    return out


def check_verdict(evidence: str, verdict: str, visible_text: str) -> dict:
    visible = visible_values(visible_text)
    cited = [n for n in parse_numbers(evidence) if eligible(n[0], n[2])]
    hits = [grounded(n, visible) for n in cited]
    share = sum(hits) / len(hits) if hits else None
    flagged = verdict in POINT_VERDICTS and bool(hits) and share < MIN_GROUNDED_SHARE
    return {"cited": len(cited), "grounded": sum(hits), "share": share, "flagged": flagged,
            "ungrounded": [n[0] for n, ok in zip(cited, hits) if not ok][:10]}
