# app/blog/service.py
from slugify import slugify
from beanie import PydanticObjectId

from app.models.blog_post import BlogPost, PostStatus
from app.models.user import User, Role
from app.blog.schemas import BlogPostCreate

class BlogService:
    @staticmethod
    async def create_post(post_data: BlogPostCreate, current_user: User) -> BlogPost:
        slug = slugify(post_data.title)
        
        # Check if a post with this slug already exists
        existing_post = await BlogPost.find_one(BlogPost.slug == slug)
        if existing_post:
            # You might want to append a unique ID or handle this differently
            raise ValueError("A post with this title already exists.")

        # Your "review" logic is implemented here!
        status = PostStatus.PUBLISHED if current_user.role == Role.ADMIN else PostStatus.PENDING_REVIEW

        post = BlogPost(
            **post_data.dict(),
            slug=slug,
            author=current_user,
            status=status
        )
        return await post.insert()

    @staticmethod
    async def like_post(post_id: PydanticObjectId, current_user: User):
        post = await BlogPost.get(post_id, fetch_links=True)
        if not post:
            return None # Or raise an exception

        # Check if user has already liked the post
        user_already_liked = any(liked_user.id == current_user.id for liked_user in post.likes)

        if user_already_liked:
            # Unlike the post
            post.likes = [user for user in post.likes if user.id != current_user.id]
        else:
            # Like the post
            post.likes.append(current_user)
        
        await post.save()
        return post