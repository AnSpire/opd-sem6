import pytest

pytestmark = pytest.mark.asyncio(loop_scope="session")


@pytest.mark.asyncio
async def test_healthz(client):
    r = await client.get("/api/v1/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_readyz(client):
    r = await client.get("/api/v1/readyz")
    assert r.status_code in (200, 503)
    assert r.json()["status"] in ("ok", "degraded")
