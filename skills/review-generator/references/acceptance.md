# Acceptance criteria

A generator is accepted when no finding is MEDIUM or HIGH. Each criterion names the default severity of a failure; raise or lower it by how visible the defect is in the data.

## Severity

- **HIGH** - the output is wrong or unusable: invented or broken native format, the complete chain in background, the generator fails or stalls, real personal data or secrets.
- **MEDIUM** - the data gives the scenario away or misleads its consumer: a feature that separates anomaly mode from background other than the complete chain, a broken limit, broken recurrence, a false README claim about behaviour.
- **LOW** - the data is sound but a number or wording is off, or a disclosed realism limit.

## Criteria

| # | Criterion | Failure |
|---|---|---|
| 1 | Native format follows the reference records and vendor specification; inferred parts are named in the README; ECS mapping follows the source's integration when one exists. | HIGH |
| 2 | The shipped configuration runs out of the box (`eventum generate --path generator.yml --id x --live-mode true`) with file output, and a finite batch window runs to exit 0 with an empty `-vvv` log. | HIGH |
| 3 | `anomaly_mode: false` produces no complete chain; `true` produces exactly one per episode (strict count, every binding kept). | HIGH |
| 4 | Every input timestamp yields exactly one record; `dispatch.drop()` / `next()` do not shape the rate. | MEDIUM |
| 5 | Volume and hours come from the inputs; people follow a working day with a low night, and presence follows the same curve as volume; automation may be flat. | MEDIUM |
| 6 | Background is a normal day: failures a few percent of attempts with a monotone law, no incident- or outage-like patterns, no single filler action dominating. | MEDIUM |
| 7 | Every event type of the chain, and every actor and actor pair an episode can use, occurs in ordinary background of every 4-day capture; nothing occurs only in episodes. | MEDIUM |
| 8 | Episodes respect every cap and limit background respects (lockout thresholds, session caps, counters, uniqueness, live-object counts). | MEDIUM |
| 9 | Around an episode the actor behaves as at the same hour on ordinary days: lead-in, spacing and aftermath match; the episode does not cancel, delay or take over the actor's own work. | MEDIUM |
| 10 | An episode leaves no state behind: counters, locks, open objects and names in use return on the schedule background uses; nothing stays armed afterwards. | MEDIUM |
| 11 | A guard, if any, acts only on the exact final step within the chain window, changes its target or outcome to a normal alternative, fires rarely, and suppresses no noticeable share of an ordinary action (no pile-up just below the chain threshold). | MEDIUM |
| 12 | Recurrence: first start within min(interval, 24 h); gaps within interval ± w/2 (w = min(interval / 4, 6 h)) at the default and a short interval; start hours follow the actor's activity; actor and target rotate; no skipped or replayed episodes; the parameter range excludes intervals the design cannot serve. | MEDIUM |
| 13 | Every container in template state stays bounded over an endless run. | MEDIUM |
| 14 | Live mode: records at wall-clock time, in order, no catch-up burst, empty log. | MEDIUM |
| 15 | Samples are realistic but fake (documentation or private addresses, example domains, synthetic names) and live in `samples/`. | HIGH if real data, else LOW |
| 16 | The README describes the generated data only (no inputs, queues, guards, validation process); its sample is a byte-exact generated line; its commands run as written. | LOW; MEDIUM if a claim about behaviour is false |
| 17 | Every number in the README matches measured output (shares, per-day counts, ranges, spans, gaps, start hours). | LOW |

## Defects that most often slip through

- A 1-second `cron` with drops instead of rate-setting inputs; people active around the clock.
- An address, account or actor pair that exists only in episodes or is missing from some background capture.
- Background that looks like an ongoing attack or outage.
- A guard that leaves many sequences one step short of the chain, or stays armed after an episode and changes the actor's next ordinary action.
- An episode that pushes a live-object count past the background maximum or leaves an object open.
- Episode starts pinned to one clock hour, stuck at night after a night first start, or skipped when no actor is free.
- `loop.index0` in a filtered loop; `rand.chance(15)` instead of `0.15`; datetimes without an offset; `--params` used for `event.template.params`.
