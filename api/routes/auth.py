import time

from fastapi import APIRouter, Depends, Request, Response

from api.schemas.auth import LoginRequest, RegisterRequest
from auth.dependencies import (CSRF_COOKIE, SESSION_COOKIE, csrf_digest, get_current_user,
                               new_csrf, read_session, require_csrf, verify_csrf)
from api.errors import APIError

router = APIRouter(prefix="/auth", tags=["Authentication"])


def public_identity(database, user):
    wallet = database.wallet(user["id"])
    return {"user": {"id": user["id"], "username": user["username"], "email": user["email"]},
            "wallet": {"address": wallet["address"]}}


def set_csrf_cookie(response, config, token):
    response.set_cookie(CSRF_COOKIE, token, httponly=False, secure=config.cookie_secure,
                        samesite="lax", path="/", max_age=config.session_seconds)


@router.get("/csrf")
async def csrf(request: Request, response: Response):
    config = request.app.state.config
    if request.cookies.get(SESSION_COOKIE):
        try:
            _, claims = read_session(request)
            token = claims["csrf"]
        except APIError as exc:
            if exc.status_code != 401:
                raise
            response.delete_cookie(SESSION_COOKIE, path="/", secure=config.cookie_secure, samesite="lax")
            token = new_csrf(config.jwt_secret.get_secret_value())
    else:
        token = new_csrf(config.jwt_secret.get_secret_value())
    set_csrf_cookie(response, config, token)
    response.headers["Cache-Control"] = "no-store"
    return {"csrf_token": token}


@router.post("/register", status_code=201, dependencies=[Depends(verify_csrf)])
async def register(body: RegisterRequest, request: Request):
    user = await request.app.state.auth_service.register(body.email, body.username, body.password)
    return public_identity(request.app.state.app_database, user)


@router.post("/login", dependencies=[Depends(verify_csrf)])
async def login(body: LoginRequest, request: Request, response: Response):
    state = request.app.state
    ip = request.client.host if request.client else "127.0.0.1"
    user = await state.auth_service.login(body.identifier, body.password, ip)
    csrf_token = new_csrf(state.config.jwt_secret.get_secret_value())
    token, claims = state.tokens.create(user["id"], csrf_token)
    with state.app_database.transaction():
        state.app_database.execute("DELETE FROM sessions WHERE expires_at<=?", (int(time.time()),))
        if request.cookies.get(SESSION_COOKIE):
            _, previous = read_session(request)
            state.app_database.execute("DELETE FROM sessions WHERE token_id=?", (previous["jti"],))
        state.app_database.execute("INSERT INTO sessions(token_id,user_id,csrf_hash,expires_at) VALUES(?,?,?,?)",
                                   (claims["jti"], user["id"], csrf_digest(csrf_token), claims["exp"]))
    response.set_cookie(SESSION_COOKIE, token, httponly=True, secure=state.config.cookie_secure,
                        samesite="lax", path="/", max_age=state.config.session_seconds)
    set_csrf_cookie(response, state.config, csrf_token)
    response.headers["Cache-Control"] = "no-store"
    return {**public_identity(state.app_database, user), "csrf_token": csrf_token}


@router.get("/me")
async def me(request: Request, response: Response, user=Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    return public_identity(request.app.state.app_database, user)


@router.post("/logout")
async def logout(request: Request, response: Response, user=Depends(require_csrf)):
    _, claims = read_session(request)
    request.app.state.app_database.execute("DELETE FROM sessions WHERE token_id=?", (claims["jti"],))
    for name in (SESSION_COOKIE, CSRF_COOKIE):
        response.delete_cookie(name, path="/", secure=request.app.state.config.cookie_secure, samesite="lax")
    return {"logged_out": True}
