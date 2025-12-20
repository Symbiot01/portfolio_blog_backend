# app/auth/backend.py
import os
from fastapi_users.authentication import (
    AuthenticationBackend,
    BearerTransport,
    JWTStrategy,
)

SECRET = os.getenv("SECRET_KEY")
if not SECRET:
    # Fail fast in production instead of returning 500 during login.
    raise RuntimeError("SECRET_KEY environment variable is required for JWT auth")

# This URL tells the frontend where to send the username and password for login
bearer_transport = BearerTransport(tokenUrl="api/auth/jwt/login")

def get_jwt_strategy() -> JWTStrategy:
    """Returns the JWT strategy instance configured with our secret key."""
    return JWTStrategy(secret=SECRET, lifetime_seconds=3600)

# This is the main authentication object that fastapi-users will use
auth_backend = AuthenticationBackend(
    name="jwt",
    transport=bearer_transport,
    get_strategy=get_jwt_strategy,
)