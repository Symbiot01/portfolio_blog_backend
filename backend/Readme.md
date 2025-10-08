```
> codecache.txt

find . -path "./venv" -prune -o -name "*.py" -print | while read -r file; do
  echo "======== FILE: $file ========" >> codecache.txt
  
  cat "$file" >> codecache.txt
  
  echo -e "\n\n" >> codecache.txt
done

echo "Code cache created successfully in backend/codecache.txt"
```


NOTE:
```
# /// to be changed in production
origins = ["*"] 

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

-----

# Portfolio & Blog API

This is a robust, feature-rich backend API for a personal portfolio and blog, built with **FastAPI**. It leverages a modern, asynchronous tech stack including MongoDB with Beanie ODM for database interactions, FastAPI-Users for secure authentication, and Cloudinary for image hosting.

The API is designed to be modular, scalable, and easy to extend, following best practices for code organization and separation of concerns.

## Table of Contents

  * [Key Features](https://www.google.com/search?q=%23key-features)
  * [Tech Stack](https://www.google.com/search?q=%23tech-stack)
  * [Getting Started](https://www.google.com/search?q=%23getting-started)
      * [Prerequisites](https://www.google.com/search?q=%23prerequisites)
      * [Installation & Setup](https://www.google.com/search?q=%23installation--setup)
      * [Running the Application](https://www.google.com/search?q=%23running-the-application)
  * [Project Architecture](https://www.google.com/search?q=%23project-architecture)
      * [Directory Structure](https://www.google.com/search?q=%23directory-structure)
      * [Architectural Philosophy](https://www.google.com/search?q=%23architectural-philosophy)
  * [Module Breakdown](https://www.google.com/search?q=%23module-breakdown)
      * [`main.py`](https://www.google.com/search?q=%23mainpy)
      * [`app/core/`](https://www.google.com/search?q=%23appcore)
      * [`app/models/`](https://www.google.com/search?q=%23appmodels)
      * [`app/auth/`](https://www.google.com/search?q=%23appauth)
      * [`app/blog/`](https://www.google.com/search?q=%23appblog)
      * [`app/admin/`](https://www.google.com/search?q=%23appadmin)
      * [`app/uploads/`](https://www.google.com/search?q=%23appuploads)
  * [API Documentation](https://www.google.com/search?q=%23api-documentation)
  * [Extending the API: A Walkthrough](https://www.google.com/search?q=%23extending-the-api-a-walkthrough)
      * [Example: Adding "Categories" to Blog Posts](https://www.google.com/search?q=%23example-adding-categories-to-blog-posts)

-----

## Key Features

  * **Asynchronous:** Built on FastAPI and Starlette for high performance.
  * **User Authentication:** Secure, ready-to-use authentication system (Register, Login, JWT) powered by `fastapi-users`.
  * **Role-Based Access Control (RBAC):** Differentiates between regular users (`AUTHOR`) and `ADMIN` users with specific permissions.
  * **Complete Blog System:**
      * Full CRUD operations for blog posts.
      * Slug generation for SEO-friendly URLs.
      * Post like/unlike functionality.
      * Commenting system on posts.
  * **Admin Review Workflow:** Posts by non-admin users are set to `PENDING_REVIEW` for an admin to approve or reject.
  * **Image Uploads:** Seamless image uploading integrated with Cloudinary.
  * **Rate Limiting:** Basic protection against brute-force attacks on sensitive endpoints.
  * **Database ORM:** Modern, Pydantic-based ODM (`Beanie`) for intuitive and type-safe MongoDB interactions.

## Tech Stack

  * **Framework:** [FastAPI](https://fastapi.tiangolo.com/)
  * **Database:** [MongoDB](https://www.mongodb.com/)
  * **ODM (Object-Document Mapper):** [Beanie](https://beanie-odm.dev/)
  * **Authentication:** [FastAPI-Users](https://fastapi-users.github.io/fastapi-users/)
  * **Data Validation:** [Pydantic](https://docs.pydantic.dev/latest/)
  * **Image Hosting:** [Cloudinary](https://cloudinary.com/)
  * **Rate Limiting:** [slowapi](https://github.com/laurents/slowapi)
  * **Web Server:** [Uvicorn](https://www.uvicorn.org/)

-----

## Getting Started

Follow these steps to get the API running on your local machine.

### Prerequisites

  * **Python 3.8+**
  * **Poetry** or **pip** for package management.
  * A **MongoDB** instance (either local or a cloud service like MongoDB Atlas).
  * A **Cloudinary** account for image hosting.

### Installation & Setup

1.  **Clone the repository:**

    ```bash
    git clone <your-repository-url>
    cd <repository-name>
    ```

2.  **Create and activate a virtual environment:**

    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows, use `venv\Scripts\activate`
    ```

