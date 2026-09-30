# Eventum generator reference

What a generator can use, verified against the source of Eventum 2.8.0 (package `eventum-generator`). Changes merged for the next release are marked *next release*.

## generator.yml

```yaml
input:                      # non-empty list of one-key maps; inputs are merged in time order
  - time_patterns:
      tags: [office]        # optional on every input; reaches templates as `tags`
      patterns: [patterns/office.yml]
event:
  template:
    mode: all               # all | any | chance | spin | chain | fsm
    params: {...}           # constants -> `params` in templates
    samples: {...}          # datasets -> `samples` in templates
    templates: [...]        # list of one-key maps: alias -> template config
output:                     # non-empty list of one-key maps
  - file:
      path: output/events.json
      write_mode: overwrite
      formatter:
        format: json
```

- Only `input`, `event` and `output` are allowed at the top level; unknown fields are rejected in every plugin config.
- Paths (templates, samples, patterns, output) are relative to the directory of `generator.yml`.
- The file is rendered as Jinja with `${ }` as variable delimiters before YAML parsing; `{% %}` and `{# #}` stay active, so a literal `{%` or `{#` anywhere in `generator.yml` (a regex, an inline template) is consumed.
- `${params.x}` / `${secrets.x}` work anywhere in `generator.yml`, `event.template.params` included; every placeholder is then required on every run (`--params '{"x": 1}'`, secrets from the keyring), and a missing one stops the run with exit 1. Pattern files and templates are never substituted.

## CLI

```bash
eventum generate --path <generator.yml> --id <id> [options]
```

| Option | Default | Meaning |
|---|---|---|
| `--live-mode` | `true` | `true`: release timestamps at wall-clock time; `false`: as fast as possible (batch). |
| `--skip-past` | `true` | Live mode: drop timestamps before now. |
| `--keep-order` | `false` | Write events strictly in timestamp order. |
| `--timezone` | `UTC` | Zone attached to template timestamps and used for cron, time-of-day and phrase values. |
| `--params` | `{}` | JSON for `${params.*}`. |
| `--batch.size` / `--batch.delay` | 10000 / 1.0 s | Defaults apply only when neither is given; giving one unsets the other. Batch runs ignore the delay unless size is unset. |
| `-v` ... `-vvvvv` | off | Log level critical ... debug. |

- Live mode releases a batch when the clock reaches its last timestamp: records arrive up to `batch.delay` late plus the file output's `flush_interval`, never early.
- A batch run ends when every input is exhausted: every input needs an `end`, a finite `repeat`, `count` or list.
- Exit codes: 1 when startup fails (YAML or validation error, missing param or secret, template not found or syntax error, sample load error, no FSM initial state); 130 / 143 on SIGINT / SIGTERM; 0 otherwise, including runs in which templates failed to render or events failed to format. Only the log shows those.

### Logging

- A normal run logs nothing at `-vvv`, batch or live.
- Template runtime error: ERROR with `reason`, `template_alias` and a traceback with the template line; that timestamp yields nothing and the run continues.
- Format error: ERROR "Failed to format event" with `original_event`, once per event (*next release*: throttled to one line per 10 s with a count).
- WARNING on FSM comparisons with a missing or `None` value (every check), on "Timestamps/Events queue is full" when live throughput falls behind, and on a `globals` lock left acquired.
- `dispatch.drop()` logs nothing.

## Time

- Datetime values (`start`, `end`, oscillator bounds, `timestamps` lists): ISO with offset (`"2026-09-01T00:00:00+00:00"` or `Z`) is converted exactly; **without an offset it is the local time of the machine**, not `--timezone`; keywords `now`, `never` (`never` = far future, not allowed in `linspace.end`); relative `[+|-]<n>d<n>h<n>m<n>s` (an `end` is relative to its `start`, otherwise to now); a time of day (`"08:00:00"`) takes the date of `start`, or today; phrases (`"tomorrow 9am"`) go through dateparser in `--timezone`.
- `end` bounds of `cron`, `linspace` and `time_patterns` are inclusive.
- Equal timestamps from several inputs: the input listed first comes first.
- `timestamp` in templates is the input time with `--timezone` attached. `timestamp.isoformat()` omits the fraction when microseconds are 0 (every cron and timer tick) and writes `+00:00`, never `Z`; use `strftime` for a fixed-width format.

