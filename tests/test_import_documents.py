import unittest
from unittest.mock import patch

from openpyxl import Workbook

from app.user_documents import integration_map_documents
from import_documents import read_integration_sheet


class ImportIntegrationSheetTests(unittest.TestCase):
    def integration_workbook(self, sheet_name: str) -> Workbook:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = sheet_name
        sheet.append(["No", "Judul Standar", "No Dokumen Pedoman/ SOP", "PIC", "Link Dokumen"])
        return workbook

    def test_2022_rows_preserve_standard_pedoman_and_sop_relationships(self):
        workbook = self.integration_workbook("Integrasi Standar 2022")
        sheet = workbook.active
        sheet.append(["A", "Pelampauan", None, None, None])
        sheet.append([1, "Standar Uji", "STD-01", None, ""])
        sheet.append([None, "Pedoman Uji", "PED-01", None, ""])
        sheet.append([None, "SOP Uji", "SOP-01", None, ""])
        sheet.append([None, "Subjudul Uji", "DOC-01", None, ""])

        records = read_integration_sheet(workbook, sheet.title, True)

        standards = [record for record in records if record["kategori"] == "Standar PT"]
        guideline = next(record for record in records if record["judul"] == "Pedoman Uji")
        procedure = next(record for record in records if record["judul"] == "SOP Uji")
        subtitle = next(record for record in records if record["judul"] == "Subjudul Uji")

        self.assertEqual(len(standards), 1)
        self.assertEqual(standards[0]["subjudul"], "Pelampauan")
        self.assertEqual(guideline["standard_id"], standards[0]["id"])
        self.assertEqual(procedure["guideline_id"], guideline["id"])
        self.assertEqual(procedure["parent_document_id"], guideline["id"])
        self.assertEqual(subtitle["kategori"], "Lainnya")
        self.assertEqual(subtitle["standard_id"], standards[0]["id"])
        self.assertEqual(subtitle["tahun_integrasi"], "2022")
        workbook.close()

    def test_2025_letter_groups_keep_subtitles_and_standalone_guideline(self):
        workbook = self.integration_workbook("Integrasi Standar 2025")
        sheet = workbook.active
        sheet.append([None, "Kebijakan SPMI PT", "KEB-01", None, ""])
        sheet.append([None, "Pedoman Siklus PPEPP", "PED-01", None, ""])
        sheet.append(["A", "Standar Pendidikan", "STD-01", "PIC Pendidikan", ""])
        sheet.append([None, "Pengolahan Karya Tulis Tercetak", "DOC-01", "PIC Perpustakaan", ""])
        sheet.append(["B", "Standar Penelitian", "STD-02", None, ""])
        sheet.append(["E", "Pedoman Tata Cara Pendokumentasian Dokumen SPMI", "PED-02", None, ""])

        records = read_integration_sheet(workbook, sheet.title, True)
        standards = [record for record in records if record["kategori"] == "Standar PT"]
        subtitle = next(record for record in records if record["judul"] == "Pengolahan Karya Tulis Tercetak")
        standalone_guideline = next(
            record
            for record in records
            if record["judul"] == "Pedoman Tata Cara Pendokumentasian Dokumen SPMI"
        )

        self.assertEqual(
            [record["judul"] for record in standards],
            ["Standar Pendidikan", "Standar Penelitian"],
        )
        self.assertEqual(standards[0]["subjudul"], "Standar Pendidikan")
        self.assertEqual(standards[0]["pic"], "PIC Pendidikan")
        self.assertEqual(standards[0]["source_sheet"], "Integrasi Standar 2025")
        self.assertEqual(standards[0]["source_row"], 4)
        self.assertEqual(subtitle["kategori"], "Lainnya")
        self.assertEqual(subtitle["standard_id"], standards[0]["id"])
        self.assertEqual(subtitle["pic"], "PIC Perpustakaan")
        self.assertEqual(subtitle["source_row"], 5)
        self.assertEqual(standalone_guideline["standard_id"], "")
        self.assertTrue(all(record["tahun_integrasi"] == "2025" for record in records))
        workbook.close()

    def test_integration_map_only_uses_2022_and_2025_sheets(self):
        documents = [
            {"id": "2022", "tahun_integrasi": "2022"},
            {"id": "2025", "tahun_integrasi": "2025"},
            {"id": "pedoman-register", "tahun_integrasi": ""},
            {"id": "sop-register", "tahun_integrasi": None},
        ]

        with patch("app.user_documents.public_documents", return_value=documents):
            result = integration_map_documents()

        self.assertEqual([document["id"] for document in result], ["2022", "2025"])
