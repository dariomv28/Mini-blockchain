import asyncio
import threading
from dataclasses import replace
from unittest.mock import patch

import pytest
from cryptography.fernet import Fernet
from httpx import ASGITransport, AsyncClient

from api.app import create_app
from api.config import ApiConfig
from storage.errors import StorageError
from wallet.keystore import KeyStoreError
from wallet.transaction_builder import build_signed_transaction
from wallet.service import MAX_WALLET_INPUTS
from transaction.tx_output import TxOutput
from phase11_helpers import application, csrf, fund, login, register


def test_wallet_real_send_history_pending_spends_and_idempotency():
    async def scenario():
        async with application() as (app, alice):
            a = await register(alice,"alice")
            b = await register(alice,"bob")
            address = a["wallet"]["address"]
            await fund(app.state.node, address)
            assert (await login(alice)).status_code == 200
            summary = (await alice.get("/api/v1/wallet")).json()
            assert summary["confirmed_balance"] == summary["available_balance"] == 50
            body = {"recipient_address": b["wallet"]["address"], "amount":10, "fee":1}
            headers = {**await csrf(alice), "Idempotency-Key":"intent-one"}
            sent = await alice.post("/api/v1/wallet/send",headers=headers,json=body)
            assert sent.status_code == 201, sent.text
            txid = sent.json()["txid"]
            pending = await app.state.node.get_pending_transactions()
            assert len(pending) == 1 and pending[0].txid() == txid
            assert [o.amount for o in pending[0].outputs] == [10,39]
            after = (await alice.get("/api/v1/wallet")).json()
            assert after["confirmed_balance"] == 50 and after["available_balance"] == 0
            assert after["pending_outgoing"] == 50 and after["pending_incoming"] == 39
            retry = await alice.post("/api/v1/wallet/send",headers=headers,json=body)
            assert retry.status_code == 201 and retry.json() == sent.json()
            changed = await alice.post("/api/v1/wallet/send",headers=headers,json={**body,"amount":11})
            assert changed.status_code == 409 and changed.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
            another = await alice.post("/api/v1/wallet/send",headers={**headers,"Idempotency-Key":"new-intent"},json=body)
            assert another.status_code == 409 and another.json()["error"]["code"] == "INSUFFICIENT_BALANCE"
            history = (await alice.get("/api/v1/wallet/transactions")).json()
            assert history[0]["txid"] == txid and history[0]["direction"] == "sent" and history[0]["amount"] == 10
            # No user_id/body selector can grant access to a different wallet.
            forged = await alice.post("/api/v1/wallet/send",headers=headers,json={**body,"user_id":b["user"]["id"]})
            assert forged.status_code == 400
            async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as bob:
                assert (await login(bob,"bob")).status_code == 200
                bob_view = (await bob.get("/api/v1/wallet")).json()
                assert bob_view["confirmed_balance"] == 0 and bob_view["pending_incoming"] == 10
                bob_history = (await bob.get("/api/v1/wallet/transactions")).json()
                assert bob_history[0]["direction"] == "received" and bob_history[0]["amount"] == 10
            template = await app.state.node.create_mempool_block_template(address)
            from mining.miner import mine_block
            block = mine_block(template,max_nonce=100_000)
            assert await app.state.node.accept_block(block)
            assert (await alice.get("/api/v1/wallet/transactions")).json()[0]["status"] == "confirmed"
            assert (await alice.get("/api/v1/wallet")).json()["confirmed_balance"] == 90
    asyncio.run(scenario())


def test_concurrent_retry_submits_once_and_cross_user_key_is_independent():
    async def scenario():
        async with application() as (app, client):
            a = await register(client)
            b = await register(client,"bob")
            await fund(app.state.node,a["wallet"]["address"])
            assert (await login(client)).status_code == 200
            body = {"recipient_address":b["wallet"]["address"],"amount":10,"fee":1}
            headers = {**await csrf(client),"Idempotency-Key":"same-key"}
            with patch.object(app.state.node,"submit_transaction",wraps=app.state.node.submit_transaction) as submit:
                responses = await asyncio.gather(*[client.post("/api/v1/wallet/send",json=body,headers=headers) for _ in range(3)])
            assert all(r.status_code == 201 for r in responses)
            assert len({r.json()["txid"] for r in responses}) == 1
            assert submit.await_count == 1
            assert (await login(client,"bob")).status_code == 200
            response = await client.post("/api/v1/wallet/send",json=body,headers={**await csrf(client),"Idempotency-Key":"same-key"})
            assert response.status_code == 409 and response.json()["error"]["code"] == "INSUFFICIENT_BALANCE"
    asyncio.run(scenario())


