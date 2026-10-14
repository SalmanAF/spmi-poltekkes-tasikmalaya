import sqlite3
from contextlib import closing
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app import auth


PPEPP_STAGES = (
    {
        "key": "penetapan",
        "label": "Penetapan",
        "guidance": "Uraikan standar/SOP yang ditetapkan, pihak yang menetapkan, dan dasar penetapannya.",
    },
    {
        "key": "pelaksanaan",
        "label": "Pelaksanaan",
        "guidance": "Uraikan pelaksanaan dokumen oleh unit terkait beserta kondisi dan bukti nyatanya.",
    },
    {
        "key": "evaluasi",
        "label": "Evaluasi",
        "guidance": "Uraikan cara menilai kesesuaian pelaksanaan terhadap standar atau SOP.",
    },
    {
        "key": "pengendalian",
        "label": "Pengendalian",
        "guidance": "Uraikan tindakan koreksi dan tindak lanjut berdasarkan hasil evaluasi.",
    },
    {
        "key": "peningkatan",
        "label": "Peningkatan",
        "guidance": "Uraikan upaya peningkatan standar atau kualitas berdasarkan evaluasi dan tindak lanjut.",
    },
)
PpeppStage = Literal[
    "penetapan",
    "pelaksanaan",
    "evaluasi",
    "pengendalian",
    "peningkatan",
]


class PpeppStageUpdate(BaseModel):
    activity: str = Field(default="", max_length=2000)
    documents_used: str = Field(default="", max_length=2000)
    output: str = Field(default="", max_length=2000)
    frequency: str = Field(default="", max_length=500)
    narrative: str = Field(default="", max_length=10000)

    @field_validator("activity", "documents_used", "output", "frequency", "narrative")
    @classmethod
    def trim_values(cls, value: str) -> str:
        return value.strip()

    def has_content(self) -> bool:
        return any(
            getattr(self, field).strip()
            for field in ("activity", "documents_used", "output", "frequency", "narrative")
        )


class MonitoringUpdate(BaseModel):
    unit: str = Field(default="", max_length=200)
    pic: str = Field(default="", max_length=200)
    evidence: str = Field(default="", max_length=2000)
    implementation_date: date | None = None
    notes: str = Field(default="", max_length=5000)

    @field_validator("unit", "pic", "evidence", "notes")
    @classmethod
    def trim_values(cls, value: str) -> str:
        return value.strip()


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(auth.ADMIN_DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS implementation_documents (
            document_id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            synced_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS implementation_monitoring (
            document_id TEXT PRIMARY KEY
                REFERENCES implementation_documents(document_id) ON DELETE CASCADE,
            unit TEXT NOT NULL DEFAULT '',
            pic TEXT NOT NULL DEFAULT '',
            evidence TEXT NOT NULL DEFAULT '',
            implementation_date TEXT,
            notes TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS ppepp_stages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id TEXT NOT NULL
                REFERENCES implementation_documents(document_id) ON DELETE CASCADE,
            stage TEXT NOT NULL CHECK (
                stage IN ('penetapan', 'pelaksanaan', 'evaluasi', 'pengendalian', 'peningkatan')
            ),
            activity TEXT NOT NULL DEFAULT '',
            documents_used TEXT NOT NULL DEFAULT '',
            output TEXT NOT NULL DEFAULT '',
            frequency TEXT NOT NULL DEFAULT '',
            narrative TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL,
            UNIQUE (document_id, stage)
        );
        CREATE INDEX IF NOT EXISTS idx_ppepp_stages_document
            ON ppepp_stages(document_id);
        """
    )
    return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sync_document_registry(documents: list[dict]) -> None:
    with closing(_connect()) as connection, connection:
        for document in documents:
            document_id = str(document.get("id") or "").strip()
            title = str(document.get("judul") or "").strip()
            category = str(document.get("kategori") or "").strip()
            if not document_id or not title or not category:
                continue
            connection.execute(
                """
                INSERT INTO implementation_documents (document_id, title, category, synced_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(document_id) DO UPDATE SET
                    title = excluded.title,
                    category = excluded.category,
                    synced_at = excluded.synced_at
                """,
                (document_id, title, category, _now()),
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO implementation_monitoring
                    (document_id, pic, updated_at)
                VALUES (?, ?, ?)
                """,
                (document_id, str(document.get("pic") or "").strip(), _now()),
            )


def _stage_records(connection: sqlite3.Connection, document_id: str) -> dict[str, dict]:
    rows = connection.execute(
        "SELECT id, stage, activity, documents_used, output, frequency, narrative, updated_at "
        "FROM ppepp_stages WHERE document_id = ?",
        (document_id,),
    ).fetchall()
    return {str(row["stage"]): dict(row) for row in rows}


def get_document_implementation(document_id: str, documents: list[dict]) -> dict | None:
    sync_document_registry(documents)
    document = next((item for item in documents if item.get("id") == document_id), None)
    if document is None:
        return None
    with closing(_connect()) as connection:
        monitoring = connection.execute(
            "SELECT unit, pic, evidence, implementation_date, notes, updated_at "
            "FROM implementation_monitoring WHERE document_id = ?",
            (document_id,),
        ).fetchone()
        stages = _stage_records(connection, document_id)
    return {
        "document": document,
        "monitoring": dict(monitoring) if monitoring else {},
        "stages": stages,
    }


def implementation_overview(documents: list[dict]) -> list[dict]:
    sync_document_registry(documents)
    ids = [str(item.get("id") or "") for item in documents]
    if not ids:
        return []
    placeholders = ",".join("?" for _ in ids)
    with closing(_connect()) as connection:
        monitoring_rows = connection.execute(
            f"SELECT * FROM implementation_monitoring WHERE document_id IN ({placeholders})",
            ids,
        ).fetchall()
        stage_rows = connection.execute(
            f"SELECT document_id, stage, activity, documents_used, output, frequency, narrative "
            f"FROM ppepp_stages WHERE document_id IN ({placeholders})",
            ids,
        ).fetchall()
    monitoring_by_id = {str(row["document_id"]): dict(row) for row in monitoring_rows}
    stages_by_id: dict[str, list[dict]] = {}
    for row in stage_rows:
        stages_by_id.setdefault(str(row["document_id"]), []).append(dict(row))
    overview = []
    for document in documents:
        document_id = str(document.get("id") or "")
        stages = stages_by_id.get(document_id, [])
        complete_stages = sum(
            all(str(stage.get(field) or "").strip() for field in (
                "activity",
                "documents_used",
                "output",
                "frequency",
                "narrative",
            ))
            for stage in stages
        )
        overview.append(
            {
                **document,
                **monitoring_by_id.get(document_id, {}),
                "ppepp_count": len(stages),
                "ppepp_complete": complete_stages == len(PPEPP_STAGES),
                "has_ppepp": bool(stages),
            }
        )
    return overview


def implementation_stage_counts(documents: list[dict]) -> dict[str, int]:
    sync_document_registry(documents)
    ids = [str(item.get("id") or "") for item in documents if item.get("id")]
    if not ids:
        return {stage["key"]: 0 for stage in PPEPP_STAGES}
    placeholders = ",".join("?" for _ in ids)
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT stage, COUNT(*) AS total FROM ppepp_stages "
            f"WHERE document_id IN ({placeholders}) GROUP BY stage",
            ids,
        ).fetchall()
    counts = {stage["key"]: 0 for stage in PPEPP_STAGES}
    counts.update({str(row["stage"]): int(row["total"]) for row in rows})
    return counts


def implementation_stage_complete_counts(documents: list[dict]) -> dict[str, int]:
    sync_document_registry(documents)
    ids = [str(item.get("id") or "") for item in documents if item.get("id")]
    if not ids:
        return {stage["key"]: 0 for stage in PPEPP_STAGES}
    placeholders = ",".join("?" for _ in ids)
    required_fields = ("activity", "documents_used", "output", "frequency", "narrative")
    complete_clause = " AND ".join(
        f"TRIM(COALESCE({field}, '')) <> ''" for field in required_fields
    )
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT stage, COUNT(*) AS total FROM ppepp_stages "
            f"WHERE document_id IN ({placeholders}) AND {complete_clause} "
            "GROUP BY stage",
            ids,
        ).fetchall()
    counts = {stage["key"]: 0 for stage in PPEPP_STAGES}
    counts.update({str(row["stage"]): int(row["total"]) for row in rows})
    return counts


