CREATE TABLE users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT NOT NULL UNIQUE,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at INTEGER NOT NULL
);
CREATE TABLE wallets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL UNIQUE REFERENCES users(id),
    address TEXT NOT NULL UNIQUE,
    public_key TEXT NOT NULL,
    encrypted_private_key BLOB NOT NULL,
    key_version INTEGER NOT NULL DEFAULT 1 CHECK(key_version > 0),
    created_at INTEGER NOT NULL
);
CREATE TABLE sessions (
    token_id TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    csrf_hash TEXT NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE TABLE idempotency_records (
    user_id INTEGER NOT NULL REFERENCES users(id),
    idempotency_key TEXT NOT NULL,
    operation TEXT NOT NULL,
    request_fingerprint TEXT NOT NULL,
    result_txid TEXT,
    transaction_data BLOB,
    state TEXT NOT NULL CHECK(state IN ('reserved','prepared','accepted','rejected')),
    created_at INTEGER NOT NULL,
    PRIMARY KEY(user_id, idempotency_key, operation)
);
CREATE TABLE metadata (name TEXT PRIMARY KEY, value BLOB NOT NULL);
