import asyncio
import time

import jwt
import pytest

from auth.password import hash_password, verify_password
from auth.service import LoginGuard
from auth.token import TokenError, TokenService
from api.errors import APIError
from phase11_helpers import PASSWORD, application, csrf, login, register


def test_password_is_argon2id_and_wrong_password_is_rejected():
    hashed = hash_password(PASSWORD)
    assert hashed != PASSWORD and hashed.startswith("$argon2id$")
    assert verify_password(hashed, PASSWORD)
    assert not verify_password(hashed, "wrong")
    assert not verify_password("malformed", PASSWORD)


def test_jwt_expiry_signature_and_algorithm_are_checked():
    service = TokenService("test-secret-material-01234567890123456789")
    token, claims = service.create(1, "csrf")
    assert service.decode(token)["sub"] == "1"
    claims["exp"] = int(time.time()) - 1
    expired = jwt.encode(claims, service.secret, algorithm="HS256")
    for invalid in (expired, "malformed", TokenService("another-secret-material-0123456789012345").create(1,"csrf")[0],
                    jwt.encode(claims, "", algorithm="none")):
        with pytest.raises(TokenError):
            service.decode(invalid)


def test_login_guard_has_identifier_ip_windows_and_failure_cooldown():
    now = [0.0]
    guard = LoginGuard(clock=lambda: now[0])
    for _ in range(5):
        guard.failed(guard.check("ip", "alice"))
    with pytest.raises(APIError) as limited:
        guard.check("other-ip", "alice")
    assert limited.value.status_code == 429
    now[0] = 61
    guard.check("ip", "alice")
    for i in range(19):
        guard.check("ip", "different" + str(i))
    with pytest.raises(APIError):
        guard.check("ip", "yet-another")


def test_register_uniqueness_cookies_login_and_logout():
    async def scenario():
        async with application() as (app, client):
            identity = await register(client)
            database = app.state.app_database
            user = database.user(identity["user"]["id"])
            wallet = database.wallet(user["id"])
            assert user["password_hash"] != PASSWORD
            assert wallet["key_version"] == 1
            assert wallet["encrypted_private_key"] != wallet["public_key"].encode()
            assert "private_key" not in str(identity)
            for data in [dict(email="ALICE@example.com",username="other",password=PASSWORD),
                         dict(email="other@example.com",username="ALICE",password=PASSWORD)]:
                response = await client.post("/api/v1/auth/register",headers=await csrf(client),json=data)
                assert response.status_code == 409
            assert database.execute("SELECT count(*) FROM users").fetchone()[0] == 1
            assert database.execute("SELECT count(*) FROM wallets").fetchone()[0] == 1
            unknown = await login(client,"missing")
            wrong = await login(client,"alice","wrong")
            assert unknown.status_code == wrong.status_code == 401
            assert unknown.json() == wrong.json()
            response = await login(client,"alice@example.com")
            assert response.status_code == 200
            cookie = next(value for value in response.headers.get_list("set-cookie") if value.startswith("pychain_session="))
            assert "HttpOnly" in cookie and "SameSite=lax" in cookie and "Path=/" in cookie
            assert "pychain_session" not in response.json()
            assert (await client.get("/api/v1/auth/me")).json()["user"]["id"] == user["id"]
            stolen_cookie = client.cookies.get("pychain_session")
            assert (await client.post("/api/v1/auth/logout", headers=await csrf(client))).status_code == 200
            assert (await client.get("/api/v1/auth/me")).status_code == 401
            client.cookies.set("pychain_session", stolen_cookie, domain="test.local", path="/")
            assert (await client.get("/api/v1/auth/me")).status_code == 401
            # A bootstrap request clears an expired/revoked cookie so login works again.
            assert (await login(client)).status_code == 200
    asyncio.run(scenario())


def test_csrf_protection_and_session_requirement():
    async def scenario():
        async with application() as (_, client):
            assert (await client.get("/api/v1/wallet")).status_code == 401
            response = await client.post("/api/v1/auth/register",json={"email":"alice@example.com","username":"alice","password":PASSWORD})
            assert response.status_code == 403
            await register(client)
            assert (await login(client)).status_code == 200
            data = {"recipient_address": "PYC_" + "a"*48,"amount":1,"fee":0}
            assert (await client.post("/api/v1/wallet/send",json=data)).status_code == 403
            headers = await csrf(client)
            headers["Origin"] = "http://evil.example"
            assert (await client.post("/api/v1/auth/logout",headers=headers)).status_code == 403
            assert (await client.get("/api/v1/auth/me")).status_code == 200
    asyncio.run(scenario())


def test_csrf_token_from_another_session_and_forged_cookie_are_rejected():
    async def scenario():
        from httpx import ASGITransport, AsyncClient
        async with application() as (app, alice):
            await register(alice)
            await register(alice,"bob")
            await login(alice)
            alice_token = (await csrf(alice))["X-CSRF-Token"]
            async with AsyncClient(transport=ASGITransport(app=app),base_url="http://test") as bob:
                await login(bob,"bob")
                bob.cookies.set("pychain_csrf",alice_token,domain="test.local",path="/")
                denied = await bob.post("/api/v1/auth/logout",headers={"X-CSRF-Token":alice_token})
                assert denied.status_code == 403
                assert (await bob.get("/api/v1/auth/me")).json()["user"]["username"] == "bob"
            anonymous = "a"*64 + "." + "b"*64
            alice.cookies.clear()
            alice.cookies.set("pychain_csrf",anonymous,domain="test.local",path="/")
            denied = await alice.post("/api/v1/auth/login",headers={"X-CSRF-Token":anonymous},json={"identifier":"alice","password":PASSWORD})
            assert denied.status_code == 403
    asyncio.run(scenario())


@pytest.mark.parametrize("registered_email", ["alice@xn--bcher-kva.de", "alice@bücher.de"])
def test_idna_email_register_and_login_share_canonical_identity(registered_email):
    async def scenario():
        async with application() as (_, client):
            response = await client.post("/api/v1/auth/register", headers=await csrf(client),
                                        json={"email": registered_email, "username": "alice", "password": PASSWORD})
            assert response.status_code == 201
            identity = response.json()
            assert identity["user"]["email"] == "alice@bücher.de"
            for identifier in ("alice@xn--bcher-kva.de", "alice@bücher.de", " ALICE@XN--BCHER-KVA.DE ", "ALICE"):
                logged_in = await login(client, identifier)
                assert logged_in.status_code == 200, logged_in.text
                assert logged_in.json()["user"]["id"] == identity["user"]["id"]
            duplicate = await client.post("/api/v1/auth/register", headers=await csrf(client),
                                         json={"email": "alice@bücher.de", "username": "other", "password": PASSWORD})
            assert duplicate.status_code == 409
            unknown = await login(client, "unknown@xn--bcher-kva.de")
            malformed = await login(client, "unknown@")
            assert unknown.status_code == malformed.status_code == 401
            assert unknown.json() == malformed.json()
    asyncio.run(scenario())
