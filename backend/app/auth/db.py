from fastapi_users.db import BeanieUserDatabase
from app.models.user import User

async def get_user_db():
    yield BeanieUserDatabase(User)