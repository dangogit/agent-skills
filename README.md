# Daniel's Agent Skills

Practical, privacy-first skills for AI coding agents. Each skill solves a real
workflow, ships with deterministic helpers where reliability matters, and is
tested with synthetic data only.

## Skills

| Skill | What it does |
|---|---|
| [`invoice-pack`](skills/invoice-pack/) | Collects invoices from email, reconciles Israeli card statements, removes duplicates, and builds a private local report. |

## Install

Clone the repository, then copy or symlink the skill folder into the skill
directory used by your agent.

### Codex

```bash
git clone https://github.com/dangogit/agent-skills.git
mkdir -p ~/.codex/skills
ln -s "$(pwd)/agent-skills/skills/invoice-pack" ~/.codex/skills/invoice-pack
```

### Claude Code

```bash
git clone https://github.com/dangogit/agent-skills.git
mkdir -p ~/.claude/skills
ln -s "$(pwd)/agent-skills/skills/invoice-pack" ~/.claude/skills/invoice-pack
```

Then ask:

```text
Use invoice-pack to collect my July invoices from Gmail and reconcile them
against the card statements in Downloads. Keep everything local.
```

## Try the synthetic demo

```bash
python3 skills/invoice-pack/scripts/invoice_pack.py \
  --documents examples/synthetic-input/documents \
  --statements examples/synthetic-input/statements \
  --output /tmp/invoice-pack-demo

open /tmp/invoice-pack-demo/report.html
```

Expected result: two verified matches and one missing invoice. All names,
amounts, card suffixes, and document identifiers in the demo are synthetic.

## פרטיות לפני הכול

הסקילים בריפו עובדים מקומית כברירת מחדל. `invoice-pack` לא מעלה חשבוניות,
לא משנה הודעות במייל ולא שולח מסמכים לשירות OCR. הדוגמאות והבדיקות מכילות
מידע סינתטי בלבד.

## Invoice Pack בעברית

הסקיל מחפש חשבוניות וקבלות בחשבונות המייל המחוברים, מוריד אותן לתיקיית עבודה
מקומית, מסיר כפילויות ומתאים אותן לפירוטי אשראי של Max, ישראכרט, כאל ולאומי.
בסיום מתקבלת תיקייה עם דוח HTML בעברית, CSV, מסמכים שנמצאה להם התאמה,
מסמכים לבדיקה ורשימת חשבוניות חסרות.

ללא פירוט אשראי הסקיל עדיין אוסף ומסדר מסמכים, אבל אינו טוען שהאיסוף מלא.
הדוח מסייע בארגון ובהתאמה ואינו מהווה ייעוץ מס או תחליף לבדיקה של רואה חשבון.

## Repository principles

- Local-first and read-only around personal data.
- Fail closed when evidence is ambiguous.
- No real invoices, credentials, or customer identifiers in Git.
- One self-contained folder per skill.
- Small deterministic scripts for fragile operations.

## License

MIT
