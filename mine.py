"""Utility script to mine blocks and fund any wallet address with 50 PYC per block.

Usage:
    python mine.py <username_or_address> [num_blocks]

Examples:
    python mine.py dangvm
    python mine.py vmdang 2
    python mine.py PYC_3ffb8df06c0f1aaf5dc42e57b232f7ddca0d0f81beabbcea
"""

from __future__ import annotations

import json
import sqlite3
import sys
import urllib.request
import urllib.error
from pathlib import Path

from blockchain.blockchain import Blockchain
from crypto.address import validate_address
from mining.miner import mine_block
from api.config import ApiConfig


def resolve_address(target: str, app_db_path: str = "data/app.sqlite3") -> str:
    """Resolve username to wallet address, or validate raw address."""
    if target.startswith("PYC_"):
        if validate_address(target):
            return target
        raise ValueError(f"Invalid PYC address format: {target}")

    # Check app database for username
    db_file = Path(app_db_path)
    if db_file.exists():
        conn = sqlite3.connect(db_file)
        try:
            row = conn.execute(
                "SELECT w.address FROM users u JOIN wallets w ON u.id = w.user_id WHERE u.username = ?",
                (target,),
            ).fetchone()
            if row:
                return row[0]
        finally:
            conn.close()

    raise ValueError(f"Username '{target}' not found in {app_db_path} and is not a valid PYC address.")


def is_api_running(base_url: str) -> bool:
    """Check if the API server is currently responsive."""
    try:
        req = urllib.request.Request(f"{base_url}/api/v1/health", method="GET")
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def mine_online(base_url: str, admin_token: str, address: str, count: int = 1) -> None:
    """Mine blocks via the running API server's admin routes."""
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }
    for i in range(1, count + 1):
        print(f"[*] [{i}/{count}] Requesting block template for {address}...")
        template_payload = json.dumps({
            "miner_address": address,
            "max_transactions": 50,
            "max_bytes": 50000,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{base_url}/api/v1/admin/blocks/template",
            data=template_payload,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            tpl_data = json.loads(resp.read().decode("utf-8"))

        # Reconstruct Block object to mine
        from blockchain.block import Block, BlockHeader
        from transaction.transaction import Transaction
        from transaction.tx_input import TxInput
        from transaction.tx_output import TxOutput

        header_dict = tpl_data["header"]
        header = BlockHeader(
            version=header_dict["version"],
            previous_block_hash=header_dict["previous_block_hash"],
            merkle_root=header_dict["merkle_root"],
            timestamp=header_dict["timestamp"],
            difficulty=header_dict["difficulty"],
            nonce=header_dict["nonce"],
        )
        transactions = []
        for tx_dict in tpl_data["transactions"]:
            inputs = [
                TxInput(
                    previous_tx_id=inp["previous_tx_id"],
                    output_index=inp["output_index"],
                    signature=inp.get("signature", ""),
                    public_key=inp.get("public_key", ""),
                )
                for inp in tx_dict["inputs"]
            ]
            outputs = [
                TxOutput(amount=out["amount"], recipient_address=out["recipient_address"])
                for out in tx_dict["outputs"]
            ]
            transactions.append(
                Transaction(
                    version=tx_dict["version"],
                    inputs=inputs,
                    outputs=outputs,
                    timestamp=tx_dict["timestamp"],
                )
            )

        template_block = Block(header, transactions)
        print(f"[*] Mining block (PoW difficulty: {template_block.difficulty})...")
        mined = mine_block(template_block, max_nonce=500_000)
        if not mined:
            raise RuntimeError("Proof-of-work mining failed or timed out.")

        print(f"[+] Block mined! Nonce: {mined.nonce}, Hash: {mined.hash()}")

        # Submit block
        submit_payload = json.dumps({
            "header": {
                "version": mined.version,
                "previous_block_hash": mined.previous_block_hash,
                "merkle_root": mined.merkle_root,
                "timestamp": mined.timestamp,
                "difficulty": mined.difficulty,
                "nonce": mined.nonce,
            },
            "transactions": [
                {
                    "version": tx.version,
                    "timestamp": tx.timestamp,
                    "inputs": [
                        {
                            "previous_tx_id": inp.previous_tx_id,
                            "output_index": inp.output_index,
                            "signature": inp.signature,
                            "public_key": inp.public_key,
                        }
                        for inp in tx.inputs
                    ],
                    "outputs": [
                        {
                            "amount": out.amount,
                            "recipient_address": out.recipient_address,
                        }
                        for out in tx.outputs
                    ],
                }
                for tx in mined.transactions
            ],
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{base_url}/api/v1/admin/blocks",
            data=submit_payload,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            submit_resp = json.loads(resp.read().decode("utf-8"))
            if submit_resp.get("accepted"):
                print(f"[SUCCESS] Block accepted! 50 PYC sent to {address}.")


def mine_offline(db_path: str, address: str, count: int = 1) -> None:
    """Mine blocks directly into SQLite database when server is offline."""
    print(f"[*] Server is offline. Mining directly into {db_path}...")
    chain = Blockchain(db_path=db_path)
    try:
        for i in range(1, count + 1):
            print(f"[*] [{i}/{count}] Creating block template for {address}...")
            template = chain.create_block_template(address)
            print(f"[*] Mining block (difficulty: {template.difficulty})...")
            mined = mine_block(template, max_nonce=500_000)
            if not mined:
                raise RuntimeError("Proof-of-work mining failed.")
            if not chain.add_block(mined):
                raise RuntimeError("Failed to add mined block to blockchain.")
            print(f"[+] Block #{chain.height} mined! Hash: {mined.hash()}")
            print(f"[SUCCESS] Block accepted! Balance for {address}: {chain.get_balance(address)} PYC")
    finally:
        chain.close()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    target = sys.argv[1].strip()
    num_blocks = int(sys.argv[2]) if len(sys.argv) > 2 else 1

    config = ApiConfig()
    address = resolve_address(target, config.app_db)
    print(f"[*] Target recipient address: {address}")

    base_url = f"http://{config.api_host}:{config.api_port}"
    if is_api_running(base_url):
        print(f"[*] PyChain API server detected at {base_url}.")
        admin_token = config.admin_token
        if not admin_token or not config.enable_admin_routes:
            print("[!] API server is running, but PYC_ENABLE_ADMIN_ROUTES or PYC_ADMIN_TOKEN is not configured in .env.")
            print("[!] Tip: Add the following to your .env to enable online mining:")
            print("    PYC_ENABLE_ADMIN_ROUTES=true")
            print("    PYC_ADMIN_TOKEN=pychain_demo_admin_secret_2026")
            print("[!] Alternatively, stop the server with Ctrl+C and run this script again to mine offline.")
            sys.exit(1)
        mine_online(base_url, admin_token, address, num_blocks)
    else:
        node_db = config.node_db or "data/node-a.sqlite3"
        mine_offline(node_db, address, num_blocks)


if __name__ == "__main__":
    main()
