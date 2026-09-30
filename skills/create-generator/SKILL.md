---
name: create-generator
description: Use when the user wants an Eventum generator for a log source - "make a generator for FortiGate logs", "synthetic Windows security events for detection testing", "fake nginx access logs with an attack scenario", "Eventum content pack for Keycloak". Researches the source, designs realistic background traffic with recurring anomaly episodes, builds generator.yml, templates, samples and time patterns, validates the output and writes the README. Not for editing Eventum itself or for one-off sample files without a generator.
---

# Create an Eventum generator

A generator is a directory with `generator.yml`, Jinja templates, sample data and time patterns that Eventum turns into a stream of realistic log records. The result of this skill is a generator that:

- writes records in the source's native format (mapped to ECS when the output is event-like);
- produces a normal day of background activity, with volume and hours set by its inputs;
- by default mixes in recurring episodes of one anomaly chain - an ordered sequence of records a detection rule should fire on - and with `anomaly_mode: false` produces background only;
- is validated on its own output and documented for the people who consume the data.

## Before starting

- `eventum --version` must work (Eventum 2.x; install with `uv tool install eventum-generator` or `pip install eventum-generator`, Python 3.14+). Python 3.9+ runs `scripts/chain_check.py`.
- Ask where the generator goes if the user has not said; default `./generators/<name>/`. Keep captures and test copies outside it (a scratch directory).
- The skill writes only inside the generator directory and the scratch directory; it reads vendor documentation and public integrations on the web.

## References

- `references/eventum-api.md` - everything the generator can use: `generator.yml`, CLI, input plugins and `time_patterns` semantics, picking modes and FSM conditions, samples, state, dispatch, `module.rand`, faker, mimesis, Jinja gotchas. Use it instead of reading Eventum's source.
- `references/generator-rules.md` - layout, naming, parameters, samples, ECS output, templates, speed, distributions, README sections.
- `references/chain-spec.md` - the spec format read by `scripts/chain_check.py`.

## Process

Seven phases in order. Phases 4 and 5 send work back to phase 3, or to phase 2 when the cause is a design choice.

### 1. Research

- Native format from primary sources: vendor documentation of the chosen version and transport, or a complete raw record from a maintained integration. Confirm every modeled event class, field meaning and timestamp source. Without a complete raw record or a field-complete format specification, stop and tell the user; do not invent a wire format.
- Elastic integration `sample_event.json` and `fields.yml` when one exists - the reference for ECS structure, not proof of the native format.
- Event ID catalogs, documented frequencies and timing; limits the data must respect (lockout thresholds, session caps, rate limits, counters that only grow, names that must be unique).
- Model the anomaly chain from records the vendor documents. Keep it at the level of log fields a detection rule reads.

Exit: a field map (path, source, generation strategy) covering ≥ 90% of the reference fields when a reference event exists, with gaps and assumptions listed; the native format of every event class; the vendor limits.

### 2. Design

Write down each decision with the fact behind it; phase 4 checks them.

- **Rate and hours** - the input sets the rate: every input timestamp yields exactly one record. Use `time_patterns` inputs with a 1-day period anchored at midnight (weekly: 7 days anchored on a Monday), one pattern file per hour band, randomizer deviation about 0.03. Give each population its own tagged input: people follow a working day with a low night; automation, services and scanners stay flat. State the daily volume and hourly rates.
- **Population** - actors in `samples/` with a bounded activity weight (a floor and a cap), so every actor appears in every 4-day window; enough actors that each one's own rate is realistic at the chosen volume.
- **Dispatcher** - one template (`mode: all`) or a few, driven by a queue in `shared`: on each timestamp emit the earliest due record, otherwise start new activity for an idle actor of the timestamp's population, chosen by weight. Records of one moment (a request and its log lines) take consecutive timestamps and stay adjacent. The timestamp is the event time.
- **Background** - a normal day, not an incident or an outage: failures a few percent of attempts with a monotone law (one failure more common than two), retries and give-ups, occasional bursts carried by a few busy actors. Every vendor limit holds.
- **Anomaly chain** - an ordered, source-specific sequence whose actors, targets and identifiers stay consistent amid ordinary traffic; its steps, linking fields, time window and a detection idea.
- **Chain in background** - every chain step, and every actor and actor pair an episode can use, also occurs in ordinary background often enough to appear in every 4-day capture (expected count ≥ 10), and the actor is active at the hours episodes start. Only the complete ordered sequence is absent from background.
- **Recurrence** - `anomaly_interval_hours` (default 24): the first episode starts within min(interval, 24 h); each next one is due one interval after the actual start of the previous one and starts in a window of w = min(interval / 4, 6 h) centred on the due time; start hours, the first one included, are weighted by the square of the actor's hourly activity plus a small floor; missed episodes are not replayed. An eligible actor must always be available in the window. If a finite resource (name pool, free slot, working hours) cannot serve short intervals, restrict the parameter range (a minimum, or multiples of 24) instead of letting episodes slip.
- **Episode shape** - an episode is ordinary activity of its actor with the chain inside: it respects every cap background respects, uses the actor's usual address and host, looks like the actor's ordinary activity at that hour just before and just after (lead-in, spacing, aftermath), leaves every state (counters, locks, open objects, names in use) as an ordinary session would, and never cancels, delays or takes over the actor's ordinary work. Rotate actor and target between episodes.
- **Guard** - background must never complete the chain. Prefer a background design in which the full sequence cannot form (cooldowns, caps). A guard, if needed, acts only on the exact final step within the chain window, changes that step's target or outcome to a normal alternative (never reassigns, defers or drops), fires rarely, and suppresses no noticeable share of an ordinary action; the episode's own records count in its history, and nothing stays armed after an episode.
- **Bounded state** - every list, dict, heap or queue in `shared` / `locals` has a fixed key set, a cap, or eviction on every path.

