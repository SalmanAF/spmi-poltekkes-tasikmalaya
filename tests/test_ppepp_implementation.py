import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import auth, implementation
from app import main


class PpeppImplementationTests(unittest.TestCase):
    documents = [
        {
            "id": "doc-test-a",
            "judul": "SOP Kegiatan PKM",
            "kode": "SOP-PKM-01",
            "kategori": "SOP",
            "pic": "PIC awal",
        },
        {
            "id": "doc-test-b",
            "judul": "Pedoman Akademik",
            "kode": "PED-01",
            "kategori": "Pedoman",
            "pic": "",
        },
    ]

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_patch = patch.object(
            auth,
            "ADMIN_DB_PATH",
            Path(self.temporary_directory.name) / "admin_auth.sqlite3",
        )
        self.database_patch.start()
        self.environment_patch = patch.dict(os.environ, {"SPMI_ADMIN_TOKEN": ""})
        self.environment_patch.start()
        self.documents_patch = patch.object(
            main, "all_documents", return_value=self.documents
        )
        self.documents_patch.start()
        auth.initialize_auth_db()
        implementation.sync_document_registry(self.documents)
        auth.register_admin(
            "Administrator Uji",
            "admin.uji",
            "admin.uji@example.ac.id",
            "StrongPassword123!",
        )
        self.client = TestClient(main.app, follow_redirects=False)
        self._login()

    def tearDown(self):
        self.client.close()
        self.documents_patch.stop()
        self.environment_patch.stop()
        self.database_patch.stop()
        self.temporary_directory.cleanup()

    @staticmethod
    def _csrf(response):
        match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
        if match is None:
            raise AssertionError("CSRF token tidak ditemukan.")
        return match.group(1)

    @staticmethod
    def _page_csrf(response):
        match = re.search(r'<meta name="csrf-token" content="([^"]+)"', response.text)
        if match is None:
            raise AssertionError("Token CSRF halaman tidak ditemukan.")
        return match.group(1)

    def _login(self):
        page = self.client.get("/admin/login")
        response = self.client.post(
            "/admin/login",
            data={
                "csrf_token": self._csrf(page),
                "username_or_email": "admin.uji",
                "password": "StrongPassword123!",
            },
        )
        self.assertEqual(response.status_code, 303)

    def test_admin_pages_provide_id_specific_ppepp_forms(self):
        monitoring_page = self.client.get("/admin/monitoring")
        self.assertEqual(monitoring_page.status_code, 200)
        self.assertIn("Isi PPEPP", monitoring_page.text)
        self.assertIn("document_id=doc-test-a", monitoring_page.text)
        self.assertIn("<th>Bentuk Implementasi</th>", monitoring_page.text)
        self.assertNotIn("<th>Status Implementasi</th>", monitoring_page.text)
        self.assertIn('id="implementationMonitoringSearch"', monitoring_page.text)
        self.assertIn('id="implementationMonitoringCount"', monitoring_page.text)
        self.assertIn('data-monitoring-record', monitoring_page.text)
        self.assertIn("admin-monitoring-search.js", monitoring_page.text)

        implementation_page = self.client.get(
            "/admin/implementasi?document_id=doc-test-a"
        )
        self.assertEqual(implementation_page.status_code, 200)
        self.assertIn("Tahapan PPEPP", implementation_page.text)
        self.assertIn("SOP Kegiatan PKM", implementation_page.text)
        self.assertIn('data-stage="penetapan"', implementation_page.text)
        self.assertIn('data-stage="peningkatan"', implementation_page.text)

    def test_stage_crud_is_persistent_unique_and_scoped_to_document(self):
        csrf = self._page_csrf(self.client.get("/admin/implementasi?document_id=doc-test-a"))
        headers = {"X-CSRF-Token": csrf}
        stages = ("penetapan", "pelaksanaan", "evaluasi", "pengendalian", "peningkatan")
        for stage in stages:
            response = self.client.put(
                f"/api/admin/implementations/doc-test-a/ppepp/{stage}",
                headers=headers,
                json={
                    "activity": f"Aktivitas {stage}",
                    "documents_used": f"Dokumen {stage}",
                    "output": f"Output {stage}",
                    "frequency": "Tahunan",
                    "narrative": f"Narasi nyata {stage}",
                },
            )
            self.assertEqual(response.status_code, 200, response.text)

        overview = self.client.get("/api/admin/implementations")
        row = next(
            item for item in overview.json()["implementations"]
            if item["id"] == "doc-test-a"
        )
        self.assertTrue(row["has_ppepp"])
        self.assertTrue(row["ppepp_complete"])
        self.assertEqual(row["ppepp_count"], 5)
        monitoring_page = self.client.get("/admin/monitoring")
        self.assertIn("Lihat/Edit PPEPP", monitoring_page.text)

        before = self.client.get(
            "/api/admin/implementations/doc-test-a"
        ).json()["stages"]["evaluasi"]["id"]
        self.client.put(
            "/api/admin/implementations/doc-test-a/ppepp/evaluasi",
            headers=headers,
            json={
                "activity": "Aktivitas evaluasi diperbarui",
                "documents_used": "Dokumen evaluasi",
                "output": "Output evaluasi",
                "frequency": "Semester",
                "narrative": "Narasi hasil evaluasi terbaru",
            },
        )
        reloaded = self.client.get(
            "/api/admin/implementations/doc-test-a"
        ).json()["stages"]["evaluasi"]
        self.assertEqual(reloaded["id"], before)
        self.assertEqual(reloaded["frequency"], "Semester")
        self.assertEqual(reloaded["narrative"], "Narasi hasil evaluasi terbaru")

        other_document = self.client.get(
            "/api/admin/implementations/doc-test-b"
        ).json()
        self.assertEqual(other_document["stages"], {})
        self.client.put(
            "/api/admin/implementations/doc-test-b/ppepp/penetapan",
            headers=headers,
            json={
                "activity": "Aktivitas dokumen B",
                "documents_used": "Dokumen B",
                "output": "Output B",
                "frequency": "Tahunan",
                "narrative": "Narasi dokumen B",
            },
        )
        deleted = self.client.delete(
            "/api/admin/implementations/doc-test-a/ppepp/penetapan",
            headers=headers,
        )
        self.assertEqual(deleted.status_code, 200)
        updated = self.client.get(
            "/api/admin/implementations/doc-test-a"
        ).json()["stages"]
        self.assertNotIn("penetapan", updated)
        self.assertEqual(len(updated), 4)
        other_stages = self.client.get(
            "/api/admin/implementations/doc-test-b"
        ).json()["stages"]
        self.assertEqual(set(other_stages), {"penetapan"})
        self.assertEqual(other_stages["penetapan"]["narrative"], "Narasi dokumen B")

    def test_monitoring_metadata_is_saved_and_ppepp_api_requires_admin(self):
        csrf = self._page_csrf(self.client.get("/admin/implementasi?document_id=doc-test-a"))
        response = self.client.put(
            "/api/admin/implementations/doc-test-a/monitoring",
            headers={"X-CSRF-Token": csrf},
            json={
                "unit": "LP2M",
                "pic": "Admin Uji",
                "evidence": "Berita acara",
                "implementation_date": "2026-10-12",
                "notes": "Catatan monitoring",
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        monitoring = self.client.get("/admin/monitoring")
        self.assertIn("LP2M", monitoring.text)
        self.assertIn("Berita acara", monitoring.text)
        self.assertIn("Admin Uji", monitoring.text)
        self.assertIn("Isi PPEPP", monitoring.text)

        self.client.post(
            "/admin/logout",
            data={"csrf_token": self._csrf(self.client.get("/admin/dashboard"))},
        )
        protected = self.client.put(
            "/api/admin/implementations/doc-test-a/ppepp/penetapan",
            json={"narrative": "Tidak boleh"},
        )
        self.assertEqual(protected.status_code, 401)


if __name__ == "__main__":
    unittest.main()
