##  Folder and File Structure

The project is organized into a primary `app` directory, which contains all the core logic, neatly divided into modules.

### Root Directory (`/`)

* `main.py`: This is the **main entry point** of the entire application.
    * It creates the main `FastAPI` instance.
    * It initializes middleware for **CORS** (to allow frontend access) and **rate limiting** (using `slowapi` to prevent abuse).
    * It defines a `startup` event to initialize the database connection via Beanie.
    * It includes the routers from all the different modules (`auth`, `blog`, `admin`, `uploads`) into the main app, prefixing their routes (e.g., all auth routes start with `/api/auth`).
    * It defines a simple `/api/health` check endpoint.

### `app/`

This is the main Python package containing all the application code.

#### `app/models/`
This directory defines the **database schemas** using Beanie `Document` models. These are the Python representations of your MongoDB collections.
* `user.py`: Defines the `User` document. It inherits from `BeanieBaseUser` to be compatible with `fastapi-users`. It specifies fields like `username`, `email`, and a `Role` enum (`ADMIN` or `AUTHOR`). Crucially, it defines unique indexes for `email` and `username` to prevent duplicates.
* `blog_post.py`: Defines the `BlogPost` document. It includes fields for title, content, a unique `slug`, status (as a `PostStatus` enum), and creation date. It uses Beanie's `Link` to create relationships to the `User` model for the `author` and the list of `likes`.
* `comment.py`: Defines the `Comment` document. It links to both a `BlogPost` and a `User` (the author of the comment).

#### `app/auth/`
This module handles everything related to **user authentication and authorization**.
* `schemas.py`: Contains Pydantic models for user-related API operations, like `UserRead` (how user data is sent to the client) and `UserCreate` (what data is required for registration).
* `manager.py`: Implements the `UserManager`, which contains the core business logic for handling users. It's customized here to add a check for a unique `username` in addition to the default unique `email` check.
* `backend.py`: Configures the authentication strategy. It sets up JWT (JSON Web Tokens) as the method for verifying users and a `BearerTransport` which tells the API how to expect the token (in the `Authorization: Bearer <token>` header).
* `db.py`: Provides a simple dependency function (`get_user_db`) that gives `fastapi-users` the Beanie database adapter for the `User` model.
* `core.py`: Creates the central `fastapi_users` object, which ties the user manager, auth backends, and user model together. It also exposes the `current_active_user` dependency, which is used to protect endpoints and get the current logged-in user.
* `router.py`: Combines all the pre-built routers from `fastapi-users` for login, registration, and user management (`/users/me`) into a single `APIRouter` for easy inclusion in `main.py`.
* `guards.py`: Defines authorization logic. The `admin_guard` is a dependency that can be added to any endpoint to ensure that only a user with the `ADMIN` role can access it.

#### `app/blog/`
This module contains the logic for the public-facing **blog features**.
* `router.py`: Defines all the API endpoints related to blog posts and comments, such as listing all posts, getting a single post by its slug, liking a post, and adding/viewing comments.
* `schemas.py`: Pydantic models that define the shape of data for blog-related API requests and responses (e.g., `BlogPostCreate`, `BlogPostRead`, `CommentRead`).
* `service.py`: The business logic layer. It handles tasks that are separate from the HTTP request/response cycle, like generating a URL-friendly `slug` from a post title, determining a new post's status based on the author's role (`ADMIN` vs. `AUTHOR`), and managing the logic for liking/unliking a post.

#### `app/admin/`
This module contains endpoints for **administrative actions**, protected by the `admin_guard`.
* `router.py`: Defines API endpoints for admin-only tasks, such as fetching posts pending review, updating a post's status (e.g., from `PENDING_REVIEW` to `PUBLISHED`), and deleting posts or comments.

#### `app/uploads/`
This module handles **file uploads**.
* `router.py`: Defines the `/api/uploads/image` endpoint where users can send image files.
* `service.py`: Contains the logic for processing the upload. In this case, it sends the uploaded file to the **Cloudinary** cloud service for storage and returns the secure URL.

#### `app/core/`
This module holds core, application-wide functionality.
* `database.py`: Contains a single, important function `initialize_database` which sets up the connection to MongoDB and tells Beanie which document models (`User`, `BlogPost`, `Comment`) to manage. This function is called once when the application starts.

---

##  Code Flow: A Typical Request Lifecycle

Let's trace a request to create a new blog post to understand how all the pieces work together.

1.  **Request Sent**: A logged-in user (as an `AUTHOR`) sends a `POST` request to `/api/blog/posts` with a JWT in the `Authorization` header and a JSON body containing `title` and `content`.

2.  **Routing**: FastAPI receives the request and matches the path and method to the `submit_post` function in `app/blog/router.py`.

3.  **Dependency Injection**: Before executing the function, FastAPI resolves its dependencies.
    * `post_data: BlogPostCreate`: It validates the incoming JSON body against the `BlogPostCreate` schema. If the data is invalid (e.g., `title` is too long), it automatically returns a 422 Unprocessable Entity error.
    * `user: User = Depends(current_active_user)`: This is the critical authentication step. The `current_active_user` dependency (from `app/auth/core.py`) kicks in. It extracts the JWT from the header, validates its signature and expiration, and uses the ID inside it to fetch the corresponding user from the `users` collection in MongoDB. If the token is invalid or the user doesn't exist, it returns a 401 Unauthorized error. If successful, the full `User` object is passed to the `submit_post` function.

4.  **Execution**: The `submit_post` function now runs with the validated `post_data` and the authenticated `user` object.
    * It calls `BlogService.create_post(post_data, user)`.

5.  **Business Logic (Service Layer)**: Inside `app/blog/service.py`:
    * `slugify(post_data.title)` is called to create a slug (e.g., "My New Post" -> "my-new-post").
    * It checks if a post with that slug already exists to prevent duplicates.
    * It checks `current_user.role`. Since the role is `AUTHOR`, it sets the post's `status` to `PostStatus.PENDING_REVIEW`.
    * It creates a `BlogPost` Beanie model instance, linking the `user` object to the `author` field.
    * It calls `await post.insert()` to save the new blog post document to the MongoDB database.
    * It returns the newly created `BlogPost` object.

6.  **Response Formatting**: Back in `app/blog/router.py`:
    * The `submit_post` function receives the new `BlogPost` object from the service.
    * It calls `BlogPostRead.from_db_model(new_post)` to convert the database model into the `BlogPostRead` Pydantic schema. This ensures the response sent to the client has the correct format, including calculating `likes_count` and formatting the author's data.

7.  **Response Sent**: FastAPI automatically converts the `BlogPostRead` Pydantic object into a JSON response and sends it back to the client with a `201 Created` status code.
