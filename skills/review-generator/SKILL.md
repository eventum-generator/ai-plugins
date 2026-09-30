---
name: review-generator
description: Use to accept or check an Eventum generator - "review this generator", "is this pack ready", "check the generator after the fixes", "review the content-pack PR". Not for building or fixing a generator (create-generator).
---

# Review an Eventum generator

An independent acceptance review: fresh captures measured against the acceptance criteria, with a verdict tied to the exact files reviewed. The review reports; it does not edit the generator.

## Before starting

- Run in a context that did not build the generator (a subagent or a new session); the author's notes and reports are claims to verify, not evidence.
- `python <skill dir>/../../scripts/capture.py doctor` reports `ok`.
- Inputs: the generator directory; `.content-design/<name>/brief.md` and `reference/` for the native format when they exist (otherwise the README's references); `measure.json` when it exists (otherwise write it from the README per `../create-generator/references/measure-spec.md`).
- The review writes only `.content-design/<name>/review.md`, `review-digest.json` and `captures/review/`.

## References

- `references/acceptance.md` - criteria, severities, the capture set, what each measurement proves, defects that most often slip through.
- `../create-generator/references/anomaly-chain.md` - the chain rules the chain criteria refer to.
- `../create-generator/references/eventum-api.md` - the Eventum API, to judge templates and inputs.
- `../create-generator/references/generator-rules.md` - the conventions criteria 8-11 refer to.

Scripts are at `<skill dir>/../../scripts/`.

## Process

1. **Record the files** - `python <scripts>/measure.py digest <generator> --save .content-design/<name>/review-digest.json`, adding `--previous <old review-digest.json>` on a re-review: only the changed and added files need reading again; every measurement is rerun.
2. **Read** `generator.yml`, templates, samples and inputs against the criteria: format against the reference records, rate and rhythm, template branches, parameter validation, state bounds, and with a chain the guard and episode logic. Note what the measurements must confirm.
3. **Capture** - `python <scripts>/capture.py run <generator> --out .content-design/<name>/captures/review --set review` and `capture.py live` into the same directory, with the carrier tags (`--carrier`) and the shortest admitted interval (`--short-interval`) that the generator's inputs and parameter checks show.
4. **Measure** - `python <scripts>/measure.py report <measure.json> <captures/review/manifest.json>`; every flag is a finding; judge the other numbers by `references/acceptance.md`; check every README number and command.
5. **Classify** each failure by `references/acceptance.md`.
6. **Write** `.content-design/<name>/review.md`: digest, date, Eventum version, verdict (CLEAR when no MEDIUM or HIGH, otherwise NOT CLEAR), findings as a table (criterion, severity, evidence with numbers or file and line, what a consumer of the data would see), and the numbers behind the passed criteria. Delete the captures.
7. **Feedback** - `../using-content-design/references/feedback.md`.

## Result

- CLEAR: the author fixes LOW findings or describes them in the README, and the generator can be published (`publish-generator`); fixes limited to the README do not need a new review.
- NOT CLEAR: the author fixes the generator (`create-generator`), and a new review runs on the new files.

## Rules

- Every finding rests on a measurement or a cited line; no finding from impression.
- The verdict holds for the recorded files; any change outside the README invalidates it.
- Background tuned only to hide a number is itself a finding under criterion 5.
