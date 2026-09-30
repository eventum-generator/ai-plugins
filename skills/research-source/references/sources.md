# Where facts about a log source come from

In order of authority. Record the URL and the product version for every fact.

## Primary

- **Vendor documentation** of the chosen version. The log part goes by names such as log message reference, syslog or CEF/LEEF guide, event or audit reference, field dictionary, and is often a separate document per release. Version-specific pages beat "latest". Read:
  - the event or message catalog and the format guide: every class, its severity, its fields;
  - field descriptions with their value lists, units and formats;
  - status, reason and error code tables;
  - the logging and audit settings that decide what is written and their defaults;
  - the administration chapters on the processes that emit events (authentication, sessions, connections, policy evaluation, scheduled jobs, error handling): which events one action writes, in what order, and what links them.
- **Protocol and format standards** for how a record is framed: syslog RFC 5424 and RFC 3164 (header, priority, timestamp), RFC 5425/6587 (TCP framing), the CEF and LEEF specifications (header fields, escaping, extension keys), RFC 4180 for CSV.
- **Raw records from maintained integrations.** Elastic: `github.com/elastic/integrations`, `packages/<package>/data_stream/<stream>/`:
  - `_dev/test/pipeline/test-*.log` (or `.json`) - raw input lines as the source emits them; `*-expected.json` - the parsed result;
  - `sample_event.json` - one parsed event in the integration's ECS shape;
  - `fields/*.yml` - every field the integration produces, with types;
  - `elasticsearch/ingest_pipeline/*.yml` - how each native field maps to ECS.
  Other maintained parsers with test fixtures (SIEM normalizers, log-shipper plugins) serve the same purpose.
- **Published real datasets** of the source (for example OTRF Security-Datasets for Windows telemetry): real record shapes and co-occurrence of events.

## Supporting

- **Detection content** (for example SigmaHQ rules for the log source): which fields and values detections read - the basis for anomaly chain candidates. Not proof of a format.
- **Vendor knowledge-base articles and community posts with pasted records**: accepted for a record shape only when they show a complete raw record of the stated version.
- **Blogs and tutorials**: corroboration only.

## Stop rules

- An event class goes into the brief only with a complete raw record or a field-complete format specification; otherwise it is listed under gaps.
- Search stops when the primary sources above are exhausted for the chosen version; remaining unknowns are recorded as gaps, not guessed.
- Frequencies without a published basis are marked synthetic and justified by what the source is used for.
