# app/auth/core.py
from fastapi_users import FastAPIUsers
from beanie import PydanticObjectId  # <-- CORRECTED: Import from beanie
from app.models.user import User      # <-- User is still imported from here
from app.auth.backend import auth_backend
from app.auth.manager import get_user_manager

# This is the central object that ties everything together
fastapi_users = FastAPIUsers[User, PydanticObjectId](
    get_user_manager,
    [auth_backend],
)

# This is a dependency that can be used in your own API endpoints to get the current user
current_active_user = fastapi_users.current_user(active=True)

# Optional auth dependency for endpoints that support "guest via access link" flows.
# When unauthenticated, this dependency returns None instead of raising 401.
current_optional_user = fastapi_users.current_user(active=True, optional=True)