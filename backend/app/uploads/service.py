# app/uploads/service.py
import cloudinary
import cloudinary.uploader
from fastapi import HTTPException, UploadFile
import os

# Cloudinary configuration is automatically read from the CLOUDINARY_URL env variable


class UploadService:
    @staticmethod
    def upload_image(file: UploadFile):
        cloudinary_url = (os.getenv("CLOUDINARY_URL") or "").strip()
        if not cloudinary_url:
            raise HTTPException(
                status_code=503,
                detail="Image upload is not configured (missing CLOUDINARY_URL)",
            )

        # Explicit config so Coolify/runtime env changes are picked up reliably.
        cloudinary.config(cloudinary_url=cloudinary_url, secure=True)

        upload_result = cloudinary.uploader.upload(
            file.file,
            folder="portfolio_blog",
        )
        return upload_result.get("secure_url")
