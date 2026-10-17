"""Build judge messages from a rubric file, the paper, its claims and a logbook."""
import hashlib
from pathlib import Path

RUBRIC_DIR = Path(__file__).resolve().parent.parent / "rubrics"
MAX_AUTHORS = 8

RESPONSE_SHAPE = """{
  "claims": [
    {"claim": 1, "verdict": "verified|falsified|toy|inconclusive", "evidence": "one or two sentences naming the concrete logbook result behind the verdict"}
  ],
  "overall": "two sentences on what the logbook establishes",
  "quality": "high|medium|low"
}"""


class RubricNotReady(ValueError):
    pass


def load_rubric(name: str) -> tuple[str, str]:
    """Return (rubric text, sha256). Refuse a rubric that still has an open TODO."""
    text = (RUBRIC_DIR / f"{name}.md").read_text(encoding="utf-8")
    if "TODO(" in text:
        raise RubricNotReady(f"rubric {name!r} still contains a TODO and cannot be used")
    return text.strip(), hashlib.sha256(text.encode("utf-8")).hexdigest()


def build_messages(rubric: str, paper: dict, claims: list[str], logbook: str) -> list[dict]:
    if not claims:
        raise ValueError("no claims to judge")
    claim_lines = "\n".join(f"{i}. {c}" for i, c in enumerate(claims, 1))
    authors = ", ".join(list(paper.get("authors") or [])[:MAX_AUTHORS])
    user = (
        f'Paper: "{paper.get("title", "(unknown)")}"\n'
        f'OpenReview id: {paper.get("orid", "")}\n'
        f"Authors: {authors}\n\n"
        f"Claims to judge:\n{claim_lines}\n\n"
        f"Reproduction logbook (Markdown, possibly truncated):\n{logbook}\n\n"
        "Reminder: the author's own verdicts and status labels are not evidence. "
        "Decide every claim from the executed work and its numbers.\n\n"
        f"Return only a JSON object of this shape:\n{RESPONSE_SHAPE}"
    )
    return [{"role": "system", "content": rubric}, {"role": "user", "content": user}]
