# app/auth/guards.py
from fastapi import Depends, HTTPException, status
from app.models.user import User, Role
from app.auth.core import current_active_user

# This is a dependency that can be used on any endpoint
def admin_guard(user: User = Depends(current_active_user)):
    """
    A dependency that raises an HTTPException if the current user
    is not an admin.
    """
    if user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action."
        )
    return user # Optionally return the user object