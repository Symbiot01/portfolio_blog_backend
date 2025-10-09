# app/models/user.py
from beanie import Document
from pydantic import EmailStr, Field
from enum import Enum
from fastapi_users.db import BeanieBaseUser
from typing import Optional
from pymongo import IndexModel
from pymongo.collation import Collation # <-- 1. Import Collation

class Role(str, Enum):
    ADMIN = "admin"
    AUTHOR = "author"

class User(BeanieBaseUser, Document):
    email: EmailStr
    username: str
    is_guest: bool = Field(default=False)
    googleId: Optional[str] = None
    avatar: Optional[str] = None
    bio: Optional[str] = None
    role: Role = Role.AUTHOR

    class Settings:
        name = "users"
        
        # --- THIS IS THE FIX ---
        # 2. We explicitly define the collation object that the library is looking for.
        email_collation = Collation(locale="en", strength=2)
        # --- END OF FIX ---

        # We still keep the indexes list to ensure MongoDB creates them correctly.
        indexes = [
            IndexModel(
                "email",
                unique=True,
                collation=email_collation # Use the collation object here
            ),
            IndexModel("username", unique=True),
        ]