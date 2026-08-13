#!/usr/bin/env python3
"""Claude Code UserPromptSubmit hook for Hebrew keyboard mistypes."""

from __future__ import annotations

import json
import sys
from pathlib import Path


HEBREW_START = 0x0590
HEBREW_END = 0x05FF


def contains_hebrew(text: str) -> bool:
    return any(HEBREW_START <= ord(character) <= HEBREW_END for character in text)


def cli() -> int:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return 0
    if not isinstance(payload, dict):
        return 0

    prompt = payload.get("prompt", "")
    if not isinstance(prompt, str) or not contains_hebrew(prompt):
        return 0

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        from decode import hebrew_to_english
    except ImportError:
        return 0

    decoded = hebrew_to_english(prompt)
    context = (
        "[hebrew-keyboard-mistype] The prompt contains Hebrew characters. "
        "If they do not form coherent Hebrew, consider this same-keyboard-position "
        f"English candidate: {decoded!r}. Use it only when it fits the conversation; "
        "otherwise treat the original as Hebrew."
    )
    output = {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": context,
        }
    }
    print(json.dumps(output, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
