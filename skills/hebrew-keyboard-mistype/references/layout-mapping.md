# Israeli Hebrew keyboard mapping

The decoder maps a character to the key at the same physical QWERTY position.
It does not translate language or guess words.

| Hebrew | English | Hebrew | English | Hebrew | English |
|---|---|---|---|---|---|
| ק | e | ש | a | ז | z |
| ר | r | ד | s | ס | x |
| א | t | ג | d | ב | c |
| ט | y | כ | f | ה | v |
| ו | u | ע | g | נ | b |
| ן | i | י | h | מ | n |
| ם | o | ח | j | צ | m |
| פ | p | ל | k | ת | , |
| ף | ; | ך | l | ץ | . |
| / | q | ' | w | . | / |

The Hebrew layout swaps the comma and apostrophe positions. Generate examples
with `scripts/decode.py --reverse` instead of writing them by hand, especially
when punctuation is present.
