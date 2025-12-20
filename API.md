  # API Documentation

  This document contains all endpoints and schemas for the Portfolio & Blog API.

  ## Base URL

  ```
  http://localhost:8000
  ```

  ## Authentication

  Most endpoints require authentication using JWT tokens. Include the token in the Authorization header:

  ```
  Authorization: Bearer <token>
  ```

  ---

  ## Table of Contents

  1. [Health Check](#health-check)
  2. [Authentication](#authentication-endpoints)
  3. [Blog](#blog-endpoints)
  4. [Admin](#admin-endpoints)
  5. [Uploads](#uploads-endpoints)
  6. [TripSync](#tripsync-endpoints)
  7. [Schemas](#schemas)

  ---

  ## Health Check

  ### GET `/api/health`

  Check if the API is running and connected to the database.

  **Rate Limit:** 5/minute

  **Response:**
  ```json
  {
    "status": "ok",
    "message": "Connected to DB: portfolio_db"
  }
  ```

  ---

  ## Authentication Endpoints

  Base path: `/api/auth`

  ### POST `/api/auth/register`

  Register a new user.

  **Request Body:**
  ```json
  {
    "email": "user@example.com",
    "password": "securepassword",
    "username": "johndoe"
  }
  ```

  **Response:** `UserRead` (201 Created)

  ### POST `/api/auth/jwt/login`

  Login and get JWT token.

  **Request Body:**
  ```json
  {
    "username": "user@example.com",
    "password": "securepassword"
  }
  ```

  **Response:**
  ```json
  {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "token_type": "bearer"
  }
  ```

  ### POST `/api/auth/jwt/logout`

  Logout (invalidate token).

  **Authentication:** Required

  **Response:** 204 No Content

  ### GET `/api/auth/users/me`

  Get current user information.

  **Authentication:** Required

  **Response:** `UserRead`

  ### GET `/api/auth/users/{id}`

  Get user by ID.

  **Authentication:** Required

  **Response:** `UserRead`

  ---

  ## Blog Endpoints

  Base path: `/api/blog`

  ### GET `/api/blog/posts`

  Get all published blog posts.

  **Query Parameters:**
  - `skip` (int, default: 0): Number of posts to skip
  - `limit` (int, default: 10): Maximum number of posts to return

  **Response:** `List[BlogPostList]`

  ### POST `/api/blog/posts`

  Create a new blog post.

  **Authentication:** Required

  **Request Body:** `BlogPostCreate`

  **Response:** `BlogPostRead` (201 Created)

  ### GET `/api/blog/posts/{slug}`

  Get a blog post by slug.

  **Response:** `BlogPostRead`

  ### POST `/api/blog/posts/{post_id}/like`

  Like a blog post.

  **Authentication:** Required

  **Response:** `BlogPostRead`

  ### GET `/api/blog/posts/me`

  Get all posts authored by the current user.

  **Authentication:** Required

  **Response:** `List[BlogPostList]`

  ### POST `/api/blog/posts/{post_id}/comments`

  Create a comment on a blog post.

  **Authentication:** Required

  **Request Body:** `CommentCreate`

  **Response:** `CommentRead` (201 Created)

  ### GET `/api/blog/posts/{post_id}/comments`

  Get all comments for a blog post.

  **Query Parameters:**
  - `skip` (int, default: 0): Number of comments to skip
  - `limit` (int, default: 20): Maximum number of comments to return

  **Response:** `List[CommentRead]`

  ---

  ## Admin Endpoints

  Base path: `/api/admin`

  **Note:** All admin endpoints require admin role.

  ### GET `/api/admin/posts/pending`

  Get all posts pending review.

  **Authentication:** Required (Admin)

  **Response:** `List[BlogPostRead]`

  ### PATCH `/api/admin/posts/{post_id}/status`

  Update a post's status.

  **Authentication:** Required (Admin)

  **Request Body:**
  ```json
  {
    "status": "PUBLISHED"  // or "PENDING_REVIEW", "REJECTED"
  }
  ```

  **Response:** `BlogPostRead`

  ### DELETE `/api/admin/posts/{post_id}`

  Delete a blog post and all associated comments.

  **Authentication:** Required (Admin)

  **Response:** 204 No Content

  ### DELETE `/api/admin/comments/{comment_id}`

  Delete a comment.

  **Authentication:** Required (Admin)

  **Response:** 204 No Content

  ---

  ## Uploads Endpoints

  Base path: `/api/uploads`

  ### POST `/api/uploads/image`

  Upload an image file.

  **Authentication:** Required

  **Request:** Multipart form data with `file` field

  **Response:**
  ```json
  {
    "url": "https://cloudinary.com/image/..."
  }
  ```

  ---

  ## TripSync Endpoints

  Base path: `/api/tripsync`

  ### POST `/api/tripsync/`

  Create a new trip.

  **Authentication:** Required

  **Request Body:** `TripCreate`

  **Response:** `TripRead` (201 Created)

  ### GET `/api/tripsync/my`

  Get all trips for the current user.

  **Authentication:** Required

  **Response:** `List[TripRead]`

  ### GET `/api/tripsync/access/{access_token}`

  Preview a trip by access token (public link).

  **Rate Limit:** 30/minute

  **Response:** `TripRead`

  ### POST `/api/tripsync/{trip_id}/members`

  Add a member to a trip.

  **Authentication:** Required (must be a member or have access token)

  **Rate Limit:** 60/minute

  **Request Body:** `TripMemberCreate`

  **Response:** `TripRead`

  ### POST `/api/tripsync/{trip_id}/members/link-self`

  Link a trip member to the current user account.

  **Authentication:** Required

  **Request Body:** `LinkSelfRequest`

  **Response:** `TripRead`

  ### POST `/api/tripsync/{trip_id}/itinerary`

  Add an itinerary item to a trip.

  **Authentication:** Required (must be a member or have access token)

  **Rate Limit:** 60/minute

  **Request Body:** `ItineraryItemCreate`

  **Response:**
  ```json
  {
    "id": "507f1f77bcf86cd799439011"
  }
  ```

  ### GET `/api/tripsync/{trip_id}/itinerary/{item_id}`

  Get a single itinerary item by ID for editing.

  **Authentication:** Required (must be a member or have access token)

  **Response:**
  ```json
  {
    "id": "507f1f77bcf86cd799439011",
    "title": "Visit Eiffel Tower",
    "item_type": "activity",
    "start_time": "2024-07-15T10:00:00",
    "end_time": "2024-07-15T12:00:00",
    "location": "Paris, France",
    "notes": "Don't forget tickets"
  }
  ```

  ### PATCH `/api/tripsync/{trip_id}/itinerary/{item_id}`

  Update an itinerary item.

  **Authentication:** Required (must be a member or have access token)

  **Rate Limit:** 60/minute

  **Request Body:** `ItineraryItemUpdate`

  **Response:**
  ```json
  {
    "id": "507f1f77bcf86cd799439011"
  }
  ```

  ### DELETE `/api/tripsync/{trip_id}/itinerary/{item_id}`

  Delete an itinerary item.

  **Authentication:** Required (must be a member or have access token)

  **Rate Limit:** 60/minute

  **Response:** 204 No Content

### GET `/api/tripsync/{trip_id}/itinerary`

List all itinerary items for a trip.

**Authentication:** Required (must be a member or have access token)

**Response:** `List[ItineraryItemRead]`

  ### POST `/api/tripsync/{trip_id}/expenses`

  Add an expense to a trip.

  **Authentication:** Required (must be a member or have access token)

  **Rate Limit:** 60/minute

  **Request Body:** `ExpenseCreate`

  **Response:**
  ```json
  {
    "id": "507f1f77bcf86cd799439011"
  }
  ```

### GET `/api/tripsync/{trip_id}/expenses/{expense_id}`

Get a single expense by ID for editing.

**Authentication:** Required (must be a member or have access token)

**Response:**
```json
{
  "id": "507f1f77bcf86cd799439011",
  "description": "Dinner at restaurant",
  "amount": 150.50,
  "paid_by_member_id": "uuid-string",
  "split_with_member_ids": ["uuid-1", "uuid-2"]
}
```

### PATCH `/api/tripsync/{trip_id}/expenses/{expense_id}`

Update an expense.

**Authentication:** Required (must be a member or have access token)

**Rate Limit:** 60/minute

**Request Body:** `ExpenseUpdate`

**Response:**
```json
{
  "id": "507f1f77bcf86cd799439011"
}
```

### DELETE `/api/tripsync/{trip_id}/expenses/{expense_id}`

  Delete an expense.

  **Authentication:** Required (must be a member or have access token)

  **Rate Limit:** 60/minute

  **Response:** 204 No Content

### GET `/api/tripsync/{trip_id}/expenses`

List all expenses for a trip.

**Authentication:** Required (must be a member or have access token)

**Response:** `List[ExpenseRead]`

  ### POST `/api/tripsync/{trip_id}/settlements`

  Add a settlement to a trip.

  **Authentication:** Required (must be a member or have access token)

  **Rate Limit:** 60/minute

  **Request Body:** `SettlementCreate`

  **Response:**
  ```json
  {
    "id": "507f1f77bcf86cd799439011"
  }
  ```

### GET `/api/tripsync/{trip_id}/settlements/{settlement_id}`

Get a single settlement by ID for editing.

**Authentication:** Required (must be a member or have access token)

**Response:**
```json
{
  "id": "507f1f77bcf86cd799439011",
  "payer_member_id": "uuid-string-1",
  "payee_member_id": "uuid-string-2",
  "amount": 50.00,
  "mode": "upi"
}
```

### PATCH `/api/tripsync/{trip_id}/settlements/{settlement_id}`

Update a settlement.

**Authentication:** Required (must be a member or have access token)

**Rate Limit:** 60/minute

**Request Body:** `SettlementUpdate`

**Response:**
```json
{
  "id": "507f1f77bcf86cd799439011"
}
```

### DELETE `/api/tripsync/{trip_id}/settlements/{settlement_id}`

  Delete a settlement.

  **Authentication:** Required (must be a member or have access token)

  **Rate Limit:** 60/minute

  **Response:** 204 No Content

### GET `/api/tripsync/{trip_id}/settlements`

List all settlements for a trip.

**Authentication:** Required (must be a member or have access token)

**Response:** `List[SettlementRead]`

  ### GET `/api/tripsync/{trip_id}/balances`

  Get balance calculations for all members in a trip.

  **Authentication:** Required (must be a member or have access token)

  **Rate Limit:** 60/minute

  **Response:** `List[BalanceEntry]`

  ### GET `/api/tripsync/{trip_id}/link`

  Get the current access link for a trip.

  **Authentication:** Required (must be a linked member)

  **Response:** `TripLinkInfo`
  ```json
  {
    "secret_access_url": "http://localhost:8000/api/tripsync/access/{token}",
    "link_revoked": false,
    "link_expires_at": "2024-12-31T23:59:59",
    "access_token_version": 1
  }
  ```

  ### POST `/api/tripsync/{trip_id}/rotate-link`

  Rotate the access token for a trip.

  **Authentication:** Required (must be a linked member)

  **Response:**
  ```json
  {
    "secret_access_url": "/api/tripsync/access/{new_token}"
  }
  ```

  ### POST `/api/tripsync/{trip_id}/revoke-link`

  Revoke the access link for a trip.

  **Authentication:** Required (must be a linked member)

  **Response:** 204 No Content

  ### PATCH `/api/tripsync/{trip_id}/link-expiry`

  Update the expiry date for the access link.

  **Authentication:** Required (must be a linked member)

  **Request Body:** `LinkExpiryUpdate`

  **Response:**
  ```json
  {
    "link_expires_at": "2024-12-31T23:59:59"
  }
  ```

  ### GET `/api/tripsync/{trip_id}`

  Get trip details.

  **Authentication:** Required (must be a member or have access token)

  **Response:** `TripRead`

  ---

  ## Schemas

  ### Authentication Schemas

  #### UserRead
  ```json
  {
    "id": "507f1f77bcf86cd799439011",
    "email": "user@example.com",
    "username": "johndoe",
    "avatar": "https://example.com/avatar.jpg",
    "bio": "User bio",
    "role": "user",
    "is_active": true,
    "is_superuser": false,
    "is_verified": false,
    "created_at": "2024-01-01T00:00:00"
  }
  ```

  #### UserCreate
  ```json
  {
    "email": "user@example.com",
    "password": "securepassword",
    "username": "johndoe"
  }
  ```

  ---

  ### Blog Schemas

  #### AuthorRead
  ```json
  {
    "id": "507f1f77bcf86cd799439011",
    "username": "johndoe"
  }
  ```

  #### BlogPostCreate
  ```json
  {
    "title": "My Blog Post",
    "cover_image_url": "https://example.com/image.jpg",
    "content": "Full blog post content in markdown...",
    "excerpt": "Short excerpt of the post",
    "tags": ["python", "fastapi", "web"]
  }
  ```

  **Fields:**
  - `title` (string, required, max 100 chars)
  - `cover_image_url` (string, optional)
  - `content` (string, required)
  - `excerpt` (string, optional, max 300 chars)
  - `tags` (array of strings, optional)

  #### BlogPostRead
  ```json
  {
    "id": "507f1f77bcf86cd799439011",
    "title": "My Blog Post",
    "slug": "my-blog-post",
    "cover_image_url": "https://example.com/image.jpg",
    "content": "Full blog post content...",
    "excerpt": "Short excerpt",
    "author": {
      "id": "507f1f77bcf86cd799439011",
      "username": "johndoe"
    },
    "likes_count": 42,
    "status": "PUBLISHED",
    "tags": ["python", "fastapi"],
    "createdAt": "2024-01-01T00:00:00"
  }
  ```

  #### BlogPostList
  ```json
  {
    "id": "507f1f77bcf86cd799439011",
    "title": "My Blog Post",
    "slug": "my-blog-post",
    "cover_image_url": "https://example.com/image.jpg",
    "excerpt": "Short excerpt",
    "author": {
      "id": "507f1f77bcf86cd799439011",
      "username": "johndoe"
    },
    "likes_count": 42,
    "tags": ["python", "fastapi"],
    "createdAt": "2024-01-01T00:00:00"
  }
  ```

  #### CommentCreate
  ```json
  {
    "content": "This is a great post!"
  }
  ```

  **Fields:**
  - `content` (string, required, max 1000 chars)

  #### CommentRead
  ```json
  {
    "id": "507f1f77bcf86cd799439011",
    "author": {
      "id": "507f1f77bcf86cd799439011",
      "email": "user@example.com",
      "username": "johndoe",
      "avatar": "https://example.com/avatar.jpg",
      "bio": "User bio",
      "role": "user",
      "is_active": true,
      "is_superuser": false,
      "is_verified": false,
      "created_at": "2024-01-01T00:00:00"
    },
    "content": "This is a great post!",
    "createdAt": "2024-01-01T00:00:00"
  }
  ```

  ---

  ### TripSync Schemas

  #### TripCreate
  ```json
  {
    "name": "Summer Vacation 2024",
    "description": "Trip to Europe"
  }
  ```

  **Fields:**
  - `name` (string, required, max 100 chars)
  - `description` (string, optional)

  #### TripRead
  ```json
  {
    "id": "507f1f77bcf86cd799439011",
    "name": "Summer Vacation 2024",
    "description": "Trip to Europe",
    "members": [
      {
        "member_id": "uuid-string",
        "display_name": "John Doe",
        "linked": true
      }
    ],
    "secret_access_url": "http://localhost:8000/api/tripsync/access/{token}"
  }
  ```

  #### TripMemberInfo
  ```json
  {
    "member_id": "uuid-string",
    "display_name": "John Doe",
    "linked": true
  }
  ```

  #### TripMemberCreate
  ```json
  {
    "display_name": "Jane Doe"
  }
  ```

  **Fields:**
  - `display_name` (string, required, max 100 chars)

  #### LinkSelfRequest
  ```json
  {
    "member_id": "uuid-string"
  }
  ```

  **Fields:**
  - `member_id` (string, optional)

  #### ItineraryItemCreate
  ```json
  {
    "title": "Visit Eiffel Tower",
    "item_type": "activity",
    "start_time": "2024-07-15T10:00:00",
    "end_time": "2024-07-15T12:00:00",
    "location": "Paris, France"
  }
  ```

  **Fields:**
  - `title` (string, required, max 100 chars)
  - `item_type` (string, required)
  - `start_time` (datetime, required)
  - `end_time` (datetime, optional)
  - `location` (string, optional)

  #### ItineraryItemUpdate
  ```json
  {
    "title": "Visit Eiffel Tower",
    "item_type": "activity",
    "start_time": "2024-07-15T10:00:00",
    "end_time": "2024-07-15T12:00:00",
    "location": "Paris, France",
    "notes": "Don't forget tickets"
  }
  ```

  All fields are optional.

  #### ExpenseCreate
  ```json
  {
    "description": "Dinner at restaurant",
    "amount": 150.50,
    "paid_by_member_id": "uuid-string",
    "split_with_member_ids": ["uuid-1", "uuid-2"]
  }
  ```

  **Fields:**
  - `description` (string, required, max 150 chars)
  - `amount` (float, required)
  - `paid_by_member_id` (string, required)
  - `split_with_member_ids` (array of strings, required)

  #### ExpenseUpdate
  ```json
  {
    "description": "Dinner at restaurant",
    "amount": 150.50,
    "paid_by_member_id": "uuid-string",
    "split_with_member_ids": ["uuid-1", "uuid-2"]
  }
  ```

  All fields are optional.

  #### ExpenseRead
  ```json
  {
    "id": "507f1f77bcf86cd799439011",
    "description": "Dinner at restaurant",
    "amount": 150.50,
    "paid_by_member_id": "uuid-string",
    "split_with_member_ids": ["uuid-1", "uuid-2"]
  }
  ```

  #### SettlementCreate
  ```json
  {
    "payer_member_id": "uuid-string-1",
    "payee_member_id": "uuid-string-2",
    "amount": 50.00,
    "mode": "upi"
  }
  ```

  **Fields:**
  - `payer_member_id` (string, required)
  - `payee_member_id` (string, required)
  - `amount` (float, required)
  - `mode` (string, optional, default: "upi"): Payment mode - must be one of "cash", "upi", or "card"

  #### SettlementUpdate
  ```json
  {
    "payer_member_id": "uuid-string-1",
    "payee_member_id": "uuid-string-2",
    "amount": 50.00,
    "mode": "card"
  }
  ```

  **Fields:** All fields are optional.
  - `payer_member_id` (string, optional)
  - `payee_member_id` (string, optional)
  - `amount` (float, optional)
  - `mode` (string, optional): Payment mode - must be one of "cash", "upi", or "card"

  #### SettlementRead
  ```json
  {
    "id": "507f1f77bcf86cd799439011",
    "payer_member_id": "uuid-string-1",
    "payee_member_id": "uuid-string-2",
    "amount": 50.00,
    "mode": "upi"
  }
  ```

  **Fields:**
  - `id` (string): Settlement ID
  - `payer_member_id` (string): Member ID of the payer
  - `payee_member_id` (string): Member ID of the payee
  - `amount` (float): Settlement amount
  - `mode` (string): Payment mode - "cash", "upi", or "card"

  #### BalanceEntry
  ```json
  {
    "member_id": "uuid-string",
    "balance": 25.50
  }
  ```

  **Fields:**
  - `member_id` (string)
  - `balance` (float): Positive means others owe them, negative means they owe

  #### LinkExpiryUpdate
  ```json
  {
    "link_expires_at": "2024-12-31T23:59:59"
  }
  ```

  **Fields:**
  - `link_expires_at` (datetime, optional)

  #### TripLinkInfo
  ```json
  {
    "secret_access_url": "http://localhost:8000/api/tripsync/access/{token}",
    "link_revoked": false,
    "link_expires_at": "2024-12-31T23:59:59",
    "access_token_version": 1
  }
  ```

  **Fields:**
  - `secret_access_url` (string): The full URL to access the trip without authentication
  - `link_revoked` (boolean): Whether the link has been revoked
  - `link_expires_at` (datetime, optional): When the link expires (null if no expiry)
  - `access_token_version` (integer): The version number of the access token (increments on rotation)

  ---

  ## Post Status Values

  For blog posts:
  - `PUBLISHED`: Post is live and visible to everyone
  - `PENDING_REVIEW`: Post is awaiting admin approval
  - `REJECTED`: Post was rejected by admin

  ---

  ## Rate Limits

  Various endpoints have rate limits:
  - Health check: 5/minute
  - Trip access link: 30/minute
  - Trip operations (members, itinerary, expenses, settlements): 60/minute

  Rate limit errors will return a 429 status code.

  ---

  ## Error Responses

  ### 400 Bad Request
  ```json
  {
    "detail": "Error message describing what went wrong"
  }
  ```

  ### 401 Unauthorized
  ```json
  {
    "detail": "Not authenticated"
  }
  ```

  ### 403 Forbidden
  ```json
  {
    "detail": "Not enough permissions"
  }
  ```

  ### 404 Not Found
  ```json
  {
    "detail": "Resource not found"
  }
  ```

  ### 429 Too Many Requests
  ```json
  {
    "detail": "Rate limit exceeded"
  }
  ```

  ### 500 Internal Server Error
  ```json
  {
    "detail": "Internal server error message"
  }
  ```


