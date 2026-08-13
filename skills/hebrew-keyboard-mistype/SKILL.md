---
name: hebrew-keyboard-mistype
description: Recover messages typed with the wrong Hebrew or English keyboard layout. Use when Hebrew characters form layout gibberish in an English or technical request, or when Latin gibberish may have been intended as Hebrew. Decode locally, confirm a coherent interpretation in one short sentence, and continue with the recovered request.
license: MIT
compatibility: Works with Codex and Claude Code. Requires Python 3.9 or newer. No network access is used.
---

# Hebrew Keyboard Mistype

Recover a layout mistype without making the user type the request again. The
decoder maps each character to the key at the same physical position on the
standard Israeli Hebrew keyboard.

## When to Use

Suspect a layout mistake when one or more of these signals appear:

- Hebrew letters form no plausible Hebrew words in an English or technical
  conversation.
- Final-form letters appear in the middle of a word or repeat, such as `ךך`.
- A Hebrew-looking chunk appears beside code, a path, a URL, or English text.
- Latin text is gibberish where a Hebrew request would fit the conversation.

Grammatical Hebrew in a Hebrew conversation is ordinary Hebrew. Continue in
Hebrew without decoding it.

## Prerequisites

- Python 3.9 or newer.
- The absolute path of the installed `hebrew-keyboard-mistype` skill.

## Workflow

### 1. Decode with the bundled script

Run the suspected text through the deterministic decoder:

```bash
KEYBOARD_SKILL_DIR=/absolute/path/to/hebrew-keyboard-mistype
python3 "$KEYBOARD_SKILL_DIR/scripts/decode.py" "יקךךם"
```

For Latin characters typed while Hebrew was intended:

```bash
python3 "$KEYBOARD_SKILL_DIR/scripts/decode.py" "akuo" --reverse
```

The script preserves spaces, digits, emoji, and characters outside the mapping.
For mixed input, pass the complete message or only the suspicious chunk.

### 2. Validate the interpretation

Use the decoded text only when it forms a coherent request and fits the current
conversation. If both the original and decoded forms are plausible, ask one
short clarifying question. If neither is coherent, quote the decoded candidate
without acting on it.

### 3. Confirm and continue

Open with one short confirmation, then perform the recovered request in the
same response:

```text
קראתי את זה כ־"check this script" כי המקלדת הייתה על עברית.
```

Completion means the intended request was handled, not merely decoded.

## Output

Return one short interpretation sentence followed immediately by the response
to the recovered request. For an ambiguous candidate, return one short question
instead of acting on either interpretation.

## Examples

| Typed text | Decoded text |
|---|---|
| `יקךךם` | `hello` |
| `ביקבל איןד דברןפא` | `check this script` |
| `כןס איןד נוע` | `fix this bug` |
| `יקךךםת בשמ טםו אקךך צק ש חםלק?` | `hello, can you tell me a joke?` |

`תכתוב לי בעברית בבקשה` is valid Hebrew and must remain Hebrew.

## Resources

- For automatic detection on every Claude Code prompt, follow
  [claude-code-hook.md](references/claude-code-hook.md). The hook adds a candidate
  interpretation to the current prompt context, makes no network calls, and
  stores no prompt content.
- Read [layout-mapping.md](references/layout-mapping.md) only when checking a key,
  debugging punctuation, or adding another keyboard layout.
