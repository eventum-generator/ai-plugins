# Eventum content design

Eventum (eventum.run, CLI `eventum`, package `eventum-generator`) streams events from a **generator**: a directory with `generator.yml`, Jinja templates, sample data and time patterns. Content design is building generators whose output passes for a real log source: the native format, a normal day of activity and, by default, recurring episodes of one **anomaly chain** - an ordered sequence of records a detection rule should fire on.

## Skills

| Skill | Stage | Invoke when |
|---|---|---|
| `research-source` | Research | The user names a product or log source and no format specification or sample records are at hand. |
| `create-generator` | Build | A source brief exists, or the user provides the format, sample records or an existing log to imitate; also to change an existing generator's design. |
| `review-generator` | Review | A generator is finished or changed and has not been reviewed at its current files; the user asks to check or accept a generator. |
| `publish-generator` | Publish | Only when the user asks to share or submit a generator to the official catalog (`eventum-generator/content-packs`) or the Eventum Hub. |

## Pipeline

research-source → create-generator → review-generator → publish-generator.

- Start at the stage the user's material allows: own format or samples → `create-generator`; an existing generator → `review-generator`.
- Each stage reads the previous stage's files from the working directory and writes its own.
- A review with MEDIUM or HIGH findings returns to `create-generator`; LOW findings are fixed in the README and the pipeline continues.
- The review is done by a context that did not build the generator: a subagent or a new session.
- Publishing is optional and changes public repositories; it runs only on the user's request.

## Working directory

`.content-design/<name>/` in the project root (the directory the session works in) holds everything that is not shipped with the generator: `brief.md`, `reference/` (raw records, `sample_event.json`), `chain.json` (chain spec), `captures/`, `review.md`. The generator directory holds only the generator. Keep `.content-design/` out of commits.

## Tools

- `eventum --version` must work before any build or review (install: `uv tool install eventum-generator`, Python 3.14+).
- `scripts/chain_check.py` at the plugin root (Python 3.9+, standard library): `count`, `accept` and `digest` - chain counts, background acceptance, and the hash that ties a review to the generator's files.
