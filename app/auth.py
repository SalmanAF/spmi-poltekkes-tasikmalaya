import base64
import hashlib
import hmac
import re
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
ADMIN_DB_PATH = BASE_DIR / "uploads" / "admin_auth.sqlite3"
PASSWORD_HASH_N = 2**14
PASSWORD_HASH_R = 8
PASSWORD_HASH_P = 1
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,32}$")
EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+$")
DOMAIN_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


class AccountAlreadyExists(ValueError):
    pass


class SetupUnavailable(ValueError):
    pass


def _connect() -> sqlite3.Connection:
    connection = sqlite3.connect(ADMIN_DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_auth_db() -> None:
    ADMIN_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect()) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS admin_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                username TEXT NOT NULL COLLATE NOCASE UNIQUE,
                email TEXT NOT NULL COLLATE NOCASE UNIQUE,
                password_hash TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active'
                    CHECK (status = 'active'),
                created_at TEXT NOT NULL,
                approved_at TEXT,
                approved_by INTEGER REFERENCES admin_accounts(id)
            );
            CREATE INDEX IF NOT EXISTS idx_admin_accounts_status
                ON admin_accounts(status);
            """
        )
        with connection:
            connection.execute(
                "UPDATE admin_accounts SET status = 'active' WHERE status != 'active'"
            )


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=PASSWORD_HASH_N,
        r=PASSWORD_HASH_R,
        p=PASSWORD_HASH_P,
        dklen=64,
    )
    return "scrypt${}${}${}${}${}".format(
        PASSWORD_HASH_N,
        PASSWORD_HASH_R,
        PASSWORD_HASH_P,
        base64.urlsafe_b64encode(salt).decode("ascii"),
        base64.urlsafe_b64encode(digest).decode("ascii"),
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, n, r, p, salt_value, digest_value = stored_hash.split("$")
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_value.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_value.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n),
            r=int(r),
            p=int(p),
            dklen=len(expected),
        )
    except (ValueError, TypeError, UnicodeEncodeError):
        return False
    return hmac.compare_digest(actual, expected)


def validate_account_fields(full_name: str, username: str, email: str, password: str) -> str | None:
    if len(full_name.strip()) < 2 or len(full_name.strip()) > 100:
        return "Nama lengkap harus terdiri dari 2 sampai 100 karakter."
    if any(ord(character) < 32 for character in full_name):
        return "Nama lengkap tidak boleh berisi karakter kontrol."
    if not USERNAME_PATTERN.fullmatch(username):
        return "Username harus berisi 3-32 karakter berupa huruf, angka, titik, tanda hubung, atau garis bawah."

    email = email.strip()
    local, separator, domain = email.rpartition("@")
    labels = domain.split(".")
    if (
        len(email) > 254
        or not separator
        or not local
        or len(local) > 64
        or local.startswith(".")
        or local.endswith(".")
        or ".." in local
        or not EMAIL_PATTERN.fullmatch(local)
        or len(domain) > 253
        or len(labels) < 2
        or any(not DOMAIN_LABEL_PATTERN.fullmatch(label) for label in labels)
    ):
        return "Format email tidak valid."
    if (
        len(password) < 12
        or len(password) > 128
        or not re.search(r"[a-z]", password)
        or not re.search(r"[A-Z]", password)
        or not re.search(r"\d", password)
        or not re.search(r"[^A-Za-z0-9]", password)
    ):
        return "Password minimal 12 karakter dan harus memuat huruf besar, huruf kecil, angka, serta simbol."
    return None


def _public_account(row: sqlite3.Row) -> dict[str, object]:
    return {
        "id": row["id"],
        "full_name": row["full_name"],
        "username": row["username"],
        "email": row["email"],
        "created_at": row["created_at"],
    }


def _insert_account(
    connection: sqlite3.Connection,
    full_name: str,
    username: str,
    email: str,
    password: str,
) -> int:
    try:
        cursor = connection.execute(
            """
            INSERT INTO admin_accounts
                (full_name, username, email, password_hash, status, created_at, approved_at, approved_by)
            VALUES (?, ?, ?, ?, 'active', ?, NULL, NULL)
            """,
            (
                full_name.strip(),
                username.strip(),
                email.strip().lower(),
                hash_password(password),
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
            ),
        )
    except sqlite3.IntegrityError as exc:
        raise AccountAlreadyExists("Username atau email sudah digunakan.") from exc
    return int(cursor.lastrowid)


def register_admin(full_name: str, username: str, email: str, password: str) -> None:
    with closing(_connect()) as connection:
        try:
            with connection:
                _insert_account(connection, full_name, username, email, password)
        except AccountAlreadyExists:
            raise


def create_initial_admin(full_name: str, username: str, email: str, password: str) -> int:
    with closing(_connect()) as connection:
        try:
            with connection:
                connection.execute("BEGIN IMMEDIATE")
                active_count = connection.execute(
                    "SELECT COUNT(*) FROM admin_accounts WHERE status = 'active'"
                ).fetchone()[0]
                if active_count:
                    raise SetupUnavailable("Setup administrator pertama sudah ditutup.")
                return _insert_account(connection, full_name, username, email, password)
        except AccountAlreadyExists:
            raise


def authenticate_admin(identifier: str, password: str) -> dict[str, object] | None:
    if len(password) > 128:
        return None
    with closing(_connect()) as connection:
        row = connection.execute(
            """
            SELECT id, full_name, username, email, created_at, password_hash
            FROM admin_accounts
            WHERE username = ? COLLATE NOCASE OR email = ? COLLATE NOCASE
            """,
            (identifier.strip(), identifier.strip()),
        ).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        return None
    return _public_account(row)


def get_active_admin(admin_id: object) -> dict[str, object] | None:
    try:
        parsed_id = int(admin_id)
    except (TypeError, ValueError):
        return None
    with closing(_connect()) as connection:
        row = connection.execute(
            """
            SELECT id, full_name, username, email, created_at
            FROM admin_accounts
            WHERE id = ? AND status = 'active'
            """,
            (parsed_id,),
        ).fetchone()
    return _public_account(row) if row else None


def has_active_admin() -> bool:
    with closing(_connect()) as connection:
        return connection.execute(
            "SELECT 1 FROM admin_accounts WHERE status = 'active' LIMIT 1"
        ).fetchone() is not None
