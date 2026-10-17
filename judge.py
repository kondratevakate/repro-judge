"""repro-judge command line.

  python judge.py judge --space USER/SPACE --claims claims.txt [--rubric icml2026_v2]
  python judge.py prepare --run calib_001 --user kondratevakate --verdicts verdicts.json
  python judge.py prepare --run calib_002 --copy-from calib_001
  python judge.py run --run calib_002 --pass A [--limit 1] [--dry-run]
  python judge.py run --run calib_002 --pass B
  python judge.py report --run calib_002 [--baseline calib_001]
"""
import argparse
import concurrent.futures as cf
import datetime as dt
import hashlib
import json
import platform
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx
import huggingface_hub
from huggingface_hub import get_token

from repro_judge import agreement, grounding, logbook, prompt, router, verdicts

ROOT = Path(__file__).resolve().parent
RUNS = ROOT / "runs"
CACHE = ROOT / "cache"
CHALLENGE_INDEX = "https://huggingface.co/spaces/ICML-2026-agent-repro/challenge/resolve/main/index.json"
ROUTER_MODELS = "https://router.huggingface.co/v1/models"
DEFAULTS = {"model": "zai-org/GLM-5.2", "provider": "novita", "temperature": 0.1,
            "max_tokens": 8000, "attempts": 2, "rubric": "icml2026_v2"}
RETEST_POSITIONS = range(0, 50, 5)  # 1-based positions 1, 6, ..., 46


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def write_new(path: Path, obj) -> None:
    """Write JSON, refusing to replace an existing accepted result."""
    if path.exists():
        raise FileExistsError(f"{path} exists; results are never overwritten")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def require_token() -> str:
    token = get_token()
    if not token:
        sys.exit("No Hugging Face token found. Run `hf auth login` first.")
    return token


