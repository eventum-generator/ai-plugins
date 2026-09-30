"""Inject the content-design orientation at session start."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

MARKER = "CONTENT_DESIGN_ORIENTATION"


def build_context() -> Optional[str]:
    orientation = (
        Path(__file__).resolve().parent.parent
        / "skills"
        / "using-content-design"
        / "references"
        / "orientation.md"
    )
    try:
        content = orientation.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return f"<{MARKER}>\n{content}\n</{MARKER}>"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    harness = sys.argv[1].lower() if len(sys.argv) > 1 else "agent"
    context = build_context()
    if not context:
        return 0

    if harness == "cursor":
        payload = {"additional_context": context}
    else:
        payload = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            }
        }

    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