def test_admission_race_is_clean_conflict():
    async def scenario():
        async with application() as (app, client):
            a = await register(client)
            await fund(app.state.node,a["wallet"]["address"])
            await login(client)
            body = {"recipient_address":a["wallet"]["address"],"amount":10,"fee":1}
            with patch.object(app.state.node,"submit_transaction",return_value=False):
                response = await client.post("/api/v1/wallet/send",json=body,headers={**await csrf(client),"Idempotency-Key":"race"})
            assert response.status_code == 409 and response.json()["error"]["code"] == "TRANSACTION_CONFLICT"
            assert len(await app.state.node.get_pending_transactions()) == 0
    asyncio.run(scenario())


def test_idempotency_recovers_after_result_write_failure_and_restart(tmp_path):
    async def scenario():
        config = ApiConfig(node_port=0,node_db=str(tmp_path/"chain.sqlite3"),app_db=str(tmp_path/"app.sqlite3"))
        app = create_app(config)
        txid = None
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as client:
                a = await register(client)
                b = await register(client,"bob")
                await fund(app.state.node,a["wallet"]["address"])
                await login(client)
                original = app.state.app_database.execute
                def fail_result(sql,parameters=()):
                    if sql.startswith("UPDATE idempotency_records SET state="):
                        raise StorageError("Injected result write failure")
                    return original(sql,parameters)
                body = {"recipient_address":b["wallet"]["address"],"amount":10,"fee":1}
                with patch.object(app.state.app_database,"execute",fail_result):
                    response = await client.post("/api/v1/wallet/send",json=body,headers={**await csrf(client),"Idempotency-Key":"durable"})
                assert response.status_code == 503
                pending = await app.state.node.get_pending_transactions()
                assert len(pending) == 1
                txid = pending[0].txid()
                record = app.state.app_database.idempotency(a["user"]["id"],"durable")
                assert record["state"] == "prepared" and record["result_txid"] == txid
        reopened = create_app(config)
        async with reopened.router.lifespan_context(reopened):
            async with AsyncClient(transport=ASGITransport(app=reopened),base_url="http://test") as client:
                assert (await login(client)).status_code == 200
                with patch.object(reopened.state.node,"submit_transaction",wraps=reopened.state.node.submit_transaction) as submit:
                    retry = await client.post("/api/v1/wallet/send",json=body,headers={**await csrf(client),"Idempotency-Key":"durable"})
                assert retry.status_code == 201 and retry.json()["txid"] == txid
                assert submit.await_count == 0
                assert len(await reopened.state.node.get_pending_transactions()) == 1
        # Wrong master key cannot silently replace or orphan existing wallets.
        wrong = create_app(config.model_copy(update={"wallet_master_key":__import__('pydantic').SecretStr(Fernet.generate_key().decode())}))
        with pytest.raises(KeyStoreError):
            async with wrong.router.lifespan_context(wrong):
                pass
    asyncio.run(scenario())


@pytest.mark.parametrize("setting,value", [("wallet_master_key",None),("wallet_master_key","CHANGE_ME"),("jwt_secret",None),("jwt_secret","CHANGE_ME"),("jwt_secret","short")])
def test_startup_requires_nonplaceholder_secrets_before_node_start(setting,value):
    async def scenario():
        from pydantic import SecretStr
        config = ApiConfig(node_port=0)
        config = config.model_copy(update={setting:None if value is None else SecretStr(value)})
        app = create_app(config)
        with pytest.raises(RuntimeError):
            async with app.router.lifespan_context(app):
                pass
        assert not hasattr(app.state,"node")
    asyncio.run(scenario())


def test_wallet_send_requires_idempotency_and_authenticated_admin_requires_csrf():
    async def scenario():
        config = ApiConfig(node_port=0,enable_admin_routes=True,admin_token="admin-token",demo_mode=True)
        async with application(config) as (_,client):
            a = await register(client)
            await login(client)
            response = await client.post("/api/v1/wallet/send",headers=await csrf(client),json={"recipient_address":a["wallet"]["address"],"amount":1,"fee":0})
            assert response.status_code == 400
            admin = {"Authorization":"Bearer admin-token"}
            assert (await client.post("/api/v1/admin/validate-chain",headers=admin)).status_code == 403
            assert (await client.post("/api/v1/admin/validate-chain",headers={**admin,**await csrf(client)})).status_code == 200
    asyncio.run(scenario())


