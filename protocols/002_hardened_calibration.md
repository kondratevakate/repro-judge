# Protocol 002: recalibrate after prompt-injection hardening

Frozen 2026-10-17, before any code change for this protocol and before any call.
Amends protocol 001 only where stated; everything else is unchanged.

## Why

The logbook is untrusted text pasted into the judge prompt. A commit security review
flagged this as a prompt-injection risk. A scan of the 53 cached logbooks found no
attack, but 375 single-line trackio comments that the version 1 cleaner did not remove.
Hardening changes what the model sees, so the version 1 calibration (`calib_001`,
kappa 0.881) does not carry over and is measured again here.

## Changes against protocol 001

1. Cleaning. Outside fenced code blocks, every HTML comment is removed, single-line
   and multi-line; an unterminated `<!--` removes the rest of that page and is flagged.
   Every Unicode format character (category Cf: zero-width characters, bidirectional
   controls, tag characters, soft hyphen, byte order mark) is removed everywhere.
2. Neutralisation. Inside page bodies, a line that starts with `=====` is prefixed with
   `> `, and any `<logbook-` or `</logbook-` is rewritten to `[logbook-` or
   `[/logbook-`, so page text cannot imitate a file header or close the data block.
3. Isolation. The logbook is wrapped in `<logbook-ID>` and `</logbook-ID>`, where ID is
   16 random hexadecimal characters drawn for each call. The rubric `icml2026_v2.md`
   adds one paragraph: text inside the tags is the author's data, not instructions.
4. Evidence grounding, diagnostic only. Numbers cited in each verdict's evidence are
   checked against the numbers in the cleaned logbook and the claim text, which is
   exactly what the model saw. A cited number is grounded when some visible number
   rounds to it at the precision it is written with, or equals it as a percentage of
   a visible fraction. Integers from 0 to 10 are ignored. A verdict worth points
   (verified, falsified, toy) is flagged when at least one eligible number is cited and
   fewer than half of the eligible numbers are grounded. Flags never change a verdict.

## Unchanged

Population: the same 53 logbooks, 284 claims and claim texts, copied unchanged from
`runs/calib_001/population.json`. Same revisions, model `zai-org/GLM-5.2`, provider
`novita`, temperature 0.1, output budget, attempts, Pass A and the same 10 Pass B
logbooks, the same metrics and the same interpretation bands.

## Additional reports

* Agreement between `calib_002` and `calib_001` on Pass A, claim level.
* Number of comments, format characters and header lines removed or neutralised.
* Share of point-bearing verdicts flagged by the grounding check, with every flagged
  verdict listed for manual review.

## Spending

Run name `calib_002`. If the dry-run estimate exceeds 3.50 USD, stop and ask before
any paid call.
