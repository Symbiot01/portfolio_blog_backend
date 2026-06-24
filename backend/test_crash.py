from fastapi.testclient import TestClient
from main import app
import asyncio

# The app uses Beanie, so we need an event loop and init_db before testing.
# TestClient doesn't do lifespan by default in some older versions, or we can use "with TestClient(app) as client:"
with TestClient(app) as client:
    response = client.post(
        "/api/auth/register",
        json={
            "email": "testcrash@example.com",
            "password": "test123@",
            "is_active": True,
            "is_superuser": True,
            "is_verified": True,
            "username": "crash123"
        }
    )
    print("Status:", response.status_code)
    print("Response:", response.text)
