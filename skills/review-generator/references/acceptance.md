# Acceptance criteria

A generator is accepted when no finding is MEDIUM or HIGH. Each criterion names the default severity of a failure; raise or lower it by how visible the defect is in the data. Chain rules are in `../../create-generator/references/anomaly-chain.md`.

## Severity

- **HIGH** - the output is wrong or unusable: invented or broken native format, the complete chain in background, the generator fails or stalls, real personal data or secrets.
- **MEDIUM** - the data gives the scenario away or misleads its consumer: a feature that separates anomaly mode from background other than the complete chain, a broken limit, broken recurrence, a false README claim about behaviour.
- **LOW** - the data is sound but a number or wording is off, or a disclosed realism limit.

## Criteria

| # | Criterion | Failure |
|---|---|---|
| 1 | Native format follows the reference records and vendor specification, in the output shape the brief sets; inferred parts are named in the README; ECS mapping follows the source's integration when one exists. | HIGH |
| 2 | Every run exits 0 with an empty `-vvv` log (exit 0 alone proves nothing: render and format errors only reach the log); the shipped configuration runs out of the box with `--live-mode true`. | HIGH |
| 3 | Every input timestamp yields exactly one record, except timestamps of a carrier input with nothing due. | MEDIUM |
| 4 | Each population follows its own rhythm from its input: people a working day with a low night and presence following the same curve as volume; scheduled jobs their documented schedule; machine traffic may be flat. | MEDIUM |
| 5 | Background is a normal period: failures a few percent of attempts with a monotone law, measurements within their usual range, no incident- or outage-like pattern, no single filler action dominating, every limit of the brief held. | MEDIUM |
| 6 | Template state stays bounded over an endless run. | MEDIUM |
| 7 | Live mode: records never ahead of the wall clock, in order, no catch-up burst, empty log. | MEDIUM |
| 8 | Every template branch emits a record; every sample column read exists; every parameter and sample is validated with one readable error. | MEDIUM |
| 9 | Samples are realistic but fake (documentation or private addresses, example domains, synthetic names). | HIGH if real data, else LOW |
| 10 | The README follows the section order of `../../create-generator/references/generator-rules.md`, describes the generated data only, its sample is a byte-exact generated record, its commands run as written. | LOW; MEDIUM if a claim about behaviour is false |
| 11 | Every number in the README matches the measurement report (shares, per-day counts, ranges, spans, gaps, start hours). | LOW |

With a chain:

| # | Criterion | Failure |
|---|---|---|
| 12 | `anomaly_mode: false` produces no complete chain; `true` produces exactly one per episode (strict count, every binding kept). | HIGH |
| 13 | Presence: every step, and every actor and actor pair an episode can use, occurs in ordinary background of every background capture; nothing occurs only in episodes. | MEDIUM |
| 14 | Episodes respect every cap and limit background respects (lockout thresholds, session caps, counters, uniqueness, live-object counts). | MEDIUM |
| 15 | Around an episode the actor behaves as at the same hour on ordinary days: activity before and after within the range of ordinary days; the episode does not cancel, delay or take over the actor's own work. | MEDIUM |
| 16 | An episode leaves no state behind: counters, locks, open objects and names in use return on the schedule background uses; nothing stays armed. | MEDIUM |
| 17 | A guard, if any, follows the guard rules; no pile-up just below the chain threshold. | MEDIUM |
| 18 | Recurrence follows its rules at the default and a short interval: gaps within interval ± w/2, first start, start hours on the population's curve, rotation, no skipped or replayed episodes; the parameter range excludes intervals the design cannot serve. | MEDIUM |

## Captures

`capture.py run <generator> --out <dir> --set author|review` (scripts at the plugin root) runs the set in parallel under host slots, each run on a bounded copy of the generator, and writes `manifest.json`; `capture.py live` adds the live check. The window starts on a Monday midnight UTC.

| Run | Author | Review | Criteria |
|---|---|---|---|
| Background (`anomaly_mode: false`, or the generator without a chain), 4 days | 2 | 3 | 1, 4, 5, 13 |
| With a chain, default interval, 4 days | 2 | 3 | 12-18 |
| With a chain, 6-hour interval, 4 days | 1 | 1 | 18 |
| Default configuration, 14 days: memory series, speed, volume | 1 | 1 | 4, 6, 11 |
| The same 14 days with a trivial template: Eventum's own memory curve | 1 | 1 | 6 |
| Timestamps only, then the same moments replayed through the templates, 2 days | 1 | 1 | 3 |
| Live, 90 s: the busiest hour shifted to now, rates scaled to about 40 records, schedules moved into the window | 1 | 1 | 7 |

Four days hold four default-interval episodes; fourteen days make memory growth visible against Eventum's own; forty live records show lag, order and catch-up. Timestamps of carrier inputs are left out of the replay; whether a carrier emits exactly the due records is judged from the template.

## Measurements

`measure.py report <measure.json> <manifest.json>` gives every number, keyed by criterion (`2_runs`, `3_one_record_per_timestamp`, `4_5_profile` with per-day, per-weekday, class, group and hourly figures, `6_state`, `7_live`, `12_chains`, `13_presence`, `15_18_episodes_default`, `18_episodes_short`, `speed_records_per_s`), and `flags`: measured facts that fail a criterion outright; it exits 1 while flags remain. Days and hours are UTC; records outside a run's window are counted, not measured. Each flag becomes a finding; the numbers without a flag are judged against the criteria:

- 4, 5: class shares, group shares and hourly curves against the brief and the design.
- 6: memory growth over the long run beyond the trivial-template baseline, above 10% and 50 MB between its second and last quarter.
- 15: the actor's records in the 30 minutes before and after each episode against the same actor around ordinary background records of the chain's last step and at the same clock time on background days; with fewer than about five records per window the ratios carry no signal, and the criterion is judged from the templates.
- 18: gaps, first start, start hours, distinct actors and keys per capture.

Criteria 1, 8, 9, 10, 14, 16 and 17 need reading: the sample record against the reference records, the templates, the samples, the README.

## Defects that most often slip through

- A 1-second `cron` with drops thinning a stream into a curve; people active around the clock.
- An address, account or actor pair that exists only in episodes or is missing from some background capture.
- Background that looks like an ongoing attack or outage.
- A guard that leaves many sequences one step short of the chain, or stays armed after an episode and changes the actor's next ordinary action.
- An episode that pushes a live-object count past the background maximum or leaves an object open.
- Episode starts pinned to one clock hour, stuck at night after a night first start, or skipped when no actor is free.
- A parameter check that logs an error on every timestamp instead of stopping once.
- FSM conditions on keys not yet set ("Comparing with None" warnings); `loop.index0` in a filtered loop; `rand.chance(15)` instead of `0.15`; datetimes without an offset; `rand.network.ip_v4_public()` for "fake" addresses.
