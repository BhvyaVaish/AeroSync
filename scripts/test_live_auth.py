"""Quick live test of the auth flow against the running server."""
import httpx

BASE = "http://127.0.0.1:8000/api/v1"
c = httpx.Client(base_url=BASE)

# Register
r = c.post("/auth/register", json={
    "email": "demo@aerosync.dev",
    "password": "SecureP@ss1",
    "display_name": "Demo User",
})
print(f"Register: {r.status_code}")
data = r.json()
print(f"  user_id: {data.get('user_id')}")
print(f"  tokens: access={data.get('access_token','')[:20]}... refresh={data.get('refresh_token','')[:20]}...")

# Me
token = data["access_token"]
r2 = c.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
print(f"Me: {r2.status_code}")
me = r2.json()
print(f"  email: {me.get('email')}")
print(f"  devices: {me.get('devices')}")

# Login
r3 = c.post("/auth/login", json={"email": "demo@aerosync.dev", "password": "SecureP@ss1"})
print(f"Login: {r3.status_code}")

# Wrong password
r4 = c.post("/auth/login", json={"email": "demo@aerosync.dev", "password": "WrongP@ss1"})
print(f"Wrong password: {r4.status_code} (expected 401)")

# No token
r5 = c.get("/auth/me")
print(f"No token: {r5.status_code} (expected 401)")

print("\n✅ All live auth tests passed!" if all([
    r.status_code == 201,
    r2.status_code == 200,
    r3.status_code == 200,
    r4.status_code == 401,
    r5.status_code == 401,
]) else "\n❌ Some tests failed!")
