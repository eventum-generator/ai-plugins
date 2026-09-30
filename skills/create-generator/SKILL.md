---
name: create-generator
description: Use to build or redesign an Eventum generator once the source format is known - from a research-source brief or from the user's own format, sample records or log to imitate - "build the generator from the brief", "here are sample lines, make a generator", "add an anomaly scenario to this generator", "fix the review findings". Designs background traffic and recurring anomaly episodes, builds generator.yml, templates, samples and time patterns, validates the output and writes the README. Not for finding out a source's format (research-source) or for accepting a finished generator (review-generator).
---

# Create an Eventum generator

Builds a generator that writes the source's native format, produces a normal day of activity with volume and hours set by its inputs, mixes in recurring episodes of one anomaly chain by default (`anomaly_mode: true`; `false` gives background only), is validated on its own output, and is documented for the people who consume the data.

## Before starting

- Input is one of: `.content-design/<name>/brief.md` from `research-source`; or the user's own material (format description, sample records, a log file). From user material, write the brief yourself (`../research-source/references/brief.md`, sections Source, Event classes, Fields, Time, Limits, Anomaly chain candidates), save the given records under `reference/`, and ask the user only for what the material does not answer (volume, actors, the chain). With neither, run `research-source` first.
- `eventum --version` works (Eventum 2.8+).
- The generator goes where the user says, default `./generators/<name>/`; everything else goes to `.content-design/<name>/`. The skill writes only there.

## References

- `references/eventum-api.md` - everything a generator can use: `generator.yml`, CLI, input plugins and `time_patterns` semantics, picking modes, FSM conditions, samples, state, dispatch, `module.rand`, faker, mimesis, Jinja gotchas.
- `references/generator-rules.md` - layout, naming, parameters, samples, ECS output, templates, speed, distributions, README sections.
- `references/chain-spec.md` - the chain spec read by `scripts/chain_check.py` (plugin root, `<skill dir>/../../scripts/`).
- `../review-generator/references/acceptance.md` - the acceptance criteria the finished generator is judged by.

## Process

Phases 3 and 4 send work back to phase 2, or to phase 1 when the cause is a design choice.

### 1. Design

Write each decision down with the brief fact behind it; phase 3 checks them.

- **Rate and hours** - the input sets the rate: every input timestamp yields exactly one record. `time_patterns` inputs with a 1-day period anchored at midnight (weekly: 7 days anchored on a Monday), one pattern file per hour band, randomizer deviation about 0.03. Each population has its own tagged input: people follow a working day with a low night; automation, services and scanners stay flat.
- **Population** - actors in `samples/` with a bounded activity weight (floor and cap), so every actor appears in every 4-day window; enough actors that each one's own rate is realistic at the chosen volume.
- **Dispatcher** - one template (`mode: all`) or a few, driven by a queue in `shared`: on each timestamp emit the earliest due record, otherwise start new activity for an idle actor of the timestamp's population, chosen by weight. Records of one moment take consecutive timestamps and stay adjacent. The timestamp is the event time.
- **Background** - a normal day, not an incident or an outage: failures a few percent of attempts with a monotone law (one failure more common than two), retries and give-ups, occasional bursts carried by a few busy actors; every limit in the brief holds.
- **Chain** - one chain from the brief's candidates: steps, linking fields, window, detection idea. Every step, and every actor and actor pair an episode can use, also occurs in ordinary background often enough to appear in every 4-day capture (expected count ≥ 10), and the actor is active at the hours episodes start. Only the complete ordered sequence is absent from background.
- **Recurrence** - `anomaly_interval_hours` (default 24): the first episode starts within min(interval, 24 h); each next one is due one interval after the actual start of the previous one and starts in a window of w = min(interval / 4, 6 h) centred on the due time; start hours, the first one included, are weighted by the square of the actor's hourly activity plus a small floor; missed episodes are not replayed. An eligible actor is always available in the window; if a finite resource (name pool, free slot, working hours) cannot serve short intervals, the parameter range is restricted (a minimum, or multiples of 24).
- **Episode shape** - ordinary activity of its actor with the chain inside: within every cap background respects, from the actor's usual address and host, looking like the actor's ordinary activity at that hour just before and just after, leaving every state (counters, locks, open objects, names in use) as an ordinary session would, never cancelling, delaying or taking over the actor's own work. Actor and target rotate between episodes.
- **Guard** - background must never complete the chain; prefer a background design in which it cannot form (cooldowns, caps). A guard acts only on the exact final step within the chain window, changes its target or outcome to a normal alternative (never reassigns, defers or drops), fires rarely, suppresses no noticeable share of an ordinary action, counts the episode's own records, and keeps nothing armed after an episode.
- **Bounded state** - every list, dict, heap or queue in `shared` / `locals` has a fixed key set, a cap, or eviction on every path.

