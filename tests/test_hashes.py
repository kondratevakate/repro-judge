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


def test_results_are_written_with_lf(tmp_path):
    p = tmp_path / "r.json"
    judge.write_new(p, {"a": [1, 2]})
    assert b"\r\n" not in p.read_bytes() and b"\n" in p.read_bytes()


def test_copy_from_hash_ignores_line_endings(tmp_path, monkeypatch):
    # Regression: calib_002 recorded the hash of a CRLF file that Git stores as LF.
    import argparse
    import json

    monkeypatch.setattr(judge, "RUNS", tmp_path)
    body = json.dumps({"n": 1, "official_total": 2, "items": []}, indent=1)
    for name, eol in (("src_lf", "\n"), ("src_crlf", "\r\n")):
        (tmp_path / name).mkdir()
        (tmp_path / name / "population.json").write_bytes(body.replace("\n", eol).encode())
    hashes = []
    for name in ("src_lf", "src_crlf"):
        judge.cmd_prepare(argparse.Namespace(run=f"copy_{name}", copy_from=name, user=None, verdicts=None))
        rec = json.loads((tmp_path / f"copy_{name}" / "population.json").read_text(encoding="utf-8"))
        hashes.append(rec["copied_from"]["sha256_lf"])
    assert hashes[0] == hashes[1] == judge.lf_sha256(body.encode())


def test_rubric_hash_ignores_line_endings(tmp_path, monkeypatch):
    (tmp_path / "lf.md").write_bytes(b"line one\nline two\n")
    (tmp_path / "crlf.md").write_bytes(b"line one\r\nline two\r\n")
    monkeypatch.setattr(prompt, "RUBRIC_DIR", tmp_path)
    assert prompt.load_rubric("lf") == prompt.load_rubric("crlf")
