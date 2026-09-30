---
name: create-generator
description: Use to build or redesign an Eventum generator once the source format is known - from a research-source brief or from the user's own format, sample records or log to imitate - "build the generator from the brief", "here are sample lines, make a generator", "add an anomaly scenario to this generator", "fix the review findings". Not for finding out a source's format (research-source) or for accepting a finished generator (review-generator).
---

# Create an Eventum generator

Builds a generator whose output passes for the source: its native format, its ordinary activity with realistic volume and rhythm, and, when the source suits one, recurring episodes of an anomaly chain. The generator is validated on its own output and documented for the people who consume the data.

## Before starting

- Input is one of: `.content-design/<name>/brief.md` from `research-source`; or the user's own material (format description, sample records, a log file). From user material, write the brief yourself (`../research-source/references/brief.md`, sections Source, Event classes, Fields, Time, Limits, Anomaly chain candidates), save the given records under `reference/`, and ask the user only for what the material does not answer (volume, populations, whether a chain is wanted). With neither, run `research-source` first.
- `eventum --version` works (Eventum 2.8+).
- The generator goes where the user says, default `./generators/<name>/`; everything else goes to `.content-design/<name>/`. The skill writes only there.

## References

- `references/eventum-api.md` - `generator.yml`, CLI, input plugins, picking modes, samples, state, dispatch, `module.rand`, Jinja gotchas.
- `references/generator-rules.md` - layout, naming, parameters, output shape, templates, speed, distributions, README.
- `references/anomaly-chain.md` - designing a chain: choice, presence in background, recurrence, episode shape, guard.
- `references/chain-spec.md` - the chain spec read by `scripts/chain_check.py` (plugin root, `<skill dir>/../../scripts/`).
- `../review-generator/references/acceptance.md` - the acceptance criteria and the capture protocol.

## Process

Validation and self-check send work back to the build, or to the design when the cause is a design choice.

### 1. Design

Write each decision down with the brief fact behind it.

- **Output shape** - as the brief sets it: what one record is (a line, a host snapshot, one metric sample), and native records only or ECS JSON with the native record in `event.original`.
- **Rate and rhythm** - inputs set volume and rhythm. Each population gets its own tagged input, chosen by how it produces records; several inputs merge in time order. An input's rate counts records, not actions: an action that writes k records takes k timestamps of its population. Every timestamp yields one record, and templates never thin a stream into a curve with `dispatch.drop()` or `next()`. The exception is a carrier: when records fall at moments no input schedules (the steps of a job after its scheduled start), a fine-grained `cron` or `timer` input supplies timestamps, and the template emits the due record or drops the timestamp.

  | Population | Input |
  |---|---|
  | People and workloads that follow a working day or week | `time_patterns`: a daily or weekly curve built from pattern files, one per hour band |
  | Scheduled jobs: backups, reports, syncs, polls | `cron` at the schedule the source documents |
  | Fixed-interval emitters: heartbeats, metrics, keepalives | `timer`, or `cron` with seconds |
  | Steady machine traffic without a daily cycle | `cron` with `count` records per tick |
  | A known series of moments | `timestamps` |

- **Event mix** - every class with its share from the brief. A class that stands alone (an access line, a flow record, a metric snapshot) is picked per timestamp by weight. When one action writes several related records (a logon and its logoff; a job start, its per-item results and its finish), each population keeps its pending records in a queue in `shared`: a timestamp emits the earliest due record of its population, otherwise starts the population's next action (a session of an idle actor, a job run). The timestamp is the event time.
- **Population** - actors (users, hosts, clients, services) live in `samples/`. Actors that act on demand have skewed activity weights bounded from below and above, so every actor appears regularly and none dominates, and are numerous enough that each one's own rate is realistic at the chosen volume. Members that act on a schedule or an interval (hosts reporting metrics, machines in a backup job) all act every cycle; they vary in outcome and load.
- **Background** - a normal period of the source, not an incident or an outage: failures a few percent of attempts with a monotone law (one failure more common than two), retries and give-ups; occasional bursts carried by a few actors; measurements within their usual range, counters monotone; every limit in the brief holds.
- **Anomaly chain** - included by default when the source records activity a detection or alert rule targets and the brief has a chain candidate; the user may leave it out. A chain is designed per `references/anomaly-chain.md`; without one, every chain step below is skipped.
- **Bounded state** - every list, dict, heap or queue in `shared` / `locals` has a fixed key set, a cap, or eviction on every path.

### 2. Build

- Files per `references/generator-rules.md`, API per `references/eventum-api.md`; the template fails on out-of-range `event.template.params`.
- With a chain: `anomaly_mode: true` and `anomaly_interval_hours: 24` in `event.template.params`, and the chain spec in `.content-design/<name>/chain.json`.
- Reason the logic through before the first run: queue order, due times, each population at its quietest hour, a moment with no eligible actor; with a chain, what the guard sees.

### 3. Validate

Capture and measure by the author's set of the capture protocol in `../review-generator/references/acceptance.md`. Record every number; after a fix, recheck only the affected checks. Delete captures once their numbers are recorded, except the one the README sample comes from, until phase 5 is done.

### 4. Self-check

Go through the criteria in `../review-generator/references/acceptance.md` against the generator and the phase 3 numbers; anything at MEDIUM or above returns to phase 1 or 2.

### 5. Document

The README per `references/generator-rules.md`, every number taken from phase 3.

### 6. Hand over

Show the user the location, event types with shares, daily volume and rhythm, field coverage, one sample record, the phase 3 results, and omissions and assumptions. Then propose `review-generator` in a fresh context.

## Rules

- Native format as in the brief's reference records; inferred parts named as inferred in the README.
- With a chain, episodes are indistinguishable from background except through the complete chain.
- Nothing from `.content-design/` goes into the generator directory.
