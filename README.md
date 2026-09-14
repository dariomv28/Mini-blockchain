# PyChain — Educational Bitcoin-like Blockchain

PyChain is an educational cryptocurrency and blockchain platform written in Python. It features a UTXO model, ECDSA (SECP256k1) cryptography, Proof of Work (PoW) consensus, mempool with ancestor-fee selection, SQLite persistence, and an asynchronous peer-to-peer (P2P) gossip network.

Phase 10 introduces FastAPI and WebSockets. Phase 11 adds accounts, HttpOnly
cookie sessions and an encrypted custodial wallet that builds and signs real
UTXO transactions through the public Node API.

## Installation

Install dependencies using `pip`:

```bash
pip install -r requirements.txt
```

Or install the package in development mode:

```bash
pip install -e ".[dev]"
```

## Running the API Server

Start the API server with an embedded PyChain node and explicitly enable SQLite storage.
From the project directory in PowerShell:

```powershell
New-Item -ItemType Directory -Force data | Out-Null
$env:PYC_NODE_DB = "data/node-a.sqlite3"
$env:PYC_APP_DB = "data/app.sqlite3"

# Generate these once for a new installation and save them outside Git.
$env:PYC_WALLET_MASTER_KEY = python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
$env:PYC_JWT_SECRET = python -c "import secrets; print(secrets.token_urlsafe(48))"
python run_api.py
```

Keep the same wallet master key when restarting: generating a replacement cannot
decrypt existing wallets and startup will fail. Keep the same JWT secret to retain
existing sessions. Both may be configured in an untracked `.env` file; see
`.env.example` for variable names. Never commit the actual secrets or databases.

On Linux/macOS:

```bash
mkdir -p data
# Set PYC_WALLET_MASTER_KEY and PYC_JWT_SECRET to saved values first.
PYC_APP_DB=data/app.sqlite3 PYC_NODE_DB=data/node-a.sqlite3 python run_api.py
```

Without `PYC_NODE_DB`, the default is **RAM-only**: chain and mempool state are
lost when the process stops. Restart from the same directory with the same database
path to restore both. Run only one API worker/node process per database.

Use `run_api.py` as the launcher: it disables forwarded-IP trust to protect
per-IP limits and applies the configured WebSocket transport limits. Do not replace
it with a bare Uvicorn invocation, which uses different security defaults.

Interactive API documentation will be available at:

- **Swagger UI:** `http://127.0.0.1:8000/docs`
- **ReDoc:** `http://127.0.0.1:8000/redoc`

WebSocket frontend clients should send the text message `ping` every 20 seconds
and handle the text reply `pong` alongside JSON `node_status` messages. With the
default settings, a client that sends no messages for 60 seconds is disconnected;
receiving status updates does not keep the connection active.

## Accounts and wallet API

Before register/login, call `GET /api/v1/auth/csrf`. Keep the cookies and send
the returned `csrf_token` in `X-CSRF-Token` on the following POST. Register
accepts `{email, username, password}`; passwords need at least 12 characters and
usernames use 3-32 ASCII letters, digits or underscores. Login accepts
`{identifier, password}` where identifier is email or username.

Login sets an HttpOnly `pychain_session` cookie and returns a new `csrf_token`.
Use that token and `credentials: "include"` for cookie-authenticated mutations.
`GET /auth/me`, `GET /wallet` and `GET /wallet/transactions?start=0&limit=20`
use the `/api/v1` prefix. `POST /auth/logout` revokes the session. After expiry,
call `/auth/csrf` again to clear the stale cookie and obtain a new login token.

`POST /api/v1/wallet/send` accepts `{recipient_address, amount, fee}` and requires
both `X-CSRF-Token` and `Idempotency-Key` (1-128 ASCII letters, digits or `._:-`).
Reuse the key for retries of the same intent; a different body with the same key
returns 409. The receipt returns the original txid and pending status; query
transaction lookup/history for its current confirmation status.

Wallet summary separates confirmed balance from available confirmed UTXOs.
`pending_outgoing` is the full confirmed input value reserved in the mempool;
`pending_incoming` counts only unspent pending outputs to the wallet, including
change, excluding outputs consumed by pending children. These are not immediately
spendable. Fees are implicit, and the Node validates every signed transaction again.

Wallet sends select at most 100 inputs; exceeding this API work limit returns
413 `TRANSACTION_TOO_LARGE` before decrypting or signing. Serialized size is
checked before signing and again afterward. Selection/signing/encoding run off
the API event loop, with at most two concurrent build workers. This limit does
not change blockchain consensus rules.

Sessions expire after one hour by default. Cookies use SameSite=Lax; set
`PYC_COOKIE_SECURE=true` when serving HTTPS (mandatory outside demo mode).
Login permits 20 attempts/minute/IP and 5/identifier; repeated failures add a
60-second cooldown. This in-memory policy assumes one API worker.

An app database stolen by itself contains encrypted private keys. An attacker
with both that database and the wallet master key can decrypt them. This is an
educational custodial wallet; Python does not guarantee secret memory zeroization.

## Running Tests

Run the test suite using pytest:

```bash
python -m pytest
```