## Input plugins

Every input accepts `tags: [..]`. Inside `time_patterns`, only the tags of the input count; tags in pattern files are ignored.

### time_patterns

```yaml
- time_patterns:
    tags: [office]
    patterns: [patterns/office-core.yml, patterns/office-edge.yml]
```

Pattern file:

```yaml
label: office core 08-18 UTC              # required, free text
oscillator:
  period: 1
  unit: days                              # weeks|days|hours|minutes|seconds|milliseconds|microseconds
  start: "2026-01-01T00:00:00+00:00"      # anchor: the phase of every period
  end: never
multiplier:
  ratio: 4000                             # timestamps per period (int >= 1)
randomizer:
  deviation: 0.03                         # 0..1
  direction: mixed                        # decrease | increase | mixed
  sampling: 1024                          # size of the factor pool (>= 16)
spreader:
  distribution: uniform                   # uniform | triangular | beta
  parameters: {low: 0.3333, high: 0.75}   # fractions of the period
```

- Per period the count is `int(ratio * factor)`, factors drawn from `[1-d, 1]`, `[1, 1+d]` or `[1-d, 1+d]` and reused from a shuffled pool. Mean count: `ratio - 0.5` for `mixed`, `ratio * (1 - d/2) - 0.5` for `decrease`, `ratio * (1 + d/2) - 0.5` for `increase`; exactly `ratio` with `deviation: 0`.
- The spreader places timestamps inside the period: `uniform {low, high}` (`0 <= low < high <= 1`), `triangular {left, mode, right}`, `beta {a, b}`.
- Several pattern files of one input add up: an hour-of-day curve is several files with a 1-day period anchored at a midnight, each covering a band (`low`/`high` = hour / 24); a weekly curve is a 7-day period anchored on a Monday.
- Periods are counted from `start` in live mode too, so a midnight anchor keeps bands on clock hours; the anchor's offset decides which clock (anchor `+00:00` with `--timezone Asia/Tokyo` puts the 12:00 band at 21:00 JST).
- Pattern files are plain YAML: no `${params.*}`.

### Other inputs

| Plugin | Fields | Behaviour |
|---|---|---|
| `cron` | `expression`, `count` (> 0), `start` (default now), `end` | `count` identical timestamps at every tick, evaluated in `--timezone`. Six fields are read by croniter with **seconds last**: `* * * * * */30` = every 30 s. |
| `timer` | `seconds` (>= 0.1), `count` (>= 1), `start`, `repeat` | `count` timestamps every `seconds`, first at `start + seconds`; `repeat` cycles, endless when unset; no `end`. |
| `linspace` | `start`, `end` (no `never`), `count`, `endpoint` (true) | `count` evenly spaced timestamps. |
| `static` | `count` | `count` timestamps at now. |
| `timestamps` | `source`: list of datetimes or a file of ISO lines | Replays given timestamps; they must be sorted and carry offsets. |
| `http` | `port`, `host`, `max_pending_requests` | Timestamps on HTTP requests. |

## Template event plugin

### Picking modes

| `mode` | Template config | Picks per timestamp |
|---|---|---|
| `all` | `template`, `vars` | Every template, in order; one event each. |
| `any` | `template`, `vars` | One template, uniform. |
| `chance` | `template`, `vars`, `chance` (> 0, relative weight) | One template by weight. |
| `spin` | `template`, `vars` | Next template in declaration order, cycling. |
| `chain` | `template`, `vars`; plugin-level `chain: [alias, ...]` | Next alias of `chain`, cycling. |
| `fsm` | `template`, `vars`, `initial: true` (exactly one), `transitions: [{to, when}]` | Current state; see below. |

`templates` is a list of one-key maps: `- alias: {template: templates/x.json.jinja, ...}`; aliases are unique.

**FSM.** The first timestamp renders the initial state. Before every later timestamp the transitions of the current state are checked in order against the context of the previous render (`timestamp` and `tags` of the new timestamp, `locals` of the previously rendered template, `shared`, `globals`); the first true condition moves the state, none keeps it.

