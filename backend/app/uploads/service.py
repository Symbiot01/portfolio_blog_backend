# app/uploads/service.py
import cloudinary
import cloudinary.uploader
from fastapi import UploadFile
import os

# Cloudinary configuration is automatically read from the CLOUDINARY_URL env variable

class UploadService:
    @staticmethod
    def upload_image(file: UploadFile):
        # You can specify a folder in Cloudinary to keep things organized
        upload_result = cloudinary.uploader.upload(
            file.file,
            folder="portfolio_blog"
        )
        return upload_result.get("secure_url")