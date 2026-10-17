# repro-judge

An independent LLM judge for reproduction logbooks. It re-implements the rubric of
the ICML 2026 Logbook Judge in its own words: four verdicts (verified and falsified
2 points, toy 1, inconclusive 0) and the rule that the author's own verdict labels
are not evidence. It judges text only. It does not rerun code; for that, use the
`repro-referee` agent first.

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