3.  **Install dependencies:**
    *(Note: A `requirements.txt` file is not provided, but you can generate one from your environment using `pip freeze > requirements.txt`)*

    ```bash
    pip install fastapi "uvicorn[standard]" motor beanie fastapi-users[beanie] python-slugify python-dotenv slowapi cloudinary
    ```

4.  **Configure Environment Variables:**
    Create a file named `.env` in the root of the project and populate it with the following keys. You can use the `.env.example` as a template.

    ```ini
    # .env.example

    # MongoDB Configuration
    DATABASE_URL="mongodb://localhost:27017"
    DATABASE_NAME="my_portfolio_db"

    # A strong, random string for JWT and other secrets
    SECRET_KEY="your_super_secret_key_here"

    # Cloudinary URL for image uploads. Get this from your Cloudinary dashboard.
    # Format: cloudinary://<api_key>:<api_secret>@<cloud_name>
    CLOUDINARY_URL="cloudinary://..."
    ```

### Running the Application

Once the setup is complete, you can start the development server using Uvicorn:

```bash
uvicorn main:app --reload
```

  * `main:app` tells Uvicorn to look for an object named `app` inside the `main.py` file.
  * `--reload` enables hot-reloading, so the server will restart automatically after you make code changes.

The API will now be running at `http://127.0.0.1:8000`.

-----

## Project Architecture

The project follows a modular, feature-based structure. This approach enhances scalability and maintainability by grouping related logic together.

### Directory Structure

```
.
├── app/
│   ├── admin/
│   │   └── router.py         # Admin-specific endpoints
│   ├── auth/
│   │   ├── backend.py        # Authentication strategies (JWT)
│   │   ├── core.py           # FastAPI-Users integration object
│   │   ├── db.py             # User database dependency
│   │   ├── guards.py         # Permission dependencies (e.g., admin_guard)
│   │   ├── manager.py        # Custom user manager
│   │   ├── router.py         # Auth endpoints (login, register, etc.)
│   │   └── schemas.py        # Pydantic schemas for user data
│   ├── blog/
│   │   ├── router.py         # Public blog endpoints
│   │   ├── schemas.py        # Pydantic schemas for blog/comment data
│   │   └── service.py        # Business logic for the blog feature
│   ├── core/
│   │   └── database.py       # Database initialization logic
│   ├── models/
│   │   ├── blog_post.py      # BlogPost document model
│   │   ├── comment.py        # Comment document model
│   │   └── user.py           # User document model
│   └── uploads/
│       ├── router.py         # Image upload endpoint
│       └── service.py        # Business logic for uploading to Cloudinary
├── .env                      # Environment variables (secret)
└── main.py                   # Main application entrypoint
```

### Architectural Philosophy

  * **Separation of Concerns:** The code is split into logical units.
      * **`main.py`**: The entry point, responsible only for wiring the application together (middleware, routers, startup events).
      * **`models/`**: Defines the shape of our data in the database (the "M" in MVC).
      * **`schemas/`**: Defines the shape of our data for the API (Pydantic models). This allows the API layer to be decoupled from the database layer.
      * **`router.py`**: Defines the API endpoints, handles HTTP requests and responses, and performs validation (the "C" in MVC).
      * **`service.py`**: Contains the core business logic. This keeps the routers clean and focused on HTTP concerns. For example, the logic for creating a `slug` from a title belongs in a service, not a router.
  * **Modularity:** Each major feature (e.g., `auth`, `blog`, `admin`) lives in its own directory. This makes the codebase easier to navigate and allows features to be developed in isolation.

-----

## Module Breakdown

### `main.py`

This is the heart of the application. It creates the main `FastAPI` instance, configures middleware like CORS and rate limiting (`slowapi`), and includes all the feature-specific routers from the `app` directory. It also contains a `startup` event to initialize the database connection via Beanie.

### `app/core/`

This module is for cross-cutting concerns that don't belong to a specific feature. Currently, it holds `database.py`, which is responsible for connecting to MongoDB and initializing all the Beanie `Document` models.

### `app/models/`

This directory contains the database models. Each file corresponds to a MongoDB collection. We use **Beanie `Document`** classes to define the schema, indexes, and relationships. `Link` is a crucial Beanie type used here to create references between documents (e.g., a `BlogPost` has a `Link[User]` to its author).

### `app/auth/`

This is a complete authentication and user management module built around `fastapi-users`.

  * **`schemas.py`**: Defines `UserRead` and `UserCreate` Pydantic models for API interactions.
  * **`manager.py`**: The `UserManager` class extends the base manager from `fastapi-users` to add custom logic, such as checking for unique usernames in addition to unique emails.
  * **`guards.py`**: Contains dependencies that protect endpoints. The `admin_guard` is a reusable function that can be added to any endpoint to restrict access to only users with the `ADMIN` role.
  * **`router.py`**: Combines the pre-built routers from `fastapi-users` for login, registration, and user management (`/users/me`) into a single, organized router.

### `app/blog/`

