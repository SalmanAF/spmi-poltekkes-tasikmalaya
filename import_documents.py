#!/usr/bin/env python
"""Import public SPMI document links from the Excel register into documents.json.

Run from the project root:
    python import_documents.py

Optional paths:
    python import_documents.py "path/to/workbook.xlsx" --output "uploads/documents.json"
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
import unicodedata
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell


PROJECT_DIR = Path(__file__).resolve().parent
DEFAULT_WORKBOOK = PROJECT_DIR / "uploads" / "E- Daftar Dokumen SPMI.xlsx"
DEFAULT_OUTPUT = PROJECT_DIR / "uploads" / "documents.json"
TODAY = date.today().isoformat()

SHEET_GROUPS = (
    ("SOP", "SOP", "doc-SOP"),
    ("Pedoman", "Pedoman", "doc-PED"),
    ("Integrasi Standar 2025", "Standar PT", "doc-STD"),
    ("Integrasi Standar 2022", "Standar PT", "doc-STD"),
    ("Formulir", "Formulir", "doc-FRM"),
)
TITLE_HEADERS = {
    "sop": ("Judul SOP", "Nama SOP", "Judul"),
    "pedoman": ("Judul Pedoman", "Nama Pedoman", "Judul"),
    "standar": ("Judul Standar", "Judul Standar PT", "Nama Standar", "Judul"),
    "formulir": ("Nama Formulir", "Judul Formulir", "Judul", "Nama Dokumen"),
}
NUMBER_HEADERS = ("No Dokumen", "Nomor Dokumen", "No. Dokumen", "Nomor", "No Formulir", "No Dokumen Pedoman", "No Dokumen SOP")
LINK_HEADERS = ("Link Dokumen", "Tautan Dokumen", "URL Dokumen", "Link", "Link Drive", "Link File")


def normalize_header(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(character for character in text if not unicodedata.combining(character))
    return re.sub(r"[^a-z0-9]", "", text.casefold())


def header_alias_match(cell_value: Any, aliases: tuple[str, ...]) -> bool:
    normalized_cell = normalize_header(cell_value)
    return any(alias in normalized_cell for alias in (normalize_header(alias) for alias in aliases))


def find_header_row(sheet, title_aliases: tuple[str, ...]) -> tuple[int, dict[str, int]] | None:
    wanted = {
        "title": tuple(title_aliases),
        "number": NUMBER_HEADERS,
        "link": LINK_HEADERS,
    }
    for row_number, row in enumerate(sheet.iter_rows(min_row=1, max_row=min(sheet.max_row, 60), values_only=True), 1):
        columns: dict[str, int] = {}
        for field, aliases in wanted.items():
            match = next(
                (
                    column_number
                    for column_number, value in enumerate(row, 1)
                    if value is not None and header_alias_match(value, aliases)
                ),
                None,
            )
            if match is not None:
                columns[field] = match
        if set(columns) >= {"title", "number", "link"}:
            return row_number, columns
    return None


def cell_value(sheet, row_number: int, column_number: int) -> Any:
    cell: Cell = sheet.cell(row=row_number, column=column_number)
    if cell.hyperlink and cell.hyperlink.target:
        return cell.hyperlink.target
    value = cell.value
    if isinstance(value, str):
        formula_link = re.match(r'^\s*=\s*HYPERLINK\s*\(\s*"([^"]+)"', value, flags=re.IGNORECASE)
        if formula_link:
            return formula_link.group(1)
    return value


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def find_sheet(workbook, requested_name: str):
    requested = normalize_header(requested_name)
    if requested in {normalize_header(name) for name in workbook.sheetnames}:
        actual = next(name for name in workbook.sheetnames if normalize_header(name) == requested)
        return workbook[actual]
    if requested.startswith("integrasistandar"):
        actual = next((name for name in workbook.sheetnames if normalize_header(name).startswith(requested)), None)
        if actual:
            return workbook[actual]
    return None


def classify_related_title(title: str) -> str:
    lowered = title.casefold()
    if "kebijakan" in lowered:
        return "Kebijakan"
    if "formulir" in lowered:
        return "Formulir"
    if "sop" in lowered or "prosedur" in lowered or "procedure" in lowered:
        return "SOP"
    if "pedoman" in lowered or "panduan" in lowered or "etik" in lowered or "manual" in lowered:
        return "Pedoman"
    return "Standar PT"


def read_form_sheet(
    workbook,
    id_counters: Counter[str],
    downloadable: bool,
) -> list[dict[str, Any]]:
    sheet = find_sheet(workbook, "Formulir")
    if sheet is None:
        return []

    records: list[dict[str, Any]] = []
    for row_number, row in enumerate(sheet.iter_rows(values_only=True), 1):
        if row_number < 5:
            continue
        if not row or all(value is None for value in row):
            continue
        if row[1] is None and row[2] is None and row[3] is None:
            continue
        if row[1] in {"Unit Kerja", "Unit Kerja ", "Unit Kerja *"}:
            continue
        title = clean_text(row[2])
        if not title:
            continue
        if title.lower() in {"dst", "data selesai"}:
            continue
        number = clean_text(row[3]) or "-"
        link = clean_text(row[8]) if len(row) > 8 else ""
        id_counters["doc-FRM"] += 1
        records.append(
            {
                "id": f"doc-FRM-{id_counters['doc-FRM']}",
                "judul": title,
                "no_dokumen": number,
                "kode": number,
                "kategori": "Formulir",
                "tipe_sumber": "drive_link" if link else "drive_link",
                "file_url": link,
                "status": "publik",
                "is_downloadable": downloadable and bool(link),
                "created_at": TODAY,
                "tahun": "2025",
            }
        )
    return records


def make_document_id(prefix: str, title: str, counter: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", title.casefold()).strip("-") or "dokumen"
    return f"{prefix}-{slug}-{counter:03d}" if slug else f"{prefix}-{counter:03d}"


def normalise_document_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def dedupe_documents(documents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    for document in documents:
        record_id = str(document.get("document_id") or document.get("id") or "").strip()
        if record_id:
            fallback_key = f"document_id:{record_id}"
        else:
            title = clean_text(document.get("judul") or document.get("document_name") or document.get("name") or "")
            category = clean_text(document.get("kategori") or "")
            number = clean_text(document.get("no_dokumen") or document.get("kode") or "")
            fallback_key = f"{normalise_document_key(category)}:{normalise_document_key(title)}:{normalise_document_key(number)}"
        if fallback_key in seen:
            existing = seen[fallback_key]
            for key, value in document.items():
                if not existing.get(key) and value not in (None, "", [], {}):
                    existing[key] = value
            continue
        seen[fallback_key] = dict(document)
    return list(seen.values())


def read_integration_sheet(
    workbook,
    sheet_name: str,
    downloadable: bool,
) -> list[dict[str, Any]]:
    sheet = find_sheet(workbook, sheet_name)
    if sheet is None:
        print(f"Peringatan: sheet '{sheet_name}' tidak ditemukan; dilewati.", file=sys.stderr)
        return []

    rows = list(sheet.iter_rows(values_only=True))
    header_row = next(
        (
            index
            for index, row in enumerate(rows[:80])
            if len(row) >= 5 and any(clean_text(value).casefold() == "judul standar" for value in row if value is not None)
        ),
        None,
    )
    if header_row is None:
        return []

    year = sheet_name.rsplit(" ", 1)[-1]
    category_code = "PEL"
    documents: dict[str, dict[str, Any]] = {}
    relationships: list[dict[str, Any]] = []
    relationship_counter = 1
    standard_counter = 0
    current_standard_id: str | None = None
    current_guideline_id: str | None = None
    current_section_title = ""
    document_counters: Counter[tuple[str, str]] = Counter()

    def ensure_standard(
        title: str,
        no_dokumen: str,
        link: str,
        pic: str,
        source_row: int,
    ) -> str:
        nonlocal standard_counter, current_standard_id, current_guideline_id, relationship_counter
        standard_counter += 1
        standard_id = f"PEL-STD-{year}-{standard_counter:03d}"
        current_standard_id = standard_id
        current_guideline_id = None
        standard_record = {
            "id": standard_id,
            "document_id": standard_id,
            "judul": title,
            "no_dokumen": no_dokumen or "-",
            "kode": no_dokumen or "-",
            "kategori": "Standar PT",
            "kategori_id": category_code,
            "category_name": current_section_title,
            "subjudul": current_section_title,
            "document_type": "STANDARD",
            "pic": pic,
            "source_sheet": sheet_name,
            "source_row": source_row,
            "tipe_sumber": "drive_link",
            "file_url": link,
            "status": "publik",
            "is_downloadable": downloadable and bool(link),
            "created_at": TODAY,
            "tahun": year,
            "tahun_integrasi": year,
            "standard_id": standard_id,
            "relationship_id": f"REL-{relationship_counter:03d}",
            "relationship_type": "STANDARD",
            "parent_document_id": "",
            "related_ids": [],
            "document_name": title,
            "name": title,
        }
        documents[standard_id] = standard_record
        relationship_counter += 1
        return standard_id

    def append_relationship(
        standard_id: str,
        document_id: str,
        rel_type: str,
        parent_document_id: str = "",
    ) -> dict[str, Any]:
        nonlocal relationship_counter
        relationship = {
            "relationship_id": f"REL-{relationship_counter:03d}",
            "standard_id": standard_id,
            "document_id": document_id,
            "relationship_type": rel_type,
            "parent_document_id": parent_document_id,
        }
        relationships.append(relationship)
        relationship_counter += 1
        return relationship

    def classify_document_type(title: str) -> tuple[str, str]:
        normalized = title.casefold()
        if "formulir" in normalized:
            return "Formulir", "FRM"
        if any(keyword in normalized for keyword in ("sop", "prosedur", "procedure")):
            return "SOP", "SOP"
        if any(keyword in normalized for keyword in ("pedoman", "panduan", "etik", "manual")):
            return "Pedoman", "PED"
        if "kebijakan" in normalized:
            return "Kebijakan", "KEB"
        return "Lainnya", "DOC"

    for excel_row, row in enumerate(rows[header_row + 1 :], start=header_row + 2):
        if not row or all(value is None for value in row):
            continue
        codex = clean_text(row[0]) if len(row) > 0 else ""
        title = clean_text(row[1]) if len(row) > 1 else ""
        number = clean_text(row[2]) if len(row) > 2 else ""
        pic = clean_text(row[3]) if len(row) > 3 else ""
        link = clean_text(row[4]) if len(row) > 4 else ""

        if not title and not number and not link:
            continue
        if title.lower().startswith("total ") or "standar pelampauan" in title.casefold() or "buku" in title.casefold():
            if not codex or not codex.isalpha():
                continue
        if not title:
            continue

        normalized_title = title.casefold()
        category, type_code = classify_document_type(title)
        marker = codex.strip()
        if len(marker) == 1 and marker.isalpha() and category != "Lainnya":
            current_standard_id = None
            current_guideline_id = None
            if number or link:
                current_section_title = title
        is_group_marker = (
            len(marker) == 1
            and marker.isalpha()
            and not number
            and not link
            and (
                normalized_title in {"pelampauan", "pendidikan", "pengabdian", "penelitian"}
                or normalized_title.startswith("standar pelampauan")
            )
        )
        if is_group_marker:
            current_section_title = title.strip()
            current_standard_id = None
            current_guideline_id = None
            continue

        is_standard_row = marker.isdigit() or (
            len(marker) == 1
            and marker.isalpha()
            and category == "Lainnya"
            and normalized_title.startswith("standar ")
        )

        if is_standard_row:
            if len(marker) == 1 and marker.isalpha():
                current_section_title = title
            current_standard_id = ensure_standard(title, number, link, pic, excel_row)
            continue

        parent_standard_id = current_standard_id or ""
        if not parent_standard_id:
            if category not in {"Kebijakan", "Pedoman", "SOP", "Formulir"}:
                continue
            counter_key = ("", type_code)
            document_counters[counter_key] += 1
            document_id = f"PEL-{year}-{type_code}-{document_counters[counter_key]:03d}"
        else:
            counter_key = (parent_standard_id, type_code)
            document_counters[counter_key] += 1
            document_id = (
                f"{parent_standard_id}-{type_code}-"
                f"{document_counters[counter_key]:03d}"
            )

        parent_document_id = ""
        guideline_id = ""
        relationship_type = "STANDARD_SUBTITLE"
        if category == "Pedoman":
            current_guideline_id = document_id
            parent_document_id = parent_standard_id
            relationship_type = "STANDARD_PEDOMAN" if parent_standard_id else "PEDOMAN"
        elif category == "SOP":
            guideline_id = current_guideline_id or ""
            parent_document_id = guideline_id
            relationship_type = (
                "GUIDELINE_SOP"
                if guideline_id
                else "STANDARD_SOP" if parent_standard_id else "SOP"
            )
        elif category in {"Formulir", "Kebijakan"}:
            relationship_type = f"STANDARD_{category.upper()}" if parent_standard_id else category.upper()
        record = {
            "id": document_id,
            "document_id": document_id,
            "judul": title,
            "no_dokumen": number or "-",
            "kode": number or "-",
            "kategori": category,
            "kategori_id": category_code,
            "category_name": current_section_title,
            "document_type": category.upper(),
            "tipe_sumber": "drive_link",
            "file_url": link,
            "status": "publik",
            "is_downloadable": downloadable and bool(link),
            "created_at": TODAY,
            "tahun": year,
            "tahun_integrasi": year,
            "standard_id": parent_standard_id,
            "guideline_id": guideline_id,
            "related_ids": [parent_document_id] if parent_document_id else [],
            "relationship_id": "",
            "relationship_type": relationship_type,
            "parent_document_id": parent_document_id,
            "document_name": title,
            "name": title,
            "pic": pic,
            "source_sheet": sheet_name,
            "source_row": excel_row,
        }
        documents[document_id] = record
        if parent_standard_id:
            parent = documents[parent_standard_id]
            parent["related_ids"].append(document_id)
            relationship = append_relationship(
                parent_standard_id,
                document_id,
                relationship_type,
                parent_document_id,
            )
            if guideline_id:
                guideline = documents.get(guideline_id)
                if guideline is not None:
                    guideline["related_ids"].append(document_id)
                record["standard_id"] = parent_standard_id
        else:
            relationship = {
                "relationship_id": f"REL-{relationship_counter:03d}",
                "standard_id": "",
                "document_id": document_id,
                "relationship_type": relationship_type,
                "parent_document_id": parent_document_id,
            }
            relationships.append(relationship)
            relationship_counter += 1
        record["relationship_id"] = relationship["relationship_id"]

    return list(documents.values())


def read_sheet(
    workbook,
    sheet_name: str,
    category: str,
    id_prefix: str,
    id_counters: Counter[str],
    downloadable: bool,
) -> list[dict[str, Any]]:
    if sheet_name in {"Integrasi Standar 2022", "Integrasi Standar 2025"}:
        return read_integration_sheet(workbook, sheet_name, downloadable)
    if sheet_name == "Formulir":
        return read_form_sheet(workbook, id_counters, downloadable)

    sheet = find_sheet(workbook, sheet_name)
    if sheet is None:
        print(f"Peringatan: sheet '{sheet_name}' tidak ditemukan; dilewati.", file=sys.stderr)
        return []

    title_key = {
        "SOP": "sop",
        "Pedoman": "pedoman",
        "Standar PT": "standar",
        "Formulir": "formulir",
    }.get(category, "standar")
    header = find_header_row(sheet, TITLE_HEADERS[title_key])
    if header is None:
        print(f"Peringatan: kolom Judul/No Dokumen/Link Dokumen tidak ditemukan di sheet '{sheet.title}'; dilewati.", file=sys.stderr)
        return []

    header_row, columns = header
    records: list[dict[str, Any]] = []
    for row_number in range(header_row + 1, sheet.max_row + 1):
        title = clean_text(cell_value(sheet, row_number, columns["title"]))
        number = clean_text(cell_value(sheet, row_number, columns["number"])) or "-"
        link = clean_text(cell_value(sheet, row_number, columns["link"]))
        if not title and not link:
            continue
        if not title or not link:
            print(f"Peringatan: {sheet.title} baris {row_number} dilewati (judul atau link kosong).", file=sys.stderr)
            continue

        id_counters[id_prefix] += 1
        record = {
            "id": f"{id_prefix}-{id_counters[id_prefix]}",
            "judul": title,
            "no_dokumen": number,
            "kategori": category,
            "tipe_sumber": "drive_link",
            "file_url": link,
            "status": "publik",
            "is_downloadable": downloadable,
            "created_at": TODAY,
        }
        if category == "Formulir":
            record["tahun"] = "2025"
        records.append(record)
    return records


def write_json_atomically(destination: Path, documents: list[dict[str, Any]]) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f"{destination.stem}-", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as output:
            json.dump(documents, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, destination)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def import_documents(workbook_path: Path, output_path: Path, downloadable: bool = True) -> Counter[str]:
    if not workbook_path.is_file():
        raise FileNotFoundError(f"File Excel tidak ditemukan: {workbook_path}")
    workbook = load_workbook(workbook_path, read_only=False, data_only=False)
    counts: Counter[str] = Counter()
    id_counters: Counter[str] = Counter()
    documents: list[dict[str, Any]] = []
    try:
        for sheet_name, category, id_prefix in SHEET_GROUPS:
            before = len(documents)
            documents.extend(read_sheet(workbook, sheet_name, category, id_prefix, id_counters, downloadable))
            counts[category] += len(documents) - before
    finally:
        workbook.close()

    if not documents:
        raise ValueError("Tidak ada dokumen valid yang ditemukan; documents.json tidak diubah.")

    documents = dedupe_documents(documents)

    existing_statuses: dict[str, str] = {}
    existing_statuses_by_identity: dict[tuple[str, str, str], set[str]] = {}
    if output_path.is_file():
        try:
            with output_path.open("r", encoding="utf-8") as manifest:
                existing_documents = json.load(manifest)
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("Manifest tujuan tidak dapat dibaca; impor dibatalkan.") from error
        if not isinstance(existing_documents, list):
            raise ValueError("Manifest tujuan harus berisi array dokumen; impor dibatalkan.")
        existing_statuses = {
            item["id"]: item["status"]
            for item in existing_documents
            if isinstance(item, dict)
            and isinstance(item.get("id"), str)
            and item.get("status") in {"publik", "privat", "draft"}
        }
        for item in existing_documents:
            if not isinstance(item, dict) or item.get("status") not in {"publik", "privat", "draft"}:
                continue
            title = normalise_document_key(clean_text(item.get("judul", "")))
            number = normalise_document_key(
                clean_text(item.get("no_dokumen") or item.get("kode") or "")
            )
            year = clean_text(
                item.get("tahun_integrasi")
                or item.get("tahun")
                or str(item.get("created_at") or "")[:4]
            )
            if title:
                existing_statuses_by_identity.setdefault(
                    (title, number, year), set()
                ).add(item["status"])
    for document in documents:
        identity = (
            normalise_document_key(clean_text(document.get("judul", ""))),
            normalise_document_key(
                clean_text(document.get("no_dokumen") or document.get("kode") or "")
            ),
            clean_text(
                document.get("tahun_integrasi")
                or document.get("tahun")
                or str(document.get("created_at") or "")[:4]
            ),
        )
        identity_statuses = existing_statuses_by_identity.get(identity, set())
        preserved_status = next(
            (
                status
                for status in ("draft", "privat", "publik")
                if status in identity_statuses
            ),
            None,
        )
        document["status"] = existing_statuses.get(
            document["id"],
            preserved_status or document.get("status", "publik"),
        )

    write_json_atomically(output_path, documents)
    return Counter(document["kategori"] for document in documents)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import dokumen SPMI dari workbook Excel ke uploads/documents.json.")
    parser.add_argument("workbook", nargs="?", type=Path, default=DEFAULT_WORKBOOK, help="Path workbook Excel (default: file di root project).")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="Path JSON output (default: uploads/documents.json).")
    parser.add_argument("--view-only", action="store_true", help="Import dengan is_downloadable=false; default mengizinkan download.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    workbook_path = args.workbook.expanduser().resolve()
    output_path = args.output.expanduser().resolve()
    try:
        counts = import_documents(workbook_path, output_path, downloadable=not args.view_only)
    except (FileNotFoundError, ValueError, OSError) as error:
        print(f"Gagal mengimpor: {error}", file=sys.stderr)
        return 1

    print(
        "Berhasil mengimpor "
        f"{counts['SOP']} SOP, {counts['Pedoman']} Pedoman, dan "
        f"{counts['Standar PT']} Standar PT ke {output_path}."
    )
    print(f"Total: {sum(counts.values())} dokumen; status publik; tanggal {TODAY}.")
    if args.view_only:
        print("Mode akses: preview saja (is_downloadable=false).")
    else:
        print("Mode akses: unduh diizinkan (is_downloadable=true).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
