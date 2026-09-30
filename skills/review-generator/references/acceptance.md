# Acceptance criteria

A generator is accepted when no finding is MEDIUM or HIGH. Each criterion names the default severity of a failure; raise or lower it by how visible the defect is in the data. Chain design rules are in `../../create-generator/references/anomaly-chain.md`.

## Severity

- **HIGH** - the output is wrong or unusable: invented or broken native format, the complete chain in background, the generator fails or stalls, real personal data or secrets.
- **MEDIUM** - the data gives the scenario away or misleads its consumer: a feature that separates anomaly mode from background other than the complete chain, a broken limit, broken recurrence, a false README claim about behaviour.
- **LOW** - the data is sound but a number or wording is off, or a disclosed realism limit.

## Criteria

| # | Criterion | Failure |
|---|---|---|
| 1 | Native format follows the reference records and vendor specification, in the output shape the brief sets; inferred parts are named in the README; ECS mapping follows the source's integration when one exists. | HIGH |
| 2 | The shipped configuration runs out of the box (`eventum generate --path generator.yml --id x --live-mode true`) with file output, and a finite batch window runs to exit 0 with an empty `-vvv` log. | HIGH |
| 3 | Every input timestamp yields exactly one record, except timestamps of a carrier input with nothing due; `dispatch.drop()` / `next()` never thin a stream into a curve. | MEDIUM |
| 4 | Each population follows its own rhythm from its input: people a working day with a low night, with presence following the same curve as volume; scheduled jobs their documented schedule; machine traffic may be flat. | MEDIUM |
| 5 | Background is a normal period: failures a few percent of attempts with a monotone law, measurements within their usual range, no incident- or outage-like patterns, no single filler action dominating, every limit of the brief held. | MEDIUM |
| 6 | Every container in template state stays bounded over an endless run. | MEDIUM |
| 7 | Live mode: records at wall-clock time, in order, no catch-up burst, empty log. | MEDIUM |
| 8 | Samples are realistic but fake (documentation or private addresses, example domains, synthetic names) and live in `samples/`. | HIGH if real data, else LOW |
| 9 | The README describes the generated data only (no inputs, queues, guards, validation process); its sample is a byte-exact generated line; its commands run as written. | LOW; MEDIUM if a claim about behaviour is false |
| 10 | Every number in the README matches measured output (shares, per-day counts, ranges, spans, gaps, start hours). | LOW |

With a chain:

| # | Criterion | Failure |
|---|---|---|
| 11 | `anomaly_mode: false` produces no complete chain; `true` produces exactly one per episode (strict count, every binding kept). | HIGH |
| 12 | Presence: every event type of the chain, and every actor and actor pair an episode can use (accounts, addresses, hosts, targets), occurs in ordinary background of every 4-day capture; nothing occurs only in episodes. | MEDIUM |
| 13 | Episodes respect every cap and limit background respects (lockout thresholds, session caps, counters, uniqueness, live-object counts). | MEDIUM |
| 14 | Around an episode the actor behaves as at the same hour on ordinary days: lead-in, spacing and aftermath match; the episode does not cancel, delay or take over the actor's own work. | MEDIUM |
| 15 | An episode leaves no state behind: counters, locks, open objects and names in use return on the schedule background uses; nothing stays armed afterwards. | MEDIUM |
| 16 | A guard, if any, follows the guard rules (no pile-up just below the chain threshold). | MEDIUM |
| 17 | Recurrence follows its rules at the default and a short interval: gaps within due time ± w/2, first start, start hours on the episode population's curve, rotation, no skipped or replayed episodes; the parameter range excludes intervals the design cannot serve. | MEDIUM |

## Captures

Test copies go to `.content-design/<name>/captures/` (the review's to `captures/review/`). For each run, copy the generator and bound every input of the copy: `start` at a midnight with an explicit offset (`"2026-09-01T00:00:00+00:00"`) and `end` at the end of the window - in every pattern file for `time_patterns`, in the input for `cron` and `linspace`; `timer` is bounded by `repeat`. With a chain, set `anomaly_mode` and `anomaly_interval_hours` in the copy's `generator.yml`. Run

```bash
eventum generate --path <copy>/generator.yml --id <run> --live-mode false --keep-order true -vvv
```

Every run exits 0 with an empty log.

| Run | Author | Review |
|---|---|---|
| Background (`anomaly_mode: false`, or the generator without a chain), 4 days | 2 | 3 |
| With a chain: default interval, 4 days | 2 | 3 |
| With a chain: 6- or 8-hour interval, 4 days | 1 | 1 |
| Default configuration, 14 days | 1 | 1 |

## Measurements

- **Format** (1) - every line parses in the output shape; the native record (the line or `event.original`) matches the reference record of its class; at least 90% of the reference fields are present, misses listed with reasons.
- **One record per timestamp** (3) - the same inputs with a template that outputs only `{"t": {{ timestamp.isoformat() | tojson }}}` give the same line count; a carrier input is left out of the comparison.
- **Rhythm** (4) - hourly counts per population against the intended curve or schedule.
- **Bounded state** (6), **speed** - the 14-day run: every container stays flat; wall time recorded.
- **Live** (7) - a copy with `end: never` and rates scaled ×10-×100 (a schedule moved so that a run falls inside the window), `--live-mode true`, stopped after 90 seconds.
- **Chains** (11, 12) - `python <chain_check.py> accept chain.json --off OFF... --on ON...` reports `ok`; `count` gives exactly one chain per episode. With a random-ID chain key, actor and actor-pair presence is checked separately.
- **Episode vs background** (13-16) - the episode actor's 30 minutes before and after each episode against the same hours on ordinary days; caps and live-object counts per mode; guard actions per mode.
- **Recurrence** (17) - from `count` at both intervals: gaps, first start, start hours, actor and target rotation.

## Defects that most often slip through

- A 1-second `cron` with drops thinning a stream into a curve; people active around the clock.
- An address, account or actor pair that exists only in episodes or is missing from some background capture.
- Background that looks like an ongoing attack or outage.
- A guard that leaves many sequences one step short of the chain, or stays armed after an episode and changes the actor's next ordinary action.
- An episode that pushes a live-object count past the background maximum or leaves an object open.
- Episode starts pinned to one clock hour, stuck at night after a night first start, or skipped when no actor is free.
- `loop.index0` in a filtered loop; `rand.chance(15)` instead of `0.15`; datetimes without an offset; `--params` used for `event.template.params`.
