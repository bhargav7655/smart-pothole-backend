import os
import uuid
from typing import Tuple
from fastapi import UploadFile, HTTPException, status
from PIL import Image
import io

from app.core.config import settings


class StorageService:
    @staticmethod
    async def validate_and_save_image(file: UploadFile) -> Tuple[str, str]:
        """
        Validates content type, file size, and image integrity.
        Saves the file to protected storage with a secure UUID filename.
        Returns: (relative_file_path, original_extension)
        """
        # Validate MIME type
        if file.content_type not in settings.ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file format '{file.content_type}'. Allowed: JPEG, PNG, WEBP.",
            )

        # Read binary data
        content = await file.read()
        file_size_mb = len(content) / (1024 * 1024)
        if file_size_mb > settings.MAX_UPLOAD_SIZE_MB:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB.",
            )

        # Validate image integrity using Pillow
        try:
            image = Image.open(io.BytesIO(content))
            image.verify()  # Verifies image header and stream integrity
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Corrupt or invalid image file: {str(e)}",
            )

        # Generate unique sanitized filename
        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
            ext = ".jpg"
        unique_filename = f"{uuid.uuid4().hex}{ext}"
        destination_path = os.path.join(settings.UPLOAD_DIR, unique_filename)

        # Save to disk
        with open(destination_path, "wb") as f:
            f.write(content)

        return destination_path, unique_filename

    @staticmethod
    def get_file_path(filename: str) -> str:
        """Resolves filename within UPLOAD_DIR safely, preventing directory traversal."""
        safe_name = os.path.basename(filename)
        path = os.path.join(settings.UPLOAD_DIR, safe_name)
        if not os.path.exists(path):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Requested image was not found.",
            )
        return path
