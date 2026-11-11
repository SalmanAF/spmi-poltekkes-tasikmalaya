import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import auth
from app import main
from create_super_admin import create_super_admin


class CreateSuperAdminTests(unittest.TestCase):
    def test_application_startup_seeds_from_deployment_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.object(
                    auth,
                    "ADMIN_DB_PATH",
                    Path(directory) / "admin_auth.sqlite3",
                ),
                patch.dict(
                    os.environ,
                    {
                        "SPMI_BOOTSTRAP_ADMIN_NAME": "Admin Production",
                        "SPMI_BOOTSTRAP_ADMIN_USERNAME": "admin.production",
                        "SPMI_BOOTSTRAP_ADMIN_EMAIL": "admin.production@example.ac.id",
                        "SPMI_BOOTSTRAP_ADMIN_PASSWORD": "ProductionPassword123!",
                    },
                ),
                patch("app.main.all_documents", return_value=[]),
            ):
                with TestClient(main.app):
                    account = auth.authenticate_admin(
                        "admin.production", "ProductionPassword123!"
                    )

        self.assertIsNotNone(account)
        self.assertEqual(account["status"], "active")
        self.assertEqual(account["role"], "super_admin")

    def test_bootstrap_super_admin_is_active_and_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(
                auth,
                "ADMIN_DB_PATH",
                Path(directory) / "admin_auth.sqlite3",
            ):
                auth.initialize_auth_db()
                account_id = auth.bootstrap_super_admin(
                    "Admin Bootstrap",
                    "admin.bootstrap",
                    "admin.bootstrap@example.ac.id",
                    "StrongPassword123!",
                )
                self.assertIsNotNone(account_id)
                self.assertEqual(
                    auth.bootstrap_super_admin(
                        "Akun Kedua",
                        "admin.kedua",
                        "admin.kedua@example.ac.id",
                        "AnotherPassword123!",
                    ),
                    None,
                )
                account = auth.authenticate_admin(
                    "admin.bootstrap", "StrongPassword123!"
                )
                self.assertEqual(account["status"], "active")
                self.assertEqual(account["role"], "super_admin")

    def test_bootstrap_rejects_weak_password(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(
                auth,
                "ADMIN_DB_PATH",
                Path(directory) / "admin_auth.sqlite3",
            ):
                auth.initialize_auth_db()
                with self.assertRaisesRegex(ValueError, "Password minimal 12"):
                    auth.bootstrap_super_admin(
                        "Admin Bootstrap",
                        "admin.bootstrap",
                        "admin.bootstrap@example.ac.id",
                        "weak",
                    )

    def test_creates_active_super_admin_that_can_authenticate(self):
        with tempfile.TemporaryDirectory() as directory:
            database_patch = patch.object(
                auth,
                "ADMIN_DB_PATH",
                Path(directory) / "admin_auth.sqlite3",
            )
            with database_patch:
                account_id = create_super_admin(
                    "Admin Darurat",
                    "admin.spmi",
                    "admin@spmi.com",
                    "StrongPassword123!",
                )

                account = auth.authenticate_admin(
                    "admin@spmi.com", "StrongPassword123!"
                )
                self.assertEqual(account["id"], account_id)
                self.assertEqual(account["status"], "active")
                self.assertEqual(account["role"], "super_admin")
                self.assertEqual(
                    auth.get_active_admin(account_id)["role"], "super_admin"
                )

    def test_refuses_duplicate_username_or_email(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(
                auth,
                "ADMIN_DB_PATH",
                Path(directory) / "admin_auth.sqlite3",
            ):
                create_super_admin(
                    "Admin Darurat",
                    "admin.spmi",
                    "admin@spmi.com",
                    "StrongPassword123!",
                )
                with self.assertRaises(auth.AccountAlreadyExists):
                    create_super_admin(
                        "Admin Kedua",
                        "admin.kedua",
                        "admin@spmi.com",
                        "AnotherPassword123!",
                    )


if __name__ == "__main__":
    unittest.main()
