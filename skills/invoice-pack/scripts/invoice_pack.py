#!/usr/bin/env python3
"""Build a private local invoice package from documents and card statements.

The command performs no network calls and never modifies its inputs.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
from typing import Iterable, Iterator, Optional
from xml.etree import ElementTree as ET

VERSION = "0.1.0"
AUTO_MATCH_SCORE = 10
AMBIGUITY_MARGIN = 2
SUPPORTED_DOCUMENTS = {".pdf", ".txt", ".html", ".htm", ".eml", ".png", ".jpg", ".jpeg", ".webp"}
SUPPORTED_STATEMENTS = {".xlsx", ".csv"}
EXCEL_EPOCH = date(1899, 12, 30)

CURRENCY_ALIASES = {
    "₪": "ILS", "ILS": "ILS", "NIS": "ILS", "שח": "ILS", "שקל": "ILS",
    "$": "USD", "USD": "USD", "US$": "USD",
    "€": "EUR", "EUR": "EUR",
    "£": "GBP", "GBP": "GBP",
    "฿": "THB", "THB": "THB",
    "₱": "PHP", "PHP": "PHP",
}

STOPWORDS = {
    "invoice", "receipt", "payment", "paid", "subscription", "monthly", "total",
    "ltd", "llc", "inc", "com", "www", "the", "and", "from", "card", "credit",
    "חשבונית", "קבלה", "תשלום", "שולם", "סכום", "מסמך", "בעמ", "כרטיס",
}


@dataclass
class Transaction:
    id: str
    date: date
    vendor: str
    amount: Decimal
    currency: str
    original_amount: Optional[Decimal]
    original_currency: Optional[str]
    card: Optional[str]
    source_file: str
    source_sheet: str
    source_row: int


@dataclass
class Document:
    id: str
    path: Path
    name: str
    sha256: str
    text: str
    amounts: set[tuple[str, Decimal]] = field(default_factory=set)
    dates: set[date] = field(default_factory=set)
    cards: set[str] = field(default_factory=set)
    identifiers: set[str] = field(default_factory=set)
    duplicate_of: Optional[str] = None
    extraction_warning: Optional[str] = None
    output_path: Optional[str] = None


@dataclass
class MatchResult:
    transaction: Transaction
    status: str
    document: Optional[Document]
    score: int
    reasons: list[str]
    warning: Optional[str] = None
    output_path: Optional[str] = None


@dataclass(frozen=True)
class HtmlCell:
    value: str


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())

    def text(self) -> str:
        return "\n".join(self.parts)


def normalize_space(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_text(value: object) -> str:
    text = unicodedata.normalize("NFKC", normalize_space(value)).casefold()
    return re.sub(r"[^\w₪$€£฿₱]+", " ", text, flags=re.UNICODE).strip()


def normalize_currency(value: object, default: str = "ILS") -> str:
    raw = normalize_space(value).upper().replace('"', "").replace("'", "")
    compact = raw.replace(" ", "")
    return CURRENCY_ALIASES.get(raw, CURRENCY_ALIASES.get(compact, compact or default))


def parse_decimal(value: object) -> Optional[Decimal]:
    raw = normalize_space(value)
    if not raw:
        return None
    raw = raw.replace("\u00a0", "").replace(" ", "")
    raw = re.sub(r"[^0-9,().+-]", "", raw)
    if raw.startswith("(") and raw.endswith(")"):
        raw = "-" + raw[1:-1]
    if "," in raw and "." not in raw:
        tail = raw.rsplit(",", 1)[-1]
        raw = raw.replace(",", ".") if len(tail) in (1, 2) else raw.replace(",", "")
    else:
        raw = raw.replace(",", "")
    try:
        return Decimal(raw).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def parse_date(value: object) -> Optional[date]:
    raw = normalize_space(value)
    if not raw:
        return None
    if re.fullmatch(r"\d+(?:\.\d+)?", raw):
        serial = float(raw)
        if 20_000 < serial < 80_000:
            return EXCEL_EPOCH + timedelta(days=int(serial))
    formats = (
        "%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y",
        "%d-%m-%y", "%d/%m/%y", "%d.%m.%y", "%m/%d/%Y",
        "%B %d, %Y", "%b %d, %Y", "%d %B %Y", "%d %b %Y",
    )
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            pass
    return None


def safe_name(value: str, fallback: str = "document") -> str:
    value = unicodedata.normalize("NFKC", value)
    value = re.sub(r"[\\/:*?\"<>|\x00-\x1f]+", "-", value)
    value = re.sub(r"\s+", " ", value).strip(" .-")
    return (value[:120] or fallback)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iter_safe_files(root: Path, suffixes: set[str]) -> Iterator[Path]:
    root = root.resolve()
    for path in sorted(root.rglob("*")):
        if path.is_symlink() or not path.is_file() or path.suffix.lower() not in suffixes:
            continue
        try:
            path.resolve().relative_to(root)
        except ValueError:
            continue
        yield path


def decode_text(data: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1255", "windows-1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            pass
    return data.decode("utf-8", errors="replace")


def strip_html(value: str) -> str:
    parser = TextExtractor()
    parser.feed(value)
    return parser.text()


def extract_document_text(path: Path) -> tuple[str, Optional[str]]:
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        executable = shutil.which("pdftotext")
        if not executable:
            return "", "PDF text extraction unavailable: install pdftotext"
        try:
            result = subprocess.run(
                [executable, "-layout", str(path), "-"],
                check=False, capture_output=True, timeout=30,
            )
            if result.returncode != 0:
                return "", "PDF text extraction failed"
            text = decode_text(result.stdout)
            return text, None if text.strip() else "PDF contains no extractable text"
        except (OSError, subprocess.TimeoutExpired):
            return "", "PDF text extraction failed"
    if suffix in {".html", ".htm"}:
        return strip_html(decode_text(path.read_bytes())), None
    if suffix == ".eml":
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        parts = [f"From: {message.get('from', '')}", f"To: {message.get('to', '')}",
                 f"Date: {message.get('date', '')}", f"Subject: {message.get('subject', '')}"]
        body = message.get_body(preferencelist=("plain", "html"))
        if body:
            payload = body.get_content()
            parts.append(strip_html(payload) if body.get_content_type() == "text/html" else payload)
        return "\n".join(parts), None
    if suffix == ".txt":
        return decode_text(path.read_bytes()), None
    return "", "Image requires local manual review; no OCR was performed"


def extract_amounts(text: str) -> set[tuple[str, Decimal]]:
    found: set[tuple[str, Decimal]] = set()
    token = r"(?:ILS|NIS|USD|US\$|EUR|GBP|THB|PHP|₪|\$|€|£|฿|₱)"
    number = r"-?\d{1,3}(?:[ ,]\d{3})*(?:[.,]\d{1,2})?|-?\d+(?:[.,]\d{1,2})?"
    for match in re.finditer(fr"(?P<currency>{token})\s*(?P<amount>{number})", text, re.I):
        amount = parse_decimal(match.group("amount"))
        if amount is not None:
            found.add((normalize_currency(match.group("currency")), amount))
    for match in re.finditer(fr"(?P<amount>{number})\s*(?P<currency>{token})(?!\w)", text, re.I):
        amount = parse_decimal(match.group("amount"))
        if amount is not None:
            found.add((normalize_currency(match.group("currency")), amount))
    return found


def extract_dates(text: str) -> set[date]:
    found: set[date] = set()
    patterns = (
        r"\b\d{4}-\d{1,2}-\d{1,2}\b",
        r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b",
        r"\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+\d{1,2},\s+\d{4}\b",
    )
    for pattern in patterns:
        for raw in re.findall(pattern, text, re.I):
            parsed = parse_date(raw)
            if parsed:
                found.add(parsed)
    return found


def extract_cards(text: str) -> set[str]:
    return set(re.findall(r"(?:\*{3,4}|•{3,4}|ending\s+in|card\s*[-:]?)\s*(\d{4})\b", text, re.I))


def extract_identifiers(text: str) -> set[str]:
    pattern = r"(?:invoice|receipt|transaction|order|booking|חשבונית|קבלה|עסקה)\s*(?:number|no\.?|#|מספר|:)?\s*([A-Z0-9][A-Z0-9_-]{4,})"
    return {match.upper() for match in re.findall(pattern, text, re.I)}


def load_documents(root: Path) -> list[Document]:
    documents: list[Document] = []
    first_by_hash: dict[str, str] = {}
    document_root = root.resolve()
    for path in iter_safe_files(document_root, SUPPORTED_DOCUMENTS):
        digest = sha256_file(path)
        text, warning = extract_document_text(path)
        searchable = f"{path.stem}\n{text}"
        duplicate_of = first_by_hash.get(digest)
        if duplicate_of is None:
            doc_id = f"doc_{digest[:12]}"
            first_by_hash[digest] = doc_id
        else:
            relative_name = path.relative_to(document_root).as_posix()
            suffix = hashlib.sha256(relative_name.encode("utf-8")).hexdigest()[:6]
            doc_id = f"doc_{digest[:12]}_{suffix}"
        documents.append(Document(
            id=doc_id,
            path=path,
            name=path.name,
            sha256=digest,
            text=searchable,
            amounts=extract_amounts(searchable),
            dates=extract_dates(searchable),
            cards=extract_cards(searchable),
            identifiers=extract_identifiers(searchable),
            duplicate_of=duplicate_of,
            extraction_warning=warning,
        ))
    return documents


def column_index(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference.upper())
    if not letters:
        return 0
    result = 0
    for char in letters.group(0):
        result = result * 26 + ord(char) - 64
    return result - 1


def xlsx_rows(path: Path) -> Iterator[tuple[str, list[list[str]]]]:
    ns = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
          "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
          "p": "http://schemas.openxmlformats.org/package/2006/relationships"}
    with zipfile.ZipFile(path) as archive:
        shared: list[str] = []
        if "xl/sharedStrings.xml" in archive.namelist():
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            for item in root.findall("m:si", ns):
                shared.append("".join(node.text or "" for node in item.iter() if node.tag.endswith("}t")))
        rel_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        relationships = {node.attrib["Id"]: node.attrib["Target"] for node in rel_root.findall("p:Relationship", ns)}
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        for sheet in workbook.findall("m:sheets/m:sheet", ns):
            name = sheet.attrib.get("name", "Sheet")
            rel_id = sheet.attrib.get(f"{{{ns['r']}}}id")
            target = relationships.get(rel_id or "", "")
            target = target.lstrip("/")
            if not target.startswith("xl/"):
                target = "xl/" + target
            sheet_root = ET.fromstring(archive.read(target))
            rows: list[list[str]] = []
            for row in sheet_root.findall(".//m:sheetData/m:row", ns):
                values: dict[int, str] = {}
                for cell in row.findall("m:c", ns):
                    index = column_index(cell.attrib.get("r", "A1"))
                    cell_type = cell.attrib.get("t")
                    value_node = cell.find("m:v", ns)
                    inline = cell.find("m:is", ns)
                    raw = value_node.text if value_node is not None else ""
                    if cell_type == "s" and raw:
                        raw = shared[int(raw)]
                    elif cell_type == "inlineStr" and inline is not None:
                        raw = "".join(node.text or "" for node in inline.iter() if node.tag.endswith("}t"))
                    values[index] = raw or ""
                width = max(values, default=-1) + 1
                rows.append([values.get(index, "") for index in range(width)])
            yield name, rows


def csv_rows(path: Path) -> list[list[str]]:
    text = decode_text(path.read_bytes())
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return [list(row) for row in csv.reader(text.splitlines(), dialect)]


def header_kind(value: object) -> Optional[str]:
    text = normalize_text(value)
    if not text:
        return None
    if any(term in text for term in ("סכום עסקה מקורי", "original amount", "transaction amount")) or text == "סכום עסקה":
        return "original_amount"
    if any(term in text for term in ("מטבע עסקה מקורי", "original currency", "transaction currency")) or text == "מטבע עסקה":
        return "original_currency"
    if any(term in text for term in ("תאריך עסקה", "תאריך רכישה", "transaction date", "purchase date")) or text == "תאריך" or text == "date":
        return "date"
    if any(term in text for term in ("שם בית העסק", "שם בית עסק", "בית עסק", "merchant", "vendor", "supplier")):
        return "vendor"
    if any(term in text for term in ("סכום חיוב", "סכום החיוב", "charge amount", "charged amount")) or text == "amount" or text == "סכום":
        return "amount"
    if any(term in text for term in ("מטבע חיוב", "charge currency", "charged currency")) or text == "currency" or text == "מטבע":
        return "currency"
    if any(term in text for term in ("4 ספרות", "ארבע ספרות", "last 4", "last four", "card", "כרטיס")):
        return "card"
    return None


def detect_header(rows: list[list[str]]) -> tuple[int, dict[str, int]]:
    best_index = -1
    best_map: dict[str, int] = {}
    best_score = -1
    for index, row in enumerate(rows[:25]):
        mapping: dict[str, int] = {}
        for column, value in enumerate(row):
            kind = header_kind(value)
            if kind and kind not in mapping:
                mapping[kind] = column
        score = sum(key in mapping for key in ("date", "vendor", "amount")) * 3 + len(mapping)
        if score > best_score:
            best_index, best_map, best_score = index, mapping, score
    if not all(key in best_map for key in ("date", "vendor", "amount")):
        raise ValueError("No supported transaction header row found")
    return best_index, best_map


def row_value(row: list[str], mapping: dict[str, int], key: str) -> str:
    index = mapping.get(key)
    return row[index] if index is not None and index < len(row) else ""


def infer_card(path: Path, rows: list[list[str]], header_index: int) -> Optional[str]:
    leading = re.match(r"(\d{4})(?:\D|$)", path.stem)
    if leading and not leading.group(1).startswith("20"):
        return leading.group(1)
    candidates = [" ".join(row) for row in rows[:header_index]] + [path.stem]
    for value in candidates:
        matches = [match for match in re.findall(r"(?<!\d)(\d{4})(?!\d)", value) if not match.startswith("20")]
        if matches:
            return matches[0]
    return None


def transactions_from_rows(path: Path, sheet: str, rows: list[list[str]]) -> list[Transaction]:
    header_index, mapping = detect_header(rows)
    inferred_card = infer_card(path, rows, header_index)
    transactions: list[Transaction] = []
    for row_number, row in enumerate(rows[header_index + 1:], start=header_index + 2):
        txn_date = parse_date(row_value(row, mapping, "date"))
        vendor = normalize_space(row_value(row, mapping, "vendor"))
        amount = parse_decimal(row_value(row, mapping, "amount"))
        if not txn_date or not vendor or amount is None or amount <= 0:
            continue
        currency = normalize_currency(row_value(row, mapping, "currency"), "ILS")
        original_amount = parse_decimal(row_value(row, mapping, "original_amount"))
        original_currency_raw = row_value(row, mapping, "original_currency")
        original_currency = normalize_currency(original_currency_raw, "") if original_currency_raw else None
        card_raw = row_value(row, mapping, "card")
        card_match = re.findall(r"(?<!\d)(\d{4})(?!\d)", card_raw)
        card = card_match[-1] if card_match else inferred_card
        identity = "|".join((path.name, sheet, str(row_number), txn_date.isoformat(), vendor,
                             str(amount), currency, card or ""))
        transactions.append(Transaction(
            id="txn_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12],
            date=txn_date, vendor=vendor, amount=amount, currency=currency,
            original_amount=original_amount,
            original_currency=original_currency,
            card=card, source_file=path.name, source_sheet=sheet, source_row=row_number,
        ))
    return transactions


def load_transactions(root: Path, from_date: Optional[date], to_date: Optional[date]) -> tuple[list[Transaction], list[str]]:
    transactions: list[Transaction] = []
    warnings: list[str] = []
    for path in iter_safe_files(root, SUPPORTED_STATEMENTS):
        try:
            sheets: Iterable[tuple[str, list[list[str]]]]
            sheets = [("CSV", csv_rows(path))] if path.suffix.lower() == ".csv" else xlsx_rows(path)
            found_in_file = 0
            for sheet, rows in sheets:
                try:
                    parsed = transactions_from_rows(path, sheet, rows)
                except ValueError:
                    continue
                found_in_file += len(parsed)
                transactions.extend(parsed)
            if found_in_file == 0:
                warnings.append(f"Unsupported or empty statement: {path.name}")
        except (OSError, zipfile.BadZipFile, ET.ParseError, KeyError, ValueError) as exc:
            warnings.append(f"Could not parse statement {path.name}: {type(exc).__name__}")
    if from_date:
        transactions = [txn for txn in transactions if txn.date >= from_date]
    if to_date:
        transactions = [txn for txn in transactions if txn.date <= to_date]
    transactions.sort(key=lambda txn: (txn.date, txn.vendor, txn.amount, txn.id))
    return transactions, warnings


def vendor_tokens(vendor: str) -> set[str]:
    return {token for token in normalize_text(vendor).split() if len(token) >= 3 and token not in STOPWORDS and not token.isdigit()}


def target_amounts(txn: Transaction) -> set[tuple[str, Decimal]]:
    values = {(txn.currency, txn.amount)}
    if txn.original_amount is not None and txn.original_currency:
        values.add((txn.original_currency, txn.original_amount))
    return values


def score_candidate(txn: Transaction, doc: Document) -> Optional[tuple[int, list[str]]]:
    exact_amounts = target_amounts(txn) & doc.amounts
    if not exact_amounts:
        return None
    score = 6
    original_pair = (
        (txn.original_currency, txn.original_amount)
        if txn.original_currency and txn.original_amount is not None else None
    )
    reasons = ["סכום ומטבע מקוריים זהים" if original_pair in exact_amounts else "סכום ומטבע זהים"]
    doc_text = normalize_text(doc.text)
    hits = sorted(token for token in vendor_tokens(txn.vendor) if token in doc_text)
    if hits:
        score += 3
        reasons.append("זהות ספק")
    if doc.dates:
        delta = min(abs((txn.date - candidate).days) for candidate in doc.dates)
        if delta <= 2:
            score += 3
            reasons.append("תאריך בטווח יומיים")
        elif delta <= 7:
            score += 2
            reasons.append("תאריך בטווח שבוע")
        elif delta <= 31:
            score += 1
            reasons.append("תאריך בטווח חודש")
    if doc.cards:
        if txn.card and txn.card in doc.cards:
            score += 3
            reasons.append("סיומת כרטיס")
        elif txn.card:
            return None
    if doc.identifiers:
        score += 1
        reasons.append("מזהה מסמך")
    return score, reasons


def match_transactions(transactions: list[Transaction], documents: list[Document]) -> list[MatchResult]:
    canonical_docs = [doc for doc in documents if doc.duplicate_of is None]
    ranked: dict[str, list[tuple[int, Document, list[str]]]] = {}
    for txn in transactions:
        candidates: list[tuple[int, Document, list[str]]] = []
        for doc in canonical_docs:
            scored = score_candidate(txn, doc)
            if scored:
                candidates.append((scored[0], doc, scored[1]))
        ranked[txn.id] = sorted(candidates, key=lambda item: (-item[0], item[1].name))

    proposals: list[tuple[int, int, Transaction, Document, list[str]]] = []
    for txn in transactions:
        candidates = ranked[txn.id]
        if not candidates:
            continue
        best_score, best_doc, reasons = candidates[0]
        margin = best_score - candidates[1][0] if len(candidates) > 1 else best_score
        proposals.append((best_score, margin, txn, best_doc, reasons))
    proposals.sort(key=lambda item: (-item[0], -item[1], item[2].id))

    claimed: set[str] = set()
    assigned: dict[str, MatchResult] = {}
    for score, margin, txn, doc, reasons in proposals:
        candidates = ranked[txn.id]
        ambiguous = len(candidates) > 1 and margin < AMBIGUITY_MARGIN
        if score >= AUTO_MATCH_SCORE and not ambiguous and doc.id not in claimed and not doc.extraction_warning:
            claimed.add(doc.id)
            assigned[txn.id] = MatchResult(txn, "matched", doc, score, reasons)
        else:
            warning = doc.extraction_warning or (
                "יש כמה מסמכים מועמדים" if ambiguous else (
                    "המסמך כבר הותאם לעסקה אחרת" if doc.id in claimed else "אין מספיק ראיות תומכות"
                )
            )
            assigned[txn.id] = MatchResult(txn, "needs-review", doc, score, reasons, warning)

    return [assigned.get(txn.id, MatchResult(txn, "missing", None, 0, [])) for txn in transactions]


def copy_unique(source: Path, directory: Path) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / safe_name(source.name)
    counter = 2
    while target.exists():
        target = directory / f"{safe_name(source.stem)}-{counter}{source.suffix.lower()}"
        counter += 1
    shutil.copy2(source, target)
    return target


def decimal_text(value: Optional[Decimal]) -> str:
    return "" if value is None else format(value, ".2f")


def write_csv_report(path: Path, results: list[MatchResult], collected: list[Document]) -> None:
    fields = ["status", "date", "vendor", "amount", "currency", "original_amount", "original_currency",
              "card", "document", "document_id", "score", "reasons", "warning", "output_path"]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for result in results:
            txn = result.transaction
            writer.writerow({
                "status": result.status, "date": txn.date.isoformat(), "vendor": txn.vendor,
                "amount": decimal_text(txn.amount), "currency": txn.currency,
                "original_amount": decimal_text(txn.original_amount), "original_currency": txn.original_currency or "",
                "card": txn.card or "", "document": result.document.name if result.document else "",
                "document_id": result.document.id if result.document else "", "score": result.score,
                "reasons": "; ".join(result.reasons), "warning": result.warning or "",
                "output_path": result.output_path or "",
            })
        for doc in collected:
            writer.writerow({"status": "collected", "document": doc.name, "document_id": doc.id,
                             "warning": doc.extraction_warning or "", "output_path": doc.output_path or ""})


def html_table(headers: list[str], rows: list[list[object]]) -> str:
    head = "".join(f"<th>{html.escape(header)}</th>" for header in headers)
    def render_cell(cell: object) -> str:
        return cell.value if isinstance(cell, HtmlCell) else html.escape(str(cell or ""))
    body = "".join("<tr>" + "".join(f"<td>{render_cell(cell)}</td>" for cell in row) + "</tr>" for row in rows)
    return f"<div class='table-wrap'><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>"


def document_link(output_path: Optional[str], label: str) -> HtmlCell | str:
    if not output_path:
        return label
    href = html.escape(output_path, quote=True)
    return HtmlCell(f'<a href="{href}"><bdi>{html.escape(label)}</bdi></a>')


def write_html_report(path: Path, results: list[MatchResult], documents: list[Document], warnings: list[str], email_only: bool) -> None:
    counts = {status: sum(result.status == status for result in results) for status in ("matched", "needs-review", "missing")}
    duplicate_count = sum(doc.duplicate_of is not None for doc in documents)
    unmatched = 0 if email_only else sum(
        doc.duplicate_of is None and all(result.document is not doc for result in results) for doc in documents
    )
    card_values = (
        ((sum(doc.duplicate_of is None for doc in documents), "מסמכים שנאספו"), (duplicate_count, "כפילויות"))
        if email_only else
        ((counts["matched"], "התאמות מאומתות"), (counts["needs-review"], "דורש בדיקה"),
         (counts["missing"], "חשבוניות חסרות"), (unmatched, "מסמכים ללא התאמה"), (duplicate_count, "כפילויות"))
    )
    cards = "".join(f"<div class='card'><strong>{value}</strong><span>{label}</span></div>" for value, label in card_values)
    sections: list[str] = []
    labels = {"matched": "נמצאה התאמה", "needs-review": "דורש בדיקה", "missing": "חסר מסמך"}
    for status in ("matched", "needs-review", "missing"):
        subset = [result for result in results if result.status == status]
        if not subset:
            continue
        rows = [[result.transaction.date.strftime("%d.%m.%Y"), HtmlCell(f"<bdi>{html.escape(result.transaction.vendor)}</bdi>"),
                 HtmlCell(f"<bdi>{html.escape(decimal_text(result.transaction.amount))} {html.escape(result.transaction.currency)}</bdi>"),
                 HtmlCell(f"<bdi>{html.escape(result.transaction.card or '')}</bdi>"),
                 document_link(result.output_path, result.document.name) if result.document else "",
                 "; ".join(result.reasons), result.warning or ""] for result in subset]
        sections.append(f"<section><h2>{labels[status]}</h2>{html_table(['תאריך','ספק','סכום','כרטיס','מסמך','ראיות','הערה'], rows)}</section>")
    warning_html = "" if not warnings else "<section class='warnings'><h2>אזהרות</h2><ul>" + "".join(
        f"<li>{html.escape(item)}</li>" for item in warnings) + "</ul></section>"
    mode_note = "<p class='notice'>מצב איסוף בלבד: ללא פירוט אשראי אי אפשר לקבוע אילו חשבוניות חסרות.</p>" if email_only else ""
    document_rows = [[document_link(doc.output_path, doc.name), HtmlCell(f"<bdi>{html.escape(doc.id)}</bdi>"),
                      "כן" if doc.duplicate_of else "לא", doc.extraction_warning or ""] for doc in documents]
    page = f"""<!doctype html>
