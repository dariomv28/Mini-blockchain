import hashlib
import hmac
import secrets

from fastapi import Depends, Request

from api.errors import APIError
from auth.token import TokenError

SESSION_COOKIE = "pychain_session"
CSRF_COOKIE = "pychain_csrf"


def new_csrf(secret):
    nonce = secrets.token_hex(32)
    signature = hmac.new(secret.encode("utf-8"), nonce.encode("ascii"), hashlib.sha256).hexdigest()
    return nonce + "." + signature


def csrf_digest(token):
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def read_session(request):
    cookie = request.cookies.get(SESSION_COOKIE)
    if not cookie or len(cookie) > 4096:
        raise APIError(401, "UNAUTHORIZED", "Authentication required")
    try:
        claims = request.app.state.tokens.decode(cookie)
    except TokenError:
        raise APIError(401, "UNAUTHORIZED", "Invalid or expired session") from None
    database = request.app.state.app_database
    record = database.session(claims["jti"])
    if record is None or record["user_id"] != int(claims["sub"]) or record["expires_at"] != claims["exp"]:
        raise APIError(401, "UNAUTHORIZED", "Invalid or expired session")
    if not hmac.compare_digest(record["csrf_hash"], csrf_digest(claims["csrf"])):
        raise APIError(401, "UNAUTHORIZED", "Invalid or expired session")
    user = database.user(record["user_id"])
    if user is None:
        raise APIError(401, "UNAUTHORIZED", "Invalid or expired session")
    return user, claims


async def get_current_user(request: Request):
    user, _ = read_session(request)
    return user


async def verify_csrf(request: Request):
    origin = request.headers.get("origin")
    allowed = {request.app.state.config.frontend_origin, str(request.base_url).rstrip("/")}
    if origin is not None and origin not in allowed:
        raise APIError(403, "CSRF_FAILED", "Invalid request origin")
    header = request.headers.get("x-csrf-token", "")
    cookie = request.cookies.get(CSRF_COOKIE, "")
    if not header or len(header) > 256 or not header.isascii() or not cookie.isascii() or not hmac.compare_digest(header, cookie):
        raise APIError(403, "CSRF_FAILED", "CSRF token required")
    secret = request.app.state.config.jwt_secret.get_secret_value()
    parts = header.split(".")
    if len(parts) != 2 or len(parts[0]) != 64 or len(parts[1]) != 64:
        raise APIError(403, "CSRF_FAILED", "Invalid CSRF token")
    signature = hmac.new(secret.encode("utf-8"), parts[0].encode("ascii"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, parts[1]):
        raise APIError(403, "CSRF_FAILED", "Invalid CSRF token")
    if request.cookies.get(SESSION_COOKIE):
        _, claims = read_session(request)
        if not hmac.compare_digest(header, claims["csrf"]):
            raise APIError(403, "CSRF_FAILED", "CSRF token does not match session")


async def require_csrf(request: Request, user=Depends(get_current_user)):
    await verify_csrf(request)
    return user
