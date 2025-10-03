# app/blog/schemas.py
from pydantic import BaseModel, Field
from beanie import PydanticObjectId
from typing import Optional, List
from datetime import datetime
from app.auth.schemas import UserRead

# Import models for type hinting in helper methods
from app.models.blog_post import BlogPost
from app.models.comment import Comment
from app.models.user import User # Import User for type hinting

class AuthorRead(BaseModel):
    id: PydanticObjectId
    username: str

class BlogPostCreate(BaseModel):
    title: str = Field(..., max_length=100)
    cover_image_url: Optional[str] = None
    content: str
    excerpt: Optional[str] = Field(default=None, max_length=300)
    tags: Optional[List[str]] = []

class BlogPostRead(BaseModel):
    id: PydanticObjectId
    title: str
    slug: str
    cover_image_url: Optional[str]
    content: str
    excerpt: Optional[str]
    author: AuthorRead
    likes_count: int = 0
    status: str
    tags: Optional[List[str]]
    createdAt: datetime

    @classmethod
    def from_db_model(cls, post: BlogPost) -> "BlogPostRead":
        if not post.author: # Handle case where author might not be fetched
             raise ValueError("Author not fetched for this post")
        return cls(
            id=post.id,
            title=post.title,
            slug=post.slug,
            content=post.content,
            excerpt=post.excerpt,
            cover_image_url=post.cover_image_url,
            author={"id": post.author.id, "username": post.author.username},
            likes_count=len(post.likes),
            status=post.status.value,
            tags=post.tags,
            createdAt=post.createdAt,
        )

class BlogPostList(BaseModel):
    id: PydanticObjectId
    title: str
    slug: str
    cover_image_url: Optional[str]
    excerpt: Optional[str]
    author: AuthorRead
    likes_count: int = 0
    tags: Optional[List[str]]
    createdAt: datetime

class CommentCreate(BaseModel):
    content: str = Field(..., max_length=1000)

class CommentRead(BaseModel):
    id: PydanticObjectId
    author: UserRead
    content: str
    createdAt: datetime

    @classmethod
    def from_db_model(cls, comment: Comment) -> "CommentRead":
        """Helper method to convert a DB model to this Pydantic schema."""
        if not comment.author:
            raise ValueError("Author not fetched for this comment")
        
        # --- THIS IS THE FIX ---
        # Explicitly build a dictionary and then validate it with the Pydantic model.
        # This is the safest way and avoids all collisions.
        author_dict = comment.author.dict()
        author_dict['role'] = comment.author.role.value
        author_data = UserRead.model_validate(author_dict)
        # --- END OF FIX ---
        
        return cls(
            id=comment.id,
            author=author_data,
            content=comment.content,
            createdAt=comment.createdAt,
        )