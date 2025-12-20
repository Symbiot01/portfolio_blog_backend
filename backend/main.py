# main.py
import os
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request # <-- 1. Import Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

from app.blog.router import router as blog_router
from app.auth.router import router as auth_router
from app.uploads.router import router as uploads_router
from app.admin.router import router as admin_router
from app.tripsync.router import router as tripsync_router
from app.core.database import initialize_database

limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="Portfolio & Blog API",
    version="1.0.0"
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

origins = ["*"] 

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def on_startup():
    # Production safety: fail fast if critical env vars are missing.
    required = ["DATABASE_URL", "DATABASE_NAME", "SECRET_KEY"]
    missing = [k for k in required if not os.getenv(k)]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
    await initialize_database()

app.include_router(auth_router, prefix="/api/auth")
app.include_router(admin_router, prefix="/api/admin", tags=["Admin"])
app.include_router(blog_router, prefix="/api/blog", tags=["Blog"])
app.include_router(uploads_router, prefix="/api/uploads", tags=["Uploads"])
app.include_router(tripsync_router, prefix="/api/tripsync", tags=["TripSync"])  

@app.get("/api/health")
@limiter.limit("5/minute")
# 2. Add the request argument to the function signature
def health_check(request: Request):
    return {"status": "ok", "message": f"Connected to DB: {os.getenv('DATABASE_NAME')}"}