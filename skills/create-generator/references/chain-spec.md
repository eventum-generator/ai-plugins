# Chain spec

`scripts/chain_check.py` reads the anomaly chain from a JSON spec, written the way a detector would see the chain. Keep it next to the generator's working files (not inside the generator directory) and update it whenever the chain changes.

```json
{
 "timestamp": {"path": "@timestamp"},
 "include": {"path": "event.dataset", "values": ["app.audit"]},
 "chain_seq": {
  "key": {"path": "source.ip"},
  "within": 3600,
  "steps": [
   {"match": {"path": "event.action", "values": ["role-created"]}, "bind": {"R": "user.target.name"}},
   {"match": {"all": [{"path": "event.action", "values": ["permission-granted"]},
                      {"path": "message", "regex": "ON TABLE finance\\.payroll"}]},
    "eq": {"R": "user.target.name"}},
   {"match": {"path": "event.action", "values": ["role-deleted"]}, "eq": {"R": "user.target.name"}}
  ]
 }
}
```

| Field | Meaning |
|---|---|
| `timestamp` | `{"path": ...}` - ISO 8601, epoch seconds or milliseconds; optional `format` (strptime) and `regex` (group 1). Default `@timestamp`. |
| `include` | Optional condition; rows that fail it are ignored. |
| `chain_seq.key` | `{"path": p}` or `{"paths": [p, ...]}` (joined with `\|`), optional `regex`: the value that links all steps (account, address, host). Rows without it are ignored. |
| `chain_seq.same` | Optional list of paths that must also be equal across steps. |
| `chain_seq.within` | Seconds from the first step to the last. A little above the generator's longest episode span. |
| `chain_seq.steps` | Ordered steps. `match` selects rows; `bind: {"A": path}` stores a value; `eq: {"A": path}` requires the stored value; `ne: {"A,B": path}` requires a value different from all listed variables. Steps may skip unrelated rows of the same key. |

Paths are dotted (`event.action`); a literal key containing dots (`@timestamp`) is tried first; `field.0` indexes a list.

Conditions: `{"path": p, "values": [...]}` or `{"path": p, "regex": r}` - a list field matches if any element matches; `"missing": true` matches an absent field - combined with `{"any": [...]}`, `{"all": [...]}` and `{"not": cond}`.

## What the checks count

- A chain is counted with every candidate binding kept alive: a row that advances one partial match does not consume it, partial matches expire `within` seconds after their first step, and a row counts once however many partial matches it completes. This is the strictest count - if background can form the chain in any combination of its rows, it shows.
- `accept` also counts, per background capture, the rows matching each step (`step_hits`, every step must be > 0) and checks that every chain key that completed a chain in an anomaly capture also occurs in each background capture (`missing_chain_keys`). When the key is a random identifier (a session, an incident), keys never repeat; check actor and actor-pair presence separately.
