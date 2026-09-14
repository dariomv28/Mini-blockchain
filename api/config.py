"""Configuration for the PyChain API."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from network.config import NodeConfig


class ApiConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="PYC_",
        env_file=".env",
        env_file_encoding="utf-8-sig",
        extra="ignore",
        populate_by_name=True,
    )

    api_host: str = Field(default="127.0.0.1", alias="PYC_API_HOST")
    api_port: int = Field(default=8000, alias="PYC_API_PORT")

    node_db: str | None = Field(default=None, alias="PYC_NODE_DB")
    node_host: str = Field(default="127.0.0.1", alias="PYC_NODE_HOST")
    node_port: int = Field(default=5001, alias="PYC_NODE_PORT")
    node_seeds: Any = Field(default_factory=list, alias="PYC_NODE_SEEDS")
    app_db: str = Field(default="data/app.sqlite3", alias="PYC_APP_DB")
    wallet_master_key: SecretStr | None = Field(default=None, alias="PYC_WALLET_MASTER_KEY")
    jwt_secret: SecretStr | None = Field(default=None, alias="PYC_JWT_SECRET")
    cookie_secure: bool = Field(default=False, alias="PYC_COOKIE_SECURE")
    session_seconds: int = Field(default=3600, ge=60, le=86400, alias="PYC_SESSION_SECONDS")

    frontend_origin: str = Field(default="http://localhost:5173", alias="PYC_FRONTEND_ORIGIN")
    enable_admin_routes: bool = Field(default=False, alias="PYC_ENABLE_ADMIN_ROUTES")
    admin_token: str | None = Field(default=None, alias="PYC_ADMIN_TOKEN")
    demo_mode: bool = Field(default=True, alias="PYC_DEMO_MODE")

    rate_limit_per_minute: int = Field(default=120, alias="PYC_RATE_LIMIT_PER_MINUTE")
    rate_limit_mutation_per_minute: int = Field(default=30, alias="PYC_RATE_LIMIT_MUTATION_PER_MINUTE")
    rate_limit_admin_per_minute: int = Field(default=5, alias="PYC_RATE_LIMIT_ADMIN_PER_MINUTE")

    max_body_bytes: int = Field(default=1_048_576, alias="PYC_MAX_BODY_BYTES")

    ws_max_clients: int = Field(default=50, alias="PYC_WS_MAX_CLIENTS")
    ws_max_clients_per_ip: int = Field(default=5, alias="PYC_WS_MAX_CLIENTS_PER_IP")
    ws_status_interval: float = Field(default=1.0, alias="PYC_WS_STATUS_INTERVAL")
    ws_ping_interval: float = Field(default=20.0, alias="PYC_WS_PING_INTERVAL")
    ws_idle_timeout: float = Field(default=60.0, alias="PYC_WS_IDLE_TIMEOUT")
    ws_max_message_bytes: int = Field(default=4096, alias="PYC_WS_MAX_MESSAGE_BYTES")

    @field_validator("admin_token")
    @classmethod
    def validate_admin_token(cls, token: str | None) -> str | None:
        if token is not None and (
            not token or not all("!" <= char <= "~" for char in token)
        ):
            raise ValueError("admin_token must be configured with printable ASCII characters without whitespace")
        return token

    @field_validator("frontend_origin")
    @classmethod
    def validate_origin(cls, v: str) -> str:
        s = v.strip()
        if not s or s == "*":
            raise ValueError("frontend_origin must be a specific origin URL and cannot be wildcard or empty")
        return s.rstrip("/")

    @field_validator("node_seeds", mode="before")
    @classmethod
    def parse_seeds(cls, v: object) -> list[str]:
        if v is None:
            return []

        raw_items: list[Any] = []
        if isinstance(v, str):
            s = v.strip()
            if not s:
                return []
            if s.startswith("[") and s.endswith("]"):
                try:
                    parsed = json.loads(s)
                    if not isinstance(parsed, list):
                        raise ValueError("JSON seed config must be a list")
                    raw_items = parsed
                except Exception as err:
                    raise ValueError(f"Invalid JSON in node_seeds: {err}") from err
            else:
                raw_items = [part.strip() for part in s.split(",") if part.strip()]
        elif isinstance(v, (list, tuple)):
            raw_items = list(v)
        else:
            raise ValueError("node_seeds must be a CSV string or a list of host:port strings")

        checker = NodeConfig()
        cleaned: list[str] = []
        for item in raw_items:
            if not isinstance(item, str) or not item.strip():
                raise ValueError(f"Seed endpoint must be a non-empty string: {item!r}")
            token = item.strip()
            if ":" not in token:
                raise ValueError(f"Seed endpoint missing port: {token!r}")
            host, port_str = token.rsplit(":", 1)
            try:
                port = int(port_str)
            except ValueError as err:
                raise ValueError(f"Invalid seed port in {token!r}") from err

            # Validate network policy with NodeConfig
            try:
                norm_host, norm_port = checker.validate_endpoint(host, port)
            except Exception as err:
                raise ValueError(f"Invalid seed endpoint {token!r}: {err}") from err

            normalized = f"{norm_host}:{norm_port}"
            if normalized not in cleaned:
                cleaned.append(normalized)

        return cleaned

    @model_validator(mode="after")
    def validate_overall(self) -> "ApiConfig":
        # Ports
        if not (0 <= self.api_port <= 65535):
            raise ValueError("api_port must be between 0 and 65535")
        if not (0 <= self.node_port <= 65535):
            raise ValueError("node_port must be between 0 and 65535")

        # Quotas
        for name, val in (
            ("rate_limit_per_minute", self.rate_limit_per_minute),
            ("rate_limit_mutation_per_minute", self.rate_limit_mutation_per_minute),
            ("rate_limit_admin_per_minute", self.rate_limit_admin_per_minute),
            ("max_body_bytes", self.max_body_bytes),
            ("ws_max_clients", self.ws_max_clients),
            ("ws_max_clients_per_ip", self.ws_max_clients_per_ip),
            ("ws_max_message_bytes", self.ws_max_message_bytes),
        ):
            if type(val) is not int or val <= 0:
                raise ValueError(f"{name} must be a positive integer")

        # Durations
        for name, val in (
            ("ws_status_interval", self.ws_status_interval),
            ("ws_ping_interval", self.ws_ping_interval),
            ("ws_idle_timeout", self.ws_idle_timeout),
        ):
            if not isinstance(val, (int, float)) or val <= 0 or not math.isfinite(val):
                raise ValueError(f"{name} must be a positive finite duration")

        # Admin routes & Token
        if self.enable_admin_routes:
            if not self.demo_mode:
                raise ValueError("enable_admin_routes can only be enabled when demo_mode=True")
            if not self.admin_token or not self.admin_token.strip():
                raise ValueError("admin_token must be configured and non-empty when enable_admin_routes is True")

        return self

    @property
    def node_db_path(self) -> Path | None:
        if self.node_db:
            return Path(self.node_db)
        return None
