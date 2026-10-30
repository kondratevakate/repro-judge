# repro-judge

An independent LLM judge for reproduction logbooks. It re-implements the rubric of
the ICML 2026 Logbook Judge in its own words: four verdicts (verified and falsified
2 points, toy 1, inconclusive 0) and the rule that the author's own verdict labels
are not evidence. It judges text only. It does not rerun code; rerunning the claims
is a separate step (in the author's setup, a Claude Code agent called
`repro-referee`, which is not part of this repository).

## Why it exists

In the ICML 2026 agent reproduction challenge, the official Logbook Judge reads only
the published logbook text and ignores the author's self-assigned verdicts. A
logbook is scored once it is published, so the author needs a second judge that
reads the same text the same way before publishing. This repository is that judge:
it is run on a draft logbook, and claims it would not credit are fixed or reworded
before the Space goes public.

## How it was built

Every step is a protocol in `protocols/`, written and committed before any paid
model call of that step, with its decision rule fixed in advance. Results in `runs/`
are never overwritten.

1. **Protocol 001, calibration.** Rubric `rubrics/icml2026.md` written independently
   of the official prompt, same four verdicts and point values. Judged the author's
   53 canonical logbooks from the public dataset
   [`ICML-2026-agent-repro/verdicts`](https://huggingface.co/datasets/ICML-2026-agent-repro/verdicts)
   at the exact revisions the official judge saw, with the official claims, and
   compared verdicts claim by claim. A test-retest pass judged 10 logbooks, chosen
   in advance, three times each. Result: `calib_001`.
2. **Protocol 002, prompt-injection hardening.** Treat the logbook as untrusted
   text, isolate it with a per-call nonce, and recalibrate. Result: `calib_002`,
   the current default.
3. **Protocol 003, CommonMark parsing.** Locate code blocks exactly as a Markdown
   renderer does, after a security review found a bypass. Accepted only because the
   cleaned text stayed byte-identical to `calib_002` on all 53 logbooks.
4. **Protocol 004, evidence response (frozen, not yet run).** Does the judge stop
   crediting a claim when its evidence is removed, and stay unmoved when a bare
   "VERIFIED" label is added? See below.

## Status

Calibrated 2026-10-17 against the official ICML 2026 verdicts on the same 53
logbooks (284 claims, official total 265). The default is the hardened version 2.

| Measure | v1, `calib_001` | v2 hardened, `calib_002` (default) |
|---|---:|---:|
| Same verdict as the official judge | 92.3% | 91.5% |
| Cohen's kappa against the official judge | 0.881 | 0.868 |
| Total points against official 265 | 255 | 254 |
| Claims identical in all 3 runs (10 logbooks, 54 claims) | 90.7% | 92.6% |
| Pairwise agreement between its own runs | 93.8% | 95.1% |
| Fleiss kappa across the 3 runs | 0.906 | 0.925 |
| Point verdicts whose cited numbers are not in the visible text | not measured | 0 of 149 |
| Cost of the run | $1.95 | $2.02 |

Both versions are in the band "usable as a pre-publication screening judge" fixed in
the protocols before any call. Version 2 agrees with version 1 on 91.5% of claims;
24 verdicts changed with no net direction against official, about the size of the
run-to-run noise. What the calibration does and does not mean:
* It shows this judge behaves like the official judge on the same text, with
  disagreement about as large as its own run-to-run noise.
* It does not show the verdicts are right about reproduction quality; there is no
  ground truth for that here. It is still an opinion, not evidence.
* All 53 logbooks are by one author. Other authors' logbooks, other models and the
  clinical rubric are not calibrated.
* The two judges disagree mostly on where verified ends and toy begins (small
  synthetic instances, re-aggregated author outputs).

## Prompt-injection hardening (version 2, protocol 002)

The logbook is untrusted text. Version 2:
* removes every HTML comment outside code fences, including the single-line trackio
  cell comments version 1 missed (375 in these logbooks), and treats an unterminated
  comment as hiding the rest of the page;
* removes Unicode format characters (zero-width, bidirectional controls, tag
  characters, soft hyphen, byte order mark);
* neutralises page lines that imitate a `===== FILE` header and any `<logbook-` tag;
* wraps the logbook in `<logbook-NONCE>` tags with a fresh random nonce per call, and
  `rubrics/icml2026_v2.md` adds one paragraph saying text inside is data, not
  instructions;
* checks that the numbers each verdict cites appear in the visible text, as a
  diagnostic that flags verdicts for manual review and never changes them.

Counts of everything removed are stored in each record. In these 53 logbooks no
hidden instruction, invisible character or fake header was found.

Protocol 003 then replaced the fence regular expression with the block tokens of
`markdown-it-py` (CommonMark preset), after a security review showed that a fence
opened in the middle of a line let a renderer-hidden comment through. Fenced and
indented code blocks are now located exactly as a CommonMark renderer does. The
criterion fixed in advance was met: the assembled logbook text is byte-identical to
version 2 on all 53 calibration logbooks, with identical cleaning counts, so
`calib_002` applies to this code without a new paid run. A second review then found
that splitting lines only on LF, while markdown-it also splits on a lone CR, let two
lone CRs shift a code range onto a hidden comment. Lines are now split exactly as
markdown-it splits them, and any mismatch between its token map and the text (out of
range, marker not on its line, overlapping ranges, a parser error) fails closed: the
page is treated as having no code, so every comment on it is removed, and the reason
is recorded. The byte-identity check was repeated: 53 of 53, no page failed closed.
Known conservative choice:
an HTML comment inside inline code (`` `<!-- x -->` ``) is still removed, although a
renderer shows it.

## Evidence response (protocol 004, pilot, not yet run)

Calibration shows agreement with the official judge, not that either judge reacts
to evidence. Protocol 004 tests that with deterministic edits to real logbooks, one
target claim per call, made by `mutation/mutate.py` (unit-tested, no language model):

* **R1, evidence removal:** the claim's page is emptied and every line naming the
  claim elsewhere is deleted. Expected verdict: `inconclusive`.
* **I1, content-preserving reformat:** bullets, blank lines and trailing spaces
  change on the claim's page. Expected: unchanged verdict.
* **I3, self-assessment inflation:** a confident "Verdict: VERIFIED" paragraph is
  added to a claim the official judge did not verify. Expected: no gain in points.

The judge is called evidence-responsive only if the lower 95% bound of R1
sensitivity is above 0.5 and the upper 95% bound of I3 inflation is below 0.05.
Before any paid call, `mutation/run.py gate` checks that the current code
reproduces the `calib_002` rubric hash and cleaned text length on all 53 logbooks.
The run is capped at 12 USD after a dry run.

```powershell
python mutation/run.py gate
python mutation/run.py run --dry-run
python mutation/run.py run
```

No results yet; they will go to `runs/mut_001`.

## Setup

```powershell
python -m pip install -r requirements.txt
hf auth login
```

Calls go through the Hugging Face router and are billed to the logged-in account.
They need Inference Providers credits (pre-paid credits or a PRO subscription);
without them the router answers HTTP 402 and the tool stops with that message.
One logbook costs about 3 cents and takes about a minute.

## Judge one logbook

```powershell
python judge.py judge --space kondratevakate/repro-some-paper --claims claims.txt --title "Paper title"
python judge.py judge --logbook notes.md --claims claims.txt
```

`claims.txt` has one claim per line; numbering, bullets, blank lines and `#` comments
are ignored. Use the paper's anchored claims, not a paraphrase.

Defaults: model `zai-org/GLM-5.2`, provider pinned to `novita`, temperature 0.1,
rubric `rubrics/icml2026_v2.md`. `rubrics/clinical.md` is refused until its TODO is
filled in.

## Calibration runs

```powershell
python judge.py prepare --run calib_002 --copy-from calib_001
python judge.py run --run calib_002 --pass A --dry-run
python judge.py run --run calib_002 --pass A --limit 1
python judge.py run --run calib_002 --pass A
python judge.py run --run calib_002 --pass B
python judge.py report --run calib_002 --baseline calib_001
```

The population was frozen once on 2026-10-17 and copied unchanged into later runs.
`--dry-run` builds every prompt and estimates the bill without calling the model.
Results, manifests and reports are never overwritten; a failed judgment is written
to `runs/<run>/pass<X>/errors/` and retried on the next run. `calib_001` was produced
by commit `3fe9e7c`; its settings no longer match the defaults, so `run` refuses to
extend it.

Line endings: results are written with LF, and `--copy-from` records `sha256_lf`
over LF-normalised bytes. `calib_002/population.json` predates this and records
`sha256` of the CRLF bytes on the Windows disk
(`4fe35894...93b25dd`); over the LF bytes Git stores, the same source file hashes to
`6666dbda8714828aaec08bb372cec79e92570b07d520ac1e8f0897e13f712aa2`. The recorded value
is left unchanged.

## Data handling

Logbook text is sent to the inference provider chosen above. Send only logbooks that
are already public or contain aggregate results. Never send patient-level rows, and
check the data use agreement (for example PhysioNet credentialed data) before
judging any logbook derived from restricted data. Logs contain Space ids and verdict
labels only.

## Tests

```powershell
python -m pytest tests -q
$env:RJ_LIVE = "1"; python -m pytest tests/test_router_live.py -q -s
```

The live test calls the router once and costs a few tokens.

## License

MIT, see `LICENSE`. The logbooks judged in `runs/` are public Hugging Face Spaces
and keep their own licences; `runs/` stores the judge's outputs, which may quote
short excerpts, and identifiers, not the logbooks themselves.
