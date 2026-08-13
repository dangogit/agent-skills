#!/usr/bin/env python3
"""Decode text typed with the wrong Israeli Hebrew keyboard layout."""

from __future__ import annotations

import argparse
import sys


HEB_TO_EN = {
    "/": "q", "'": "w", "ק": "e", "ר": "r", "א": "t",
    "ט": "y", "ו": "u", "ן": "i", "ם": "o", "פ": "p",
    "ש": "a", "ד": "s", "ג": "d", "כ": "f", "ע": "g",
    "י": "h", "ח": "j", "ל": "k", "ך": "l", "ף": ";",
    ",": "'", "ז": "z", "ס": "x", "ב": "c", "ה": "v",
    "נ": "b", "מ": "n", "צ": "m", "ת": ",", "ץ": ".",
    ".": "/",
}
EN_TO_HEB = {english: hebrew for hebrew, english in HEB_TO_EN.items()}


def hebrew_to_english(text: str) -> str:
    """Map Hebrew-layout characters to English keys."""
    return "".join(HEB_TO_EN.get(character, character) for character in text)


def english_to_hebrew(text: str) -> str:
    """Map English keys to Hebrew-layout characters."""
    return "".join(EN_TO_HEB.get(character.lower(), character) for character in text)


def cli(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Decode text typed with the wrong Hebrew or English keyboard layout."
    )
    parser.add_argument("text", nargs="+", help="Text to decode, or - to read standard input")
    parser.add_argument("--reverse", action="store_true", help="Convert English keys to Hebrew")
    args = parser.parse_args(argv)
    text = sys.stdin.read() if args.text == ["-"] else " ".join(args.text)
    decoded = english_to_hebrew(text) if args.reverse else hebrew_to_english(text)
    print(decoded, end="" if text.endswith("\n") else "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