def test_register_rolls_back_user_when_wallet_insert_fails():
    from appdb.database import AppDatabase, DuplicateAccountError
    from wallet.wallet import Wallet
    database = AppDatabase(":memory:")
    try:
        wallet = Wallet("duplicate-address","public",b"encrypted")
        database.create_account("alice@example.com","alice","hashed",wallet)
        with pytest.raises(DuplicateAccountError):
            database.create_account("bob@example.com","bob","hashed",wallet)
        assert database.execute("SELECT count(*) FROM users").fetchone()[0] == 1
        assert database.execute("SELECT count(*) FROM wallets").fetchone()[0] == 1
        assert database.find_user("bob") is None
    finally:
        database.close()


def test_disconnected_send_finishes_before_wallet_shutdown():
    async def scenario():
        async with application() as (app, client):
            alice = await register(client)
            bob = await register(client, "bob")
            await fund(app.state.node, alice["wallet"]["address"])
            entered = asyncio.Event()
            release = asyncio.Event()
            original_submit = app.state.node.submit_transaction

            async def delayed_submit(tx):
                entered.set()
                await release.wait()
                return await original_submit(tx)

            with patch.object(app.state.node, "submit_transaction", delayed_submit):
                request = asyncio.create_task(app.state.wallet_service.send(
                    alice["user"]["id"], bob["wallet"]["address"], 10, 1, "disconnect"))
                try:
                    await asyncio.wait_for(entered.wait(), timeout=5)
                    request.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await request
                finally:
                    release.set()
                    await asyncio.wait_for(app.state.wallet_service.close(), timeout=5)
            record = app.state.app_database.idempotency(alice["user"]["id"], "disconnect")
            assert record["state"] == "accepted"
            assert len(await app.state.node.get_pending_transactions()) == 1
            result = await app.state.wallet_service.send(
                alice["user"]["id"], bob["wallet"]["address"], 10, 1, "disconnect")
            assert result["txid"] == record["result_txid"]
    asyncio.run(scenario())


@pytest.mark.parametrize("input_count", [MAX_WALLET_INPUTS + 1, 2000])
def test_wallet_input_limit_rejects_before_decrypt_or_sign(input_count):
    async def scenario():
        async with application() as (app, client):
            alice = await register(client)
            address = alice["wallet"]["address"]
            await login(client)
            view = {"utxos": {(f"{index:064x}", 0): TxOutput(1, address) for index in range(input_count)},
                    "confirmed_balance": input_count, "pending": []}
            headers = {**await csrf(client), "Idempotency-Key": "too-many"}
            with patch.object(app.state.node, "get_wallet_state", return_value=view), \
                 patch.object(app.state.wallet_service.keystore, "decrypt_private_key") as decrypt, \
                 patch("wallet.service.build_signed_transaction") as build, \
                 patch.object(app.state.node, "submit_transaction") as submit:
                response = await client.post("/api/v1/wallet/send", headers=headers,
                                             json={"recipient_address": address, "amount": input_count, "fee": 0})
            assert response.status_code == 413
            assert response.json()["error"]["code"] == "TRANSACTION_TOO_LARGE"
            decrypt.assert_not_called()
            build.assert_not_called()
            submit.assert_not_called()
            assert app.state.app_database.idempotency(alice["user"]["id"], "too-many") is None
    asyncio.run(scenario())


def test_wallet_size_limit_rejects_before_sign_and_cleans_retry_record():
    async def scenario():
        from transaction.transaction import Transaction
        async with application() as (app, client):
            alice = await register(client)
            address = alice["wallet"]["address"]
            await fund(app.state.node, address)
            await login(client)
            headers = {**await csrf(client), "Idempotency-Key": "size-limit"}
            body = {"recipient_address": address, "amount": 10, "fee": 1}
            with patch.object(app.state.node, "config", replace(app.state.node.config, max_item_bytes=100)), \
                 patch.object(Transaction, "sign_input") as sign, \
                 patch.object(app.state.node, "submit_transaction") as submit:
                response = await client.post("/api/v1/wallet/send", headers=headers, json=body)
            assert response.status_code == 413
            sign.assert_not_called()
            submit.assert_not_called()
            assert app.state.app_database.idempotency(alice["user"]["id"], "size-limit") is None
            assert (await client.post("/api/v1/wallet/send", headers=headers, json=body)).status_code == 201
    asyncio.run(scenario())