This module handles all public-facing blog functionality.

  * **`router.py`**: Defines endpoints like `GET /posts`, `GET /posts/{slug}`, `POST /posts/{post_id}/like`, and the endpoints for managing comments.
  * **`schemas.py`**: Contains Pydantic models for creating posts (`BlogPostCreate`), reading posts (`BlogPostRead`, `BlogPostList`), and handling comments (`CommentRead`, `CommentCreate`). The `from_db_model` classmethod is a helper to safely convert a Beanie database model into a Pydantic API schema.
  * **`service.py`**: Implements the business logic. `create_post` handles slug generation and sets the initial post status based on the user's role. `like_post` contains the logic for toggling a user's "like" on a post.

### `app/admin/`

This module contains endpoints for administrative tasks. Every endpoint here is protected by the `admin_guard`.

  * **`router.py`**: Exposes endpoints for `GET /posts/pending` to see posts awaiting review, `PATCH /posts/{post_id}/status` to approve/reject posts, and `DELETE` routes for removing posts or comments.

### `app/uploads/`

A simple module dedicated to handling file uploads.

  * **`router.py`**: Provides a single `POST /image` endpoint that accepts an image file.
  * **`service.py`**: The `UploadService` class interfaces directly with the `cloudinary` library to upload the file and return its secure URL.

-----

## API Documentation

FastAPI automatically generates interactive API documentation from your code. Once the server is running, you can access it at:

  * **Swagger UI:** [http://127.0.0.1:8000/docs](https://www.google.com/search?q=http://127.0.0.1:8000/docs)
  * **ReDoc:** [http://127.0.0.1:8000/redoc](https://www.google.com/search?q=http://127.0.0.1:8000/redoc)

These interfaces allow you to see all available endpoints, their parameters, and expected responses. You can even try out the API directly from your browser.

-----

## Extending the API: A Walkthrough

The modular structure makes adding new features straightforward. Let's walk through an example.

### Example: Adding "Categories" to Blog Posts

Imagine we want to categorize our blog posts (e.g., "Technology", "Tutorials", "Life").

**Step 1: Create the Model**
Create a new file `app/models/category.py` to define the `Category` document.

```python
# app/models/category.py
from beanie import Document
from pydantic import Field

class Category(Document):
    name: str = Field(..., max_length=50, unique=True)
    slug: str = Field(..., max_length=50, unique=True)

    class Settings:
        name = "categories"
```

**Step 2: Update the `BlogPost` Model**
Modify `app/models/blog_post.py` to link it to a category.

```python
# app/models/blog_post.py
# ... other imports
from beanie import Document, Link
from app.models.user import User
from app.models.category import Category # <-- Import the new model

class BlogPost(Document):
    # ... other fields
    author: Link[User]
    category: Optional[Link[Category]] = None # <-- Add the category link
    likes: List[Link[User]] = []
    # ...
```

**Step 3: Update API Schemas**
Modify `app/blog/schemas.py` to include the category in API responses.

```python
# app/blog/schemas.py
# ...

class CategoryRead(BaseModel): # <-- New schema for reading a category
    id: PydanticObjectId
    name: str
    slug: str

class BlogPostCreate(BaseModel): # <-- Update the create schema
    title: str
    # ...
    category_id: Optional[PydanticObjectId] = None # <-- Add field to accept category ID
    tags: Optional[List[str]] = []

class BlogPostRead(BaseModel): # <-- Update the read schema
    id: PydanticObjectId
    # ...
    category: Optional[CategoryRead] = None # <-- Add the full category object
    author: AuthorRead
    # ...

    @classmethod
    def from_db_model(cls, post: BlogPost) -> "BlogPostRead":
        # ... existing logic ...
        return cls(
            # ... other fields
            category=CategoryRead(**post.category.dict()) if post.category else None,
            # ... other fields
        )
```

**Step 4: Update the Service Logic**
Modify `app/blog/service.py` to handle linking the category when a post is created.

```python
# app/blog/service.py
# ...
from app.models.blog_post import BlogPost
from app.models.user import User
from app.models.category import Category # <-- Import Category
from app.blog.schemas import BlogPostCreate

class BlogService:
    @staticmethod
    async def create_post(post_data: BlogPostCreate, current_user: User) -> BlogPost:
        # ... slug logic ...

        category = None
        if post_data.category_id:
            category = await Category.get(post_data.category_id)
            if not category:
                raise ValueError("Category not found.")

        post = BlogPost(
            title=post_data.title,
            content=post_data.content,
            # ... other fields from post_data
            slug=slug,
            author=current_user,
            status=status,
            category=category # <-- Assign the fetched category document
        )
        return await post.insert()
    # ...
```

**Step 5: Create Endpoints for Categories**
Finally, create a new feature module `app/category/` with a `router.py` to manage categories (create, list, delete). Then, include this new router in `main.py`.

This step-by-step process can be followed to add any new feature, demonstrating the power of the project's organized and modular architecture.