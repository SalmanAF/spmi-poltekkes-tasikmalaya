import json
import os
import re
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, field_validator, model_validator


BASE_DIR = Path(__file__).resolve().parent.parent
UPLOADS_DIR = (BASE_DIR / "uploads").resolve()
MANIFEST_PATH = UPLOADS_DIR / "documents.json"
DocumentCategory = Literal[
    "Kebijakan",
    "Standar PT",
    "Pedoman",
    "SOP",
    "Formulir",
    "Perangkat SPMI",
    "Unduhan",
    "Lainnya",
]
SourceType = Literal["drive_link", "local_file"]
PublishStatus = Literal["publik", "privat", "draft"]
RevisionStatus = Literal["perlu_revisi", "dalam_peninjauan", "selesai"]
RevisionSource = Literal["audit", "masukan_pengguna", "peninjauan_internal"]
ALLOWED_EXTENSIONS = {".pdf", ".docx"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DocumentRecord(BaseModel):
    id: str = Field(min_length=1, max_length=80)
    judul: str = Field(min_length=1, max_length=240)
    no_dokumen: str = "-"
    kode: str = "-"
    tahun: str = ""
    kategori: DocumentCategory
    tipe_sumber: SourceType
    file_url: str = Field(default="", max_length=2048)
    link_download: str = ""
    status: PublishStatus = "publik"
    is_downloadable: bool = False
    created_at: str
    related_ids: list[str] = Field(default_factory=list)
    standard_id: str = ""
    guideline_id: str = ""
    subjudul: str = ""
    document_id: str = ""
    relationship_id: str = ""
    relationship_type: str = ""
    parent_document_id: str = ""
    tahun_integrasi: str | None = None
    pic: str = ""
    source_sheet: str = ""
    source_row: int | None = None
    berlaku_sampai: str = ""
    status_revisi: RevisionStatus | None = None
    sumber_revisi: RevisionSource | None = None
    catatan_revisi: str = ""
    ditinjau_pada: str = ""

    @model_validator(mode="before")
    @classmethod
    def normalize_record_fields(cls, value):
        if not isinstance(value, dict):
            return value
        record = dict(value)
        code = record.get("kode", record.get("no_dokumen", "-"))
        link = record.get("link_download") or record.get("drive_link") or record.get("file_url", "")
        record["kode"] = code
        record["no_dokumen"] = code
        record["file_url"] = link
        record["link_download"] = link
        record.setdefault("tahun", str(record.get("created_at", ""))[:4])
        record["document_id"] = record.get("document_id") or record.get("id", "")
        if record.get("kategori") == "SOP":
            parent_id = record.get("guideline_id") or record.get("parent_document_id", "")
            record["guideline_id"] = parent_id
            record["parent_document_id"] = parent_id
        if "tipe_sumber" not in record and link:
            record["tipe_sumber"] = "local_file" if link.startswith("/uploads/") else "drive_link"
        return record

    @field_validator("judul")
    @classmethod
    def strip_title(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Judul wajib diisi")
        return value

    @field_validator("tahun")
    @classmethod
    def validate_year(cls, value: str) -> str:
        value = value.strip()
        if value and (len(value) != 4 or not value.isdigit()):
            raise ValueError("Tahun harus berformat empat digit")
        return value

    @field_validator("berlaku_sampai", "ditinjau_pada")
    @classmethod
    def validate_optional_date(cls, value: str) -> str:
        value = value.strip()
        if value:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("Tanggal harus berformat YYYY-MM-DD") from exc
        return value

    @field_validator("file_url")
    @classmethod
    def validate_file_url_shape(cls, value: str) -> str:
        value = value.strip()
        if not value:
            return ""
        return value

    @model_validator(mode="after")
    def validate_source(self):
        if self.file_url:
            if self.tipe_sumber == "drive_link":
                parsed = urlparse(self.file_url)
                if parsed.scheme != "https" or parsed.hostname not in {
                    "drive.google.com",
                    "docs.google.com",
                    "bit.ly",
                }:
                    raise ValueError("Gunakan URL Google Drive atau bit.ly HTTPS")
            elif not self.file_url.startswith("/uploads/"):
                raise ValueError("Path file lokal harus berada di /uploads/")
        self.kode = self.no_dokumen
        self.link_download = self.file_url
        if not self.tahun:
            self.tahun = self.created_at[:4]
        return self


class DocumentUpdate(BaseModel):
    judul: str | None = Field(default=None, min_length=1, max_length=240)
    no_dokumen: str | None = Field(default=None, max_length=120)
    kode: str | None = Field(default=None, max_length=120)
    tahun: str | None = Field(default=None, max_length=4)
    file_url: str | None = Field(default=None, max_length=2048)
    link_download: str | None = Field(default=None, max_length=2048)
    drive_link: str | None = Field(default=None, max_length=2048)
    tipe_sumber: SourceType | None = None
    kategori: DocumentCategory | None = None
    status: PublishStatus | None = None
    is_downloadable: bool | None = None
    standard_id: str | None = Field(default=None, max_length=80)
    guideline_id: str | None = Field(default=None, max_length=80)
    berlaku_sampai: str | None = Field(default=None, max_length=10)
    status_revisi: RevisionStatus | None = None
    sumber_revisi: RevisionSource | None = None
    catatan_revisi: str | None = Field(default=None, max_length=5000)
    ditinjau_pada: str | None = Field(default=None, max_length=10)

    @field_validator("berlaku_sampai", "ditinjau_pada")
    @classmethod
    def validate_optional_date(cls, value: str | None) -> str | None:
        if value:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("Tanggal harus berformat YYYY-MM-DD") from exc
        return value


def load_documents() -> list[dict]:
    try:
        with MANIFEST_PATH.open("r", encoding="utf-8") as manifest:
            payload = json.load(manifest)
    except FileNotFoundError:
        return []
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError("documents.json tidak dapat dibaca sebagai JSON valid") from exc
    if not isinstance(payload, list):
        raise RuntimeError("documents.json harus berisi array dokumen")
    records = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        try:
            records.append(DocumentRecord.model_validate(item).model_dump())
        except Exception:
            continue
    return records


def save_documents(records: list[dict]) -> None:
    validated = [DocumentRecord.model_validate(record).model_dump() for record in records]
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix="documents-", suffix=".json", dir=UPLOADS_DIR)
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as output:
            json.dump(validated, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_name, MANIFEST_PATH)
    finally:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)


