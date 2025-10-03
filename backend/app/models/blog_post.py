# app/models/blog_post.py
from beanie import Document, Link, PydanticObjectId
from pydantic import Field
from typing import Optional, List
from datetime import datetime
from enum import Enum

from app.models.user import User  # Import the User model for linking

class PostStatus(str, Enum):
    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    PUBLISHED = "published"
    REJECTED = "rejected"

class BlogPost(Document):
    title: str = Field(..., max_length=100)
    slug: str = Field(..., unique=True)
    content: str
    cover_image_url: Optional[str] = None 
    excerpt: Optional[str] = Field(default=None, max_length=300)
    
    author: Link[User]
    likes: List[Link[User]] = []
    
    status: PostStatus = PostStatus.DRAFT
    tags: Optional[List[str]] = []
    
    createdAt: datetime = Field(default_factory=datetime.utcnow)

    class Settings:
        name = "blog_posts"
        # Create a text index on title and content for full-text search later
        indexes = [
            [("title", "text"), ("content", "text")]
        ]