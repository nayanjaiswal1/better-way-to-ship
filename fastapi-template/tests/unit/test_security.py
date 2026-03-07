"""Unit tests for security utilities."""
from __future__ import annotations

import pytest

from app.core.security import create_access_token, decode_access_token, hash_password, verify_password


@pytest.mark.unit
def test_password_hash_and_verify() -> None:
    plain = "correct-horse-battery-staple"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed)


@pytest.mark.unit
def test_wrong_password_fails_verification() -> None:
    hashed = hash_password("original")
    assert not verify_password("wrong", hashed)


@pytest.mark.unit
def test_access_token_round_trip() -> None:
    token = create_access_token(subject="user-123")
    payload = decode_access_token(token)
    assert payload["sub"] == "user-123"


@pytest.mark.unit
def test_invalid_token_raises() -> None:
    with pytest.raises(ValueError, match="Invalid or expired token"):
        decode_access_token("not.a.valid.token")
