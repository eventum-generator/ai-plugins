# Generator conventions

## Layout

```text
<name>/
    generator.yml
    README.md
    templates/        Jinja templates; shared macros in templates/_base.json.jinja or templates/macros/
    samples/          CSV (with header) or JSON (array of objects) data
    patterns/         time_patterns files
    output/           generated files; not part of the generator
```

- Name: `<category>-<source>`, lowercase, hyphen-separated (`network-fortigate`, `windows-security`, `web-nginx-access`). Categories used in the public Eventum content packs: `application`, `backup`, `cloud`, `database`, `email`, `identity`, `messaging`, `network`, `proxy`, `security`, `storage`, `virtualization`, `vpn`, `web`, `windows`.
- Every path inside the generator is relative; the directory must stay portable.
- The shipped `generator.yml` writes to a local file (`output/events.json`) with a fitting formatter and runs with `eventum generate --path generator.yml --id <id> --live-mode true` without any parameter or secret.

## Parameters

- Top-level `${params.*}` / `${secrets.*}` placeholders only for values users must override (hosts, URLs, tokens, credentials); secrets come from the Eventum keyring.
- `event.template.params` hold values users may edit in the file (host names, versions, and with a chain `anomaly_mode` and `anomaly_interval_hours`); the template validates their ranges.

## Samples

- All sample data lives in `samples/`, whatever its size; 50-100 items per file is the usual scale for hosts, users and processes, more when the rate needs a larger population.
- Realistic but clearly fake data: RFC 1918 or documentation addresses (192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24), `example.test` / `example.com` domains, generic company names (Contoso, Fabrikam), synthetic user names. Never real personal data.

## Source cardinality

- **Multi-source** (workstation agents, auditd, EDR, web access, fleets): a pool of dozens of instances; correlations (session, process tree, sequence numbers) live per instance.
- **Single-source** (firewall, DNS, load balancer, proxy, broker): usually one instance; correlations (flow, session, source/destination pair) span the traffic through it.

## Output shape

Native records are written as the source writes them, with the `plain` formatter (`json` when the native record is JSON). ECS JSON mirrors the `sample_event.json` of the source's Elastic integration when one exists, otherwise a reasonable inferred ECS shape:

- Top level: `@timestamp`, `ecs.version`, `event.*`, `host.*`, `agent.*`; source-specific data under its namespace (`winlog.*`, `auditd.*`, `nginx.*`).
- The native raw line or record goes to `event.original`.
- `related.*` fields are always arrays.
- `event.sequence` only for sources that publish sequence numbers; strictly increasing per host or source.

## Templates

- Name templates after what they produce (`syscall-execve.json.jinja`), or `event.json.jinja` for one template; aliases under `templates:` are descriptive (`access_success`).
- Macro imports include the `templates/` prefix: `{% from 'templates/_base.json.jinja' import render with context %}`.
- Build the event as a dict and emit it with `{{ event | tojson }}`; never wrap `tojson` output in quotes.
- State scopes: `shared` for correlation across templates, `locals` for one template, `globals` only across generators.

## Speed

Templates render once per timestamp, so per-event work scales with the rate.

- `module.rand` is the fastest source of random values; faker and mimesis cover names, addresses and products at a much higher cost - pre-generate such values into `samples/` when a fixed pool works.
- Pick directly (`rand.choice`, `sample.weighted_pick`) instead of iterating; precompute filtered pools once and keep them in state; keep the queue a heap (`module.heapq`) and look up actors by index, not by scanning.

## Distributions

Real data is skewed.

- Byte sizes and durations: `rand.number.lognormal` (median = exp(mu)); waiting times: `exponential`; metrics: `gauss`, clamped. Use `integer(a, b)` only for data that is actually uniform.
- Categorical outcomes (status codes, logon types, protocols): `rand.weighted_choice`, with weights from vendor documentation or published samples; say in the README when a share is a synthetic choice.
- Time between an actor's actions: log-normal gaps from the actor's own rate; the hourly volume comes from the input, not from the template.

## README

Sections, all written for the consumer of the data:

- Title and a one-line description of the source and format.
- Event types - a table of type, share, category.
- Volume and rhythm - records per day, hourly curve or schedule, populations.
- `## Anomaly Chain`, with a chain - sequence, linking fields, recurrence (interval from the actual start, window, start hours, behaviour at short intervals), variation, what background contains of the chain, detection idea, and that each episode adds its own records (chain-part counts about one per episode higher).
- Parameters - Event Parameters (`event.template.params` with defaults and ranges; the sample files users edit for their own actors and hosts, and the input settings or pattern files that set volume and hours) and Output Parameters (top-level placeholders as an override pattern).
- Usage - live command; how to run a finite batch window. Every command runs as written.
- Performance - one line with generation speed.
- Sample output - one complete event copied byte for byte, escapes kept, from a capture of the default configuration.
- Limitations - only how the data differs from the real source (missing event types or fields, inferred values, synthetic rates, timing such as "related records are seconds apart, not milliseconds").
- References - vendor documentation and the matching Elastic integration.

The README never describes the generator's mechanism (inputs, ticks, queues, template state, guards) or the validation process (captures, test runs, review rounds). Every number in it is measured on generated output of the default configuration, and a range covers every capture.
