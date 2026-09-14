"""Small synchronous SQLite operations owned by the API event loop."""

from contextlib import contextmanager
from pathlib import Path
import sqlite3
import time

from storage.errors import StorageError


class DuplicateAccountError(Exception):
    pass


class AppDatabase:
    def __init__(self, path):
        self.connection = sqlite3.connect(str(path), isolation_level=None, timeout=0)
        self.connection.row_factory = sqlite3.Row
        try:
            self.connection.execute("PRAGMA foreign_keys=ON")
            version = self.connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                if self.connection.execute("SELECT name FROM sqlite_schema WHERE type='table'").fetchone():
                    raise StorageError("Unrecognized application database schema")
                schema = Path(__file__).with_name("schema.sql").read_text(encoding="utf-8")
                self.connection.executescript("BEGIN IMMEDIATE;\n" + schema + "\nPRAGMA user_version=1; COMMIT;")
            elif version != 1:
                raise StorageError("Unsupported application database version")
            if self.connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise StorageError("Application database integrity failure")
            if self.connection.execute("PRAGMA foreign_key_check").fetchone():
                raise StorageError("Application database foreign key failure")
        except BaseException:
            self.connection.close()
            raise

    def close(self):
        self.connection.close()

    def execute(self, sql, parameters=()):
        try:
            return self.connection.execute(sql, parameters)
        except sqlite3.Error as exc:
            raise StorageError("Application database operation failed") from exc

    @contextmanager
    def transaction(self):
        self.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.execute("COMMIT")
        except BaseException:
            if self.connection.in_transaction:
                self.connection.rollback()
            raise

    def create_account(self, email, username, password_hash, wallet):
        try:
            with self.transaction():
                cursor = self.connection.execute(
                    "INSERT INTO users(email,username,password_hash,created_at) VALUES(?,?,?,?)",
                    (email, username, password_hash, int(time.time())),
                )
                user_id = cursor.lastrowid
                self.connection.execute(
                    "INSERT INTO wallets(user_id,address,public_key,encrypted_private_key,key_version,created_at) VALUES(?,?,?,?,?,?)",
                    (user_id, wallet.address, wallet.public_key, wallet.encrypted_private_key, wallet.key_version, int(time.time())),
                )
        except sqlite3.IntegrityError as exc:
            raise DuplicateAccountError from exc
        except sqlite3.Error as exc:
            raise StorageError("Cannot create application account") from exc
        return self.user(user_id)

    def user(self, user_id):
        return self.execute("SELECT * FROM users WHERE id=?", (user_id,)).fetchone()

    def find_user(self, identifier):
        return self.execute("SELECT * FROM users WHERE email=? OR username=?", (identifier, identifier)).fetchone()

    def wallet(self, user_id):
        return self.execute("SELECT * FROM wallets WHERE user_id=?", (user_id,)).fetchone()

    def session(self, token_id):
        return self.execute("SELECT * FROM sessions WHERE token_id=?", (token_id,)).fetchone()

    def idempotency(self, user_id, key):
        return self.execute(
            "SELECT * FROM idempotency_records WHERE user_id=? AND idempotency_key=? AND operation='wallet.send'",
            (user_id, key),
        ).fetchone()
