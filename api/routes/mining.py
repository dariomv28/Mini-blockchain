"""Mining API endpoints for template preview, background mining execution, and cancellation."""

from __future__ import annotations

import secrets
from fastapi import APIRouter, Depends, Request, Response, status
from api.errors import APIError
from api.schemas.mining import (
    CandidateTemplateRequest,
    CandidateTemplateResponse,
    MiningCancelResponse,
    MiningJobResponse,
    MiningJobStartRequest,
    MiningJobStartResponse,
)
from auth.dependencies import get_current_user, require_csrf

router = APIRouter(prefix="/mining", tags=["Mining"])


def require_mining_permission(request: Request, user: dict) -> None:
    config = request.app.state.config
    if config.demo_mode:
        return
    # Outside demo mode, mining is a privileged operation restricted to administrators
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]
        if config.admin_token and secrets.compare_digest(token, config.admin_token):
            return
    raise APIError(status.HTTP_403_FORBIDDEN, "FORBIDDEN", "Mining requires demo mode or administrator privileges")


@router.get("/template", response_model=CandidateTemplateResponse)
@router.post("/template", response_model=CandidateTemplateResponse)
async def preview_template(
    request: Request,
    response: Response,
    body: CandidateTemplateRequest | None = None,
    user=Depends(get_current_user),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    wallet = request.app.state.app_database.wallet(user["id"])
    if not wallet:
        raise APIError(status.HTTP_404_NOT_FOUND, "WALLET_NOT_FOUND", "User has no configured wallet")

    req_body = body if body is not None else CandidateTemplateRequest()
    return await request.app.state.mining_service.build_candidate_template(
        miner_address=wallet["address"],
        max_transactions=req_body.max_transactions,
        max_bytes=req_body.max_bytes,
    )


@router.post("/jobs", response_model=MiningJobStartResponse, status_code=status.HTTP_201_CREATED)
async def start_mining_job(
    request: Request,
    response: Response,
    body: MiningJobStartRequest | None = None,
    user=Depends(require_csrf),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    require_mining_permission(request, user)
    wallet = request.app.state.app_database.wallet(user["id"])
    if not wallet:
        raise APIError(status.HTTP_404_NOT_FOUND, "WALLET_NOT_FOUND", "User has no configured wallet")

    req_body = body if body is not None else MiningJobStartRequest()
    job = await request.app.state.mining_service.create_job(
        user_id=user["id"],
        miner_address=wallet["address"],
        max_transactions=req_body.max_transactions,
        max_bytes=req_body.max_bytes,
        max_nonce=req_body.max_nonce,
    )
    return {"job_id": job.id, "status": job.status}


@router.get("/jobs/active", response_model=MiningJobResponse | None)
async def get_active_job(
    request: Request,
    response: Response,
    user=Depends(get_current_user),
) -> dict | None:
    response.headers["Cache-Control"] = "no-store"
    job = request.app.state.mining_service.get_active_job()
    return job.to_dict() if job is not None else None


@router.get("/jobs/{job_id}", response_model=MiningJobResponse)
async def get_job_status(
    job_id: str,
    request: Request,
    response: Response,
    user=Depends(get_current_user),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    job = request.app.state.mining_service.get_job(job_id)
    return job.to_dict()


@router.delete("/jobs/{job_id}", response_model=MiningCancelResponse)
async def cancel_job(
    job_id: str,
    request: Request,
    response: Response,
    user=Depends(require_csrf),
) -> dict:
    response.headers["Cache-Control"] = "no-store"
    is_admin = False
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[len("Bearer "):]
        config = request.app.state.config
        if config.admin_token and secrets.compare_digest(token, config.admin_token):
            is_admin = True
    return await request.app.state.mining_service.cancel_job(
        job_id, user_id=user["id"], is_admin=is_admin
    )
