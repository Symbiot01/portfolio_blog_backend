# app/blog/router.py
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from beanie import PydanticObjectId

from app.models.blog_post import BlogPost, PostStatus
from app.models.user import User
from app.auth.core import current_active_user
from app.blog.schemas import (
    BlogPostCreate, BlogPostRead, BlogPostList,
    CommentCreate, CommentRead, UserRead
)
from app.blog.service import BlogService
from app.models.comment import Comment

router = APIRouter()

# --- Post Endpoints ---

@router.get("/posts", response_model=List[BlogPostList])
async def get_all_posts(skip: int = 0, limit: int = 10):
    # Fetch full documents to avoid N+1 query problems
    posts_from_db = await BlogPost.find(
        BlogPost.status == PostStatus.PUBLISHED, fetch_links=True
    ).sort(-BlogPost.createdAt).skip(skip).limit(limit).to_list()

    # --- THIS IS THE FIX ---
    # Manually construct the response to ensure the correct shape and data
    response_posts = []
    for post in posts_from_db:
        response_posts.append(
            BlogPostList(
                id=post.id,
                title=post.title,
                slug=post.slug,
                excerpt=post.excerpt,
                cover_image_url=post.cover_image_url,
                author={"id": post.author.id, "username": post.author.username},
                likes_count=len(post.likes),
                tags=post.tags,
                createdAt=post.createdAt
            )
        )
    return response_posts
    # --- END OF FIX ---

@router.post("/posts", response_model=BlogPostRead, status_code=201)
async def submit_post(post_data: BlogPostCreate, user: User = Depends(current_active_user)):
    try:
        new_post = await BlogService.create_post(post_data, user)
        return BlogPostRead.from_db_model(new_post)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/posts/{slug}", response_model=BlogPostRead)
async def get_post_by_slug(slug: str):
    post = await BlogPost.find_one(
        BlogPost.slug == slug, BlogPost.status == PostStatus.PUBLISHED, fetch_links=True
    )
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    return BlogPostRead.from_db_model(post)

@router.post("/posts/{post_id}/like", response_model=BlogPostRead)
async def like_a_post(post_id: PydanticObjectId, user: User = Depends(current_active_user)):
    updated_post = await BlogService.like_post(post_id, user)
    if not updated_post:
        raise HTTPException(status_code=404, detail="Post not found")
    return BlogPostRead.from_db_model(updated_post)

# --- Comment Endpoints ---

@router.post("/posts/{post_id}/comments", response_model=CommentRead, status_code=201)
async def create_comment(post_id: PydanticObjectId, comment_data: CommentCreate, user: User = Depends(current_active_user)):
    post = await BlogPost.get(post_id)
    if not post or post.status != PostStatus.PUBLISHED:
        raise HTTPException(status_code=404, detail="Post not found or not published")
    
    comment = Comment(post=post, author=user, content=comment_data.content)
    await comment.insert()
    return CommentRead.from_db_model(comment)

@router.get("/posts/{post_id}/comments", response_model=List[CommentRead])
async def get_comments(post_id: PydanticObjectId, skip: int = 0, limit: int = 20):
    comments = await Comment.find(
        Comment.post.id == post_id, fetch_links=True
    ).sort(-Comment.createdAt).skip(skip).limit(limit).to_list()
    
    return [CommentRead.from_db_model(comment) for comment in comments]



@router.get("/posts/me", response_model=List[BlogPostList])
async def get_my_posts(user: User = Depends(current_active_user)):
    """Get all posts authored by the current logged-in user."""
    posts = await BlogPost.find(
        BlogPost.author.id == user.id, fetch_links=True
    ).sort(-BlogPost.createdAt).to_list()
    
    return [
        BlogPostList(
            **post.dict(),
            author={"id": post.author.id, "username": post.author.username},
            likes_count=len(post.likes)
        ) for post in posts
    ]