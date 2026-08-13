from __future__ import annotations

import csv
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/invoice-pack/scripts/invoice_pack.py"
SPEC = importlib.util.spec_from_file_location("invoice_pack", SCRIPT)
assert SPEC and SPEC.loader
invoice_pack = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = invoice_pack
SPEC.loader.exec_module(invoice_pack)


def write_csv(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle).writerows(rows)


def xlsx_column(index: int) -> str:
    result = ""
    index += 1
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


def write_minimal_xlsx(path: Path, rows: list[list[str]]) -> None:
    row_xml = []
    for row_index, row in enumerate(rows, start=1):
        cells = []
        for column, value in enumerate(row):
            ref = f"{xlsx_column(column)}{row_index}"
            escaped = str(value).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escaped}</t></is></c>')
        row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
    sheet = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' \
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' \
            + "".join(row_xml) + '</sheetData></worksheet>'
    workbook = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' \
               '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" ' \
               'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">' \
               '<sheets><sheet name="עסקאות" sheetId="1" r:id="rId1"/></sheets></workbook>'
    rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' \
           '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' \
           '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>' \
           '</Relationships>'
    content_types = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' \
                    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' \
                    '<Default Extension="xml" ContentType="application/xml"/>' \
                    '</Types>'
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("xl/workbook.xml", workbook)
        archive.writestr("xl/_rels/workbook.xml.rels", rels)
        archive.writestr("xl/worksheets/sheet1.xml", sheet)


class InvoicePackTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.documents = self.base / "documents"
        self.statements = self.base / "statements"
        self.documents.mkdir()
        self.statements.mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_reconciles_ils_and_foreign_amounts_conservatively(self) -> None:
        (self.documents / "openai.txt").write_text(
            "Receipt\nInvoice number SYNTH-OPENAI-001\nDate paid July 8, 2026\n"
            "OpenAI ChatGPT\n₪310.00 paid\nMastercard - 2517\n", encoding="utf-8"
        )
        metricool = (
            "Invoice number SYNTH-METRICOOL-001\nJuly 12, 2026\nMetricool\n"
            "Monthly subscription 25.00 USD\nCard **** 7329\n"
        )
        (self.documents / "metricool.txt").write_text(metricool, encoding="utf-8")
        (self.documents / "metricool-copy.txt").write_text(metricool, encoding="utf-8")
        (self.documents / "unrelated.txt").write_text(
            "Receipt number SYNTH-OTHER-001\nJuly 3, 2026\nOther Shop\n99.00 ILS\n", encoding="utf-8"
        )
        write_csv(self.statements / "7329_07_2026.csv", [
            ["תאריך עסקה", "שם בית העסק", "סכום חיוב", "מטבע חיוב", "סכום עסקה מקורי", "מטבע עסקה מקורי", "כרטיס"],
            ["2026-07-08", "OPENAI CHATGPT", "310.00", "ILS", "", "", "2517"],
            ["2026-07-11", "METRICOOL.COM", "75.62", "ILS", "25.00", "USD", "7329"],
            ["2026-07-22", "VERCEL INC.", "62.24", "ILS", "20.00", "USD", "7329"],
        ])

        output = self.base / "invoice-pack-2026-07"
        manifest = invoice_pack.build_package(self.documents, self.statements, output, None, None)

        self.assertEqual(manifest["summary"]["matched"], 2)
        self.assertEqual(manifest["summary"]["missing"], 1)
        self.assertEqual(manifest["summary"]["duplicates"], 1)
        document_ids = [document["id"] for document in manifest["documents"]]
        self.assertEqual(len(document_ids), len(set(document_ids)))
        self.assertTrue((output / "report.html").is_file())
        self.assertTrue((output / "report.csv").is_file())
        self.assertTrue((output / "missing-invoices/missing.csv").is_file())
        self.assertEqual(len(list((output / "matched").rglob("*.txt"))), 2)
        self.assertEqual(len(list((output / "unmatched-documents").glob("*.txt"))), 1)
        report = (output / "report.html").read_text(encoding="utf-8")
        self.assertIn("חבילת חשבוניות", report)
        self.assertIn("VERCEL INC.", report)
        serialized = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
        self.assertNotIn("Receipt\n", json.dumps(serialized))

    def test_keeps_equal_candidates_in_review(self) -> None:
        for suffix in ("A", "B"):
            (self.documents / f"receipt-{suffix}.txt").write_text(
                f"Invoice number SYNTH-{suffix}-0001\nJuly 8, 2026\nExample Cloud\n20.00 USD\n",
                encoding="utf-8",
            )
        write_csv(self.statements / "statement.csv", [
            ["Date", "Merchant", "Charge amount", "Charge currency", "Original amount", "Original currency"],
            ["2026-07-08", "EXAMPLE CLOUD", "65.00", "ILS", "20.00", "USD"],
        ])
        output = self.base / "out"
        manifest = invoice_pack.build_package(self.documents, self.statements, output, None, None)
        self.assertEqual(manifest["summary"]["matched"], 0)
        self.assertEqual(manifest["summary"]["needsReview"], 1)

    def test_email_only_mode_does_not_claim_completeness(self) -> None:
        content = "Receipt number SYNTH-0001\nExample Vendor\n50.00 ILS\n"
        (self.documents / "one.txt").write_text(content, encoding="utf-8")
        (self.documents / "duplicate.txt").write_text(content, encoding="utf-8")
        output = self.base / "email-only"
        manifest = invoice_pack.build_package(self.documents, None, output, None, None)
        self.assertEqual(manifest["mode"], "email-only")
        self.assertEqual(manifest["summary"]["duplicates"], 1)
        self.assertEqual(len(list((output / "collected").glob("*.txt"))), 1)
        self.assertIn("אי אפשר לקבוע", (output / "report.html").read_text(encoding="utf-8"))

    def test_parses_minimal_hebrew_xlsx(self) -> None:
        workbook = self.statements / "5584_07_2026.xlsx"
        write_minimal_xlsx(workbook, [
            ["כרטיס 5584"],
            ["תאריך רכישה", "שם בית עסק", "סכום חיוב", "מטבע חיוב"],
            ["21/07/2026", "ספק לדוגמה", "116.82", "₪"],
        ])
        transactions, warnings = invoice_pack.load_transactions(self.statements, None, None)
        self.assertEqual(warnings, [])
        self.assertEqual(len(transactions), 1)
        self.assertEqual(transactions[0].card, "5584")
        self.assertEqual(transactions[0].currency, "ILS")

    def test_refuses_existing_output_and_escapes_report_values(self) -> None:
        (self.documents / "receipt.txt").write_text(
            "Invoice number SYNTH-0001\nJuly 8, 2026\n<script>alert(1)</script>\n10.00 ILS\n", encoding="utf-8"
        )
        write_csv(self.statements / "statement.csv", [
            ["Date", "Merchant", "Amount", "Currency"],
            ["2026-07-08", "<script>alert(1)</script>", "10.00", "ILS"],
        ])
        output = self.base / "safe-output"
        invoice_pack.build_package(self.documents, self.statements, output, None, None)
        report = (output / "report.html").read_text(encoding="utf-8")
        self.assertIn("&lt;script&gt;", report)
        self.assertNotIn("<script>alert(1)</script>", report)
        with self.assertRaises(FileExistsError):
            invoice_pack.build_package(self.documents, self.statements, output, None, None)

    def test_public_demo_runs_through_cli(self) -> None:
        output = self.base / "public-demo"
        result = subprocess.run(
            [sys.executable, str(SCRIPT),
             "--documents", str(ROOT / "examples/synthetic-input/documents"),
             "--statements", str(ROOT / "examples/synthetic-input/statements"),
             "--output", str(output)],
            check=False, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["matched"], 2)
        self.assertEqual(summary["missing"], 1)

    def test_image_filename_evidence_never_auto_matches_without_ocr(self) -> None:
        (self.documents / "example-cloud 20.00 USD 2026-07-08.jpg").write_bytes(b"synthetic image bytes")
        write_csv(self.statements / "statement.csv", [
            ["Date", "Merchant", "Charge amount", "Charge currency", "Original amount", "Original currency"],
            ["2026-07-08", "EXAMPLE CLOUD", "65.00", "ILS", "20.00", "USD"],
        ])
        output = self.base / "image-review"
        manifest = invoice_pack.build_package(self.documents, self.statements, output, None, None)
        self.assertEqual(manifest["summary"]["matched"], 0)
        self.assertEqual(manifest["summary"]["needsReview"], 1)
        self.assertIn("no OCR", manifest["transactions"][0]["warning"])


if __name__ == "__main__":
    unittest.main()
