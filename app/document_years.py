from __future__ import annotations

import re
from datetime import date
from typing import Any


_YEAR_PATTERN = re.compile(r"(?<!\d)((?:19|20|21)\d{2})(?!\d)")
_VALID_YEAR_PATTERN = re.compile(r"^(?:19|20|21)\d{2}$")


def _year_from_value(value: Any) -> str:
    year = str(value or "").strip()
    return year if _VALID_YEAR_PATTERN.fullmatch(year) else ""


def infer_document_year(record: dict[str, Any]) -> str:
    document_date = str(record.get("document_date") or "").strip()
    if document_date:
        try:
            return date.fromisoformat(document_date).strftime("%Y")
        except ValueError:
            pass

    explicit_year = _year_from_value(record.get("document_year"))
    if explicit_year:
        return explicit_year

    title_years = set(_YEAR_PATTERN.findall(str(record.get("judul") or "")))
    if len(title_years) == 1:
        return title_years.pop()

    code = " ".join(
        str(record.get(field) or "")
        for field in ("no_dokumen", "kode")
    )
    code_years = set(_YEAR_PATTERN.findall(code))
    if len(code_years) == 1:
        return code_years.pop()

    legacy_year = _year_from_value(record.get("tahun"))
    created_year = str(record.get("created_at") or "")[:4]
    if legacy_year and legacy_year != created_year:
        return legacy_year

    integration_year = _year_from_value(record.get("tahun_integrasi"))
    if integration_year:
        return integration_year

    return ""
