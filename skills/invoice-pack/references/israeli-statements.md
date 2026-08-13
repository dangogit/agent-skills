# Israeli card statements

## Supported inputs

The bundled parser reads `.xlsx` and `.csv` files and detects a header row from
common Hebrew and English aliases.

Recognized concepts include:

| Concept | Common headers |
|---|---|
| Transaction date | תאריך עסקה, תאריך רכישה, תאריך, Transaction date |
| Merchant | שם בית העסק, שם בית עסק, בית עסק, Merchant, Vendor |
| Charged amount | סכום חיוב, סכום החיוב, Charge amount, Amount |
| Charged currency | מטבע חיוב, מטבע, Charge currency |
| Original amount | סכום עסקה מקורי, סכום עסקה, Original amount |
| Original currency | מטבע עסקה מקורי, מטבע עסקה, Original currency |
| Card suffix | כרטיס, 4 ספרות אחרונות, Last 4, Card |

The parser checks every workbook sheet and scans the first 25 rows for the best
header candidate. It also looks for a four-digit card suffix in the filename and
the rows above the header.

## Matching dates

Issuer exports may show purchase date, processing date, or billing date.
Invoices may be issued one or more days later. Date proximity is supporting
evidence, not a substitute for amount, currency, and merchant identity.

## Foreign currency

Prefer original transaction amount and currency when the statement exposes
them. The ILS charge reflects card-network conversion and may not appear on the
vendor document.

## Unknown layouts

If no header is detected:

1. Open the workbook read-only.
2. Identify the sheet and exact header row.
3. Export that sheet to UTF-8 CSV without modifying the original.
4. Use recognizable column names from the table above.
5. Run the pack builder again and report the conversion.

Never guess positional columns from a workbook that was not detected.
