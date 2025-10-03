# app/models/comment.py
from beanie import Document, Link
from pydantic import Field
from datetime import datetime

from app.models.blog_post import BlogPost
from app.models.user import User

class Comment(Document):
    post: Link[BlogPost]
    author: Link[User]
    content: str = Field(..., max_length=1000)
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "comments"