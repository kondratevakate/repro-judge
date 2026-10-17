# Protocol 003: CommonMark code regions and line-ending-stable hashes

Frozen 2026-10-17, before the code change. Amends protocol 002; nothing else changes.

## Why

A commit security review found a parser differential. Version 2 located code fences
with a regular expression that also accepted a fence opened in the middle of a line.
For the text `Result ```x`, then `<!-- instruction -->`, then ```` ``` ````, the
cleaner kept the comment as code, while a CommonMark renderer hides it. A probe found
no such line in the 53 calibration logbooks.

Separately, `calib_002/population.json` records the sha256 of the copied population
as it was on disk, with CRLF line endings, while Git stores the file with LF.

## Changes

1. Code regions (fenced and indented code blocks) are taken from the block tokens of
   `markdown-it-py` 4.0.0 with the `commonmark` preset, by their line ranges. HTML
   comments are removed only outside those regions, as before. HTML figure
   placeholders and long raw block truncation apply to fenced blocks found this way.
2. Results are written with LF line endings on every platform, and the population
   hash of `prepare --copy-from` is taken over LF-normalised bytes.

## Acceptance criterion, fixed in advance

For every one of the 53 calibration logbooks at its judged revision, the assembled
logbook text produced by the new code must equal, byte for byte, the text produced by
commit `89b22f4`. If all 53 are identical, the model input is unchanged apart from
the per-call nonce, and `calib_002` applies to the new code without a new paid run.
If any differs, stop: report which logbooks and why, and make no paid call without
Kate's word.

Recorded results stay untouched. The CRLF-based hash already stored in
`calib_002/population.json` is kept, and the LF-normalised value is reported next to it.