def all_documents() -> list[dict]:
    return load_documents()


def save_document(document: DocumentRecord) -> dict:
    records = load_documents()
    if any(record["id"] == document.id for record in records):
        raise ValueError("ID dokumen sudah digunakan")
    record = document.model_dump()
    _validate_document_relationship(record, records)
    records.append(record)
    save_documents(records)
    return record


def _validate_document_relationship(record: dict, records: list[dict]) -> None:
    if record["kategori"] == "Pedoman" and record["standard_id"]:
        parent = next(
            (item for item in records if item["id"] == record["standard_id"]),
            None,
        )
        if parent is None or parent["kategori"] != "Standar PT":
            raise ValueError("Relasi Pedoman harus menunjuk ke Standar PT yang tersedia")
    if record["kategori"] == "SOP" and record["guideline_id"]:
        parent = next(
            (item for item in records if item["id"] == record["guideline_id"]),
            None,
        )
        if parent is None or parent["kategori"] != "Pedoman":
            raise ValueError("Relasi SOP harus menunjuk ke Pedoman yang tersedia")
        record["parent_document_id"] = parent["id"]
        if parent["standard_id"]:
            record["standard_id"] = parent["standard_id"]


def update_document(document_id: str, changes: dict) -> dict | None:
    records = load_documents()
    for record in records:
        if record["id"] == document_id:
            if changes.get("kode") is not None:
                changes["no_dokumen"] = changes["kode"]
            elif changes.get("no_dokumen") is not None:
                changes["kode"] = changes["no_dokumen"]
            if changes.get("guideline_id") is not None:
                changes["parent_document_id"] = changes["guideline_id"]
            link = changes.get("link_download") or changes.get("drive_link") or changes.get("file_url")
            if link:
                changes["file_url"] = link
                changes["link_download"] = link
                changes.setdefault("tipe_sumber", "local_file" if link.startswith("/uploads/") else "drive_link")
            record.update({key: value for key, value in changes.items() if value is not None})
            validated = DocumentRecord.model_validate(record).model_dump()
            _validate_document_relationship(
                validated,
                [item for item in records if item["id"] != document_id],
            )
            record.clear()
            record.update(validated)
            save_documents(records)
            return record
    return None


