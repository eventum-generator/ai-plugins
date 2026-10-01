---
name: create-generator
description: Use to build or redesign an Eventum generator once the source format is known - from a research-source brief or from the user's own format, sample records or log to imitate - "build the generator from the brief", "here are sample lines, make a generator", "add an anomaly scenario to this generator", "fix the review findings". Not for finding out a source's format (research-source) or for accepting a finished generator (review-generator).
---

# Create an Eventum generator

Builds a generator whose output passes for the source: its native format, its ordinary activity with realistic volume and rhythm and, when the source suits one, recurring episodes of an anomaly chain. The generator is measured on its own output and documented for the people who consume the data.

## Before starting

- `python3 <skill dir>/../../scripts/capture.py doctor` reports `ok` (Eventum 2.8+); fix what it names first.
- Input is one of: `.content-design/<name>/brief.md` from `research-source`; or the user's own material (format description, sample records, a log file). From user material, claim `.content-design/<name>/`, write the brief yourself (`../research-source/references/brief.md`, sections Source, Event classes, Fields, Time, Limits, Anomaly chain candidates), save the given records under `reference/`, and ask the user only for what the material does not answer (volume, populations, whether a chain is wanted). With neither, run `research-source` first.
- The generator goes where the user says, default `./generators/<name>/`; everything else goes to `.content-design/<name>/`. The skill writes only there.
- Catalog generators are not a standard: many predate these rules (flat 1-second `cron`, rates shaped by drops, guards that drop records). Facts come from the brief, rules from this skill.

## References

- `references/eventum-api.md` - `generator.yml`, CLI, logging, time, inputs, picking modes, samples, state, dispatch, `module.rand`, Jinja, formatters.
- `references/generator-rules.md` - layout, naming, output shape, parameters, samples, templates, speed, distributions, README.
- `references/anomaly-chain.md` - designing a chain: choice, actors, presence in background, recurrence, episode shape, guard.
- `references/measure-spec.md` - the measurement spec read by `measure.py`.
- `../review-generator/references/acceptance.md` - the acceptance criteria, the capture set and what each measurement proves.

`<scripts>` is `<skill dir>/../../scripts`; scripts run with `python3` (`py -3` on Windows).

## Process

Validation and self-check send work back to the build, or to the design when the cause is a design choice.

### 1. Design

Write each decision down with the brief fact behind it.

- **Output shape** - as the brief sets it: what one record is (a line, a host snapshot, one metric sample); ECS JSON with the native record in `event.original`, or native records only (then `measure.json` gets a `parse` regex).
- **Rate and rhythm** - inputs set volume and rhythm; each population gets its own tagged input, chosen by how it produces records:

  | Population | Input |
  |---|---|
  | People and workloads that follow a working day or week | `time_patterns`: a daily or weekly curve from pattern files, one per band |
  | Scheduled jobs: backups, reports, syncs, polls | `cron` at the schedule the source documents |
  | Fixed-interval emitters: heartbeats, metrics, keepalives | `timer`, or `cron` with seconds |
  | Steady machine traffic without a daily cycle | `cron` with `count` records per tick |

  An input's rate counts records, not actions: an action that writes k records takes k timestamps of its population. Every timestamp yields one record; a scheduled tick emits the first record of the action it starts (a job's start line).

  A carrier is the one exception: when records fall at moments no input schedules (the steps of a job after its start), or when a population's own timestamps are sparser than the delays between an action's records (follow-ups of rare night sessions), an input with its own tag supplies timestamps, and the template emits the earliest due record or drops the timestamp. The record's event time is its due time, which lies inside the carrier's tick interval, never the whole-second tick itself. Every timestamp first emits a record already due, so records stay in time order; a population timestamp used that way starts its action at the next free timestamp. A carrier tick carries as many timestamps (`count`) as records can fall due within one tick; a carrier covers only the hours its records can fall in, at the coarsest resolution they need, since drops are costly. No population's volume is ever shaped by drops.
