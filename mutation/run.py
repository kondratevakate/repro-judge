"""Protocol 004 runner: build edited logbooks, gate, dry run, judge, never overwrite.

Usage (from the repository root):
  python mutation/run.py gate
  python mutation/run.py run --dry-run
  python mutation/run.py run [--limit N] [--workers 3]
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(HERE))
import judge as J  # noqa: E402
from repro_judge import logbook, prompt, router, verdicts  # noqa: E402
import mutate as M  # noqa: E402

RUN = "mut_001"
BASE = "calib_002"
CAP_USD = 12.0
ARMS = {"R1": ("verified",), "I1": ("verified",), "I3": ("inconclusive", "toy")}


def population():
    return json.loads((J.RUNS / "calib_001/population.json").read_text(encoding="utf-8"))["items"]


def raw_pages(item):
    path = J.CACHE / f"{J.safe_name(item['space_id'])}__{item['sha']}.pages.json"
    return [tuple(p) for p in json.loads(path.read_text(encoding="utf-8"))["pages"]]


def baseline(item):
    path = J.RUNS / BASE / "passA" / f"{J.safe_name(item['space_id'])}__r1.json"
    return json.loads(path.read_text(encoding="utf-8"))


def gate() -> dict:
    cfg = dict(J.DEFAULTS)
    _, rubric_sha = prompt.load_rubric(cfg["rubric"])
    man = json.loads((J.RUNS / BASE / "manifest.json").read_text(encoding="utf-8"))
    problems = []
    if rubric_sha != man["rubric_sha256"]:
        problems.append("rubric sha differs from calib_002")
    if any(man[k] != cfg[k] for k in J.DEFAULTS):
        problems.append("judge settings differ from calib_002")
    for it in population():
        text, _ = logbook.assemble(raw_pages(it))
        if len(text) != baseline(it)["logbook_chars"]:
            problems.append(f"{it['space_id']}: cleaned length {len(text)} != {baseline(it)['logbook_chars']}")
    return {"passed": not problems, "problems": problems, "rubric_sha256": rubric_sha}


def jobs():
    out, skipped = [], []
    for it in population():
        pages = raw_pages(it)
        for i, off in enumerate(it["official"], 1):
            for arm, allowed in ARMS.items():
                if off not in allowed:
                    continue
                if M.claim_page_index(pages, i) is None:
                    skipped.append((it["space_id"], i, arm))
                    continue
                out.append((arm, it, i))
    return out, skipped


def out_path(arm, it, i):
    return J.RUNS / RUN / arm / f"{J.safe_name(it['space_id'])}__c{i}.json"


def build(arm, it, i, rubric):
    pages, edit = M.EDITS[arm](raw_pages(it), i)
    text, stats = logbook.assemble(pages)
    nonce = prompt.new_nonce(text)
    msgs = prompt.build_messages(rubric, {"title": it["title"], "orid": it["orid"], "authors": it["authors"]},
                                 it["claims"], text, nonce)
    return msgs, text, stats, nonce, edit


def judge_job(arm, it, i, cfg, rubric, token):
    t0 = time.time()
    msgs, text, stats, nonce, edit = build(arm, it, i, rubric)
    res = router.judge_call(msgs, token=token, model=cfg["model"], provider=cfg["provider"],
                            temperature=cfg["temperature"], max_tokens=cfg["max_tokens"], attempts=cfg["attempts"])
    rows = verdicts.normalize(res["parsed"], len(it["claims"]))
    base = {v["claim"]: v["verdict"] for v in baseline(it)["verdicts"]}
    return {"space_id": it["space_id"], "sha": it["sha"], "arm": arm, "target_claim": i, "edit": edit,
            "official": it["official"], "baseline": [base.get(k + 1) for k in range(len(it["claims"]))],
            "verdicts": rows, "judged_at": J.now(), "logbook_chars": len(text), "cleaning": stats,
            "nonce": nonce, "usage": res["usage"], "attempts": res["attempts"],
            "finish_reason": res["finish_reason"], "model_id": res["model_id"], "served_by": res["served_by"],
            "raw_content": res["content"], "elapsed_s": round(time.time() - t0, 1)}


def file_sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def cmd_run(a):
    g = gate()
    if not g["passed"]:
        sys.exit("gate failed:\n" + "\n".join(g["problems"]))
    cfg = dict(J.DEFAULTS)
    rubric, rubric_sha = prompt.load_rubric(cfg["rubric"])
    token = J.require_token()
    all_jobs, skipped = jobs()
    todo = [j for j in all_jobs if not out_path(*j).exists()]
    if a.limit:
        todo = todo[: a.limit]
    print(f"jobs {len(all_jobs)} (skipped, no unique claim page: {len(skipped)}), to do {len(todo)}")
    if a.dry_run:
        pricing = J.provider_pricing(cfg["model"], cfg["provider"])
        chars = sum(sum(len(m["content"]) for m in build(arm, it, i, rubric)[0]) for arm, it, i in todo)
        lo = chars / 4 / 1e6 * pricing["input"]
        hi = lo + len(todo) * cfg["max_tokens"] / 1e6 * pricing["output"]
        by_arm = {arm: sum(1 for x in todo if x[0] == arm) for arm in ARMS}
        print(f"dry run: by arm {by_arm}; input about ${lo:.2f}; with full output budget at most ${hi:.2f}; cap ${CAP_USD}")
        print("WITHIN CAP" if hi <= CAP_USD else "ABOVE CAP: stop and ask before any paid call")
        return
    man = J.RUNS / RUN / "manifest.json"
    if not man.exists():
        J.write_new(man, {**cfg, "protocol": "004", "rubric_sha256": rubric_sha, "judge_code_sha256": J.code_sha256(),
                          "mutate_sha256": file_sha(HERE / "mutate.py"), "run_sha256": file_sha(Path(__file__)),
                          "git_rev": J.git_rev(),
                          "git_dirty": bool(subprocess.run(["git", "-C", str(ROOT), "status", "--porcelain"],
                                                           capture_output=True, text=True).stdout.strip()),
                          "gate": g, "baseline_run": BASE, "pricing_per_million": J.provider_pricing(cfg["model"], cfg["provider"]),
                          "created_at": J.now()})
    done = errors = 0
    with cf.ThreadPoolExecutor(max_workers=a.workers) as pool:
        futs = {pool.submit(judge_job, arm, it, i, cfg, rubric, token): (arm, it, i) for arm, it, i in todo}
        for f in cf.as_completed(futs):
            arm, it, i = futs[f]
            try:
                rec = f.result()
            except Exception as e:  # recorded, never swallowed
                errors += 1
                err = J.RUNS / RUN / arm / "errors" / f"{J.safe_name(it['space_id'])}__c{i}__{int(time.time())}.json"
                err.parent.mkdir(parents=True, exist_ok=True)
                err.write_text(json.dumps({"space_id": it["space_id"], "claim": i, "arm": arm, "at": J.now(),
                                           "error": f"{type(e).__name__}: {e}"[:500]}), encoding="utf-8", newline="\n")
                print(f"ERROR {arm} {it['space_id']} c{i}: {type(e).__name__}: {str(e)[:160]}", flush=True)
                continue
            J.write_new(out_path(arm, it, i), rec)
            done += 1
            v = rec["verdicts"][i - 1]["verdict"]
            print(f"[{done}/{len(todo)}] {arm} {it['space_id'][-40:]} c{i}: {rec['baseline'][i - 1]} -> {v} "
                  f"served_by={rec['served_by']}", flush=True)
    print(f"done {done}, errors {errors}")
    if errors:
        sys.exit(f"{errors} job(s) failed; rerun to retry")


def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("gate")
    r = sub.add_parser("run")
    r.add_argument("--dry-run", action="store_true")
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--workers", type=int, default=3)
    a = p.parse_args()
    if a.cmd == "gate":
        print(json.dumps(gate(), indent=1))
    else:
        cmd_run(a)


if __name__ == "__main__":
    main()
