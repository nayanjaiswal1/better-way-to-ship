"""Smoke tests to verify the test infrastructure works correctly."""
from __future__ import annotations

import pytest


@pytest.mark.unit
def test_django_is_configured() -> None:
    import django

    assert django.VERSION >= (5, 0)