| Condition | Form |
|---|---|
| compare | `{eq: {shared.k: v}}`, `gt`, `ge`, `lt`, `le` (numbers); a missing or `None` value is false and logs a WARNING |
| length | `{len_eq: {shared.k: n}}`, `len_gt`, `len_ge`, `len_lt`, `len_le` |
| membership | `{contains: {shared.list: v}}` (state value contains v), `{in: {shared.k: [a, b]}}` (state value in list) |
| regex | `{matches: {shared.k: "^re"}}` (`re.match`; false on a non-string) |
| key present | `{defined: shared.k}` |
| tags | `{has_tags: tag}` or `{has_tags: [a, b]}` (all present) |
| time | `{before: {hour: 9}}`, `{after: {hour: 18, minute: 30}}`: components `year..microsecond` replace those of the timestamp; `after` is `>=`; all-zero components are rejected at load |
| constant | `{always: null}`, `{never: null}` |
| logic | `{and: [c, c]}`, `{or: [c, c]}` (2+ items), `{not: c}` |

`<state>.<key>` is `locals.key`, `shared.key` or `globals.key`: one flat key, not a nested path.

### Samples

```yaml
samples:
  users: {type: csv, source: samples/users.csv, header: true}   # delimiter ',', quotechar '"'
  hosts: {type: json, source: samples/hosts.json}               # array of objects with the same keys
```

- Files end in `.csv` or `.json` and are UTF-8. CSV rows with differing column counts, or JSON objects with differing keys, fail the start (exit 1).
- CSV values are strings (compare with strings in `.where()`); JSON keeps types. Without a header, columns are `_0`, `_1`, ... `type: items` is an inline list.

| Access | Result |
|---|---|
| `samples.users` | `Sample`, loaded once at start |
| `.pick()` / `.pick(default)` | Uniform random `Row`; an empty sample raises unless a default is given. |
| `.pick_n(n)` | `n` rows with replacement. |
| `.weighted_pick(col)` / `.weighted_pick_n(col, n)` | Weighted by a numeric, non-negative column. |
| `.where(col=value, ...)` | New `Sample` of exact-match rows; O(rows) per call. |
| `len(s)`, `s[i]`, `s['col']`, `s.columns` | Size, row by index, the whole column as a list, column names. |
| `row.name`, `row[0]` | A `Row` is an immutable tuple with named access; columns named `count` or `index` return tuple methods and cannot be read by name. |

### Render context

| Name | Value |
|---|---|
| `timestamp` | Timezone-aware `datetime` of this timestamp. |
| `tags` | Tuple of the producing input's tags in config order (`'x' in tags`). |
| `params`, `vars`, `samples` | `event.template.params`, this template's `vars`, datasets. |
| `locals` / `shared` / `globals` | State: per template / per generator / per process. |
| `module` | Python modules (below). |
| `dispatch` | Flow control (below). |
| `subprocess` | `subprocess.run(command, cwd=None, env=None, timeout=None)`. |

### State

`get(key, default=None)`, `set(key, value)`, `pop(key, default=None)`, `update(dict)`, `clear()`, `as_dict()` (shallow copy), `state[key]`.

- `get` returns the stored object: mutating a list or dict in place changes the state without `set`.
- State lives for the whole run.
- `globals` is shared by every generator of the process and thread-safe per call; compound updates go between `globals.acquire()` and `globals.release()`.

### Output of a render

- One render is one event. A multi-line render is one event: `plain` writes it as several lines, `json` collapses it to one.
- An empty render writes an empty line with `plain` and a format error with `json`; only `dispatch.drop()` emits nothing.

### Dispatch

| Call | Effect |
|---|---|
| `dispatch.drop()` | No event for this timestamp; in `mode: all` the output of every other template of that timestamp is discarded too. |
| `dispatch.next(max_repicks=64)` | Discard output, pick templates again for the same timestamp; more than `max_repicks` is an error. |
| `dispatch.exhaust()` | End the event stage; the current batch is still written. |

### module

`module.<name>` imports a bundled module first, then any installed or standard-library module, cached: `module.math`, `module.random`, `module.datetime`, `module.heapq`, `module.bisect`, `module.json`, `module.hashlib`, `module.uuid`, `module.ipaddress`, `module.numpy`, ...

**`module.rand`** (the fastest source of random values):