def test_build_worker_does_not_block_http_timer_or_abandon_disconnected_send():
    async def scenario():
        async with application() as (app, client):
            alice = await register(client)
            address = alice["wallet"]["address"]
            await fund(app.state.node, address)
            await login(client)
            entered = asyncio.Event()
            release = threading.Event()
            loop = asyncio.get_running_loop()
            api_thread = threading.get_ident()
            worker_threads = []

            def slow_builder(**kwargs):
                worker_threads.append(threading.get_ident())
                loop.call_soon_threadsafe(entered.set)
                if not release.wait(timeout=5):
                    raise AssertionError("Event loop could not release signing worker")
                return build_signed_transaction(**kwargs)

            with patch("wallet.service.build_signed_transaction", slow_builder):
                request = asyncio.create_task(app.state.wallet_service.send(alice["user"]["id"], address, 10, 1, "worker"))
                try:
                    await asyncio.wait_for(entered.wait(), timeout=3)
                    assert len(worker_threads) == 1 and worker_threads[0] != api_thread
                    timer = asyncio.Event()
                    loop.call_later(0.01, timer.set)
                    summary = await asyncio.wait_for(client.get("/api/v1/wallet"), timeout=2)
                    assert summary.status_code == 200
                    await asyncio.wait_for(timer.wait(), timeout=2)
                    request.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await request
                    closing = asyncio.create_task(app.state.wallet_service.close())
                    await asyncio.sleep(0)
                    assert not closing.done()
                finally:
                    release.set()
                    await asyncio.wait_for(app.state.wallet_service.close(), timeout=3)
                    await asyncio.gather(request, return_exceptions=True)
            await closing
            assert app.state.app_database.idempotency(alice["user"]["id"], "worker")["state"] == "accepted"
            assert len(await app.state.node.get_pending_transactions()) == 1
    asyncio.run(scenario())


@pytest.mark.parametrize("child_amount,expected", [(20, 18), (38, 0)])
def test_pending_incoming_excludes_change_spent_by_child(child_amount, expected):
    async def scenario():
        async with application() as (app, client):
            alice = await register(client)
            bob = await register(client, "bob")
            address = alice["wallet"]["address"]
            recipient = bob["wallet"]["address"]
            await fund(app.state.node, address)
            await login(client)
            parent_receipt = await client.post("/api/v1/wallet/send", headers={**await csrf(client), "Idempotency-Key": "parent"},
                                              json={"recipient_address": recipient, "amount": 10, "fee": 1})
            assert parent_receipt.status_code == 201
            parent = (await app.state.node.get_pending_transactions())[0]
            wallet = app.state.app_database.wallet(alice["user"]["id"])
            key = app.state.wallet_service.keystore.decrypt_private_key(wallet["encrypted_private_key"], wallet["key_version"])
            child = build_signed_transaction(selected_utxos=[((parent.txid(), 1), parent.outputs[1])],
                                             sender_address=address, recipient_address=recipient,
                                             amount=child_amount, fee=1, private_key=key)
            del key
            assert await app.state.node.submit_transaction(child)
            summary = (await client.get("/api/v1/wallet")).json()
            assert summary["pending_incoming"] == expected
            assert summary["pending_outgoing"] == 50
            assert summary["available_balance"] == 0
            assert summary["pending_count"] == 2
            # Outpoint-based accounting must not depend on mempool ordering.
            view = await app.state.node.get_wallet_state(address)
            view["pending"].reverse()
            with patch.object(app.state.node, "get_wallet_state", return_value=view):
                assert (await client.get("/api/v1/wallet")).json()["pending_incoming"] == expected
            from mining.miner import mine_block
            block = mine_block(await app.state.node.create_mempool_block_template(recipient), max_nonce=100_000)
            assert block is not None and await app.state.node.accept_block(block)
            confirmed = (await client.get("/api/v1/wallet")).json()
            assert confirmed["confirmed_balance"] == expected
            assert confirmed["pending_incoming"] == confirmed["pending_count"] == 0
    asyncio.run(scenario())
