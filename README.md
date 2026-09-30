# AI Plugins

Plugins that teach AI coding agents to work with [Eventum](https://eventum.run), the synthetic event generator. The repository is both the plugin and its marketplace, and supports Claude Code, Codex, Cursor and OpenCode.

Marketplace: `eventum-ai-plugins`. Plugin: `content-design`.

## Skills

| Skill | Use it for |
|---|---|
| `create-generator` | Building an Eventum generator for a log source: research of the native format, realistic background traffic on a daily curve, recurring anomaly episodes for detection testing, validation of the output and a README for the consumers of the data. |

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

Ask the agent in plain words, for example "create an Eventum generator for Keycloak admin events with a privilege-escalation scenario" or "make synthetic FortiGate traffic logs for testing our SIEM rules". In Claude Code the skill can also be called as `/content-design:create-generator`, in Codex as `$create-generator`.

## Versioning

The plugin version is the commit SHA: every merge into `master` is a release for all users. Manifests must not declare `version` - it would pin users to that version. `scripts/check-no-version.sh` checks this.

## Repository layout

```text
.claude-plugin/  .codex-plugin/  .cursor-plugin/  .opencode/  .agents/plugins/   harness adapters
assets/          plugin assets
scripts/         repository checks
skills/          skills: SKILL.md, references/, scripts/
```

## License

[Apache 2.0](LICENSE)