<html lang="he" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Invoice Pack</title><style>
:root{{--ink:#152033;--muted:#667085;--line:#e4e7ec;--bg:#f8fafc;--accent:#6d5ce7}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Arial,sans-serif}}
main{{max-width:1180px;margin:auto;padding:40px 20px 80px}}h1{{font-size:36px;margin:0 0 8px}}h2{{margin-top:34px}}.subtitle,.generated{{color:var(--muted)}}
.summary{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:28px 0}}.card{{background:white;border:1px solid var(--line);border-radius:16px;padding:20px}}
.card strong{{display:block;font-size:30px;color:var(--accent)}}.card span{{color:var(--muted)}}.notice,.warnings{{background:#fff8e7;border:1px solid #f4d58d;border-radius:14px;padding:14px 18px}}
.table-wrap{{overflow:auto;background:white;border:1px solid var(--line);border-radius:14px}}table{{width:100%;border-collapse:collapse;min-width:760px}}th,td{{padding:12px 14px;text-align:right;border-bottom:1px solid var(--line);vertical-align:top}}th{{background:#f2f4f7}}tr:last-child td{{border-bottom:0}}a{{color:var(--accent);text-decoration:none}}a:hover{{text-decoration:underline}}
</style></head><body><main><h1>חבילת חשבוניות</h1><p class="subtitle">Invoice Pack · דוח מקומי ופרטי</p>
<p class="generated">נוצר ב־{html.escape(datetime.now().astimezone().strftime('%d.%m.%Y %H:%M'))}</p>{mode_note}<div class="summary">{cards}</div>{warning_html}
{''.join(sections)}<section><h2>מסמכים שנאספו</h2>{html_table(['קובץ','מזהה','כפילות','הערת חילוץ'], document_rows)}</section>
</main></body></html>"""
    path.write_text(page, encoding="utf-8")


def build_manifest(results: list[MatchResult], documents: list[Document], warnings: list[str], email_only: bool) -> dict[str, object]:
    return {
        "schemaVersion": 1, "generator": f"invoice-pack/{VERSION}",
        "generatedAt": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": "email-only" if email_only else "reconciliation",
        "privacy": "local-only; extracted document text is not retained",
        "summary": {
            "transactions": len(results), "documents": len(documents),
            "matched": sum(result.status == "matched" for result in results),
            "needsReview": sum(result.status == "needs-review" for result in results),
            "missing": sum(result.status == "missing" for result in results),
            "duplicates": sum(doc.duplicate_of is not None for doc in documents),
        },
        "warnings": warnings,
        "documents": [{
            "id": doc.id, "name": doc.name, "sha256": doc.sha256,
            "duplicateOf": doc.duplicate_of, "extractionWarning": doc.extraction_warning,
            "outputPath": doc.output_path,
        } for doc in documents],
        "transactions": [{
            "id": result.transaction.id, "date": result.transaction.date.isoformat(),
            "vendor": result.transaction.vendor, "amount": decimal_text(result.transaction.amount),
            "currency": result.transaction.currency, "originalAmount": decimal_text(result.transaction.original_amount) or None,
            "originalCurrency": result.transaction.original_currency, "card": result.transaction.card,
            "sourceFile": result.transaction.source_file, "sourceSheet": result.transaction.source_sheet,
            "sourceRow": result.transaction.source_row, "status": result.status,
            "documentId": result.document.id if result.document else None, "score": result.score,
            "reasons": result.reasons, "warning": result.warning, "outputPath": result.output_path,
        } for result in results],
    }


def build_package(documents_dir: Path, statements_dir: Optional[Path], output: Path,
                  from_date: Optional[date], to_date: Optional[date]) -> dict[str, object]:
    if output.exists():
        raise FileExistsError(f"Output already exists: {output}")
    if not documents_dir.is_dir():
        raise FileNotFoundError(f"Documents directory not found: {documents_dir}")
    if statements_dir and not statements_dir.is_dir():
        raise FileNotFoundError(f"Statements directory not found: {statements_dir}")

    documents = load_documents(documents_dir)
    transactions: list[Transaction] = []
    warnings: list[str] = []
    if statements_dir:
        transactions, warnings = load_transactions(statements_dir, from_date, to_date)
        if not transactions:
            warnings.append("No transactions were parsed; invoice coverage cannot be determined")
    if not documents:
        warnings.append("No supported invoice or receipt documents were found")
    results = match_transactions(transactions, documents)
    email_only = statements_dir is None

    output.parent.mkdir(parents=True, exist_ok=True)
    temp_root = Path(tempfile.mkdtemp(prefix=f".{output.name}-", dir=str(output.parent)))
    try:
        used_document_ids: set[str] = set()
        for result in results:
            if not result.document:
                continue
            directory = temp_root / ("matched" if result.status == "matched" else "needs-review")
            if result.status == "matched":
                directory = directory / result.transaction.date.strftime("%Y-%m") / safe_name(result.transaction.vendor, "vendor")
            copied = copy_unique(result.document.path, directory)
            result.output_path = copied.relative_to(temp_root).as_posix()
            result.document.output_path = result.output_path
            used_document_ids.add(result.document.id)

        collected: list[Document] = []
        for doc in documents:
            if doc.duplicate_of:
                continue
            if email_only:
                copied = copy_unique(doc.path, temp_root / "collected")
                doc.output_path = copied.relative_to(temp_root).as_posix()
                collected.append(doc)
            elif doc.id not in used_document_ids:
                copied = copy_unique(doc.path, temp_root / "unmatched-documents")
                doc.output_path = copied.relative_to(temp_root).as_posix()

        missing_dir = temp_root / "missing-invoices"
        missing_dir.mkdir(parents=True, exist_ok=True)
        with (missing_dir / "missing.csv").open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["date", "vendor", "amount", "currency", "card", "transaction_id"])
            for result in results:
                if result.status == "missing":
                    txn = result.transaction
                    writer.writerow([txn.date.isoformat(), txn.vendor, decimal_text(txn.amount), txn.currency, txn.card or "", txn.id])

        write_csv_report(temp_root / "report.csv", results, collected)
        write_html_report(temp_root / "report.html", results, documents, warnings, email_only)
        manifest = build_manifest(results, documents, warnings, email_only)
        (temp_root / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        temp_root.replace(output)
        return manifest
    except Exception:
        shutil.rmtree(temp_root, ignore_errors=True)
        raise


def cli() -> int:
    parser = argparse.ArgumentParser(description="Build a local invoice package without uploading documents.")
    parser.add_argument("--documents", required=True, type=Path, help="Directory containing invoice and receipt files")
    parser.add_argument("--statements", type=Path, help="Directory containing card statement XLSX or CSV files")
    parser.add_argument("--output", required=True, type=Path, help="New output directory")
    parser.add_argument("--from-date", type=parse_date, help="Inclusive transaction start date (YYYY-MM-DD)")
    parser.add_argument("--to-date", type=parse_date, help="Inclusive transaction end date (YYYY-MM-DD)")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args()
    if args.from_date is None and "--from-date" in sys.argv:
        parser.error("--from-date must be a valid date")
    if args.to_date is None and "--to-date" in sys.argv:
        parser.error("--to-date must be a valid date")
    if args.from_date and args.to_date and args.from_date > args.to_date:
        parser.error("--from-date must be on or before --to-date")
    try:
        manifest = build_package(args.documents, args.statements, args.output, args.from_date, args.to_date)
    except (FileExistsError, FileNotFoundError, PermissionError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    summary = manifest["summary"]
    print(json.dumps({"output": str(args.output.resolve()), **summary}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
