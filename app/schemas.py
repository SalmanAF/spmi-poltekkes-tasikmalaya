from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


DocumentType = Literal["Standar PT", "Pedoman", "SOP"]
DocumentStatus = Literal["publik", "privat", "draft"]
PillarId = Literal["pendidikan", "penelitian", "pengabdian", "tambahan"]


class DocumentSummary(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    judul: str
    kategori: str
    kode: str = "-"
    status: DocumentStatus
    tahun: str = ""
    tahun_integrasi: str | None = None
    has_file: bool = False
    download_allowed: bool = False
    standard_id: str = ""
    guideline_id: str = ""
    parent_document_id: str = ""


class StructureNode(DocumentSummary):
    children: list[StructureNode] = Field(default_factory=list)


class StructureSummary(BaseModel):
    total_dokumen: int
    total_publik: int
    total_non_publik: int
    filter_tahun: str | None = None
    tahun_tersedia: list[str]
    per_tipe: dict[DocumentType, int]
    ketersediaan_file: dict[str, int]


class StructureTreeResponse(BaseModel):
    standards: list[StructureNode]
    unlinked: list[DocumentSummary]
    total_standards: int


class StructureSearchResponse(BaseModel):
    total: int
    limit: int
    offset: int
    documents: list[DocumentSummary]


class IntegrationStandard(BaseModel):
    standard: DocumentSummary
    pedoman: list[DocumentSummary]
    sop: list[DocumentSummary]


class IntegrationPillar(BaseModel):
    pilar_id: PillarId
    nama: str
    jumlah_standar: int
    jumlah_pedoman: int
    jumlah_sop: int
    standards: list[IntegrationStandard]


class IntegrationMapResponse(BaseModel):
    pilar: list[IntegrationPillar]


class IntegrationPillarDetail(BaseModel):
    pilar: IntegrationPillar
    total_dokumen: int
    documents: list[DocumentSummary]


class CompletenessItem(BaseModel):
    document: DocumentSummary
    siap_audit: bool
    kekurangan: list[str]


class CompletenessReport(BaseModel):
    total_dokumen: int
    siap_audit: int
    belum_lengkap: int
    persentase_siap_audit: float
    kriteria: list[str]
    documents: list[CompletenessItem]


class DocumentRelationship(BaseModel):
    sumber_id: str
    sumber_tipe: str
    target_id: str
    target_tipe: str
    relasi: str


class IntegrationReport(BaseModel):
    total_dokumen: int
    total_relasi: int
    integrasi_lengkap: int
    integrasi_belum_lengkap: int
    persentase_integrasi_lengkap: float
    dokumen_yatim: list[DocumentSummary]
    standar_tanpa_pedoman: list[DocumentSummary]
    pedoman_tanpa_sop: list[DocumentSummary]
    per_tipe_relasi: dict[str, int]
    relationships: list[DocumentRelationship]


class ImplementationReport(BaseModel):
    total_dokumen: int
    terpantau: int
    belum_terpantau: int
    memiliki_data_ppepp: int
    ppepp_lengkap: int
    persentase_ppepp_lengkap: float
    ppepp_belum_lengkap: list[DocumentSummary]
    per_tahap: dict[str, int]
    tahap_lengkap: dict[str, int]


class RevisionItem(BaseModel):
    document: DocumentSummary
    alasan: list[str]
    berlaku_sampai: str | None = None
    status_revisi: str | None = None
    sumber_revisi: str | None = None
    catatan_revisi: str = ""
    ditinjau_pada: str = ""


class RevisionReport(BaseModel):
    data_tersedia: bool
    total: int
    message: str
    kedaluwarsa: int
    dalam_peninjauan: int
    perlu_revisi: int
    documents: list[RevisionItem]


class DocumentTrend(BaseModel):
    tahun: str
    dokumen_baru: int
    kumulatif: int


class DevelopmentReport(BaseModel):
    total_dokumen: int
    basis_tanggal: str
    catatan: str
    perkembangan: list[DocumentTrend]


class ReportExportSummary(BaseModel):
    total_dokumen: int
    siap_audit: int
    belum_lengkap: int
    total_relasi: int
    terpantau: int
    ppepp_lengkap: int
    persentase_siap_audit: float
    persentase_integrasi_lengkap: float
    persentase_ppepp_lengkap: float
    kedaluwarsa: int
    dalam_peninjauan: int
    perlu_revisi: int