### 2. Build

- Files per `references/generator-rules.md`, API per `references/eventum-api.md`.
- `event.template.params`: `anomaly_mode: true`, `anomaly_interval_hours: 24`, and the values users edit; the template fails on out-of-range values.
- `.content-design/<name>/chain.json` - the chain spec.
- Reason the logic through before the first run: queue order, due times, each population at night, a window with no eligible actor, what the guard sees.

### 3. Validate

One validation set; after a fix, recheck only the affected check.

**Test copies** in `.content-design/<name>/captures/`: copy the generator once per run; in every pattern file of the copy set `start` to a midnight with an explicit offset (`"2026-09-01T00:00:00+00:00"`) and `end` to the end of the window; set `anomaly_mode` and `anomaly_interval_hours` in the copy's `generator.yml`; run

```bash
eventum generate --path <copy>/generator.yml --id <run> --live-mode false --keep-order true -vvv
```

Exit 0 and no log lines.

**Set:** 2 copies with `anomaly_mode: false` and 2 with `true`, 4 days each, plus 1 `true` copy at a 6- or 8-hour interval.

- **Format** - every line valid JSON; `event.original` matches the reference record of each class; ≥ 90% of the reference fields present, misses listed with reasons.
- **Chains** - `python <chain_check.py> accept chain.json --off OFF1 OFF2 --on ON1 ON2` reports `ok`; `count` gives exactly one chain per episode. A random-ID chain key needs a separate actor and actor-pair presence check.
- **Recurrence** - from `count`: gaps within interval ± w/2 at both intervals; first start within min(interval, 24 h); start hours on the actor's curve; actor and target rotate.
- **One record per timestamp** - the same inputs with a template that outputs only `{"t": {{ timestamp.isoformat() | tojson }}}` give the same line count.
- **Episode vs background** - the episode actor's 30 minutes before and after episodes against its ordinary activity at the same hours; caps and live-object counts per mode; guard actions per mode.
- **Bounded state** - a 14-day run: every container stays flat.
- **Live** - a copy with `end: never` and rates scaled ×10-×100, `--live-mode true`, stopped after 90 seconds: records at wall-clock time, in order, no catch-up burst, empty log. The generator keeps its own rates.
- **Speed** - wall time of the 14-day run.

Delete captures once their numbers are recorded; keep the one the README sample comes from until phase 5.

### 4. Self-check

Go through `../review-generator/references/acceptance.md` against the generator and the phase 3 numbers; anything at MEDIUM or above returns to phase 1 or 2.

### 5. Document

The README per `references/generator-rules.md`, in data terms only.

- Every number is measured: each figure checked against the phase 3 numbers; a range covers every capture; defaults, not one run.
- Sample output: one line copied byte for byte from a default-configuration capture, escapes kept.
- `## Anomaly Chain`: sequence, linking fields, recurrence (interval from the actual start, window, start hours, behaviour at short intervals), variation, what background contains of the chain, detection idea, and that each episode adds its own records (chain-part counts about one per episode higher).
- Parameters name the sample files users edit for their own actors and hosts, and the pattern files that set volume and hours; Usage gives the live command and the finite batch window recipe. Every command runs as written.

### 6. Hand over

Show the user the location, event types with shares, daily volume and hourly curve, field coverage, one sample record, the phase 3 results, and omissions and assumptions. Then propose `review-generator` in a fresh context.

## Rules

- Native format as in the brief's reference records; inferred parts named as inferred in the README.
- Every input timestamp yields a record; rate and hours live in the inputs.
- Episodes are indistinguishable from background except through the complete chain.
- Datetimes in configs carry an explicit offset; one without is read as the machine's local time.
- Nothing from `.content-design/` goes into the generator directory.
