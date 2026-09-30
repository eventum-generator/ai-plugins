# Source brief - structure

`.content-design/<name>/brief.md`, with raw records saved under `.content-design/<name>/reference/` (one file per event class, exactly as published; `sample_event.json` of the integration when one exists). Every claim carries its source reference `[n]`.

1. **Source** - vendor, product, component or stream; version; what the data is for (detections, dashboards, load); transport and encoding (syslog RFC 3164/5424, CEF, LEEF, JSON, Windows XML, plain text); how a record is framed; the output shape the generator will write (native line only, or ECS JSON with the native record in `event.original`).
2. **Catalog check** - existing generators of the same `vendor:product:stream` in `github.com/eventum-generator/content-packs` and the Eventum Hub; aliases, rebrands and other encodings of the same stream count as the same source.
3. **Event classes** - table: class id or name, meaning, reference record file, relative frequency with its basis (documented, measured in a dataset, or synthetic with reason), outcome variants (success, failure, reasons). Then the ordinary sequences: for each action the source records (logon, connection, request, job run), the classes it writes in order, the fields that link them and the typical delays between them.
4. **Fields** - table per class or shared: native field, meaning, type and format, value domain or pattern, ECS path (from the integration pipeline, or inferred - say which), how values arise (constant per host, per session, counter, random ID, derived).
5. **Time** - timestamp fields, clock (UTC or local, zone field), precision, ordering guarantees, delay between event time and write time.
6. **Entities** - who and what emits or appears (hosts, users, services, clients), single-source or multi-source, identifier formats (GUID layouts, session IDs, counters), realistic population sizes.
7. **Volume and rhythm** - typical records per entity and per day, hourly and weekly pattern, bursts, what runs on schedules.
8. **Limits and invariants** - lockout thresholds, session caps, rate limits, monotonic counters, uniqueness rules, lifecycles that open and close (session, object, lease).
9. **Anomaly chain candidates** - when the source records activity a detection or alert rule targets: 1-3 ordered sequences of documented records a rule fires on, with steps, linking fields, time window, which ordinary activity produces each step on its own, and detection idea; the recommended one marked. Otherwise "none" with the reason.
10. **Gaps and inferences** - what could not be confirmed, what is inferred and from what.
11. **References** - numbered list: URL, title, version, date read.
