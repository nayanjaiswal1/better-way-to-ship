from __future__ import annotations

import pytest
from django.test import Client


@pytest.fixture
def client() -> Client:
    return Client()


@pytest.fixture
def api_client():  # type: ignore[no-untyped-def]
    from rest_framework.test import APIClient

    return APIClient()
