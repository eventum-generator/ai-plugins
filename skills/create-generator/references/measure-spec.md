# Measurement spec

`.content-design/<name>/measure.json` tells `scripts/measure.py` how to read the generator's records and what to count. It describes the data the way a consumer sees it, never the generator's internals; the author writes it in the design phase and the review reuses it.

```json
{
 "timestamp": {"path": "@timestamp"},
 "class": {"path": "event.code"},
 "groups": {
  "failures": {"path": "event.outcome", "values": ["failure"]},
  "admins": {"path": "user.name", "regex": "^adm-"}
 },
 "actor": {"path": "user.name"},
 "chain": {
  "key": {"path": "source.ip"},
  "within": 3600,
  "steps": [
   {"match": {"path": "event.action", "values": ["role-created"]}, "bind": {"R": "user.target.name"}},
   {"match": {"all": [{"path": "event.action", "values": ["permission-granted"]},
                      {"path": "message", "regex": "ON TABLE finance\\."}]},
    "eq": {"R": "user.target.name"}},
   {"match": {"path": "event.action", "values": ["role-deleted"]}, "eq": {"R": "user.target.name"}}
  ]
 }
}
```

| Field | Meaning |
|---|---|
| `timestamp` | Value spec of the event time: ISO 8601 (`Z` or `+HH:MM` / `+HHMM`), epoch seconds, milliseconds, microseconds or nanoseconds; optional `format` (strptime) and `year` for formats without one (RFC 3164). Default `@timestamp`. |
| `parse` | For native lines only: `{"regex": ...}` with named groups; each group becomes a field. Lines that do not match are counted as `unparsed`. |
| `include` | Optional condition; records that fail it are ignored. |
| `class` | Value spec of the event class whose shares the README table states. |
| `groups` | Named conditions: populations, outcomes or anything with a share and an hourly curve to report. |
| `actor` | Value spec of the entity an episode is attributed to: its presence in background and its activity around episodes are measured. |
| `presence` | Named value specs of further entities an episode uses (`{"pair": {"paths": ["user.name", "source.ip"]}}`): each value episodes use is counted in every background capture. `actor` is included. |
| `sequences` | Named timings `{"group": value spec, "from": condition, "to": condition}`: the delay from a `from` record to the next `to` record of the same group (a job's start to its report), reported as quantiles; they check the delays the brief states. |
| `day_start_hour` | UTC hour at which a counted day starts (default 0); 12 keeps a night of scheduled jobs in one day. |
| `chain` | The anomaly chain, when there is one (below). |

A value spec is `{"path": p}` or `{"paths": [p, ...]}` (joined with `|`), with an optional `regex` whose group 1 (or whole match) is taken. Paths are dotted; a literal key containing dots (`@timestamp`) is tried first; `field.0` indexes a list, and a value spec on a list field takes its first element.

A condition is a clause `{"path": p, ...}` with `values` (string match), `regex`, numeric `gt` / `ge` / `lt` / `le`, or `"missing": true`, combined with `{"any": [...]}`, `{"all": [...]}` and `{"not": cond}`. A list field matches when any element does.

## Chain

The chain encodes every linking field the README names (an address, a token id inside a message), because the measurements of background pairs and presence see only what the spec links. A value beyond the key that links several steps (a role name, a token id) is bound at the first of them and checked with `eq` at the later ones; pairs of later steps inherit it.

| Field | Meaning |
|---|---|
| `key` | Value spec linking all steps (account, address, host). Records without it are ignored for the chain. |
| `same` | Optional paths that must also be equal across steps; their values join the key, so presence then requires every such combination in background. For a value that must only match within an episode, use `bind` / `eq`. |
| `within` | Seconds from the first step to the last: a little above the longest episode span. |
| `steps` | Ordered. `match` selects records; `bind: {"A": path}` stores a value; `eq: {"A": path}` requires the stored value; `ne: {"A,B": path}` requires a value different from all listed variables; a target is a path or a value spec with `regex` (a token inside a message). Steps may skip unrelated records of the same key. |

A chain is counted with every candidate binding kept alive: a record that advances one partial match does not consume it, partial matches expire `within` seconds after their first step, and a record counts once however many partial matches it completes. This is the strictest count: if background can form the chain in any combination of its records, it shows. A completion whose first step falls inside the previous counted chain of the same key belongs to that chain, so a repeated final step does not count again.