- **Event mix** - every class with its share from the brief. A class that stands alone (an access line, a flow record, a metric snapshot) is picked per timestamp by weight. When one action writes several related records (a logon and its logoff; a job start, its per-item results and its finish), each population keeps its pending records in a queue in `shared`: a timestamp emits the earliest due record of its population, otherwise starts the population's next action. Records of one moment (a request and its log lines) take consecutive timestamps and stay adjacent. The timestamp is the event time, except for records emitted on a carrier.
- **Population** - actors (users, hosts, clients, services). Actors that act on demand have skewed activity weights bounded from below and above, so every actor appears regularly and none dominates, and are numerous enough that each one's own rate is realistic. Members that act on a schedule or an interval (hosts reporting metrics, machines in a backup job) all act every cycle; they vary in outcome and load.
- **Background** - a normal period of the source, not an incident or an outage: failures a few percent of attempts with a monotone law (one failure more common than two), retries and give-ups; occasional bursts carried by a few actors; measurements within their usual range, counters monotone; every limit in the brief holds.
- **Anomaly chain** - included by default when the source records activity a detection or alert rule targets and the brief has a chain candidate; the user may leave it out. Designed per `references/anomaly-chain.md`; without a chain, every chain item below is skipped.
- **Bounded state** - every list, dict, heap or queue in `shared` / `locals` has a fixed key set, a cap, or eviction on every path.
- **Measurement spec** - `.content-design/<name>/measure.json` per `references/measure-spec.md`: class, groups for every population and outcome the README will state, sequences for the delays the brief states, sessions for the spacing actors keep, the episode actor and pairs, presence limited to a step for every value an episode writes into it, the chain with every linking field. It fixes what the data must show before the build.

### 2. Build

- Files per `references/generator-rules.md`, API per `references/eventum-api.md`; the template validates parameters and samples on the first render.
- Reason the logic through before the first run: queue order, due times, each population at its quietest hour, a moment with no eligible actor, every template branch; with a chain, what the guard sees.

### 3. Validate

```bash
python3 <scripts>/capture.py run <generator> --out .content-design/<name>/captures --set author [--carrier <tag>] [--short-interval <hours>]
python3 <scripts>/capture.py live <generator> --out .content-design/<name>/captures [--carrier <tag>]
python3 <scripts>/measure.py report .content-design/<name>/measure.json .content-design/<name>/captures/manifest.json --save .content-design/<name>/report.json
```

- `--carrier <tag>` once per carrier tag; `--short-interval` takes the shortest interval the parameter range admits and every interval the README quotes (default 6; `0` for none); `live --spec <measure.json>` for native output.
- A parameter variant is a full set of its own: `run --param KEY=VALUE --out <another dir>`.
- What each run and number proves is in the acceptance criteria (Captures, Measurements). Every flag is a defect to fix; the other numbers are judged in phase 4. After a fix, rerun the set: runs execute in parallel and are cheap next to a missed defect. Keep `report.json` and the captures until the README is written.

### 4. Self-check

Go through `../review-generator/references/acceptance.md` against the generator and `report.json`; anything at MEDIUM or above returns to phase 1 or 2.

### 5. Document

The README per `references/generator-rules.md`: every number from `report.json`, the sample record from `measure.py sample .content-design/<name>/captures/long.jsonl.gz` (the middle record by default; `--contains` picks a class). Then delete the captures.

### 6. Hand over

Show the user the location, event types with shares, daily volume and rhythm, field coverage, one sample record, the report's key numbers, and omissions and assumptions. Then propose `review-generator` in a fresh context.

### 7. Feedback

`../using-content-design/references/feedback.md`.

## Rules

- Native format as in the brief's reference records; inferred parts named as inferred in the README.
- With a chain, episodes are indistinguishable from background except through the complete chain.
- Heavy work runs through the scripts, which hold host slots; nothing from `.content-design/` goes into the generator directory.
