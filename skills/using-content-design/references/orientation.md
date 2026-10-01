# Eventum content design

Eventum (eventum.run, CLI `eventum`, package `eventum-generator`) streams events from a **generator**: a directory with `generator.yml`, Jinja templates and sample data. Content design builds generators whose output passes for a real log source: its native format, ordinary activity with realistic volume and rhythm and, when the source suits one, recurring episodes of an **anomaly chain** - an ordered sequence of records a detection or alert rule fires on.

| Skill | Invoke when |
|---|---|
| `research-source` | A product or log source is named and no format specification or sample records are at hand. |
| `create-generator` | A source brief exists, or the user gives a format, sample records or a log to imitate; also to change a generator. |
| `review-generator` | A generator is finished or changed and has not been reviewed at its current files. |
| `publish-generator` | Only on the user's request: submit to the catalog (`eventum-generator/content-packs`) or the Eventum Hub. |

Stages run in this order, starting where the user's material allows. The review runs in a context that did not build the generator; MEDIUM or HIGH findings return to `create-generator`, LOW ones are fixed or described in the README.

- **Working directory**: `.content-design/<name>/` in the project root holds everything not shipped with the generator; keep it out of commits (`.git/info/exclude`).
- **Parallel work**: one subagent per generator runs its stages, the review in a subagent of its own. The plugin's scripts run every Eventum process, docs build and git operation on a shared clone under host-wide slots, so parallel agents stay within the host's memory; no process is ever killed by name.
- **Tools**: `<skill dir>/../../scripts/` (Python 3.9+, run with `python3`): `capture.py` (environment check, test captures), `measure.py` (every number), `slot.py` (host slots). Eventum 2.8+ (`uv tool install eventum-generator`).
- **Feedback**: every stage ends with `using-content-design/references/feedback.md`.
