# app/admin/router.py
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from beanie import PydanticObjectId

from app.models.blog_post import BlogPost, PostStatus
from app.models.comment import Comment
from app.auth.guards import admin_guard
from app.blog.schemas import BlogPostRead # Reuse existing schemas

router = APIRouter()

# --- Post Management ---

@router.get("/posts/pending", response_model=List[BlogPostRead], dependencies=[Depends(admin_guard)])
async def get_pending_posts():
    """Get all posts that are pending review."""
    posts = await BlogPost.find(
        BlogPost.status == PostStatus.PENDING_REVIEW, fetch_links=True
    ).sort(-BlogPost.createdAt).to_list()

    # --- THIS IS THE FIX ---
    # Explicitly construct the response to avoid the 'author' collision.
    response_posts = []
    for post in posts:
        response_posts.append(
            BlogPostRead(
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
                createdAt=post.createdAt
            )
        )
    return response_posts
    # --- END OF FIX ---

@router.patch("/posts/{post_id}/status", response_model=BlogPostRead, dependencies=[Depends(admin_guard)])
async def update_post_status(post_id: PydanticObjectId, status: PostStatus):
    """Update a post's status (e.g., publish or reject)."""
    post = await BlogPost.get(post_id, fetch_links=True)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")

    post.status = status
    await post.save()

    # --- THIS IS THE FIX (Applied here too) ---
    return BlogPostRead(
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
        createdAt=post.createdAt
    )
    # --- END OF FIX ---

@router.delete("/posts/{post_id}", status_code=204, dependencies=[Depends(admin_guard)])
async def delete_post(post_id: PydanticObjectId):
    """Delete a blog post by its ID. This will also delete all associated comments."""
    post = await BlogPost.get(post_id)
    if not post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    await Comment.find(Comment.post.id == post_id).delete()
    
    await post.delete()
    return None

# --- Comment Management ---
@router.delete("/comments/{comment_id}", status_code=204, dependencies=[Depends(admin_guard)])
async def delete_comment(comment_id: PydanticObjectId):
    """Delete a comment by its ID."""
    comment = await Comment.get(comment_id)
    if not comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    await comment.delete()
    return None