"""Tests supply isolated app storage and non-production secrets explicitly."""

import pytest
from cryptography.fernet import Fernet

TEST_MASTER_KEY = Fernet.generate_key().decode("ascii")


@pytest.fixture(autouse=True)
def isolated_application_settings(monkeypatch):
    monkeypatch.setenv("PYC_APP_DB", ":memory:")
    monkeypatch.setenv("PYC_WALLET_MASTER_KEY", TEST_MASTER_KEY)
    monkeypatch.setenv("PYC_JWT_SECRET", "phase11-test-only-secret-material-1234567890")
