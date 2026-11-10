import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.document_years import infer_document_year
from app.main import app, require_admin
from app.user_documents import DocumentRecord
from migrate_document_years import migrate_manifest


class DocumentYearFilterTests(unittest.TestCase):
    def setUp(self):
        uploaded_at = "2026-10-08T00:00:00+00:00"
        self.documents = [
            self.make_document(
                "std-2024",
                "Standar Tata Kelola 2024",
                "Standar PT",
                "STD-24",
                "2024",
                "2024-06-01",
                "Mutu",
                uploaded_at,
            ),
            self.make_document(
                "guide-2017",
                "Panduan Sipenmaru PMDP 2017",
                "Pedoman",
                "PED-17",
                "2017",
                "2017-02-01",
                "PMDP",
                uploaded_at,
            ),
            self.make_document(
                "guide-2018",
                "Panduan Sipenmaru PMDP 2018",
                "Pedoman",
                "PED-18",
                "2018",
                "2018-02-01",
                "PMDP",
                uploaded_at,
            ),
            self.make_document(
                "sop-2022",
                "SOP Pelayanan 2022",
                "SOP",
                "SOP-22",
                "2022",
                "2022-03-01",
                "Layanan",
                uploaded_at,
            ),
        ]
        app.dependency_overrides[require_admin] = lambda: None
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        app.dependency_overrides.pop(require_admin, None)

    @staticmethod
    def make_document(
        document_id,
        title,
        category,
        code,
        year,
        document_date,
        unit,
        created_at,
    ):
        return {
            "id": document_id,
            "judul": title,
            "kategori": category,
            "kode": code,
            "no_dokumen": code,
            "tahun": year,
            "document_year": year,
            "document_date": document_date,
            "unit": unit,
            "created_at": created_at,
            "updated_at": created_at,
            "status": "publik",
            "tipe_sumber": "drive_link",
            "file_url": "https://drive.google.com/file/d/example",
            "preview_url": "https://drive.google.com/file/d/example/preview",
            "file_format": "PDF",
            "has_file": True,
            "is_downloadable": True,
            "download_allowed": True,
        }

    def test_year_search_and_combined_filters_work_on_all_public_pages(self):
        with patch("app.main.public_documents", return_value=self.documents):
            cases = (
                (
                    "/standar-pt",
                    {
                        "q": "STD-24",
                        "kategori": "Standar PT",
                        "unit": "Mutu",
                        "tahun": "2024",
                    },
                    "Standar Tata Kelola 2024",
                ),
                (
                    "/pedoman",
                    {
                        "q": "PMDP",
                        "kategori": "Pedoman",
                        "unit": "PMDP",
                        "tahun": "2017",
                    },
                    "Panduan Sipenmaru PMDP 2017",
                ),
                (
                    "/pedoman",
                    {
                        "q": "Panduan",
                        "kategori": "Pedoman",
                        "tahun": "2018",
                    },
                    "Panduan Sipenmaru PMDP 2018",
                ),
                (
                    "/sop",
                    {
                        "q": "Pelayanan",
                        "kategori": "SOP",
                        "unit": "Layanan",
                        "tahun": "2022",
                    },
                    "SOP Pelayanan 2022",
                ),
            )
            for path, filters, expected_title in cases:
                with self.subTest(path=path, filters=filters):
                    response = self.client.get(path, params=filters)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn(expected_title, response.text)
                    self.assertIn("1</strong><span>dokumen ditemukan", response.text)

    def test_all_years_and_year_2022_do_not_use_upload_year(self):
        with patch("app.main.public_documents", return_value=self.documents):
            all_years = self.client.get("/katalog")
            self.assertEqual(all_years.status_code, 200)
            self.assertIn("4</strong><span>dokumen ditemukan", all_years.text)

            year_2022 = self.client.get("/katalog", params={"tahun": "2022"})
            self.assertEqual(year_2022.status_code, 200)
            self.assertIn("SOP Pelayanan 2022", year_2022.text)
            self.assertNotIn("Panduan Sipenmaru", year_2022.text)
            self.assertIn("Diunggah 2026-10-08", year_2022.text)
            self.assertIn("Lihat detail", year_2022.text)

    def test_integer_document_year_matches_string_query_and_stays_selected(self):
        documents = [dict(document) for document in self.documents]
        pedoman = documents[1]
        pedoman["document_year"] = 2017
        pedoman["tahun"] = 2017

        with patch("app.main.public_documents", return_value=documents):
            response = self.client.get("/pedoman", params={"tahun": "2017"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("Panduan Sipenmaru PMDP 2017", response.text)
        self.assertIn('option value="2017" selected', response.text)
        self.assertIn("1</strong><span>dokumen ditemukan", response.text)

    def test_pagination_keeps_selected_document_year(self):
        records = [
            self.make_document(
                f"doc-{index}",
                f"Dokumen {index}",
                "Pedoman",
                f"PED-{index}",
                "2017",
                "2017-01-01",
                "Mutu",
                "2026-10-08",
            )
            for index in range(13)
        ]
        with patch("app.main.public_documents", return_value=records):
            first_page = self.client.get("/pedoman", params={"tahun": "2017"})
            self.assertEqual(first_page.status_code, 200)
            self.assertIn("Menampilkan 12 dari 13", first_page.text)
            self.assertIn("tahun=2017", first_page.text)

            second_page = self.client.get(
                "/pedoman",
                params={"tahun": "2017", "halaman": "2"},
            )
            self.assertEqual(second_page.status_code, 200)
            self.assertIn("Menampilkan 1 dari 13", second_page.text)
            self.assertIn("Dokumen 12", second_page.text)

    def test_public_detail_shows_document_and_upload_dates_separately(self):
        document = self.documents[1]
        with patch("app.main.public_document", return_value=document):
            response = self.client.get("/dokumen/guide-2017")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Tanggal dokumen", response.text)
        self.assertIn("2017-02-01", response.text)
        self.assertIn("Tanggal diunggah", response.text)
        self.assertIn("2026-10-08", response.text)
        self.assertIn("Unduh", response.text)

    def test_admin_pages_offer_document_date_and_year_fields(self):
        with patch("app.main.current_admin", return_value={"id": "test-admin"}):
            for path in (
                "/admin/standar-pt",
                "/admin/pedoman",
                "/admin/sop",
                "/pengaturan",
            ):
                with self.subTest(path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 200)
                    self.assertIn('name="document_date"', response.text)
                    self.assertIn('name="document_year"', response.text)

    def test_legacy_year_and_date_only_metadata_are_independent_of_upload_date(self):
        legacy = DocumentRecord.model_validate(
            {
                "id": "legacy",
                "judul": "Dokumen tahun 2018",
                "kategori": "Pedoman",
                "tahun": "2018",
                "created_at": "2026-10-08",
                "source_sheet": "Dokumen Lama",
                "legacy_metadata": {"row": 4},
                "tipe_sumber": "drive_link",
            }
        )
        self.assertEqual(legacy.document_year, "2018")
        self.assertEqual(legacy.tahun, "2018")
        self.assertEqual(legacy.created_at, "2026-10-08")
        self.assertEqual(legacy.model_dump()["legacy_metadata"], {"row": 4})

        dated = DocumentRecord.model_validate(
            {
                "id": "dated",
                "judul": "Dokumen bertanggal",
                "kategori": "SOP",
                "document_date": "2022-03-01",
                "document_year": "2026",
                "created_at": "2026-10-08",
                "tipe_sumber": "drive_link",
            }
        )
        self.assertEqual(dated.document_year, "2022")
        self.assertEqual(dated.tahun, "2022")

    def test_year_inference_prefers_document_metadata_not_upload_date(self):
        self.assertEqual(
            infer_document_year(
                {
                    "judul": "Panduan Sipenmaru PMDP Tahun 2017",
                    "created_at": "2026-10-08",
                }
            ),
            "2017",
        )
        self.assertEqual(
            infer_document_year(
                {
                    "judul": "SOP Pelayanan",
                    "no_dokumen": "PR:PJM/36/04/02/2022/R2",
                    "created_at": "2026-10-08",
                }
            ),
            "2022",
        )
        self.assertEqual(
            infer_document_year(
                {
                    "judul": "Judul tanpa tahun",
                    "tahun": "2026",
                    "created_at": "2026-10-08",
                }
            ),
            "",
        )

    def test_migration_dry_run_and_apply_keep_backup_and_other_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            manifest = Path(directory) / "documents.json"
            original_records = [
                {
                    "id": "known",
                    "judul": "Panduan PMDP Tahun 2017",
                    "kategori": "Pedoman",
                    "no_dokumen": "-",
                    "tahun": "2026",
                    "created_at": "2026-10-08",
                    "custom_metadata": {"owner": "Pusjamu"},
                },
                {
                    "id": "unknown",
                    "judul": "Dokumen tanpa tahun",
                    "kategori": "SOP",
                    "tahun": "2026",
                    "created_at": "2026-10-08",
                },
            ]
            manifest.write_text(
                json.dumps(original_records),
                encoding="utf-8",
            )
            original_bytes = manifest.read_bytes()

            preview = migrate_manifest(manifest)
            self.assertEqual(preview["changed"], 2)
            self.assertEqual(preview["inferred"], 1)
            self.assertEqual(preview["unresolved"], 1)
            self.assertIsNone(preview["backup"])
            self.assertEqual(manifest.read_bytes(), original_bytes)

            applied = migrate_manifest(manifest, apply=True)
            migrated_records = json.loads(
                manifest.read_text(encoding="utf-8")
            )
            self.assertEqual(applied["changed"], 2)
            self.assertIsNotNone(applied["backup"])
            self.assertEqual(Path(applied["backup"]).read_bytes(), original_bytes)
            self.assertEqual(migrated_records[0]["document_year"], "2017")
            self.assertEqual(migrated_records[0]["tahun"], "2017")
            self.assertEqual(
                migrated_records[0]["custom_metadata"],
                {"owner": "Pusjamu"},
            )
            self.assertEqual(migrated_records[1]["document_year"], "")
            self.assertEqual(migrated_records[1]["tahun"], "")

    def test_admin_can_create_and_edit_document_date_and_year(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch("app.user_documents.MANIFEST_PATH", root / "documents.json"),
                patch("app.user_documents.UPLOADS_DIR", root),
                patch("app.main.current_admin", return_value={"id": "test-admin"}),
                patch("app.main.utc_now", return_value="2026-10-08T00:00:00+00:00"),
                patch(
                    "app.user_documents.utc_now",
                    return_value="2026-10-09T00:00:00+00:00",
                ),
            ):
                created = self.client.post(
                    "/admin/documents/add",
                    json={
                        "judul": "Panduan PMDP 2017",
                        "kode": "PED-17",
                        "kategori": "Pedoman",
                        "document_date": "2017-02-01",
                        "document_year": "2026",
                        "unit": "PMDP",
                        "link_download": "https://drive.google.com/file/d/example",
                        "status": "publik",
                    },
                )
                self.assertEqual(created.status_code, 201, created.text)
                created_document = created.json()["document"]
                document_id = created_document["id"]
                self.assertEqual(created_document["document_year"], "2017")
                self.assertEqual(created_document["created_at"], "2026-10-08T00:00:00+00:00")

                edited = self.client.post(
                    f"/admin/documents/edit/{document_id}",
                    json={
                        "document_date": "2018-05-10",
                        "document_year": "2026",
                    },
                )
                self.assertEqual(edited.status_code, 200)
                updated_document = edited.json()["document"]
                self.assertEqual(updated_document["document_year"], "2018")
                self.assertEqual(updated_document["tahun"], "2018")
                self.assertEqual(updated_document["created_at"], created_document["created_at"])
                self.assertEqual(updated_document["updated_at"], "2026-10-09T00:00:00+00:00")

                api_created = self.client.post(
                    "/api/admin/documents",
                    data={
                        "judul": "SOP Layanan 2022",
                        "kategori": "SOP",
                        "tipe_sumber": "drive_link",
                        "no_dokumen": "SOP-22",
                        "document_date": "2022-03-01",
                        "document_year": "2026",
                        "unit": "Layanan",
                        "status": "publik",
                        "is_downloadable": "true",
                        "file_url": "https://drive.google.com/file/d/example",
                    },
                )
                self.assertEqual(api_created.status_code, 201, api_created.text)
                self.assertEqual(
                    api_created.json()["document"]["document_year"], "2022"
                )

                api_document_id = api_created.json()["document"]["id"]
                api_edited = self.client.put(
                    f"/api/admin/documents/{api_document_id}",
                    json={"document_date": "2024-04-04"},
                )
                self.assertEqual(api_edited.status_code, 200, api_edited.text)
                self.assertEqual(
                    api_edited.json()["document"]["document_year"], "2024"
                )
