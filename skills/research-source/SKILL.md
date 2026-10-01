---
name: research-source
description: Use when the user wants an Eventum generator or synthetic logs for a named product or log source and there is no format specification or sample records at hand - "research FortiGate traffic logs", "what does Keycloak log for admin events", "find the native format of Cisco ASA syslog". Not for users who already provide their own format or samples - that goes straight to create-generator.
---

# Research a log source

Establishes, from primary sources, everything a generator needs to imitate one log stream, and writes it as a source brief that `create-generator` builds from.

## Before starting

- Settle with the user: product and stream, version (default: the current supported one), transport and encoding, and what the data is for (detections, dashboards, load). Ask only what cannot be decided from the request.
- `<name>` is `<category>-<product>[-<stream>]` (`../create-generator/references/generator-rules.md`). Claim the work by creating `.content-design/<name>/` in the project root; if it already exists and the user did not hand this task to it, another agent owns it: stop and tell the user.
- The skill reads the web and writes only into `.content-design/<name>/`.

## References

- `references/sources.md` - where facts come from, in order of authority, and the stop rules.
- `references/brief.md` - the structure of the brief.

## Process

1. **Identify the stream** - `vendor:product:stream`, version, transport and encoding. Run the catalog check (brief section 2) now: an existing or in-progress generator of the same stream ends the research with a proposal to extend it.
2. **Read the vendor documentation** - find the official documentation of the chosen version (`references/sources.md` names what to look for) and read in full every part that governs the stream, not only the field tables. It is the basis for field meanings, value domains, which records one action writes and in what order, and which values change together. Integration fixtures and datasets supply raw records and fill what the documentation leaves out; they do not replace it.
3. **Collect records** - for every event class, a complete raw record of the chosen version, saved verbatim under `reference/`. An integration's test fixtures are the fastest complete source.
4. **Fill the brief** section by section. Frequencies, volumes and timing come from documentation or datasets where they exist; otherwise they are marked synthetic with the reason.
5. **Chain candidates** - when the source records activity a detection or alert rule targets, build them only from documented records and from ordinary activity the source really produces, so that every step also occurs outside the chain.
6. **Hand over** - show the user the event classes, the recommended chain, and the gaps; with their agreement continue with `create-generator`.
7. **Feedback** - `../using-content-design/references/feedback.md`.

## Rules

- No invented formats, fields or values: every record shape is backed by a saved raw record or a field-complete specification of the stated version.
- Inferred parts are named as inferred, with what they are inferred from.
- Encoding variants of one stream (CEF, KV, JSON) are one source; pick one per generator.
- Records in `reference/` are the published text byte for byte; anonymised values in them are kept as published.