def remove_document(document_id: str) -> dict | None:
    records = load_documents()
    target = next((record for record in records if record["id"] == document_id), None)
    if target is None:
        return None
    save_documents([record for record in records if record["id"] != document_id])
    if target["tipe_sumber"] == "local_file":
        local_path = safe_local_path(target["file_url"])
        if local_path is not None and local_path.exists():
            local_path.unlink()
    return target


def safe_local_path(file_url: str) -> Path | None:
    prefix = "/uploads/"
    if not file_url.startswith(prefix):
        return None
    relative = file_url[len(prefix) :]
    if not relative or Path(relative).name != relative:
        return None
    candidate = (UPLOADS_DIR / relative).resolve()
    if candidate.parent != UPLOADS_DIR or candidate.suffix.lower() not in ALLOWED_EXTENSIONS:
        return None
    return candidate


def is_google_drive_url(file_url: str) -> bool:
    parsed = urlparse(file_url)
    return parsed.scheme == "https" and parsed.hostname in {"drive.google.com", "docs.google.com"}


def drive_preview_url(file_url: str) -> str:
    if not is_google_drive_url(file_url):
        return file_url
    parsed = urlparse(file_url)
    match = re.search(r"/(?:file|document|spreadsheets|presentation)/d/([^/]+)", parsed.path)
    if match:
        return f"https://drive.google.com/file/d/{match.group(1)}/preview"
    query_id = __import__("urllib.parse", fromlist=["parse_qs"]).parse_qs(parsed.query).get("id", [""])[0]
    if query_id:
        return f"https://drive.google.com/file/d/{query_id}/preview"
    return file_url


def drive_download_url(file_url: str) -> str:
    parsed = urlparse(file_url)
    match = re.search(r"/(?:file|document|spreadsheets|presentation)/d/([^/]+)", parsed.path)
    document_id = match.group(1) if match else __import__("urllib.parse", fromlist=["parse_qs"]).parse_qs(parsed.query).get("id", [""])[0]
    if not document_id:
        return file_url
    if "/document/" in parsed.path:
        return f"https://docs.google.com/document/d/{document_id}/export?format=docx"
    if "/spreadsheets/" in parsed.path:
        return f"https://docs.google.com/spreadsheets/d/{document_id}/export?format=xlsx"
    if "/presentation/" in parsed.path:
        return f"https://docs.google.com/presentation/d/{document_id}/export/pptx"
    return f"https://drive.google.com/uc?export=download&id={document_id}"


def _public_record(record: dict) -> dict:
    local_path = safe_local_path(record["file_url"]) if record["tipe_sumber"] == "local_file" else None
    file_exists = local_path is not None and local_path.is_file()
    file_format = "GOOGLE DRIVE" if record["tipe_sumber"] == "drive_link" else (local_path.suffix.lstrip(".").upper() if file_exists and local_path else "")
    related_ids = record.get("related_ids") or []
    standard_id = record.get("standard_id") or ""
    guideline_id = record.get("guideline_id") or ""
    return {
        **record,
        "preview_url": drive_preview_url(record["file_url"]) if record["tipe_sumber"] == "drive_link" else f"/dokumen/{record['id']}/preview",
        "file_url": record["file_url"] if record["is_downloadable"] or record["tipe_sumber"] == "local_file" else drive_preview_url(record["file_url"]),
        "has_file": is_google_drive_url(record["file_url"]) if record["tipe_sumber"] == "drive_link" else file_exists,
        "file_format": file_format,
        "file_size": local_path.stat().st_size if file_exists and local_path else None,
        "download_allowed": record["is_downloadable"] and (record["tipe_sumber"] == "drive_link" or file_exists),
        "name": record["judul"],
        "category": record["kategori"],
        "type": record["kategori"].lower().replace(" ", "-"),
        "code": record["no_dokumen"],
        "description": "",
        "version": "",
        "published_at": record["created_at"] if record["status"] == "publik" else "",
        "updated_at": record["created_at"],
        "unit": "",
        "related_ids": related_ids,
        "standard_id": standard_id,
        "guideline_id": guideline_id,
        "subjudul": record.get("subjudul") or "",
        "document_id": record.get("document_id") or record["id"],
        "relationship_id": record.get("relationship_id") or "",
        "relationship_type": record.get("relationship_type") or "",
        "parent_document_id": record.get("parent_document_id") or "",
    }


