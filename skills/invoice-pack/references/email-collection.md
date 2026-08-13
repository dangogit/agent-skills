# Email collection

## Gmail

Search each connected account independently. Start with the requested date
range and use `in:anywhere` so archived mail is included.

Useful query families:

```text
in:anywhere after:2026/07/01 before:2026/08/01 has:attachment filename:pdf
in:anywhere after:2026/07/01 before:2026/08/01 (invoice OR receipt)
in:anywhere after:2026/07/01 before:2026/08/01 (חשבונית OR קבלה)
in:anywhere after:2026/07/01 before:2026/08/01 from:billing@example.com
```

Gmail date bounds are exclusive at `before:`. Expand the search slightly when
card settlement dates may differ from invoice dates.

Inspect the attachment or full receipt body. A sender or subject match alone is
not sufficient. Save only files that contain accounting evidence. Keep the
original filename when safe, prefixed with the message date if collisions occur.

## Apple Mail fallback

Use Apple Mail only when Gmail connectors are unavailable and the relevant
accounts are already synced locally. Search read-only across all accounts and
save attachments into the staging `documents/` directory. Do not mark messages,
move mail, or change account configuration.

## Body-only receipts

Some Israeli payment providers send an HTML receipt without an attachment.
Preserve these fields when rendering or saving it:

- sender and recipient account
- sent date and subject
- legal issuer or merchant
- amount and currency
- invoice, receipt, order, or transaction number
- card suffix when displayed

Do not add inferred values to the rendered document.
