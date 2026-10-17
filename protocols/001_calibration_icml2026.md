# Protocol 001: calibrate the judge against official ICML 2026 verdicts

Frozen 2026-10-17, before any calibration call was made.

## Question

How often does this judge, given the same claims and the same logbook text, return
the same per-claim verdict as the official ICML 2026 Logbook Judge? How often does it
agree with itself when the same logbook is judged again?

## Population

Every canonical judged logbook of `kondratevakate` under the official leaderboard rule
(one Space per paper, the first Space that received a verdict): 53 logbooks.
Source: the public dataset `ICML-2026-agent-repro/verdicts`, file `verdicts.json`.
No logbook is excluded after seeing results. A logbook whose revision cannot be
fetched is reported as a fetch failure, not dropped silently.

## Inputs, matched to the official judge

* Claims: the claim texts stored in that logbook's official verdict entry, same order.
* Paper metadata: title, OpenReview id and first eight authors from the challenge
  `index.json` on `ICML-2026-agent-repro/challenge`.
* Logbook: every `pages/*.md` file of the Space at the revision `sha` recorded in the
  verdict, `pages/index.md` first, the rest sorted. HTML trackio cell comments are
  removed, HTML figure blocks are replaced by a placeholder, raw blocks longer than
  4,000 characters are truncated, and the whole text is capped at 120,000 characters.

## Judge

* Model `zai-org/GLM-5.2`, provider pinned to `novita` through the Hugging Face router.
  The official judge used automatic provider routing; pinning is a deliberate
  deviation so that repeated runs are comparable.
* Temperature 0.1. Output budget 8,000 tokens, doubled on the second attempt if no
  JSON was returned. At most 2 attempts.
* Rubric: `rubrics/icml2026.md`, written independently from the official prompt but
  with the same four verdicts, the same point values, the same rule that self-reported
  verdicts are not evidence, and the same backend substitution rule.

## Runs

* Pass A: all 53 logbooks, one judgment each.
* Pass B, test retest: 10 logbooks, chosen before Pass A. Sort the 53 by official
  points descending, ties broken by Space id ascending, and take positions
  1, 6, 11, ..., 46. Each is judged two more times, giving 3 runs in total.

## Metrics

Claim level, judge versus official, Pass A:
* exact agreement share;
* Cohen's kappa over the four verdicts;
* confusion matrix;
* mean absolute point difference per claim.

Logbook level, Pass A: total point difference per logbook, and the sum over all 53
against the official 265.

Test retest, Pass B: share of claims with the same verdict in all 3 runs, and Fleiss
kappa across the 3 runs.

## Interpretation, fixed in advance

These bands are a project decision, not a published standard.
* Usable as a pre-publication screening judge: Cohen's kappa at least 0.60 against
  official and identical verdicts in at least 80% of claims across 3 runs.
* Usable only as a second opinion: kappa from 0.40 to 0.60.
* Not usable: kappa below 0.40.

The official verdict is itself one sample at temperature 0.1, so agreement with it is
bounded by the official judge's own self-agreement, which is not observable here.
Pass B gives this judge's self-agreement as the closest available reference.

## Data handling

All 53 logbooks are public Hugging Face Spaces. Raw judge responses are stored in
`runs/`. No patient-level data are involved. Logs contain Space ids and verdict
labels only.
