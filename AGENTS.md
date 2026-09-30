# AGENTS.md - developing eventum-content-design

The plugin `eventum-content-design` in the marketplace `eventum-ai-plugins` holds skills that let AI coding agents design content for [Eventum](https://eventum.run): generators that stream realistic synthetic events for testing, demos and pipelines. Harnesses: Claude Code, Codex, Cursor, OpenCode. Installation is in `README.md`. Every merge into `master` is a release for all users.

## Layout

A skill lives in `skills/<name>/SKILL.md`; next to it `references/` (facts), `scripts/` (Python) and `assets/` (skeletons). The adapters `.claude-plugin/`, `.codex-plugin/plugin.json`, `.cursor-plugin/plugin.json`, `.agents/plugins/marketplace.json` and `.opencode/plugins/eventum-content-design.js` load `skills/` as a whole; a new skill needs no registration. The only automatic check is `scripts/check-no-version.sh`: a `version` field in a manifest freezes updates for users.

## Skill structure

- Frontmatter has `name` and `description`. The description says when the skill applies, lists triggers in the words users say, and ends with "Not for ..." when a neighbouring task needs to be excluded. It decides whether the skill is invoked; it does not retell the process.
- `SKILL.md` follows one outline: purpose, conditions to start, pointer to references, process, form of the result, rules. Section names fit the skill.
- `SKILL.md` holds judgement, order and rules; `references/` hold facts (APIs, formats, commands). References do not overlap each other or `SKILL.md`. Knowledge ships inside the skill, not as links to external pages.
- Skills are for any Eventum user: no assumptions about a particular repository layout, organisation or internal service. A skill states which files and systems it changes and which it only reads.
- The text is a distillate: facts, decisions, conditions. Each sentence carries knowledge the others do not. Formal, complete sentences; no filler, repetition or explanation of the obvious. Distillation removes words, not caveats.

## Eventum facts

Facts about Eventum in `references/` are verified against the Eventum source of the version they name (`github.com/eventum-generator/eventum`, package `eventum-generator`) - read the code, run it, never infer from names. When Eventum changes a plugin, a field or a default, update the reference and its version.

## Scripts

Python 3.9+ with the standard library only; they run on Linux, Windows and macOS, so skills do not rely on bash, sed or other unix tools. Paths in `SKILL.md` are written relative to the skill directory as `<skill dir>/scripts/...`; the harness provides the directory.

## Checking a skill

A subagent without the skill performs a real task (for example, a generator for a given source); its misses are the baseline. A subagent with the skill performs the same task; coverage is compared with the baseline. Then run `bash scripts/check-no-version.sh`.

## Process

Work on a branch `feat/<skill>` in a separate git worktree. Commits follow Conventional Commits (`feat(<skill>): ...`). Open a pull request into `master`; delete the branch after merge.
