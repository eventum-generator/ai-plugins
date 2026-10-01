---
name: review-generator
description: Use to accept or check an Eventum generator - "review this generator", "is this pack ready", "check the generator after the fixes", "review the content-pack PR". Not for building or fixing a generator (create-generator).
---

# Review an Eventum generator

An independent acceptance review: fresh captures measured against the acceptance criteria, with a verdict tied to the exact files reviewed. The review reports; it does not edit the generator.

## Before starting

- Run in a context that did not build the generator (a subagent or a new session); the author's notes and reports are claims to verify, not evidence.
- `python3 <skill dir>/../../scripts/capture.py doctor` reports `ok`.
- Inputs: the generator directory (for a content-pack PR: `gh pr checkout <number>` in a worktree of a content-packs clone); `.content-design/<name>/brief.md` and `reference/` for the native format when they exist (otherwise the README's references); `measure.json` when it exists (otherwise write it from the README per `../create-generator/references/measure-spec.md`).
- The review writes only `.content-design/<name>/review.md` (earlier ones kept as `review-<n>.md`), `review-digest.json`, `review-report.json`, `reviewed/` and `review-measure.json` (copies of what was reviewed), `captures/review/`, `measure.json` when it was missing or incomplete, and its feedback.

## References

- `references/acceptance.md` - criteria, severities, the capture set, what each measurement proves, defects that most often slip through.
- `../create-generator/references/anomaly-chain.md` - the chain rules the chain criteria refer to.
- `../create-generator/references/eventum-api.md` - the Eventum API, to judge templates and inputs.
- `../create-generator/references/generator-rules.md` - the conventions criteria 8-11 refer to.

`<scripts>` is `<skill dir>/../../scripts`; scripts run with `python3` (`py -3` on Windows).

## Process

A review is one capture set, one live check, the report and a targeted reading; it takes about 15 minutes. An extra run is made only to confirm a flag or a specific suspicion from the reading, at most two; no statistics beyond the report. References are opened for the criteria a flag or the reading puts in question.


1. **Record the files** - on a re-review first: keep the previous `review.md`, `review-report.json` and `review-digest.json` as `review-<n>.md`, `review-<n>-report.json` and `review-<n>-digest.json`, read `python3 <scripts>/measure.py diff .content-design/<name>/reviewed <generator>` (without a `reviewed/` snapshot: `measure.py digest <generator> --previous .content-design/<name>/review-digest.json`) and compare `measure.json` with `review-measure.json` when it exists; the diffs and the previous findings decide what to read again, every measurement is rerun, and the new review states for each previous finding whether it is resolved. Then, on every review: `python3 <scripts>/measure.py digest <generator> --save .content-design/<name>/review-digest.json --copy .content-design/<name>/reviewed`, and copy `measure.json` to `review-measure.json`.
2. **Read** `generator.yml`, templates, samples and inputs against the criteria: format against the reference records, rate and rhythm, template branches, parameter validation, state bounds, and with a chain the guard and episode logic. Check that `measure.json` encodes every class, group, linking field and actor pair the README names, and complete it where it does not. Note what the measurements must confirm.
3. **Capture** - `python3 <scripts>/capture.py run <generator> --out .content-design/<name>/captures/review --set review` and `capture.py live` into the same directory, with every carrier tag (`--carrier`), the shortest admitted interval and every interval the README quotes (`--short-interval`), and `live --spec <measure.json>` for native output.
4. **Measure** - `python3 <scripts>/measure.py report <measure.json> <captures/review/manifest.json> --save .content-design/<name>/review-report.json`; a parameter variant is a full set of its own (`capture.py run --param KEY=VALUE --out <another dir>`); every flag is a finding; judge the other numbers by `references/acceptance.md`; run `measure.py check-readme <generator>/README.md .content-design/<name>/review-report.json` and the README commands in a copy under `.content-design/<name>/readme-check/` (a batch window of one day).
5. **Classify** each failure by `references/acceptance.md`.
6. **Write** `.content-design/<name>/review.md`: digest, date, Eventum version, verdict (CLEAR when no MEDIUM or HIGH, otherwise NOT CLEAR), findings as a table (criterion, severity, evidence with numbers or file and line, what a consumer of the data would see), and the numbers behind the passed criteria. Delete the captures; keep `review-report.json`.
7. **Feedback** - `../using-content-design/references/feedback.md`, appended to `.content-design/<name>/feedback.md` under a `review` heading.

## Result

- CLEAR: the author fixes LOW findings or describes them in the README, and the generator can be published (`publish-generator`); fixes limited to the README do not need a new review.
- NOT CLEAR: the author fixes the generator (`create-generator`), and a new review runs on the new files.

## Rules

- Every finding rests on a measurement or a cited line; no finding from impression.
- The verdict holds for the recorded files; any change outside the README invalidates it.
- Background tuned only to hide a number is itself a finding under criterion 5.
