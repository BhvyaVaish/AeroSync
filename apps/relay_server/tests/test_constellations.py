"""
AeroSync Constellation Tests

Tests for:
1. Creating a constellation room with unique join code
2. Joining a constellation room via unique code
3. Enforcing the strict limit of maximum 5 computers per constellation
4. Duplicate join rejection
5. Leaving a constellation
6. Transfer target discovery within constellation rooms
"""

import os
import sys
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

os.environ["JWT_SECRET"] = "test-secret-key-for-testing-only-min32chars!!"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ENVIRONMENT"] = "testing"
os.environ["LOG_LEVEL"] = "WARNING"


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Set up a fresh in-memory database for each test."""
    from config.settings import reset_settings
    reset_settings()
    
    from apps.relay_server.core.database import init_database, close_database
    await init_database(":memory:")
    yield
    await close_database()


@pytest_asyncio.fixture
async def client():
    """Create an async test client."""
    from apps.relay_server.main import create_app
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def auth_token(client: AsyncClient):
    """Register a test user and return their access token."""
    reg_res = await client.post(
        "/api/v1/auth/register",
        json={"email": "constellation_user@example.com", "password": "Password123!", "display_name": "Constellation Tester"},
    )
    assert reg_res.status_code == 201
    return reg_res.json()["access_token"]


async def register_device(client: AsyncClient, token: str, name: str, fp: str) -> str:
    """Helper to register a device and return its device_id."""
    res = await client.post(
        "/api/v1/devices/register",
        headers={"Authorization": f"Bearer {token}"},
        json={"device_name": name, "device_fingerprint": fp, "platform": "windows"},
    )
    assert res.status_code == 201
    return res.json()["device_id"]


@pytest.mark.asyncio
async def test_create_constellation(client: AsyncClient, auth_token: str):
    """Test creating a new constellation generates unique join code."""
    dev_id = await register_device(client, auth_token, "PC-Alpha", "fp-alpha-001")
    
    res = await client.post(
        "/api/v1/constellations/create",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"name": "Alpha Studio", "device_id": dev_id},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["name"] == "Alpha Studio"
    assert data["join_code"].startswith("CST-")
    assert data["device_count"] == 1
    assert data["max_devices"] == 5
    assert not data["is_full"]
    assert len(data["members"]) == 1
    assert data["members"][0]["device_id"] == dev_id


@pytest.mark.asyncio
async def test_join_constellation_with_code(client: AsyncClient, auth_token: str):
    """Test joining an existing constellation via unique code."""
    dev1 = await register_device(client, auth_token, "PC-1", "fp-001")
    dev2 = await register_device(client, auth_token, "PC-2", "fp-002")

    # Create room with dev1
    c_res = await client.post(
        "/api/v1/constellations/create",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"name": "Testing Lab", "device_id": dev1},
    )
    join_code = c_res.json()["join_code"]

    # Join with dev2
    j_res = await client.post(
        "/api/v1/constellations/join",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"join_code": join_code, "device_id": dev2},
    )
    assert j_res.status_code == 200
    data = j_res.json()
    assert data["device_count"] == 2
    assert len(data["members"]) == 2
    device_ids = [m["device_id"] for m in data["members"]]
    assert dev1 in device_ids and dev2 in device_ids


@pytest.mark.asyncio
async def test_max_5_computers_limit_enforced(client: AsyncClient, auth_token: str):
    """
    CRITICAL TEST: Ensure maximum 5 computers can be linked together.
    Adding a 6th computer must be rejected with an error.
    """
    # Register 6 devices
    devices = []
    for i in range(1, 7):
        d_id = await register_device(client, auth_token, f"PC-{i}", f"fp-test-00{i}")
        devices.append(d_id)

    # 1. Create room with Device 1
    c_res = await client.post(
        "/api/v1/constellations/create",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"name": "Full House Room", "device_id": devices[0]},
    )
    assert c_res.status_code == 201
    join_code = c_res.json()["join_code"]

    # 2. Join Device 2, 3, 4, 5 (reaches max capacity 5)
    for i in range(1, 5):
        j_res = await client.post(
            "/api/v1/constellations/join",
            headers={"Authorization": f"Bearer {auth_token}"},
            json={"join_code": join_code, "device_id": devices[i]},
        )
        assert j_res.status_code == 200
        data = j_res.json()
        assert data["device_count"] == i + 1

    # Verify room is now full (5/5)
    get_res = await client.get(
        f"/api/v1/constellations/{c_res.json()['id']}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert get_res.json()["device_count"] == 5
    assert get_res.json()["is_full"] is True

    # 3. Attempt to link 6th computer -> MUST FAIL
    sixth_res = await client.post(
        "/api/v1/constellations/join",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"join_code": join_code, "device_id": devices[5]},
    )
    assert sixth_res.status_code == 400
    detail = sixth_res.json()["detail"]
    assert "full" in detail.lower()
    assert "5" in detail


@pytest.mark.asyncio
async def test_duplicate_join_prevented(client: AsyncClient, auth_token: str):
    """Test that a device cannot join the same constellation twice."""
    dev = await register_device(client, auth_token, "PC-Solo", "fp-solo-001")
    c_res = await client.post(
        "/api/v1/constellations/create",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"name": "Solo Room", "device_id": dev},
    )
    join_code = c_res.json()["join_code"]

    # Try to join again with same device
    j_res = await client.post(
        "/api/v1/constellations/join",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"join_code": join_code, "device_id": dev},
    )
    assert j_res.status_code == 400
    assert "already linked" in j_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_leave_constellation(client: AsyncClient, auth_token: str):
    """Test removing a computer from a constellation."""
    dev1 = await register_device(client, auth_token, "PC-1", "fp-l-001")
    dev2 = await register_device(client, auth_token, "PC-2", "fp-l-002")

    c_res = await client.post(
        "/api/v1/constellations/create",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"name": "Departure Room", "device_id": dev1},
    )
    c_id = c_res.json()["id"]
    join_code = c_res.json()["join_code"]

    await client.post(
        "/api/v1/constellations/join",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"join_code": join_code, "device_id": dev2},
    )

    # Dev2 leaves
    leave_res = await client.post(
        f"/api/v1/constellations/{c_id}/leave",
        headers={"Authorization": f"Bearer {auth_token}"},
        json={"device_id": dev2},
    )
    assert leave_res.status_code == 200

    # Verify device_count is now 1
    get_res = await client.get(
        f"/api/v1/constellations/{c_id}",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert get_res.json()["device_count"] == 1
