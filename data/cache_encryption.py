"""Encrypt and restore TenderMatch SQLite snapshots for Actions caching.

GitHub Actions caches in a public repository can be read by workflows from
fork pull requests. Cache only authenticated ciphertext when the database may
contain recipient addresses or salesperson feedback.
"""

from __future__ import annotations

import argparse
from contextlib import closing
import os
import sqlite3
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from data.backup import backup_database, restore_database


KEY_ENV = "TENDERMATCH_DB_CACHE_KEY"


def _fernet(key: str | bytes | None = None) -> Fernet:
    if key is None:
        key = os.environ.get(KEY_ENV)
    if not key:
        raise RuntimeError(f"Set {KEY_ENV} as a GitHub Actions secret before using the database cache.")
    if isinstance(key, str):
        key = key.encode("ascii")
    return Fernet(key)


def _regular_path(value: str | Path, *, must_exist: bool) -> Path:
    path = Path(value).expanduser()
    if path.is_symlink():
        raise ValueError("Database cache paths must not be symbolic links.")
    if must_exist and not path.is_file():
        raise FileNotFoundError("The database cache source is missing or is not a regular file.")
    if not must_exist and not path.parent.is_dir():
        raise FileNotFoundError("The database cache destination directory does not exist.")
    return path.resolve(strict=must_exist)


def _fsync_parent(path: Path) -> None:
    directory_fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)


def encrypt_database(
    database: str | Path,
    encrypted_cache: str | Path,
    key: str | bytes | None = None,
) -> Path:
    """Write a private, authenticated encrypted SQLite snapshot atomically."""
    _require_posix_permissions()
    cipher = _fernet(key)
    source = _regular_path(database, must_exist=True)
    destination = _regular_path(encrypted_cache, must_exist=False)
    if source == destination:
        raise ValueError("The encrypted cache path must differ from the plaintext database path.")

    with tempfile.TemporaryDirectory(prefix="tendermatch-cache-") as temporary_directory:
        snapshot = Path(temporary_directory) / "snapshot.sqlite3"
        backup_database(source, snapshot)
        ciphertext = cipher.encrypt(snapshot.read_bytes())

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
    )
    temporary_path = Path(temporary_name)
    try:
        os.chmod(temporary_path, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(ciphertext)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, destination)
        _fsync_parent(destination)
        return destination
    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def _check_sqlite_integrity(path: Path) -> None:
    uri = f"{path.as_uri()}?mode=ro"
    with closing(sqlite3.connect(uri, uri=True, timeout=30)) as connection:
        result = connection.execute("PRAGMA integrity_check").fetchone()
    if result is None or result[0] != "ok":
        raise sqlite3.DatabaseError("Decrypted database failed its integrity check.")


def decrypt_database(
    encrypted_cache: str | Path,
    database: str | Path,
    key: str | bytes | None = None,
) -> Path:
    """Authenticate and restore an encrypted snapshot without clobbering state."""
    _require_posix_permissions()
    cipher = _fernet(key)
    source = _regular_path(encrypted_cache, must_exist=True)
    destination = _regular_path(database, must_exist=False)
    if source == destination:
        raise ValueError("The encrypted cache path must differ from the plaintext database path.")
    if destination.exists():
        raise FileExistsError("The plaintext database path already exists; refusing to replace it.")

    try:
        plaintext = cipher.decrypt(source.read_bytes())
    except InvalidToken as exc:
        raise ValueError("The encrypted database cache failed authentication.") from exc

    with tempfile.TemporaryDirectory(prefix="tendermatch-restore-", dir=destination.parent) as temporary_directory:
        snapshot = Path(temporary_directory) / "snapshot.sqlite3"
        snapshot.write_bytes(plaintext)
        os.chmod(snapshot, 0o600)
        _check_sqlite_integrity(snapshot)
        restore_database(snapshot, destination)
    return destination


def _require_posix_permissions() -> None:
    if os.name != "posix":
        raise OSError("Encrypted SQLite cache files require a POSIX filesystem for owner-only permissions.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    encrypt_parser = subparsers.add_parser("encrypt", help="create encrypted SQLite cache data")
    encrypt_parser.add_argument("database")
    encrypt_parser.add_argument("encrypted_cache")
    decrypt_parser = subparsers.add_parser("decrypt", help="restore authenticated encrypted SQLite cache data")
    decrypt_parser.add_argument("encrypted_cache")
    decrypt_parser.add_argument("database")
    args = parser.parse_args(argv)

    try:
        if args.command == "encrypt":
            encrypt_database(args.database, args.encrypted_cache)
            print("Encrypted SQLite cache created; snapshot integrity passed.")
        else:
            decrypt_database(args.encrypted_cache, args.database)
            print("Encrypted SQLite cache authenticated and restored; integrity passed.")
    except RuntimeError as exc:
        print(str(exc))
        return 2
    except InvalidToken:
        print("Encrypted database cache authentication failed; no plaintext database was restored.")
        return 2
    except Exception as exc:
        print(f"Database cache operation failed ({type(exc).__name__}).")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
