---
name: review-generator
description: Use to accept or check an Eventum generator - "review this generator", "is this pack ready", "check the generator after the fixes", "review the content-pack PR". Runs an independent review on fresh output against the acceptance criteria and writes a verdict with findings by severity. Must run in a context that did not build the generator. Not for building or fixing a generator (create-generator).
---

# Review an Eventum generator

An independent acceptance review: fresh captures, measured against the acceptance criteria, with a verdict tied to the exact files reviewed. The review reports; it does not edit the generator.

## Before starting

- Run in a context that did not build the generator (a subagent or a new session); the author's notes are claims to verify, not evidence.
- Inputs: the generator directory; `.content-design/<name>/brief.md` and `reference/` for the native format when they exist (otherwise the README's references); with a chain, `chain.json` when it exists (otherwise write the spec from the README's `## Anomaly Chain`).
- `eventum --version` works. Captures go to `.content-design/<name>/captures/review/`.

## References

- `references/acceptance.md` - criteria, severities, the capture protocol, defects that most often slip through.
- `../create-generator/references/eventum-api.md` - the Eventum API, to judge template and input logic.
- `../create-generator/references/anomaly-chain.md` - the chain design rules the chain criteria refer to.
- `../create-generator/references/chain-spec.md` - the chain spec format.
- `scripts/chain_check.py` at the plugin root (`<skill dir>/../../scripts/`).

## Process

1. **Record the files** - `python <chain_check.py> digest <generator dir>`.
2. **Read** `generator.yml`, templates, samples and inputs against the criteria: format against the reference records, rate and rhythm, state bounds, parameter validation, and with a chain the guard and episode logic. Note what each capture must confirm.
3. **Capture** - the review set of the capture protocol in `references/acceptance.md`; 14-day chain runs where a check needs more episodes.
4. **Measure** each criterion as `references/acceptance.md` describes, and every README number and command.
5. **Classify** each failure by `references/acceptance.md`; a finding states the criterion, the evidence (numbers, file and line), and why it matters to a consumer of the data.
6. **Write** `.content-design/<name>/review.md`: digest, date, Eventum version, verdict (CLEAR when no MEDIUM or HIGH, otherwise NOT CLEAR), findings by severity, the measured numbers behind the passed criteria. Delete captures.

## Result

- CLEAR: LOW findings are fixed in the README by the author and the generator can be published (`publish-generator`); fixes limited to the README do not need a new review.
- NOT CLEAR: the author fixes the generator (`create-generator`), and a new review runs on the new files.

## Rules

- Every finding rests on a measurement or a cited line; no finding from impression.
- The review measures the files it records; a changed file invalidates the verdict.
- Background tuned only to hide a number is itself a finding under criterion 5.
