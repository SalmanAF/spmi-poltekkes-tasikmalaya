import getpass
import sys

from app import auth


def create_super_admin(full_name: str, username: str, email: str, password: str) -> int:
    error = auth.validate_account_fields(full_name, username, email, password)
    if error:
        raise ValueError(error)
    auth.initialize_auth_db()
    return auth.create_admin_account(
        full_name, username, email, password, "super_admin"
    )


def main() -> int:
    print("Buat akun Super Admin aktif untuk website SPMI.")
    full_name = input("Nama lengkap: ").strip()
    username = input("Username (contoh: admin.spmi): ").strip()
    email = input("Email (contoh: admin@spmi.com): ").strip()
    password = getpass.getpass("Password (min. 12 karakter): ")
    confirmation = getpass.getpass("Ulangi password: ")

    if password != confirmation:
        print("Password dan konfirmasi tidak sama.", file=sys.stderr)
        return 1

    try:
        error = auth.validate_account_fields(full_name, username, email, password)
        if error:
            print(error, file=sys.stderr)
            return 1
        print(f"Database akun: {auth.ADMIN_DB_PATH}")
        confirmation = input(
            f"Buat Super Admin aktif untuk {email} di database ini? [y/N]: "
        ).strip()
        if confirmation.lower() != "y":
            print("Dibatalkan; tidak ada perubahan.")
            return 1
        account_id = create_super_admin(full_name, username, email, password)
    except auth.AccountAlreadyExists as exc:
        print(
            f"Gagal membuat akun: {exc} Pilih username dan email yang belum digunakan.",
            file=sys.stderr,
        )
        return 1
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(
        f"Akun berhasil dibuat (ID {account_id}, role super_admin, status active)."
    )
    print("Login menggunakan username atau email yang baru dibuat.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
