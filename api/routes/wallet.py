import re

from fastapi import APIRouter, Depends, Header, Query, Request, Response

from api.errors import APIError
from api.schemas.wallet import SendRequest
from auth.dependencies import get_current_user, require_csrf

router = APIRouter(prefix="/wallet", tags=["Wallet"])


@router.get("")
async def summary(request: Request, response: Response, user=Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    return await request.app.state.wallet_service.get_wallet_summary(user["id"])


@router.get("/transactions")
async def history(request: Request, response: Response, start: int = Query(0, ge=0),
                  limit: int = Query(20, ge=1, le=100), user=Depends(get_current_user)):
    response.headers["Cache-Control"] = "no-store"
    return await request.app.state.wallet_service.history(user["id"], start, limit)


@router.post("/send", status_code=201)
async def send(body: SendRequest, request: Request, response: Response, idempotency_key: str | None = Header(default=None), user=Depends(require_csrf)):
    response.headers["Cache-Control"] = "no-store"
    if idempotency_key is None or not re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", idempotency_key):
        raise APIError(400, "INVALID_IDEMPOTENCY_KEY", "Idempotency-Key with 1-128 ASCII letters, digits or ._:- is required")
    return await request.app.state.wallet_service.send(user["id"], body.recipient_address, body.amount, body.fee, idempotency_key)
