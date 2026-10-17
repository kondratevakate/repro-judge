import pytest

from repro_judge import prompt


def test_icml_rubric_loads_and_hash_is_stable():
    text, sha = prompt.load_rubric("icml2026")
    assert "not evidence" in text and len(sha) == 64
    assert prompt.load_rubric("icml2026")[1] == sha


def test_rubric_with_open_todo_is_refused():
    with pytest.raises(prompt.RubricNotReady):
        prompt.load_rubric("clinical")


def test_messages_number_claims_and_cap_authors():
    paper = {"title": "T", "orid": "abc", "authors": [f"A{i}" for i in range(12)]}
    msgs = prompt.build_messages("RUBRIC", paper, ["first", "second"], "LOGBOOK")
    assert msgs[0] == {"role": "system", "content": "RUBRIC"}
    user = msgs[1]["content"]
    assert "1. first\n2. second" in user and "LOGBOOK" in user
    assert "A7" in user and "A8" not in user


def test_empty_claims_refused():
    with pytest.raises(ValueError):
        prompt.build_messages("R", {}, [], "L")
