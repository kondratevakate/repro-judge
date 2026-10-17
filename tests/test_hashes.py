import judge
from repro_judge import prompt


def _tree(root, eol):
    (root / "repro_judge").mkdir(parents=True)
    (root / "judge.py").write_bytes(f"a = 1{eol}b = 2{eol}".encode())
    (root / "repro_judge" / "m.py").write_bytes(f"x = 3{eol}".encode())


def test_code_hash_ignores_line_endings(tmp_path, monkeypatch):
    # Regression: a CRLF checkout must not look like different judging code.
    _tree(tmp_path / "lf", "\n")
    _tree(tmp_path / "crlf", "\r\n")
    monkeypatch.setattr(judge, "ROOT", tmp_path / "lf")
    lf = judge.code_sha256()
    monkeypatch.setattr(judge, "ROOT", tmp_path / "crlf")
    assert judge.code_sha256() == lf


def test_rubric_hash_ignores_line_endings(tmp_path, monkeypatch):
    (tmp_path / "lf.md").write_bytes(b"line one\nline two\n")
    (tmp_path / "crlf.md").write_bytes(b"line one\r\nline two\r\n")
    monkeypatch.setattr(prompt, "RUBRIC_DIR", tmp_path)
    assert prompt.load_rubric("lf") == prompt.load_rubric("crlf")
