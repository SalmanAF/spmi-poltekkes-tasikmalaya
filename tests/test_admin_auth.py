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

    def test_registration_activates_account_and_allows_immediate_login(self):
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
            status = connection.execute(
                "SELECT status FROM admin_accounts WHERE username = ?",
                ("admin.baru",),
            ).fetchone()[0]
        self.assertEqual(status, "active")

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
        login_response = self.client.post(
            "/admin/login",
            data={
                "csrf_token": self.csrf(login_page),
                "username_or_email": "admin.baru",
                "password": "StrongPassword123!",
            },
        )
        self.assertEqual(login_response.status_code, 303)
        self.assertEqual(login_response.headers["location"], "/admin/dashboard")
        self.assertEqual(self.client.get("/admin/dashboard").status_code, 200)

    def test_existing_pending_accounts_are_activated_on_database_migration(self):
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
        self.assertIsNotNone(auth.get_active_admin(account["id"]))
        with closing(sqlite3.connect(auth.ADMIN_DB_PATH)) as connection:
            status = connection.execute(
                "SELECT status FROM admin_accounts WHERE username = ?",
                ("admin.lama",),
            ).fetchone()[0]
        self.assertEqual(status, "active")

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
