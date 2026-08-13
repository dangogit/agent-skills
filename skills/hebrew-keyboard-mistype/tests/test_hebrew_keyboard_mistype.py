from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
SKILL = ROOT / "skills/hebrew-keyboard-mistype"
DECODER = SKILL / "scripts/decode.py"
HOOK = SKILL / "scripts/hook.py"
SPEC = importlib.util.spec_from_file_location("keyboard_decoder", DECODER)
assert SPEC and SPEC.loader
decoder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(decoder)


class HebrewKeyboardMistypeTests(unittest.TestCase):
    def test_documented_examples_decode_exactly(self) -> None:
        examples = {
            "יקךךם": "hello",
            "ביקבל איןד דברןפא": "check this script",
            "כןס איןד נוע": "fix this bug",
            "יקךךםת בשמ טםו אקךך צק ש חםלק?": "hello, can you tell me a joke?",
        }
        for typed, intended in examples.items():
            with self.subTest(typed=typed):
                self.assertEqual(decoder.hebrew_to_english(typed), intended)
                self.assertEqual(decoder.english_to_hebrew(intended), typed)

    def test_mixed_and_unmapped_characters_are_preserved(self) -> None:
        self.assertEqual(
            decoder.hebrew_to_english("please ביקבל איןד דברןפא 123 🚀"),
            "please check this script 123 🚀",
        )

    def test_cli_supports_stdin(self) -> None:
        result = subprocess.run(
            [sys.executable, str(DECODER), "-"],
            input="יקךךם\n",
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "hello\n")

    def test_hook_is_silent_without_hebrew(self) -> None:
        result = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps({"prompt": "check this script"}),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")

    def test_hook_emits_decoded_candidate(self) -> None:
        result = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps({"prompt": "ביקבל איןד דברןפא"}),
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        context = output["hookSpecificOutput"]["additionalContext"]
        self.assertIn("check this script", context)
        self.assertEqual(output["hookSpecificOutput"]["hookEventName"], "UserPromptSubmit")

    def test_hook_fails_open_on_malformed_input(self) -> None:
        for payload in ("not-json", "[]"):
            with self.subTest(payload=payload):
                result = subprocess.run(
                    [sys.executable, str(HOOK)],
                    input=payload,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, "")


if __name__ == "__main__":
    unittest.main()