def safe_name(space_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", space_id)


def git_rev() -> str:
    try:
        return subprocess.run(["git", "-C", str(ROOT), "rev-parse", "HEAD"], capture_output=True,
                              text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "uncommitted"


def provider_pricing(model: str, provider: str) -> dict | None:
    rows = httpx.get(ROUTER_MODELS, timeout=60).json().get("data", [])
    for row in rows:
        if row.get("id") == model:
            for p in row.get("providers", []):
                if p.get("provider") == provider:
                    return p.get("pricing")
    return None


# ---------------------------------------------------------------- prepare

def _ts(value: str) -> float:
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return float("inf")


def _better(cand: dict, cur: dict | None) -> bool:
    """Leaderboard rule: a judged Space beats an unjudged one, then the earliest
    verdict (or creation time) wins, then the smaller Space id."""
    if cur is None:
        return True
    if cand["judged"] != cur["judged"]:
        return cand["judged"]
    if cand["when"] != cur["when"]:
        return cand["when"] < cur["when"]
    return cand["space_id"] < cur["space_id"]


def canonical_judged(spaces: list[dict], all_verdicts: dict) -> list[dict]:
    best = {}
    for sp in spaces:
        tag = next((t[6:] for t in sp.get("tags", []) if str(t).lower().startswith("paper-")), None)
        if not tag:
            continue
        v = all_verdicts.get(sp["id"])
        judged = bool(v and isinstance(v.get("claims"), list))
        cand = {"space_id": sp["id"], "orid_tag": tag.lower(), "judged": judged,
                "when": _ts(v["judged_at"]) if judged else _ts(sp.get("createdAt", ""))}
        if _better(cand, best.get(cand["orid_tag"])):
            best[cand["orid_tag"]] = cand
    return [c for c in best.values() if c["judged"]]


def cmd_prepare(a) -> None:
    out = RUNS / a.run / "population.json"
    if out.exists():
        sys.exit(f"{out} exists; a frozen population is never rebuilt in place")
    if a.copy_from:
        src = RUNS / a.copy_from / "population.json"
        raw = src.read_bytes()
        pop = json.loads(raw)
        pop["copied_from"] = {"run": a.copy_from, "sha256": hashlib.sha256(raw).hexdigest(), "at": now()}
        write_new(out, pop)
        print(f"population copied from {a.copy_from}: {pop['n']} logbooks, official total {pop['official_total']}")
        return
    if not (a.user and a.verdicts):
        sys.exit("prepare needs --user and --verdicts, or --copy-from")
    all_verdicts = json.loads(Path(a.verdicts).read_text(encoding="utf-8"))
    spaces = httpx.get("https://huggingface.co/api/spaces",
                       params={"author": a.user, "full": "true", "limit": 1000}, timeout=120).json()
    index = httpx.get(CHALLENGE_INDEX, follow_redirects=True, timeout=120).json()
    papers = index.get("papers") if isinstance(index, dict) else index
    by_orid = {str(p["orid"]): p for p in papers if isinstance(p, dict) and p.get("orid")}
    items = []
    for c in canonical_judged(spaces, all_verdicts):
        v = all_verdicts[c["space_id"]]
        paper = by_orid.get(str(v.get("orid")), {})
        official = [str(x.get("verdict", "")).lower() for x in v["claims"]]
        items.append({
            "space_id": c["space_id"], "sha": v.get("sha"), "orid": v.get("orid"),
            "title": paper.get("title") or v.get("paper_title", ""),
            "authors": list(paper.get("authors") or []),
            "claims": [str(x.get("claim", "")) for x in v["claims"]],
            "official": official,
            "official_points": sum(verdicts.POINTS.get(x, 0) for x in official),
            "official_judged_at": v.get("judged_at"), "official_model": v.get("model"),
        })
    items.sort(key=lambda x: (-x["official_points"], x["space_id"]))
    retest = [items[i]["space_id"] for i in RETEST_POSITIONS if i < len(items)]
    total = sum(x["official_points"] for x in items)
    write_new(out, {"created_at": now(), "user": a.user, "n": len(items), "retest": retest,
                    "official_total": total, "items": items})
    print(f"population: {len(items)} logbooks, official total {total}, retest {len(retest)}")


# ---------------------------------------------------------------- run

def cached_logbook(space_id: str, sha: str, token: str) -> tuple[str, list[str], dict]:
    """Raw pages are cached; cleaning runs on every call so its version cannot go stale."""
    path = CACHE / f"{safe_name(space_id)}__{sha}.pages.json"
    if path.exists():
        pages = [tuple(p) for p in json.loads(path.read_text(encoding="utf-8"))["pages"]]
        failed = []
    else:
        pages, failed = logbook.fetch_space_pages(space_id, sha, token)
        if not failed:  # only complete fetches are cached
            CACHE.mkdir(exist_ok=True)
            path.write_text(json.dumps({"pages": pages}), encoding="utf-8")
    text, stats = logbook.assemble(pages)
    return text, failed, stats


def ground_rows(rows: list[dict], visible: str) -> None:
    """Attach the grounding diagnostic. It runs after a paid call, so a failure in it is
    recorded on the row instead of discarding the verdict."""
    for row in rows:
        try:
            row["grounding"] = grounding.check_verdict(row["evidence"], row["verdict"], visible)
        except Exception as e:
            row["grounding"] = {"error": f"{type(e).__name__}: {str(e)[:200]}", "flagged": False,
                                "cited": 0, "grounded": 0, "share": None, "ungrounded": []}


def judge_item(item: dict, run_no: int, cfg: dict, rubric: str, token: str) -> dict:
    t0 = time.time()
    text, failed, clean_stats = cached_logbook(item["space_id"], item["sha"], token)
    if failed:
        raise RuntimeError(f"{item['space_id']}: {len(failed)} page(s) could not be fetched")
    nonce = prompt.new_nonce(text)
    messages = prompt.build_messages(rubric, {"title": item["title"], "orid": item["orid"],
                                              "authors": item["authors"]}, item["claims"], text, nonce)
    res = router.judge_call(messages, token=token, model=cfg["model"], provider=cfg["provider"],
                            temperature=cfg["temperature"], max_tokens=cfg["max_tokens"],
                            attempts=cfg["attempts"])
    rows = verdicts.normalize(res["parsed"], len(item["claims"]))
    ground_rows(rows, text + "\n" + "\n".join(item["claims"]))
    return {"space_id": item["space_id"], "sha": item["sha"], "run": run_no, "judged_at": now(),
            "code_sha256": code_sha256(),
            "logbook_chars": len(text), "cleaning": clean_stats, "nonce": nonce,
            "verdicts": rows, "points": verdicts.points(rows),
            "overall": str(res["parsed"].get("overall", "")), "quality": str(res["parsed"].get("quality", "")),
            "usage": res["usage"], "attempts": res["attempts"], "finish_reason": res["finish_reason"],
            "model_id": res["model_id"], "served_by": res["served_by"], "raw_content": res["content"],
            "elapsed_s": round(time.time() - t0, 1)}


def code_sha256() -> str:
    """Hash of the judging code, so a run is traceable even before anything is committed.

    Line endings are normalised so a Windows checkout with CRLF hashes the same.
    """
    h = hashlib.sha256()
    for p in [ROOT / "judge.py", *sorted((ROOT / "repro_judge").glob("*.py"))]:
        h.update(p.name.encode())
        h.update(p.read_bytes().replace(b"\r\n", b"\n"))
    return h.hexdigest()


def check_manifest(run_dir: Path, cfg: dict, rubric_sha: str) -> None:
    manifest = run_dir / "manifest.json"
    if not manifest.exists():
        write_new(manifest, {**cfg, "rubric_sha256": rubric_sha, "code_sha256": code_sha256(),
                             "repro_judge_git": git_rev(),
                             "pricing_per_million": provider_pricing(cfg["model"], cfg["provider"]),
                             "python": platform.python_version(), "httpx": httpx.__version__,
                             "huggingface_hub": huggingface_hub.__version__, "created_at": now()})
        return
    m = json.loads(manifest.read_text(encoding="utf-8"))
    if m["rubric_sha256"] != rubric_sha or any(m[k] != cfg[k] for k in DEFAULTS):
        sys.exit("judge settings differ from this run's manifest; start a new run id instead")


def dry_run(todo: list, cfg: dict, rubric: str, token: str) -> None:
    """Build every prompt without calling the model and estimate the bill.

    Token counts use 4 characters per token, a rough rule; real counts are
    recorded from the router's usage field once the run happens.
    """
    pricing = provider_pricing(cfg["model"], cfg["provider"])
    chars, failures = 0, []
    cleaned = {k: 0 for k in ("comments", "format_chars", "headers_neutralised", "tags_neutralised",
                              "pages_with_unterminated_comment")}
    for it, _ in todo:
        text, failed, stats = cached_logbook(it["space_id"], it["sha"], token)
        if failed:
            failures.append((it["space_id"], failed))
        for k in cleaned:
            cleaned[k] += stats[k]
        msgs = prompt.build_messages(rubric, {"title": it["title"], "orid": it["orid"],
                                              "authors": it["authors"]}, it["claims"], text)
        chars += sum(len(m["content"]) for m in msgs)
    tok_in = chars / 4
    tok_out_max = len(todo) * cfg["max_tokens"]
    print(f"dry run: {len(todo)} judgments, {chars:,} prompt characters, about {tok_in:,.0f} input tokens")
    print(f"cleaning: {cleaned}")
    if pricing:
        lo = tok_in / 1e6 * pricing["input"]
        hi = lo + tok_out_max / 1e6 * pricing["output"]
        print(f"estimated cost at {cfg['provider']} prices {pricing}: input ${lo:.2f}, "
              f"with the full output budget at most ${hi:.2f}")
    else:
        print("no pricing published for this provider")
    for sid, failed in failures:
        print(f"FETCH FAILURE {sid}: {failed}")
    if failures:
        sys.exit(f"{len(failures)} logbook(s) incomplete; fix before a paid run")


def cmd_run(a) -> None:
    run_dir = RUNS / a.run
    pop = json.loads((run_dir / "population.json").read_text(encoding="utf-8"))
    cfg = dict(DEFAULTS)
    rubric, rubric_sha = prompt.load_rubric(cfg["rubric"])
    token = require_token()
    by_id = {x["space_id"]: x for x in pop["items"]}
    if a.pass_ == "A":
        jobs = [(by_id[s], 1) for s in by_id]
    else:
        jobs = [(by_id[s], k) for s in pop["retest"] for k in (2, 3)]
    out_dir = run_dir / f"pass{a.pass_}"
    todo = [(it, k) for it, k in jobs if not (out_dir / f"{safe_name(it['space_id'])}__r{k}.json").exists()]
    if a.limit:
        todo = todo[: a.limit]
    if a.dry_run:
        dry_run(todo, cfg, rubric, token)
        return
    check_manifest(run_dir, cfg, rubric_sha)
    print(f"pass {a.pass_}: {len(jobs)} jobs, {len(todo)} to do, workers {a.workers}")
    done = errors = 0
    t0 = time.time()

    def one(job):
        it, k = job
        return it, k, judge_item(it, k, cfg, rubric, token)

    with cf.ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures = {pool.submit(one, j): j for j in todo}
        for f in cf.as_completed(futures):
            it, k = futures[f]
            try:
                _, _, rec = f.result()
            except Exception as e:  # recorded per job, never swallowed
                errors += 1
                err = out_dir / "errors" / f"{safe_name(it['space_id'])}__r{k}__{int(time.time())}.json"
                err.parent.mkdir(parents=True, exist_ok=True)
                err.write_text(json.dumps({"space_id": it["space_id"], "run": k, "at": now(),
                                           "error": f"{type(e).__name__}: {e}"[:500]}), encoding="utf-8")
                print(f"ERROR {it['space_id']} r{k}: {type(e).__name__}: {str(e)[:160]}")
                continue
            write_new(out_dir / f"{safe_name(it['space_id'])}__r{k}.json", rec)
            done += 1
            print(f"[{done}/{len(todo)}] {it['space_id']} r{k}: {rec['points']}/{2 * len(it['claims'])} "
                  f"(official {it['official_points']}) {rec['elapsed_s']}s "
                  f"tokens {rec['usage']['prompt_tokens']}+{rec['usage']['completion_tokens']} "
                  f"served_by={rec['served_by']}", flush=True)
    print(f"done {done}, errors {errors}, wall {time.time() - t0:.0f}s")
    if errors:
        sys.exit(f"{errors} job(s) failed; see {out_dir / 'errors'}; rerun the same command to retry them")


# ---------------------------------------------------------------- report

def load_pass(run_dir: Path, name: str) -> dict:
    out = {}
    for p in sorted((run_dir / f"pass{name}").glob("*__r*.json")):
        rec = json.loads(p.read_text(encoding="utf-8"))
        out[(rec["space_id"], rec["run"])] = rec
    return out


def summarize(pop: dict, A: dict, B: dict, pricing: dict | None) -> dict:
    items = pop["items"]
    res = {"n_population": len(items),
           "missing": [x["space_id"] for x in items if (x["space_id"], 1) not in A]}
    off, mine, rows = [], [], []
    for x in items:
        rec = A.get((x["space_id"], 1))
        if rec is None:
            continue
        off += x["official"]
        mine += [r["verdict"] for r in rec["verdicts"]]
        rows.append({"space_id": x["space_id"], "official_points": x["official_points"],
                     "judge_points": rec["points"], "max_points": 2 * len(x["claims"])})
    res.update(n_judged=len(rows), n_claims=len(off))
    if off:
        res.update(exact_agreement=agreement.exact_share(off, mine),
                   cohen_kappa=agreement.cohen_kappa(off, mine),
                   confusion_official_rows=agreement.confusion(off, mine),
                   mean_abs_point_diff_per_claim=sum(abs(verdicts.POINTS[o] - verdicts.POINTS[m])
                                                     for o, m in zip(off, mine)) / len(off),
                   official_total=sum(r["official_points"] for r in rows),
                   judge_total=sum(r["judge_points"] for r in rows),
                   max_total=sum(r["max_points"] for r in rows), logbooks=rows)
    triples, retest_ids = [], []
    for s in pop["retest"]:
        runs = [A.get((s, 1)), B.get((s, 2)), B.get((s, 3))]
        if all(runs):
            retest_ids.append(s)
            triples += [[r["verdicts"][i]["verdict"] for r in runs] for i in range(len(runs[0]["verdicts"]))]
    if triples:
        res.update(retest_logbooks=len(retest_ids), retest_claims=len(triples),
                   retest_identical_share=sum(len(set(t)) == 1 for t in triples) / len(triples),
                   retest_fleiss_kappa=agreement.fleiss_kappa(triples))
    point_rows = [(r["space_id"], v) for r in A.values() for v in r["verdicts"]
                  if v["verdict"] in grounding.POINT_VERDICTS and "grounding" in v]
    if point_rows:
        flagged = [{"space_id": s, "claim": v["claim"], "verdict": v["verdict"],
                    "ungrounded": v["grounding"]["ungrounded"], "evidence": v["evidence"]}
                   for s, v in point_rows if v["grounding"]["flagged"]]
        with_numbers = [v for _, v in point_rows if v["grounding"]["cited"]]
        res["grounding_errors"] = sum(1 for r in A.values() for v in r["verdicts"]
                                      if "error" in v.get("grounding", {}))
        res.update(grounding_point_verdicts=len(point_rows), grounding_with_numbers=len(with_numbers),
                   grounding_flagged=len(flagged), grounding_flagged_share=len(flagged) / len(point_rows),
                   grounding_mean_share=(sum(v["grounding"]["share"] for v in with_numbers) / len(with_numbers)
                                         if with_numbers else None),
                   grounding_flagged_list=flagged)
    if any("cleaning" in r for r in A.values()):
        keys = ("comments", "format_chars", "headers_neutralised", "tags_neutralised",
                "pages_with_unterminated_comment")
        res["cleaning_totals_pass_a"] = {k: sum(r["cleaning"][k] for r in A.values()) for k in keys}
    recs = list(A.values()) + list(B.values())
    tok_in = sum(r["usage"]["prompt_tokens"] for r in recs)
    tok_out = sum(r["usage"]["completion_tokens"] for r in recs)
    res.update(tokens_in=tok_in, tokens_out=tok_out, cost_usd=round(
        tok_in / 1e6 * pricing.get("input", 0) + tok_out / 1e6 * pricing.get("output", 0), 2) if pricing else None)
    return res


def cmd_report(a) -> None:
    run_dir = RUNS / a.run
    pop = json.loads((run_dir / "population.json").read_text(encoding="utf-8"))
    man = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    A, B = load_pass(run_dir, "A"), load_pass(run_dir, "B")
    regrounded = 0
    if any("grounding" in v for r in A.values() for v in r["verdicts"]):
        # The diagnostic is deterministic over saved evidence and the cached text the model
        # saw, so every record is re-checked with the current code for a consistent report.
        by_id = {x["space_id"]: x for x in pop["items"]}
        for rec in list(A.values()) + list(B.values()):
            it = by_id[rec["space_id"]]
            text, failed, _ = cached_logbook(it["space_id"], it["sha"], None)
            if failed:
                sys.exit(f"cannot re-check grounding, logbook incomplete: {it['space_id']}")
            ground_rows(rec["verdicts"], text + "\n" + "\n".join(it["claims"]))
            regrounded += 1
    res = {"run": a.run, "manifest": man, "grounding_code_sha256": code_sha256() if regrounded else None,
           "grounding_rechecked_records": regrounded,
           **summarize(pop, A, B, man.get("pricing_per_million"))}
    if a.baseline:
        base = load_pass(RUNS / a.baseline, "A")
        x, y = [], []
        for key, rec in A.items():
            if key in base:
                x += [v["verdict"] for v in base[key]["verdicts"]]
                y += [v["verdict"] for v in rec["verdicts"]]
        res.update(baseline=a.baseline, baseline_claims=len(x),
                   baseline_exact_agreement=agreement.exact_share(x, y),
                   baseline_cohen_kappa=agreement.cohen_kappa(x, y),
                   baseline_confusion_rows=agreement.confusion(x, y))
    path = run_dir / f"report_{dt.datetime.now().strftime('%Y%m%dT%H%M%S')}.json"
    write_new(path, res)
    for k in ["n_judged", "n_claims", "exact_agreement", "cohen_kappa", "mean_abs_point_diff_per_claim",
              "official_total", "judge_total", "max_total", "retest_logbooks", "retest_claims",
              "retest_identical_share", "retest_fleiss_kappa", "baseline", "baseline_claims",
              "baseline_exact_agreement", "baseline_cohen_kappa", "grounding_errors", "grounding_point_verdicts",
              "grounding_with_numbers", "grounding_flagged", "grounding_flagged_share",
              "grounding_mean_share", "cleaning_totals_pass_a", "tokens_in", "tokens_out", "cost_usd"]:
        if k in res:
            v = res[k]
            print(f"{k:32} {v:.3f}" if isinstance(v, float) else f"{k:32} {v}")
    if res["missing"]:
        print(f"missing from pass A: {len(res['missing'])}")
    print(f"report: {path}")


# ---------------------------------------------------------------- single judgment

def read_claims(path: str) -> list[str]:
    lines = Path(path).read_text(encoding="utf-8").splitlines()
    return [re.sub(r"^\s*(\d+[.)]|[-*])\s*", "", l).strip() for l in lines
            if l.strip() and not l.lstrip().startswith("#")]


def cmd_judge(a) -> None:
    rubric, _ = prompt.load_rubric(a.rubric)
    token = require_token()
    if a.space:
        text, failed, stats = logbook.fetch_space_logbook(a.space, a.revision, token)
        if failed:
            sys.exit(f"{len(failed)} page(s) could not be fetched: {failed}")
    else:
        text, stats = logbook.assemble([(a.logbook, Path(a.logbook).read_text(encoding="utf-8"))])
    claims = read_claims(a.claims)
    messages = prompt.build_messages(rubric, {"title": a.title or "", "orid": a.orid or ""}, claims, text)
    res = router.judge_call(messages, token=token, model=a.model, provider=a.provider)
    rows = verdicts.normalize(res["parsed"], len(claims))
    ground_rows(rows, text + "\n" + "\n".join(claims))
    print(json.dumps({"verdicts": rows, "points": verdicts.points(rows), "max_points": 2 * len(claims),
                      "overall": res["parsed"].get("overall"), "quality": res["parsed"].get("quality"),
                      "cleaning": stats, "model_id": res["model_id"], "served_by": res["served_by"],
                      "usage": res["usage"]}, ensure_ascii=False, indent=1))


def main(argv=None) -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    j = sub.add_parser("judge")
    src = j.add_mutually_exclusive_group(required=True)
    src.add_argument("--space")
    src.add_argument("--logbook")
    j.add_argument("--revision")
    j.add_argument("--claims", required=True)
    j.add_argument("--title")
    j.add_argument("--orid")
    j.add_argument("--rubric", default=DEFAULTS["rubric"])
    j.add_argument("--model", default=DEFAULTS["model"])
    j.add_argument("--provider", default=DEFAULTS["provider"])
    pr = sub.add_parser("prepare")
    pr.add_argument("--run", required=True)
    pr.add_argument("--user")
    pr.add_argument("--verdicts")
    pr.add_argument("--copy-from", help="reuse another run's frozen population unchanged")
    r = sub.add_parser("run")
    r.add_argument("--run", required=True)
    r.add_argument("--pass", dest="pass_", choices=["A", "B"], required=True)
    r.add_argument("--limit", type=int, default=0)
    r.add_argument("--workers", type=int, default=3)
    r.add_argument("--dry-run", action="store_true", help="build prompts and estimate cost, no model calls")
    rp = sub.add_parser("report")
    rp.add_argument("--run", required=True)
    rp.add_argument("--baseline", help="another run to compare pass A verdicts with")
    a = p.parse_args(argv)
    {"judge": cmd_judge, "prepare": cmd_prepare, "run": cmd_run, "report": cmd_report}[a.cmd](a)


if __name__ == "__main__":
    main()
