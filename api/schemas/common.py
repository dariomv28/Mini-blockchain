"""Common API schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ErrorDetail(BaseModel):
    code: str = Field(..., description="Machine-readable error code")
    message: str = Field(..., description="Human-readable error description")


class ErrorResponse(BaseModel):
    error: ErrorDetail


class PaginationParams(BaseModel):
    start: int = Field(default=0, ge=0, description="Starting block height (0-indexed)")
    limit: int = Field(default=20, ge=1, le=100, description="Maximum number of items to return (1-100)")