| Function | Notes |
|---|---|
| `choice(seq)`, `choices(seq, n)`, `shuffle(seq)` | `shuffle` returns a new list (or str). |
| `weighted_choice(items, weights)` / `weighted_choice({item: w})` | |
| `weighted_choices(items, weights, n)` / `weighted_choices({item: w}, n)` | |
| `chance(p)` | True with probability `p` in 0..1 (not percent). |
| `number.integer(a, b)`, `number.floating(a, b)` | Inclusive. |
| `number.gauss(mu, sigma)`, `number.lognormal(mu, sigma)` | `lognormal` mu/sigma are of the underlying normal: median = `exp(mu)`. |
| `number.exponential(lambd)` | `lambd` = 1 / mean. |
| `number.pareto(alpha, xmin=1.0)`, `number.triangular(low, high, mode)`, `number.clamp(v, lo, hi)` | |
| `string.letters(n)`, `letters_lowercase`, `letters_uppercase`, `digits`, `hex`, `punctuation` | |
| `string.pattern('%A{3}-%d{4}')` | `%a %A %l %d %n %h %H %p %w %%`, `{N}` repeats. |
| `network.ip_v4()`, `ip_v4_private()`, `ip_v4_private_a/b/c()`, `ip_v4_in_subnet(cidr)` | `ip_v4_in_subnet` excludes the network and broadcast addresses. |
| `network.ip_v4_public()` | Real routable addresses, never documentation ranges. |
| `network.ip_v6()`, `ip_v6_global()`, `ip_v6_link_local()`, `ip_v6_ula()` | |
| `network.mac(oui=None, vendor=None)` | `vendor`: apple aruba broadcom cisco dell fortinet hp huawei ibm intel juniper lenovo microsoft mikrotik netgear paloalto samsung tplink ubiquiti vmware. |
| `crypto.uuid4()`, `md5()`, `sha1()`, `sha256()` | Random hex digests. |
| `datetime.timestamp(start, end)` | Random datetime in range. |

`module.faker.locale['en_US']` returns a cached `Faker`; `module.mimesis.locale['en']` a cached mimesis `Generic` (also `module.mimesis.enums`, `module.mimesis.random`). Unknown locales raise. Both are much slower than `rand`.

### Jinja environment

- Extensions `do` (`{% do list.append(x) %}`) and `loopcontrols` (`{% break %}`, `{% continue %}`); `range`, `namespace()`, `//`, `%` as in Python.
- Macros: `{% from 'templates/_base.json.jinja' import render with context %}`; paths relative to the generator root.
- An undefined name renders as an empty string silently; `tojson` of an undefined value raises "Object of type Undefined is not JSON serializable". No autoescape; the single trailing newline is stripped; `{%- -%}` trims whitespace.
- `{{ obj | tojson }}` sorts keys, escapes `<` `>` `&` `'` as `<` `>` `&` `'`, escapes every non-ASCII character (`é` as `é`), and separates with `", "` and `": "`. The result decodes to the original text.
- Native JSON in its own key order, compact and UTF-8: `{{ module.json.dumps(obj, ensure_ascii=False, separators=(',', ':')) }}` with the `plain` formatter.
- `loop.index0` inside `{% for x in xs if cond %}` counts only matching items.
- Attribute access tries the Python attribute first: `d.pop`, `d.items`, `d.keys`, `d.get`, `d.update` on a dict are methods; data keys that clash are read as `d['pop']`.

## Output plugins and formatters

- Formatters (2.8.0): `plain` (the default: rendered text as is), `json`, `json-batch`, `template`, `template-batch` (`template` inline or `template_path`, rendering `event` / `events`), `eventum-http-input`. *Next release*: `syslog`, and `framing: octet_counting` for tcp.
- `json` validates each event and normalises whitespace only: key order, number literals (`1.50` stays `1.50`) and string escapes are kept; output is one line with a space after `,` and `:`, so compact native JSON is not reproduced. `indent` defaults to 0. An event that is not valid JSON is logged and not written.
- `file`: `path` (relative to the generator directory, parent directories created), `write_mode` (`append` default | `overwrite`), `encoding` (utf_8), `separator` (default the OS line separator: CRLF on Windows), `flush_interval` (1 s), `file_mode` (640).
- Other outputs: `stdout` (`stream: stdout | stderr`), `tcp`, `udp`, `http`, `opensearch`, `clickhouse`, `kafka`.
