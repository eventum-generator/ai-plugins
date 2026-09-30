---
name: review-generator
description: Use to accept or check an Eventum generator - "review this generator", "is this pack ready", "check the generator after the fixes", "review the content-pack PR". Runs an independent review on fresh output against the acceptance criteria and writes a verdict with findings by severity. Must run in a context that did not build the generator. Not for building or fixing a generator (create-generator).
---

# Review an Eventum generator

An independent acceptance review: fresh captures, measured against the acceptance criteria, with a verdict tied to the exact files reviewed. The review reports; it does not edit the generator.

## Before starting

- Run in a context that did not build the generator (a subagent or a new session); the author's notes are claims to verify, not evidence.
- Inputs: the generator directory; `.content-design/<name>/brief.md` and `reference/` for the native format when they exist (otherwise the README's references); `chain.json` when it exists (otherwise write the spec from the README's `## Anomaly Chain`).
- `eventum --version` works. Captures go to `.content-design/<name>/captures/review/`.

## References

- `references/acceptance.md` - criteria, severities, defects that most often slip through.
- `../create-generator/references/eventum-api.md` - the Eventum API, to judge template and input logic.
- `../create-generator/references/chain-spec.md` - the chain spec format.
- `scripts/chain_check.py` at the plugin root (`<skill dir>/../../scripts/`).

## Process

1. **Record the files** - `python <chain_check.py> digest <generator dir>`.
2. **Read** `generator.yml`, templates, samples and patterns against the criteria: format against the reference records, rate and hours, guard and episode logic, state bounds, parameter validation. Note what each capture must confirm.
3. **Capture** - test copies as in `create-generator` phase 3 (patterns started at a midnight with an explicit offset, finite `end`): 3 with `anomaly_mode: false` and 3 with `true` at the default interval, 4 days each, plus one `true` at a 6- or 8-hour interval; 14 days where a check needs more episodes. Every run exits 0 with an empty `-vvv` log.
4. **Measure** each criterion: `chain_check.py accept` and `count`; presence of every chain actor and actor pair in each background capture; recurrence gaps and start hours; one record per timestamp; the episode actor before and after episodes against the same hours on ordinary days; caps and live-object counts per mode; guard actions per mode; state growth over 14 days; a 90-second live run on a copy with scaled-up rates; every README number and command.
5. **Classify** each failure by `references/acceptance.md`; a finding states the criterion, the evidence (numbers, file and line), and why it matters to a consumer of the data.
6. **Write** `.content-design/<name>/review.md`: digest, date, Eventum version, verdict (CLEAR when no MEDIUM or HIGH, otherwise NOT CLEAR), findings by severity, the measured numbers behind the passed criteria. Delete captures.

## Result

- CLEAR: LOW findings are fixed in the README by the author and the generator can be published (`publish-generator`); fixes limited to the README do not need a new review.
- NOT CLEAR: the author fixes the generator (`create-generator`), and a new review runs on the new files.

## Rules

- Every finding rests on a measurement or a cited line; no finding from impression.
- The review measures the files it records; a changed file invalidates the verdict.
- Background tuned only to hide a number is itself a finding under criterion 6.
