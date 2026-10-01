# Generator conventions

## Layout

```text
<name>/
    generator.yml
    README.md
    templates/        Jinja templates; one per record family, shared macros in templates/_macros.jinja
    samples/          CSV (with header) or JSON (array of objects)
    patterns/         time_patterns files
    output/           generated files; never shipped
```

- `<name>` is `<category>-<product>[-<stream>]`, lowercase, hyphen-separated (`network-bind9-query`, `identity-keycloak-admin`). The category is the source's function, taken from the prefixes already used in `generators/` of the catalog (`network`, `identity`, `proxy`, `vpn`, `database`, ...), never a vendor; a new category only when none fits.
- Every path inside the generator is relative; the directory is portable.
- The shipped `generator.yml` writes `output/events.json` with `write_mode: overwrite` and runs with `eventum generate --path generator.yml --id <name> --live-mode true` without parameters or secrets.
- `generator.yml` opens with a comment: source and version, output shape, daily volume and curve.
- Every `time_patterns` oscillator and every `cron` input states `start` and `end` explicitly (`end: never` when shipped), a `linspace` input a finite range, a `timer` its `start`; capture tooling bounds exactly these keys. Anchors are midnights with an offset. A pattern file opens with a comment giving its band and timestamps per day (actions, for populations whose actions write several records).

## Output shape

- ECS JSON, the default and the shape the Hub card describes best: the event mirrors the `sample_event.json` of the source's Elastic integration when one exists, otherwise a reasonable ECS shape; the native record goes to `event.original` as the source writes it, a multi-line message with its lines joined by `\n`. Top level `@timestamp`, `ecs.version`, `event.*`, `host.*`, `agent.*`; source data under its namespace (`winlog.*`, `nginx.*`); `related.*` always arrays; `event.sequence` only for sources that number their records, strictly increasing per host or source. Formatter `json`.
- Native records only, when the user feeds a parser: the line exactly as the source writes it, formatter `plain`; a native JSON record rendered with `module.json.dumps(obj, ensure_ascii=False, separators=(',', ':'))` to keep its key order and compactness. The catalog takes native JSON records, not native text lines.

## Parameters

- `event.template.params`: with a chain, `anomaly_mode: true` and `anomaly_interval_hours: 24` first; then the values users edit (host names, versions, domains). Names say the unit (`_hours`, `_count`).
- The template validates every parameter and sample on the first render, with the operation that will use the value (`module.ipaddress.ip_network`, a parse, a lookup) rather than a pattern, and stops on the first violation with one readable ERROR line:

  ```jinja
  {%- if shared.get('invalid') -%}{%- do dispatch.exhaust() -%}{%- endif -%}
  {%- macro invalid(message) -%}
    {%- do shared.set('invalid', message) -%}{%- do module.operator.getitem({}, message) -%}
  {%- endmacro -%}
  {%- if not shared.get('checked') -%}
    {%- if params.anomaly_interval_hours is not number or params.anomaly_interval_hours < 2 -%}
      {{- invalid('anomaly_interval_hours must be a number >= 2') -}}
    {%- endif -%}
    {%- do shared.set('checked', true) -%}
  {%- endif -%}
  ```

  An operation that can raise (`module.ipaddress.ip_network`) runs after storing its message, so a failure still ends the run after one error:

  ```jinja
  {%- do shared.set('invalid', 'vpn_subnet must be an IPv4 network') -%}
  {%- set net = module.ipaddress.ip_network(params.vpn_subnet) -%}
  {%- do shared.pop('invalid') -%}
  ```

- Top-level `${params.*}` / `${secrets.*}` appear only in the README's output override example, never in the shipped file.

## Samples

- Entities users replace with their own (hosts, accounts, servers, zones) live in `samples/`, sized by what the population needs. Large synthetic populations (thousands of clients) may be derived from parameters (prefix and count).
- Realistic but clearly fake: RFC 1918 or documentation addresses (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24; `rand.network.ip_v4_in_subnet`, never `ip_v4_public`), `example.com` / `example.test` domains, generic organisations (Contoso, Fabrikam), synthetic people. Never real personal data or secrets.
- Every sample column a template reads exists; column names avoid `count` and `index`.

## Source cardinality

