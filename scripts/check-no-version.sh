#!/usr/bin/env bash
set -euo pipefail
# Fails when a plugin manifest declares an explicit "version".
# Claude Code uses the commit SHA as the plugin version only when the field
# is absent; an explicit version silently freezes updates for users.
# package.json is not checked: its "version" is unrelated to the plugin.
root="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
fail=0
check() {
  local file="$1"
  [ -f "$file" ] || return 0
  if grep -Eq '^[[:space:]]*"version"[[:space:]]*:' "$file"; then
    echo "ERROR: '$file' declares \"version\" - remove it (the version is the commit SHA)." >&2
    fail=1
  fi
}
check "$root/.claude-plugin/plugin.json"
check "$root/.claude-plugin/marketplace.json"
check "$root/.codex-plugin/plugin.json"
check "$root/.cursor-plugin/plugin.json"
check "$root/.agents/plugins/marketplace.json"
exit "$fail"
