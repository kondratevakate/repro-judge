import pytest

import judge


def sp(i, tag, created="2026-07-01T00:00:00Z"):
    return {"id": i, "tags": [f"paper-{tag}"], "createdAt": created}


def v(at):
    return {"claims": [{"claim": "c", "verdict": "toy"}], "judged_at": at}


def test_judged_space_beats_unjudged_and_earliest_verdict_wins():
    spaces = [sp("u/a", "P1"), sp("u/b", "P1"), sp("u/c", "P1")]
    verdicts = {"u/b": v("2026-07-20T00:00:00+00:00"), "u/c": v("2026-07-10T00:00:00+00:00")}
    out = judge.canonical_judged(spaces, verdicts)
    assert [x["space_id"] for x in out] == ["u/c"]


def test_tag_case_is_ignored_and_untagged_space_skipped():
    spaces = [sp("u/a", "AbC"), sp("u/b", "abc"), {"id": "u/z", "tags": ["trackio"]}]
    verdicts = {"u/a": v("2026-07-02T00:00:00+00:00"), "u/b": v("2026-07-01T00:00:00+00:00")}
    out = judge.canonical_judged(spaces, verdicts)
    assert [x["space_id"] for x in out] == ["u/b"]


def test_read_claims_strips_numbering(tmp_path):
    f = tmp_path / "c.txt"
    f.write_text("# comment\n1. first claim\n- second\n\n3) third\n", encoding="utf-8")
    assert judge.read_claims(str(f)) == ["first claim", "second", "third"]


def test_write_new_refuses_overwrite(tmp_path):
    p = tmp_path / "x.json"
    judge.write_new(p, {"a": 1})
    with pytest.raises(FileExistsError):
        judge.write_new(p, {"a": 2})