### 3. Build

- Files per `references/generator-rules.md`; API per `references/eventum-api.md`.
- `event.template.params`: `anomaly_mode: true`, `anomaly_interval_hours: 24`, and the values users edit (host names, versions). The template fails on out-of-range values.
- A chain spec (`references/chain-spec.md`) in the scratch directory.
- Save the reference raw records and `sample_event.json` in the scratch directory for phase 4.
- Reason the logic through before the first run: queue order, due times, what each population does at night, what happens when the window has no eligible actor, what the guard sees. It is cheaper than a rerun.

### 4. Validate

One validation set, run once; after a fix, recheck only the affected check.

**Test copies.** Copy the generator into the scratch directory once per run; in every pattern file of a copy set `start` to a midnight with an explicit offset (`"2026-09-01T00:00:00+00:00"`) and `end` to the end of the window; set `anomaly_mode` and `anomaly_interval_hours` in the copy's `generator.yml`. Run each copy:

```bash
eventum generate --path <copy>/generator.yml --id <run> --live-mode false --keep-order true -vvv
```

The run exits 0 and prints no log lines.

**Set:** 2 copies with `anomaly_mode: false` and 2 with `true`, 4 days each, plus 1 `true` copy at a short interval (6 or 8 hours).

Checks:
- **Format** - every line is valid JSON; ECS fields present; `event.original` matches the vendor record or documented format for each event class; ≥ 90% of available reference fields present (misses listed with reasons).
- **Chains** - `python <skill dir>/scripts/chain_check.py accept <spec> --off OFF1 OFF2 --on ON1 ON2` reports `ok`: 0 chains in background, every step and chain key present in each background capture. `chain_check.py count <spec> <capture>` gives exactly one chain per episode in every anomaly capture. When the chain key is a random ID, check actor and actor-pair presence in background yourself.
- **Recurrence** - from `count`: gaps within interval ± w/2 at the default and the short interval; first start within min(interval, 24 h); start hours follow the actor's curve; consecutive episodes rotate actor and target.
- **One record per timestamp** - render the same inputs with a template that outputs only `{"t": {{ timestamp.isoformat() | tojson }}}` and compare the line counts with the real run: equal.
- **Episode vs background** - for the episode actor, compare the 30 minutes before and after episodes with the same actor's ordinary activity at the same hours; compare caps and live-object counts (sessions, open objects, pool usage) between modes; count guard actions in both modes.
- **Bounded state** - a 14-day run: every container stays flat.
- **Live** - a copy with `end: never` and pattern rates scaled up ×10-×100, `--live-mode true`, stopped after 90 seconds: records arrive at wall-clock time, in order, without a catch-up burst, and the log is empty. The generator keeps its own rates.
- **Speed** - wall time of a 14-day run.

Delete captures once their numbers are recorded; keep the one the README sample comes from until phase 6.

### 5. Self-review

Check the generator against phase 2 and `references/generator-rules.md`. The defects that most often slip through:

- Rate shaped by `dispatch.drop()` / `next()` or a 1-second cron; people active around the clock.
- An event type, actor, address or actor pair that occurs only in episodes, or is missing from a 4-day background capture.
- Background that looks like an incident: detections or failures everywhere, one repeated filler action dominating the output.
- A guard that suppresses a noticeable share of an ordinary action, piles up records just below the chain threshold, or stays armed after an episode.
- An episode that leaves state behind (a lingering task, an extra open object), pushes a count past the background cap, or differs from ordinary activity just before or after.
- Recurrence that slips: starts pinned to one clock hour, stuck at night, skipped when no actor is free, or ignoring the interval.
- A vendor limit broken (lockout threshold, session cap, counters that must grow).
- Unbounded state; `loop.index0` in a filtered loop; `rand.chance(15)` with a percent instead of a probability; datetimes without an offset.
- A README command that does not run as written (e.g. `--params` used for `event.template.params`).

### 6. Document

Write the README per `references/generator-rules.md`, in data terms only.

- **Every number is measured.** Check each figure against the validation numbers (shares, per-day counts, per-actor ranges, spans, gaps, start hours). A range covers every measured capture; state defaults, not one run.
- **Sample output** is one line copied byte for byte from a default-configuration capture (Eventum's JSON escapes `<`, `>`, `&`, `'` as `<`, `>`, `&`, `'` - keep the escapes).
- **Anomaly Chain** covers the sequence, linking fields, recurrence (interval from the actual start, window, start hours, behaviour at short intervals), episode variation, what background contains of the chain, and a detection idea. With `anomaly_mode: true` each episode adds its own records, so counts of chain parts are about one per episode higher - say so.
- **Parameters** name the sample files a user edits for their own actors and hosts, and the pattern files that set volume and hours.
- **Usage**: the live command, and how to run a finite batch window (set `start` / `end` in every pattern file, starting at a midnight with an offset).

### 7. Hand over

Show the user:

- location of the generator;
- event types with shares, daily volume and hourly curve;
- field coverage against the reference;
- one sample record;
- validation results: chains in background and per episode, recurrence gaps, one record per timestamp, episode vs background, bounded state, live run, speed;
- omissions and assumptions.

The public catalog of Eventum generators is `github.com/eventum-generator/content-packs`; if the user wants to share the generator, point them to it.

## Rules

- The native format comes from primary sources; an inferred part is named as inferred in the README.
- Every input timestamp yields a record; the rate and the hours live in the inputs.
- Anomaly episodes are indistinguishable from background except through the complete chain.
- Datetimes in configs carry an explicit offset; a value without one is read as the machine's local time.
- Validation output (captures, test copies) stays outside the generator directory.
