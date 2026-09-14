"""FastAPI application factory for PyChain."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.config import ApiConfig
from api.errors import register_exception_handlers
from api.lifecycle import lifespan
from api.middleware.rate_limiter import InMemoryRateLimiterMiddleware
from api.middleware.size_limit import RequestSizeLimitMiddleware
from api.routes import api_v1_router
from api.routes.admin import router as admin_router
from api.routes.auth import router as auth_router
from api.routes.wallet import router as wallet_router


def create_app(config: ApiConfig | None = None) -> FastAPI:
    if config is None:
        config = ApiConfig()

    app = FastAPI(
        title="PyChain Web API",
        version="0.1.0",
        description="REST and WebSocket interface to the PyChain Bitcoin-like blockchain",
        lifespan=lifespan,
    )

    app.state.config = config

    # Middlewares: Last added wraps first.
    # We want CORSMiddleware on the outermost layer so that 400/413/429 responses
    # produced by inner protection middlewares still contain proper CORS headers.
    app.add_middleware(
        RequestSizeLimitMiddleware,
        max_bytes=config.max_body_bytes,
    )
    app.add_middleware(
        InMemoryRateLimiterMiddleware,
        general_limit=config.rate_limit_per_minute,
        mutation_limit=config.rate_limit_mutation_per_minute,
        admin_limit=config.rate_limit_admin_per_minute,
    )
    allowed_origins = {config.frontend_origin.rstrip("/")}
    for item in list(allowed_origins):
        if "localhost" in item:
            allowed_origins.add(item.replace("localhost", "127.0.0.1"))
        elif "127.0.0.1" in item:
            allowed_origins.add(item.replace("127.0.0.1", "localhost"))

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(allowed_origins),
        allow_credentials=True,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )

    # Exception handling
    register_exception_handlers(app)

    # Include public API v1 routers
    app.include_router(api_v1_router)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(wallet_router, prefix="/api/v1")

    # Conditionally include admin routes: ONLY when BOTH enable_admin_routes AND demo_mode are True
    if config.enable_admin_routes and config.demo_mode:
        app.include_router(admin_router, prefix="/api/v1")

    return app


# Default application instance for uvicorn
app = create_app()
