---
name: research-source
description: Use when the user wants an Eventum generator or synthetic logs for a named product or log source and there is no format specification or sample records at hand - "research FortiGate traffic logs", "what does Keycloak log for admin events", "find the native format of Cisco ASA syslog". Establishes the native format, event catalog, fields, timing, limits and anomaly chain candidates from primary sources and writes a source brief. Not for users who already provide their own format or samples - that goes straight to create-generator.
---

# Research a log source

Establishes, from primary sources, everything a generator needs to imitate one log stream, and writes it as a source brief that `create-generator` builds from.

## Before starting

- Settle with the user: product and stream, version (default: the current supported one), transport and encoding, and what the data is for (which detections or dashboards). Ask only what cannot be decided from the request.
- Output goes to `.content-design/<name>/` in the project root; `<name>` is `<category>-<source>` (see `create-generator` conventions).
- The skill only reads the web and writes the brief; it changes nothing else.

## References

- `references/sources.md` - where facts come from, in order of authority, and the stop rules.
- `references/brief.md` - the structure of the brief.

## Process

1. **Identify the stream** - `vendor:product:stream`, version, transport and encoding. Check the official catalog for an existing generator of the same stream; if one exists, tell the user and propose extending it.
2. **Collect records** - for every event class the stream emits, a complete raw record of the chosen version, saved verbatim under `reference/`. An integration's test fixtures are the fastest complete source; the vendor reference confirms field meanings.
3. **Fill the brief** section by section. Frequencies, volumes and timing come from documentation or datasets where they exist; otherwise they are marked synthetic with the reason.
4. **Chain candidates** - build them only from documented records and from ordinary activity the source really produces, so that every step also occurs outside the chain.
5. **Hand over** - show the user the event classes, the recommended chain, and the gaps; with their agreement continue with `create-generator`.

## Rules

- No invented formats, fields or values: every record shape is backed by a saved raw record or a field-complete specification of the stated version.
- Inferred parts are named as inferred, with what they are inferred from.
- Encoding variants of one stream (CEF, KV, JSON) are one source; pick one per generator.
- Records in `reference/` are the published text byte for byte; anonymised values in them are kept as published.
