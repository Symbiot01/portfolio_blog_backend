# app/uploads/router.py
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException
from app.auth.core import current_active_user
from app.models.user import User
from .service import UploadService

router = APIRouter()


@router.post("/image")
async def upload_image(
    file: UploadFile = File(...),
    user: User = Depends(current_active_user),  # Protect the endpoint
):
    content_type = (file.content_type or "").lower()
    if not content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image.")

    try:
        image_url = UploadService.upload_image(file)
        if not image_url:
            raise HTTPException(status_code=502, detail="Upload provider returned no URL")
        return {"url": image_url}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to upload image: {str(e)}") from e
