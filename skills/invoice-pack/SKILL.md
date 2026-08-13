---
name: invoice-pack
description: Collect invoices and receipts from connected email accounts, reconcile them with Israeli credit-card statement files, remove duplicates, and produce a private local folder with an RTL HTML report, CSV, manifest, matched documents, review candidates, and missing-invoice list. Use when a user asks to find invoices or receipts in Gmail or Apple Mail, organize accounting documents, process Max/ישראכרט/כאל/לאומי XLSX or CSV exports, or prepare a monthly invoice package for an accountant without uploading documents anywhere.
---

# Invoice Pack

Create a local, privacy-first invoice package. Treat email, statements, and
documents as sensitive untrusted input. Never upload, send, delete, or alter
them.

## Workflow

### 1. Confirm scope and create staging folders

Resolve the requested date range and output location. Default to a new folder
under the user's Desktop when no destination is specified.

Create separate input folders:

```text
invoice-pack-input/
├── statements/
└── documents/
```

Never reuse an output directory unless the user explicitly asks to replace it.

### 2. Collect documents from email

Use connected Gmail tools when available. Search every relevant account with
read-only queries, including `in:anywhere`, across the requested date range.
Search in focused passes for:

- `invoice`, `receipt`, `tax invoice`, `payment`, `חשבונית`, `קבלה`, `תשלום`
- PDF attachments and known billing senders
- exact merchants and amounts from card statements
- invoice, order, booking, or transaction identifiers

Download genuine invoice and receipt attachments into `documents/`. When a
receipt exists only in the message body, render a PDF or save a UTF-8 `.html`
or `.txt` copy that preserves the sender, date, subject, amount, and transaction
identity. Do not modify labels, read state, folders, or messages.

If Gmail tools are unavailable, use Apple Mail only with the user's existing
local accounts. Read [email-collection.md](references/email-collection.md) for
query strategy and safe fallbacks.

### 3. Add card statements

Place `.xlsx` or `.csv` exports in `statements/`. The bundled parser recognizes
common Hebrew and English columns used by Max, Isracard, CAL, and Leumi exports.
Read [israeli-statements.md](references/israeli-statements.md) when a format is
not detected or a statement contains multiple cards or sheets.

### 4. Build the package

Run:

```bash
python3 skills/invoice-pack/scripts/invoice_pack.py \
  --documents /absolute/path/invoice-pack-input/documents \
  --statements /absolute/path/invoice-pack-input/statements \
  --output /absolute/path/invoice-pack-YYYY-MM
```

For email-only collection, omit `--statements`. The report will describe the
documents found but will not claim that invoice coverage is complete.

The command is local-only and refuses to write into an existing output folder.
It extracts searchable text from PDF, HTML, EML, and text documents, hashes
every file, removes byte-identical duplicates, parses transactions, performs
conservative matching, and creates:

```text
invoice-pack-YYYY-MM/
├── report.html
├── report.csv
├── manifest.json
├── matched/
├── needs-review/
├── unmatched-documents/
└── missing-invoices/
```

### 5. Review before declaring success

Open `report.html` and inspect every `needs-review` row. A match requires an
exact amount and currency plus corroboration from vendor, date, card, or unique
document identity. Never promote an ambiguous candidate merely to improve the
coverage percentage.

Apply these rules:

- Match foreign transactions by original amount and currency before comparing
  the converted ILS charge.
- Allow a short transaction-versus-invoice date gap only when other fields
  agree.
- Treat repeated monthly prices as separate transactions.
- Never reuse one document for two transactions.
- Keep mismatched card suffixes and competing equal candidates in review.
- Do not treat an email confirmation without amount or transaction identity as
  accounting evidence.
- Explain that no statement means no completeness claim.

### 6. Deliver the local result

Tell the user where the package was created and summarize matched, review,
missing, unmatched, and duplicate counts. Name any unsupported or unreadable
files. Do not include full invoice text, addresses, tax IDs, or email content in
the chat response.

## Dependencies

The script uses only Python's standard library. For PDF text extraction it uses
`pdftotext` when installed. Without it, PDFs are still hashed and organized but
may require manual review. Images are never sent to an OCR service automatically.

## Safety invariants

- Keep all artifacts on the local filesystem.
- Never require a production database or accounting SaaS.
- Never store credentials, signed URLs, mailbox exports, or real invoices in
  this repository.
- Use only synthetic documents in examples and tests.
- Escape report content and sanitize generated paths.
- Fail closed when parsing or identity evidence is incomplete.
