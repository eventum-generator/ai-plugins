# AI Plugins

Plugins that teach AI coding agents to work with [Eventum](https://eventum.run), the synthetic event generator. The repository is both the plugin and its marketplace, and supports Claude Code, Codex, Cursor and OpenCode.

Marketplace: `eventum-ai-plugins`. Plugin: `content-design`.

## Skills

The skills form one pipeline, from a log source to a generator in the official catalog:

| Skill | Stage |
|---|---|
| `research-source` | Establishes the native format, event catalog, fields, timing, limits and anomaly scenarios of a log source from primary sources and writes a source brief. |
| `create-generator` | Designs and builds a generator from the brief or from the user's own format and samples: background traffic on a daily curve, recurring anomaly episodes, validation of the output, README. |
| `review-generator` | Independent acceptance review of a generator on fresh output, with a verdict tied to the reviewed files. |
| `publish-generator` | On request: submits a reviewed generator to [content-packs](https://github.com/eventum-generator/content-packs) and adds its card to the Eventum Hub. |
| `using-content-design` | Loaded at session start: tells the agent which skill fits the task and in what order. |

Start anywhere the material allows: with only a product name, with your own log samples, or with an existing generator to review. Publishing is optional.

The skills need Eventum installed (`uv tool install eventum-generator` or `pip install eventum-generator`, Python 3.14+) and Python 3.9+ for their helper scripts.

## Installation

### Claude Code

```text
/plugin marketplace add eventum-generator/ai-plugins
/plugin install content-design@eventum-ai-plugins
```

To receive updates automatically, register the marketplace in `~/.claude/settings.json` with `autoUpdate` (merge with existing keys):

```json
{
  "extraKnownMarketplaces": {
    "eventum-ai-plugins": {
      "source": { "source": "github", "repo": "eventum-generator/ai-plugins" },
      "autoUpdate": true
    }
  }
}
```

Claude Code checks for updates in the background after a session starts; `/reload-plugins` or a restart applies them. Manual update: `/plugin marketplace update eventum-ai-plugins`.

### Codex

```bash
codex plugin marketplace add https://github.com/eventum-generator/ai-plugins.git --ref master
```

Codex compares the installed commit with `master` and pulls new versions; `codex plugin marketplace upgrade` updates immediately. New skills are available in a new thread.

### OpenCode

Add the plugin to `opencode.json`:

```json
{ "plugin": ["content-design@git+https://github.com/eventum-generator/ai-plugins.git"] }
```

OpenCode does not update plugins by itself; remove `~/.cache/opencode/` and restart to get a new version.

### Cursor

Add the repository as a team marketplace (Dashboard → Plugins → Add Marketplace, Teams or Enterprise plan), then run `/add-plugin content-design` in the agent chat.

## Usage

Ask the agent in plain words, for example "create an Eventum generator for Keycloak admin events with a privilege-escalation scenario", "here are sample lines from our proxy, make a generator" or "review generators/web-nginx". Skills can also be called directly: `/content-design:<skill>` in Claude Code, `$<skill>` in Codex.

At session start the plugin adds a short orientation (which skill for which stage) through a local hook in Claude Code and Cursor and through the adapter in OpenCode; the hook reads a file from the plugin and touches nothing else. Claude Code may ask you to trust the hook after installation.

## Versioning

The plugin version is the commit SHA: every merge into `master` is a release for all users. Manifests must not declare `version` - it would pin users to that version. `scripts/check-no-version.sh` checks this.

## Repository layout

```text
.claude-plugin/  .codex-plugin/  .cursor-plugin/  .opencode/  .agents/plugins/   harness adapters
assets/          plugin assets
hooks/           session-start orientation for Claude Code and Cursor
scripts/         chain checker shared by the skills, repository checks
skills/          skills: SKILL.md, references/
```

## License

[Apache 2.0](LICENSE)