- **Multi-source** (workstation agents, auditd, EDR, web servers, fleets): a pool of instances; correlations (session, process tree, sequence numbers) live per instance.
- **Single-source** (firewall, DNS resolver, load balancer, proxy, broker): usually one instance; correlations (flow, session, address pair) span the traffic through it.

## Templates

- One template per record family, named after what it produces (`query.json.jinja`, `syscall-execve.json.jinja`); `event.json.jinja` for a single one; aliases descriptive.
- Build the event as a dict and emit it with `{{ event | tojson }}`; build the native line as a string and put it in `event.original`.
- Every branch of every `if` emits a record; a stateful source runs from one dispatching template, not from `chance` over independent templates.
- State: `shared` for correlation across templates, `locals` for one template, `globals` only across generators.

## Speed

Templates render once per timestamp, so per-event work scales with the rate.

- `module.rand` for random values; faker and mimesis only where a fixed pool cannot serve, otherwise pre-generated into `samples/`.
- A carrier timestamp with nothing due drops before any import or setup: the drop path runs on most ticks. A large template costs time per render even when it drops on its first line, so the drop sits in a small head template that includes the body (`{% include 'templates/_body.jinja' %}`) only when a record is due.
- Pick directly (`rand.choice`, `weighted_pick`) instead of iterating; filtered pools computed once and kept in state; queues as heaps (`module.heapq`); actors looked up by index.

## Distributions

- Byte sizes and durations: `rand.number.lognormal` (median = exp(mu)); waiting times: `exponential`; metrics: `gauss`, clamped; `integer(a, b)` only for data that is actually uniform.
- Categorical outcomes (status codes, logon types, protocols): `rand.weighted_choice` with weights from vendor documentation or published data; a share that is a synthetic choice is named as such in the README.
- Time between an actor's actions: log-normal gaps from the actor's own rate; hourly volume comes from the inputs.

## README

Written for the consumer of the data, in this order and with these headings:

1. `# <Product> <stream>` and one paragraph: source and version, native format and output shape, estate size, what the data is for. Studio takes the title and summary from exactly these two.
2. `## Event Types` - table: native ID or class, meaning, share, category.
3. `## Volume and Timing` - records per day, hourly curve or schedule, populations.
4. `## Anomaly Chain`, with a chain - bold lead-ins: **Sequence**, **Linking fields**, **Episode shape**, **Recurrence** (interval from the actual start, window, start hours, behaviour at short intervals), **Variation**, **Background overlap** (what background contains of the chain), **Volume** (each episode adds its own records), **Detection idea**. Then: `anomaly_mode` defaults to `true`; `false` gives background only.
5. `## Parameters` - `### Event Parameters` (name, default, range, meaning), `### Sample Files` (what users edit for their own entities), `### Volume` (the input settings or pattern files that set volume and hours), `### Output Parameters` (an override example with `${params.*}` / `${secrets.*}`).
6. `## Usage` - the live command from the repository root; the finite batch window recipe (which pattern files and inputs get which `start` and `end`, with offsets); last line `Performance: about N records per second on <CPU>.` (records ÷ `cpu_s` of a one-day `capture.py one` run made while the host is otherwise idle, rounded down to two significant digits; the report's `speed` comes from parallel runs and understates it)
7. `## Sample Output` - one complete event copied byte for byte from a capture of the default configuration (`measure.py sample`).
8. `## Limitations` - only how the data differs from the real source: missing event types or fields, inferred values, synthetic rates, timing.
9. `## References` - vendor documentation, the matching Elastic integration.

The README never describes the generator's mechanism (inputs, ticks, queues, state, guards) or the validation process. Every number comes from the measurement report: background figures from the background runs, others from the default configuration; counts are ranges that contain every measured value (`class_share_pct_per_capture`, group `share_pct_per_capture`, `groups_per_day`, `hourly_pct_utc_per_capture`; `capture.py run --long-runs 3 --off-runs 4` gives more runs), rounded to two significant digits, outward only where rounding to nearest would exclude a measured value (7.81-7.89% is 7.8-7.9%, 32-100 refusals a day stay 32-100); a range resting on one or two captures widens each end by half its spread; or a value is stated as "about" with two significant digits; values the design fixes (delays, tolerances, limits) are stated as designed; shares take one decimal, two significant digits below 0.1%, and classes rarer than about one per day (`class_per_day`) are named as possibly absent from a short window.
