#!/usr/bin/env python
"""Backfill document years in the JSON document manifest.

Run a read-only preview first:
    python migrate_document_years.py

Apply changes after reviewing the summary:
    python migrate_document_years.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from app.document_years import infer_document_year
from import_documents import DEFAULT_OUTPUT


def _read_manifest(path: Path) -> list[dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as manifest:
            records = json.load(manifest)
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError(f"Manifest tidak dapat dibaca: {path}") from error
    if not isinstance(records, list) or any(
        not isinstance(record, dict) for record in records
    ):
        raise ValueError("Manifest harus berupa array berisi objek dokumen.")
    return records


def _write_atomically(path: Path, records: list[dict[str, Any]]) -> None:
    handle, temporary_name = tempfile.mkstemp(
        prefix=f"{path.stem}-",
        suffix=".tmp",
        dir=path.parent,
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as output:
            json.dump(records, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, path)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def migrate_manifest(
    path: Path,
    *,
    apply: bool = False,
) -> dict[str, Any]:
    records = _read_manifest(path)
    changed = 0
    inferred = 0
    unresolved = 0
    unresolved_categories: Counter[str] = Counter()
    migrated: list[dict[str, Any]] = []

    for record in records:
        year = infer_document_year(record)
        had_year = bool(str(record.get("document_year") or record.get("tahun") or "").strip())
        old_year = str(record.get("document_year") or record.get("tahun") or "").strip()
        created_year = str(record.get("created_at") or "")[:4]
        updated = dict(record)
        updated["document_year"] = year
        updated["tahun"] = year
        if updated != record:
            changed += 1
        if year and (
            not had_year
            or (old_year == created_year and year != old_year)
        ):
            inferred += 1
        if not year:
            unresolved += 1
            unresolved_categories[str(record.get("kategori") or "Tidak diketahui")] += 1
        migrated.append(updated)

    backup_path: Path | None = None
    if apply and changed:
        timestamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
        backup_path = path.with_name(f"{path.name}.bak.{timestamp}")
        backup_path.write_bytes(path.read_bytes())
        _write_atomically(path, migrated)

    return {
        "total": len(records),
        "changed": changed,
        "inferred": inferred,
        "unresolved": unresolved,
        "unresolved_categories": dict(unresolved_categories),
        "backup": str(backup_path) if backup_path else None,
        "applied": apply,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Backfill tahun dokumen dalam uploads/documents.json."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Path manifest JSON dokumen.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Terapkan perubahan setelah membuat salinan cadangan.",
    )
    args = parser.parse_args()

    try:
        result = migrate_manifest(args.manifest.expanduser().resolve(), apply=args.apply)
    except (OSError, ValueError) as error:
        print(f"Migrasi gagal: {error}", file=sys.stderr)
        return 1

    action = "diterapkan" if result["applied"] else "pratinjau"
    print(
        f"Hasil {action}: {result['changed']} dari {result['total']} dokumen berubah; "
        f"{result['inferred']} tahun berhasil disimpulkan; "
        f"{result['unresolved']} dokumen perlu tahun manual."
    )
    if result["backup"]:
        print(f"Cadangan dibuat: {result['backup']}")
    if result["unresolved_categories"]:
        summary = ", ".join(
            f"{category}: {count}"
            for category, count in sorted(result["unresolved_categories"].items())
        )
        print(f"Belum dapat ditentukan: {summary}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
