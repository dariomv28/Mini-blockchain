# PyChain — Educational Bitcoin-like Blockchain

PyChain is an educational cryptocurrency and blockchain platform written in Python. It features a UTXO model, ECDSA (SECP256k1) cryptography, Proof of Work (PoW) consensus, mempool with ancestor-fee selection, SQLite persistence, and an asynchronous peer-to-peer (P2P) gossip network.

Phase 10 introduces the **Web API Foundation** using FastAPI and WebSockets, exposing public node endpoints without breaking the core blockchain abstraction.

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
$env:PYC_NODE_DB = "data/node-a.sqlite3"
python run_api.py
```

On Linux/macOS:

```bash
PYC_NODE_DB=data/node-a.sqlite3 python run_api.py
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

## Running Tests

Run the test suite using pytest:

```bash
python -m pytest
```