def public_documents() -> list[dict]:
    records = [record for record in load_documents() if record["status"] == "publik"]
    return [_public_record(record) for record in records]


def integration_map_documents() -> list[dict]:
    integration_years = {"2022", "2025"}
    return [
        document
        for document in public_documents()
        if str(document.get("tahun_integrasi") or "") in integration_years
    ]


def standard_tree(standard_id: str) -> dict | None:
    records = load_documents()
    standard = next(
        (
            record
            for record in records
            if str(record.get("id") or "") == str(standard_id)
            or (str(record.get("standard_id") or "") == str(standard_id) and record.get("kategori") == "Standar PT")
        ),
        None,
    )
    if standard is None:
        return None

    target_id = str(standard_id)
    standard_records = [
        record
        for record in records
        if str(record.get("standard_id") or "") == target_id
        or str(record.get("id") or "") == target_id
    ]
    pedoman = [
        record for record in standard_records if record.get("kategori") == "Pedoman"
    ]
    sop = [
        record for record in standard_records if record.get("kategori") == "SOP"
    ]
    formulir = [
        record for record in standard_records if record.get("kategori") == "Formulir"
    ]
    relationships = []
    seen_relationships: set[str] = set()
    for record in standard_records:
        relationship_id = str(record.get("relationship_id") or "")
        document_id = str(record.get("document_id") or record.get("id") or "")
        relationship_type = str(record.get("relationship_type") or "STANDARD_DOCUMENT")
        parent_document_id = str(record.get("parent_document_id") or "")
        if not document_id:
            continue
        if relationship_id:
            key = relationship_id
        else:
            key = f"{standard_id}:{document_id}:{relationship_type}:{parent_document_id}"
        if key in seen_relationships:
            continue
        seen_relationships.add(key)
        relationships.append(
            {
                "relationship_id": relationship_id or key,
                "standard_id": str(record.get("standard_id") or standard_id),
                "document_id": document_id,
                "relationship_type": relationship_type,
                "parent_document_id": parent_document_id,
            }
        )

    return {
        "standard": {
            "id": str(standard.get("id") or standard_id),
            "name": str(standard.get("judul") or standard.get("nama") or standard.get("id") or standard_id),
        },
        "pedoman": [_public_record(record) for record in pedoman],
        "sop": [_public_record(record) for record in sop],
        "formulir": [_public_record(record) for record in formulir],
        "documents": [_public_record(record) for record in standard_records],
        "relationships": relationships,
    }


def public_document(document_id: str) -> dict | None:
    return next((record for record in public_documents() if record["id"] == document_id), None)


def document_file_path(document_id: str) -> Path | None:
    record = next((item for item in load_documents() if item["id"] == document_id), None)
    if record is None or record["status"] != "publik" or not record["is_downloadable"]:
        return None
    return safe_local_path(record["file_url"]) if record["tipe_sumber"] == "local_file" else None


def public_statistics() -> dict[str, int]:
    records = public_documents()
    return {
        "standar_pt": sum(item["kategori"] == "Standar PT" for item in records),
        "pedoman": sum(item["kategori"] == "Pedoman" for item in records),
        "sop": sum(item["kategori"] == "SOP" for item in records),
        "total": len(records),
    }