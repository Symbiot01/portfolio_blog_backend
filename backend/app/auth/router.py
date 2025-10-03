# app/auth/router.py
from fastapi import APIRouter
from app.auth.core import fastapi_users
from app.auth.schemas import UserRead, UserCreate
from app.auth.backend import auth_backend

# Create a single router to combine all auth routes
router = APIRouter()

# Router for JWT login/logout
router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/jwt",
    tags=["Auth"],
)
# Router for registration
router.include_router(
    fastapi_users.get_register_router(UserRead, UserCreate),
    tags=["Auth"],
)
# Router for user management (e.g., get /me)
router.include_router(
    fastapi_users.get_users_router(UserRead, UserRead),
    prefix="/users",
    tags=["Users"],
)