"""Tests for API configuration, seed parsing, and startup validation."""

from __future__ import annotations

import os
import pytest
from api.config import ApiConfig


def test_config_seed_parsing_formats(monkeypatch):
    # 1. CSV string
    monkeypatch.setenv("PYC_NODE_SEEDS", "127.0.0.1:5002,127.0.0.1:5003")
    cfg_csv = ApiConfig()
    assert cfg_csv.node_seeds == ["127.0.0.1:5002", "127.0.0.1:5003"]

    # 2. JSON list string
    monkeypatch.setenv("PYC_NODE_SEEDS", '["127.0.0.1:5004", "127.0.0.1:5005"]')
    cfg_json = ApiConfig()
    assert cfg_json.node_seeds == ["127.0.0.1:5004", "127.0.0.1:5005"]

    # 3. Empty string
    monkeypatch.setenv("PYC_NODE_SEEDS", "")
    cfg_empty = ApiConfig()
    assert cfg_empty.node_seeds == []

    # 4. Direct list in kwargs
    cfg_direct = ApiConfig(node_seeds=["127.0.0.1:5006"])
    assert cfg_direct.node_seeds == ["127.0.0.1:5006"]


def test_config_invalid_seeds_raise(monkeypatch):
    # Invalid port
    monkeypatch.setenv("PYC_NODE_SEEDS", "127.0.0.1:notaport")
    with pytest.raises(ValueError, match="Invalid seed"):
        ApiConfig()

    # Missing port
    monkeypatch.setenv("PYC_NODE_SEEDS", "127.0.0.1")
    with pytest.raises(ValueError, match="missing port"):
        ApiConfig()

    # Non-private / non-loopback IP (violates NodeConfig policy)
    monkeypatch.setenv("PYC_NODE_SEEDS", "8.8.8.8:5002")
    with pytest.raises(ValueError, match="Invalid seed endpoint"):
        ApiConfig()


def test_config_admin_startup_validation(monkeypatch):
    # Admin enabled without token -> raises ValueError
    monkeypatch.delenv("PYC_ADMIN_TOKEN", raising=False)
    monkeypatch.setenv("PYC_ENABLE_ADMIN_ROUTES", "true")
    monkeypatch.setenv("PYC_DEMO_MODE", "true")
    with pytest.raises(ValueError, match="admin_token must be configured"):
        ApiConfig()

    # Admin enabled with whitespace token -> raises ValueError
    monkeypatch.setenv("PYC_ADMIN_TOKEN", "   ")
    with pytest.raises(ValueError, match="admin_token must be configured"):
        ApiConfig()

    # Admin enabled when demo_mode=false -> raises ValueError
    monkeypatch.setenv("PYC_ADMIN_TOKEN", "valid-token")
    monkeypatch.setenv("PYC_DEMO_MODE", "false")
    with pytest.raises(ValueError, match="demo_mode=True"):
        ApiConfig()


def test_config_wildcard_origin_rejected(monkeypatch):
    monkeypatch.setenv("PYC_FRONTEND_ORIGIN", "*")
    with pytest.raises(ValueError, match="cannot be wildcard"):
        ApiConfig()