def save_stage(
    document_id: str,
    stage: PpeppStage,
    payload: PpeppStageUpdate,
) -> dict:
    if not payload.has_content():
        raise ValueError("Isi setidaknya satu informasi pada tahap PPEPP.")
    now = _now()
    with closing(_connect()) as connection, connection:
        connection.execute(
            """
            INSERT INTO ppepp_stages
                (document_id, stage, activity, documents_used, output, frequency, narrative, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_id, stage) DO UPDATE SET
                activity = excluded.activity,
                documents_used = excluded.documents_used,
                output = excluded.output,
                frequency = excluded.frequency,
                narrative = excluded.narrative,
                updated_at = excluded.updated_at
            """,
            (
                document_id,
                stage,
                payload.activity,
                payload.documents_used,
                payload.output,
                payload.frequency,
                payload.narrative,
                now,
            ),
        )
        row = connection.execute(
            "SELECT id, document_id, stage, activity, documents_used, output, frequency, "
            "narrative, updated_at FROM ppepp_stages WHERE document_id = ? AND stage = ?",
            (document_id, stage),
        ).fetchone()
    return dict(row)


def delete_stage(document_id: str, stage: PpeppStage) -> bool:
    with closing(_connect()) as connection, connection:
        cursor = connection.execute(
            "DELETE FROM ppepp_stages WHERE document_id = ? AND stage = ?",
            (document_id, stage),
        )
    return cursor.rowcount > 0


def save_monitoring(document_id: str, payload: MonitoringUpdate) -> dict:
    with closing(_connect()) as connection, connection:
        connection.execute(
            """
            INSERT INTO implementation_monitoring
                (document_id, unit, pic, evidence, implementation_date, notes, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(document_id) DO UPDATE SET
                unit = excluded.unit,
                pic = excluded.pic,
                evidence = excluded.evidence,
                implementation_date = excluded.implementation_date,
                notes = excluded.notes,
                updated_at = excluded.updated_at
            """,
            (
                document_id,
                payload.unit,
                payload.pic,
                payload.evidence,
                payload.implementation_date.isoformat() if payload.implementation_date else None,
                payload.notes,
                _now(),
            ),
        )
        row = connection.execute(
            "SELECT document_id, unit, pic, evidence, implementation_date, notes, updated_at "
            "FROM implementation_monitoring WHERE document_id = ?",
            (document_id,),
        ).fetchone()
    return dict(row)
