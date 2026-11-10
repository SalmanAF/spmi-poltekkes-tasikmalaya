import os
import re
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import auth
from app.main import app


class AdminAuthenticationTests(unittest.TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.database_patch = patch.object(
            auth,
            "ADMIN_DB_PATH",
            Path(self.temporary_directory.name) / "admin_auth.sqlite3",
        )
        self.database_patch.start()
        self.environment_patch = patch.dict(
            os.environ,
            {
                "SPMI_ADMIN_SETUP_TOKEN": "test-setup-token-with-at-least-32-characters",
                "SPMI_ADMIN_TOKEN": "",
            },
        )
        self.environment_patch.start()
        auth.initialize_auth_db()
        self.client = TestClient(app, follow_redirects=False)

    def tearDown(self):
        self.client.close()
        self.environment_patch.stop()
        self.database_patch.stop()
        self.temporary_directory.cleanup()

    @staticmethod
    def csrf(response):
        match = re.search(r'name="csrf_token" value="([^"]+)"', response.text)
        if match is None:
            raise AssertionError("CSRF token tidak ditemukan pada formulir.")
        return match.group(1)

    @staticmethod
    def page_csrf(response):
        match = re.search(r'<meta name="csrf-token" content="([^"]+)"', response.text)
        if match is None:
            raise AssertionError("CSRF token halaman tidak ditemukan.")
        return match.group(1)

    def create_first_admin(self):
        setup_page = self.client.get("/admin/setup")
        self.assertEqual(setup_page.status_code, 200)
        return self.client.post(
            "/admin/setup",
            data={
                "csrf_token": self.csrf(setup_page),
                "setup_token": "test-setup-token-with-at-least-32-characters",
                "full_name": "Administrator Utama",
                "username": "admin.utama",
                "email": "admin@example.ac.id",
                "password": "StrongPassword123!",
                "password_confirmation": "StrongPassword123!",
            },
        )

    def test_admin_pages_and_api_are_protected_before_login(self):
        for path in (
            "/admin/dashboard",
            "/admin/struktur-dokumen",
            "/pengaturan",
        ):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 303)
            self.assertEqual(response.headers["location"], "/admin/login")

        response = self.client.get("/api/admin/documents")
        self.assertEqual(response.status_code, 401)
        public_home = self.client.get("/")
        self.assertEqual(public_home.status_code, 200)
        self.assertIn('class="user-brand-logo"', public_home.text)
        self.assertIn("images/poltekkes-kemenkes-tasikmalaya.png", public_home.text)
        self.assertNotIn('<span class="brand-monogram">PKT</span>', public_home.text)

    def test_setup_grants_first_admin_access_and_logout_ends_session(self):
        setup_response = self.create_first_admin()
        self.assertEqual(setup_response.status_code, 303)
        self.assertEqual(setup_response.headers["location"], "/admin/dashboard")
        dashboard = self.client.get("/admin/dashboard")
        self.assertEqual(dashboard.status_code, 200)
        self.assertIn('class="sidebar-logo"', dashboard.text)
        self.assertIn("images/poltekkes-kemenkes-tasikmalaya.png", dashboard.text)
        self.assertNotIn("<span>PKT</span>", dashboard.text)
        self.assertEqual(self.client.get("/admin/struktur-dokumen").status_code, 200)
        self.assertEqual(self.client.get("/api/admin/documents").status_code, 200)
        with closing(sqlite3.connect(auth.ADMIN_DB_PATH)) as connection:
            stored_hash = connection.execute(
                "SELECT password_hash FROM admin_accounts WHERE username = ?",
                ("admin.utama",),
            ).fetchone()[0]
        self.assertTrue(stored_hash.startswith("scrypt$"))
        self.assertNotIn("StrongPassword123!", stored_hash)
        self.assertEqual(self.client.get("/admin/setup").status_code, 404)

        dashboard = self.client.get("/admin/dashboard")
        csrf_token = self.page_csrf(dashboard)
        self.assertEqual(
            self.client.put(
                "/api/admin/documents/not-found",
                json={"status": "draft"},
            ).status_code,
            403,
        )
        self.assertEqual(
            self.client.put(
                "/api/admin/documents/not-found",
                json={"status": "draft"},
                headers={"X-CSRF-Token": csrf_token},
            ).status_code,
            404,
        )
        logout_response = self.client.post(
            "/admin/logout", data={"csrf_token": self.csrf(dashboard)}
        )
        self.assertEqual(logout_response.status_code, 303)
        self.assertEqual(self.client.get("/admin/dashboard").status_code, 303)

    def test_registration_waits_for_approval_before_login(self):
        register_page = self.client.get("/admin/register")
        registration = {
            "csrf_token": self.csrf(register_page),
            "full_name": "Admin Baru",
            "username": "admin.baru",
            "email": "admin.baru@example.ac.id",
            "password": "StrongPassword123!",
            "password_confirmation": "StrongPassword123!",
        }
        response = self.client.post("/admin/register", data=registration)
        self.assertEqual(response.status_code, 303)
        self.assertIn("registration-success", response.headers["location"])
        self.assertNotIn("pending", response.headers["location"])
        with closing(sqlite3.connect(auth.ADMIN_DB_PATH)) as connection:
            status, role = connection.execute(
                "SELECT status, role FROM admin_accounts WHERE username = ?",
                ("admin.baru",),
            ).fetchone()
        self.assertEqual(status, "pending")
        self.assertEqual(role, "verifikator")

        duplicate = self.client.post("/admin/register", data=registration)
        self.assertEqual(duplicate.status_code, 400)
        self.assertIn("Username atau email sudah digunakan", duplicate.text)

        login_page = self.client.get("/admin/login")
        invalid_login = self.client.post(
            "/admin/login",
            data={
                "csrf_token": self.csrf(login_page),
                "username_or_email": "admin.baru",
                "password": "wrong-password",
            },
        )
        self.assertIn("Username/email atau password salah.", invalid_login.text)
        self.assertNotIn("wrong-password", invalid_login.text)

        login_page = self.client.get("/admin/login")
        pending_login = self.client.post(
            "/admin/login",
            data={
                "csrf_token": self.csrf(login_page),
                "username_or_email": "admin.baru",
                "password": "StrongPassword123!",
            },
        )
        self.assertEqual(pending_login.status_code, 400)
        self.assertIn("menunggu verifikasi", pending_login.text)
        self.assertEqual(self.client.get("/admin/dashboard").status_code, 303)

    def test_pending_accounts_remain_pending_on_database_migration(self):
        with closing(sqlite3.connect(auth.ADMIN_DB_PATH)) as connection:
            connection.execute("DROP TABLE admin_accounts")
            connection.execute(
                """
                CREATE TABLE admin_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_hash TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'active')),
                    created_at TEXT NOT NULL,
                    approved_at TEXT,
                    approved_by INTEGER REFERENCES admin_accounts(id)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO admin_accounts
                    (full_name, username, email, password_hash, status, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?)
                """,
                (
                    "Admin Lama",
                    "admin.lama",
                    "admin.lama@example.ac.id",
                    auth.hash_password("StrongPassword123!"),
                    "2026-10-12T00:00:00+00:00",
                ),
            )
            connection.commit()

        auth.initialize_auth_db()
        account = auth.authenticate_admin("admin.lama", "StrongPassword123!")
        self.assertIsNotNone(account)
        self.assertEqual(account["status"], "pending")
        self.assertIsNone(auth.get_active_admin(account["id"]))
        with closing(sqlite3.connect(auth.ADMIN_DB_PATH)) as connection:
            status = connection.execute(
                "SELECT status FROM admin_accounts WHERE username = ?",
                ("admin.lama",),
            ).fetchone()[0]
        self.assertEqual(status, "pending")

    def test_legacy_active_accounts_keep_access_after_schema_migration(self):
        with closing(sqlite3.connect(auth.ADMIN_DB_PATH)) as connection:
            connection.execute("DROP TABLE admin_accounts")
            connection.execute(
                """
                CREATE TABLE admin_accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    full_name TEXT NOT NULL,
                    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    password_hash TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active' CHECK (status = 'active'),
                    created_at TEXT NOT NULL,
                    approved_at TEXT,
                    approved_by INTEGER REFERENCES admin_accounts(id)
                )
                """
            )
            connection.execute(
                """
                INSERT INTO admin_accounts
                    (full_name, username, email, password_hash, status, created_at)
                VALUES (?, ?, ?, ?, 'active', ?)
                """,
                (
                    "Admin Legacy",
                    "admin.legacy",
                    "admin.legacy@example.ac.id",
                    auth.hash_password("StrongPassword123!"),
                    "2026-10-12T00:00:00+00:00",
                ),
            )
            connection.commit()

        auth.initialize_auth_db()
        account = auth.authenticate_admin("admin.legacy", "StrongPassword123!")
        self.assertIsNotNone(account)
        self.assertEqual(account["status"], "active")
        self.assertEqual(account["role"], "super_admin")
        self.assertIsNotNone(auth.get_active_admin(account["id"]))

    def test_verifikator_can_approve_pending_and_super_admin_can_create_accounts(self):
        registration_page = self.client.get("/admin/register")
        self.client.post(
            "/admin/register",
            data={
                "csrf_token": self.csrf(registration_page),
                "full_name": "Pemohon",
                "username": "pemohon",
                "email": "pemohon@example.ac.id",
                "password": "StrongPassword123!",
                "password_confirmation": "StrongPassword123!",
            },
        )
        with closing(sqlite3.connect(auth.ADMIN_DB_PATH)) as connection:
            pending_id = connection.execute(
                "SELECT id FROM admin_accounts WHERE username = ?", ("pemohon",)
            ).fetchone()[0]
        self.assertEqual(self.create_first_admin().status_code, 303)

        page = self.client.get("/admin/verifikasi-akun")
        self.assertEqual(page.status_code, 200)
        self.assertIn("pemohon@example.ac.id", page.text)
        approved = self.client.post(
            f"/admin/verifikasi-akun/{pending_id}/approve",
            data={"csrf_token": self.page_csrf(page)},
        )
        self.assertEqual(approved.status_code, 303)
        self.assertEqual(auth.get_active_admin(pending_id)["status"], "active")

        page = self.client.get("/admin/verifikasi-akun")
        created = self.client.post(
            "/admin/verifikasi-akun/accounts",
            data={
                "csrf_token": self.page_csrf(page),
                "full_name": "Verifikator Baru",
                "username": "verifikator.baru",
                "email": "verifikator.baru@example.ac.id",
                "password": "StrongPassword123!",
                "password_confirmation": "StrongPassword123!",
                "role": "verifikator",
            },
        )
        self.assertEqual(created.status_code, 303)
        with closing(sqlite3.connect(auth.ADMIN_DB_PATH)) as connection:
            status, role = connection.execute(
                "SELECT status, role FROM admin_accounts WHERE username = ?",
                ("verifikator.baru",),
            ).fetchone()
        self.assertEqual(status, "active")
        self.assertEqual(role, "verifikator")

        dashboard = self.client.get("/admin/dashboard")
        self.client.post(
            "/admin/logout", data={"csrf_token": self.csrf(dashboard)}
        )
        verifier = TestClient(app, follow_redirects=False)
        try:
            login_page = verifier.get("/admin/login")
            login = verifier.post(
                "/admin/login",
                data={
                    "csrf_token": self.csrf(login_page),
                    "username_or_email": "verifikator.baru",
                    "password": "StrongPassword123!",
                },
            )
            self.assertEqual(login.status_code, 303)
            page = verifier.get("/admin/verifikasi-akun")
            self.assertEqual(page.status_code, 403)
            dashboard = verifier.get("/admin/dashboard")
            self.assertNotIn("/admin/verifikasi-akun", dashboard.text)
            forbidden = verifier.post(
                "/admin/verifikasi-akun/accounts",
                data={
                    "csrf_token": self.page_csrf(dashboard),
                    "full_name": "Admin Terlarang",
                    "username": "admin.terlarang",
                    "email": "admin.terlarang@example.ac.id",
                    "password": "StrongPassword123!",
                    "password_confirmation": "StrongPassword123!",
                    "role": "super_admin",
                },
            )
            self.assertEqual(forbidden.status_code, 403)
            for action in ("approve", "reject"):
                denied = verifier.post(
                    f"/admin/verifikasi-akun/1/{action}",
                    data={"csrf_token": self.page_csrf(dashboard)},
                )
                self.assertEqual(denied.status_code, 403)
        finally:
            verifier.close()

    def test_verifikator_can_reject_pending_accounts(self):
        registration_page = self.client.get("/admin/register")
        self.client.post(
            "/admin/register",
            data={
                "csrf_token": self.csrf(registration_page),
                "full_name": "Pemohon Ditolak",
                "username": "pemohon.ditolak",
                "email": "pemohon.ditolak@example.ac.id",
                "password": "StrongPassword123!",
                "password_confirmation": "StrongPassword123!",
            },
        )
        with closing(sqlite3.connect(auth.ADMIN_DB_PATH)) as connection:
            pending_id = connection.execute(
                "SELECT id FROM admin_accounts WHERE username = ?",
                ("pemohon.ditolak",),
            ).fetchone()[0]
        self.assertEqual(self.create_first_admin().status_code, 303)
        page = self.client.get("/admin/verifikasi-akun")
        rejected = self.client.post(
            f"/admin/verifikasi-akun/{pending_id}/reject",
            data={"csrf_token": self.page_csrf(page)},
        )
        self.assertEqual(rejected.status_code, 303)
        with closing(sqlite3.connect(auth.ADMIN_DB_PATH)) as connection:
            status = connection.execute(
                "SELECT status FROM admin_accounts WHERE id = ?", (pending_id,)
            ).fetchone()[0]
        self.assertEqual(status, "rejected")

    def test_registration_validates_password_strength(self):
        register_page = self.client.get("/admin/register")
        response = self.client.post(
            "/admin/register",
            data={
                "csrf_token": self.csrf(register_page),
                "full_name": "Admin Baru",
                "username": "admin.baru",
                "email": "admin.baru@example.ac.id",
                "password": "weakpass",
                "password_confirmation": "weakpass",
            },
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Minimal 12 karakter", response.text)
        with closing(sqlite3.connect(auth.ADMIN_DB_PATH)) as connection:
            account_count = connection.execute(
                "SELECT COUNT(*) FROM admin_accounts"
            ).fetchone()[0]
        self.assertEqual(account_count, 0)


if __name__ == "__main__":
    unittest.main()
