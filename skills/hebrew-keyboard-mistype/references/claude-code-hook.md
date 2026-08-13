# Optional Claude Code hook

The skill can run without a hook. Use the hook only when the user wants every
prompt containing Hebrew characters to include a candidate keyboard-layout
interpretation.

Add this entry under `hooks` in `~/.claude/settings.json`, preserving the other
settings already in the file:

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/hebrew-keyboard-mistype/scripts/hook.py",
            "timeout": 5000
          }
        ]
      }
    ]
  }
}
```

Replace the command path with the installed skill's absolute path. The hook is
silent for prompts without Hebrew characters. For a prompt containing Hebrew,
it emits Claude Code `additionalContext` with the decoded candidate. Claude still
decides whether the original text is real Hebrew or a layout mistake.

Test the command before adding it to settings:

```bash
printf '%s' '{"prompt":"יקךךם"}' | python3 /absolute/path/to/hebrew-keyboard-mistype/scripts/hook.py
```

Remove the hook entry to disable automatic detection. The decoder and skill keep
working when invoked normally.
