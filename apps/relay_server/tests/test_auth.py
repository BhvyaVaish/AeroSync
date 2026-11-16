"""
AeroSync Authentication Tests

Tests for registration, login, token refresh, logout, and protected routes.
Uses FastAPI TestClient with an in-memory SQLite database.
"""

import os
import sys
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

# Ensure project root is on path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..")))

# Set test environment variables BEFORE importing app
os.environ["JWT_SECRET"] = "test-secret-key-for-testing-only-min32chars!!"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./test_aerosync.db"
os.environ["ENVIRONMENT"] = "testing"
os.environ["LOG_LEVEL"] = "WARNING"


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Set up a fresh test database for each test."""
    from config.settings import reset_settings
    reset_settings()
    
    from apps.relay_server.core.database import init_database, close_database
    
    # Use in-memory database for tests
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
async def registered_user(client: AsyncClient):
    """Register a test user and return the response data."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "test@example.com",
            "password": "TestPass1!",
            "display_name": "Test User",
        },
    )
    assert response.status_code == 201
    return response.json()


# =============================================================================
# Registration Tests
# =============================================================================

class TestRegistration:
    """Tests for POST /auth/register."""

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient):
        """Register a new user successfully."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "new@example.com",
                "password": "SecureP@ss1",
                "display_name": "New User",
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "user_id" in data
        assert data["email"] == "new@example.com"
        assert data["display_name"] == "New User"
        assert "access_token" in data
        assert "refresh_token" in data

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client: AsyncClient, registered_user):
        """Registering with an existing email returns 409."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "test@example.com",
                "password": "AnotherP@ss1",
            },
        )
        assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_register_invalid_email(self, client: AsyncClient):
        """Registering with invalid email returns 400."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "not-an-email",
                "password": "SecureP@ss1",
            },
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_register_weak_password_no_number(self, client: AsyncClient):
        """Registering with password lacking a number returns 400."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "user@example.com",
                "password": "NoNumber!",
            },
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_register_weak_password_no_special(self, client: AsyncClient):
        """Registering with password lacking a special char returns 400."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "user@example.com",
                "password": "NoSpecial1",
            },
        )
        assert response.status_code == 400

    @pytest.mark.asyncio
    async def test_register_short_password(self, client: AsyncClient):
        """Registering with password < 8 chars returns 400."""
        response = await client.post(
            "/api/v1/auth/register",
            json={
                "email": "user@example.com",
                "password": "Sh1!",
            },
        )
        assert response.status_code == 400


# =============================================================================
# Login Tests
# =============================================================================

class TestLogin:
    """Tests for POST /auth/login."""

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, registered_user):
        """Login with correct credentials returns tokens."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "TestPass1!",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert "refresh_token" in data
        assert data["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, registered_user):
        """Login with wrong password returns 401."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "test@example.com",
                "password": "WrongP@ss1",
            },
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_email(self, client: AsyncClient):
        """Login with non-existent email returns 401."""
        response = await client.post(
            "/api/v1/auth/login",
            json={
                "email": "nobody@example.com",
                "password": "SomeP@ss1",
            },
        )
        assert response.status_code == 401


# =============================================================================
# Protected Route Tests
# =============================================================================

class TestProtectedRoutes:
    """Tests for authentication-protected endpoints."""

    @pytest.mark.asyncio
    async def test_me_with_valid_token(self, client: AsyncClient, registered_user):
        """GET /auth/me with valid token returns user profile."""
        token = registered_user["access_token"]
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["email"] == "test@example.com"
        assert "devices" in data

    @pytest.mark.asyncio
    async def test_me_without_token(self, client: AsyncClient):
        """GET /auth/me without token returns 401."""
        response = await client.get("/api/v1/auth/me")
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_me_with_invalid_token(self, client: AsyncClient):
        """GET /auth/me with invalid token returns 401."""
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": "Bearer invalid-token-here"},
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_me_with_expired_token(self, client: AsyncClient, registered_user):
        """GET /auth/me with expired token returns 401."""
        # Create a token with 0 minute expiry (already expired)
        from apps.relay_server.core.security import _get_jwt_config
        from jose import jwt
        from datetime import datetime, timedelta, timezone
        
        config = _get_jwt_config()
        expired_payload = {
            "sub": registered_user["user_id"],
            "type": "access",
            "iat": datetime.now(timezone.utc) - timedelta(hours=2),
            "exp": datetime.now(timezone.utc) - timedelta(hours=1),
        }
        expired_token = jwt.encode(
            expired_payload, config["secret"], algorithm=config["algorithm"]
        )
        
        response = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert response.status_code == 401


# =============================================================================
# Token Refresh Tests
# =============================================================================

class TestTokenRefresh:
    """Tests for POST /auth/refresh."""

    @pytest.mark.asyncio
    async def test_refresh_success(self, client: AsyncClient, registered_user):
        """Refreshing with valid refresh token returns new access token."""
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": registered_user["refresh_token"]},
        )
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data

    @pytest.mark.asyncio
    async def test_refresh_invalid_token(self, client: AsyncClient):
        """Refreshing with invalid token returns 401."""
        response = await client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": "invalid-refresh-token"},
        )
        assert response.status_code == 401


# =============================================================================
# Logout Tests
# =============================================================================

class TestLogout:
    """Tests for POST /auth/logout."""

    @pytest.mark.asyncio
    async def test_logout_success(self, client: AsyncClient, registered_user):
        """Logout with valid token returns success."""
        token = registered_user["access_token"]
        response = await client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True

    @pytest.mark.asyncio
    async def test_logout_without_token(self, client: AsyncClient):
        """Logout without token returns 401."""
        response = await client.post("/api/v1/auth/logout")
        assert response.status_code == 401
