# repro-judge

An independent LLM judge for reproduction logbooks. It re-implements the rubric of
the ICML 2026 Logbook Judge in its own words: four verdicts (verified and falsified
2 points, toy 1, inconclusive 0) and the rule that the author's own verdict labels
are not evidence. It judges text only. It does not rerun code; for that, use the
`repro-referee` agent first.

**Status: calibrated 2026-10-17 against the official ICML 2026 verdicts** (protocol 001,
run `calib_001`, report `runs/calib_001/report_20261017T220035.json`, cost $1.95):

| Measure | Result |
|---|---:|
| Claims with the same verdict as the official judge | 262 of 284, 92.3% |
| Cohen's kappa against the official judge | 0.881 |
| Total points, this judge against official | 255 against 265 |
| Claims identical in all 3 runs (10 logbooks, 54 claims) | 90.7% |
| Pairwise agreement between its own runs | 93.8% |
| Fleiss kappa across the 3 runs | 0.906 |

By the bands fixed in the protocol before any call, this is "usable as a
pre-publication screening judge". What that does and does not mean:
* It shows this re-implementation behaves like the official judge on the same text,
  with disagreement about as large as its own run-to-run noise.
* It does not show the verdicts are right about reproduction quality; there is no
  ground truth for that here. It is still an opinion, not evidence.
* All 53 logbooks are by one author. Other authors' logbooks, other models and the
  clinical rubric are not calibrated.
* Where it differs from official it leans stricter on small synthetic instances
  (9 claims verified to toy) and on re-aggregating the authors' released outputs, and
  more generous to concrete counterexamples (3 claims inconclusive to falsified).

## Setup

```powershell
python -m pip install -r requirements.txt
hf auth login
```

Calls go through the Hugging Face router and are billed to the logged-in account.
They need Inference Providers credits (pre-paid credits or a PRO subscription);
without them the router answers HTTP 402 and the tool stops with that message.

## Judge one logbook

```powershell
python judge.py judge --space kondratevakate/repro-some-paper --claims claims.txt --title "Paper title"
python judge.py judge --logbook notes.md --claims claims.txt
```

`claims.txt` has one claim per line; numbering, bullets, blank lines and `#` comments
are ignored. Use the paper's anchored claims, not a paraphrase.

Defaults: model `zai-org/GLM-5.2`, provider pinned to `novita`, temperature 0.1,
rubric `rubrics/icml2026.md`. `rubrics/clinical.md` is refused until its TODO is
filled in.

## Calibration (protocol 001)

```powershell
python judge.py prepare --run calib_001 --user kondratevakate --verdicts verdicts.json
python judge.py run --run calib_001 --pass A --dry-run
python judge.py run --run calib_001 --pass A --limit 1
python judge.py run --run calib_001 --pass A
python judge.py run --run calib_001 --pass B
python judge.py report --run calib_001
```

`prepare` froze the population on 2026-10-17: 53 logbooks, 284 claims, official
total 265 points. `--dry-run` builds every prompt and estimates the bill without
calling the model. Results, manifests and reports are never overwritten; a failed
judgment is written to `runs/<run>/pass<X>/errors/` and retried on the next run.

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
