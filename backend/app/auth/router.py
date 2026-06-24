# app/auth/router.py
from fastapi import APIRouter, Request, Depends, HTTPException, status
from app.auth.core import fastapi_users
from app.auth.schemas import UserRead, UserCreate
from app.auth.backend import auth_backend
from app.auth.manager import get_user_manager
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)

# Create a single router to combine all auth routes
router = APIRouter()

# Router for JWT login/logout
router.include_router(
    fastapi_users.get_auth_router(auth_backend),
    prefix="/jwt",
    tags=["Auth"],
)

register_router = fastapi_users.get_register_router(UserRead, UserCreate)
# Wrap the register endpoint to add rate limiting and security
original_register = None
for route in register_router.routes:
    if route.path == "/register" and "POST" in route.methods:
        original_register = route.endpoint
        
        @limiter.limit("5/minute")
        async def secure_register(
            request: Request,
            user_create: UserCreate,
            user_manager = Depends(get_user_manager)
        ):
            # Security checks to prevent privilege escalation
            # Users should not be able to set their own privileges during registration
            user_create_dict = user_create.dict()
            if getattr(user_create, "is_superuser", False) or user_create_dict.get("is_superuser"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot set is_superuser during registration"
                )
            if getattr(user_create, "is_verified", False) or user_create_dict.get("is_verified"):
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cannot set is_verified during registration"
                )
            
            # Force secure defaults
            user_create.is_superuser = False
            user_create.is_verified = False
            
            return await original_register(request=request, user_create=user_create, user_manager=user_manager)
            
        route.endpoint = secure_register

# Router for registration
router.include_router(
    register_router,
    tags=["Auth"],
)
# Router for user management (e.g., get /me)
router.include_router(
    fastapi_users.get_users_router(UserRead, UserRead),
    prefix="/users",
    tags=["Users"],
)