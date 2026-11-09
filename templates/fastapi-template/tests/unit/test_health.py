"""Health endpoint smoke tests."""
from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.unit
async def test_health_returns_200(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200


@pytest.mark.unit
async def test_health_response_shape(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    body = response.json()
    assert "status" in body
    assert "version" in body
    assert body["status"] == "ok"
