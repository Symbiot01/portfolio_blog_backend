from fastapi_users import schemas
from beanie import PydanticObjectId
from typing import Optional

class UserRead(schemas.BaseUser[PydanticObjectId]):
    username: str
    avatar: Optional[str] = None
    bio: Optional[str] = None
    role: str

class UserCreate(schemas.BaseUserCreate):
    username: str