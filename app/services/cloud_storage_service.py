import io
import os
import uuid
import logging
from typing import Tuple, Optional
from fastapi import UploadFile, HTTPException, status
from PIL import Image

from app.core.config import settings
from app.services.storage_service import StorageService

logger = logging.getLogger("cloud_storage")


class CloudStorageService:
    """
    Unified storage service supporting Supabase Storage, Cloudflare R2,
    AWS S3, and local development storage.
    """

    @classmethod
    def _get_s3_client(cls):
        import boto3
        from botocore.config import Config

        session = boto3.session.Session()
        s3_client = session.client(
            service_name="s3",
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            endpoint_url=settings.S3_ENDPOINT_URL,
            region_name=settings.S3_REGION_NAME or "us-east-1",
            config=Config(signature_version="s3v4"),
        )
        return s3_client

    @classmethod
    async def validate_and_save_image(cls, file: UploadFile) -> Tuple[str, str]:
        """
        Validates image format, size, and integrity.
        Uploads directly to Cloud S3 / Supabase Storage if STORAGE_BACKEND == 's3'.
        Otherwise saves to local protected storage.
        Returns: (reference_path_or_url, unique_filename)
        """
        if file.content_type not in settings.ALLOWED_IMAGE_TYPES:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Unsupported file format '{file.content_type}'. Allowed: JPEG, PNG, WEBP.",
            )

        content = await file.read()
        file_size_mb = len(content) / (1024 * 1024)
        if file_size_mb > settings.MAX_UPLOAD_SIZE_MB:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File exceeds maximum allowed size of {settings.MAX_UPLOAD_SIZE_MB}MB.",
            )

        # Validate image integrity with Pillow
        try:
            image = Image.open(io.BytesIO(content))
            image.verify()
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Corrupt or invalid image file: {str(e)}",
            )

        ext = os.path.splitext(file.filename or "")[1].lower()
        if ext not in [".jpg", ".jpeg", ".png", ".webp"]:
            ext = ".jpg"
        unique_filename = f"{uuid.uuid4().hex}{ext}"

        # If Cloud S3 / Supabase Storage / Cloudflare R2 is enabled
        if settings.STORAGE_BACKEND == "s3" and settings.S3_BUCKET_NAME:
            try:
                s3 = cls._get_s3_client()
                s3.put_object(
                    Bucket=settings.S3_BUCKET_NAME,
                    Key=unique_filename,
                    Body=content,
                    ContentType=file.content_type,
                )
                logger.info(f"Successfully uploaded image to Cloud Bucket: {settings.S3_BUCKET_NAME}/{unique_filename}")

                # If a public domain or Supabase public URL is configured
                if settings.S3_PUBLIC_DOMAIN:
                    public_url = f"{settings.S3_PUBLIC_DOMAIN.rstrip('/')}/{unique_filename}"
                    return public_url, unique_filename

                return f"s3://{settings.S3_BUCKET_NAME}/{unique_filename}", unique_filename
            except Exception as e:
                logger.error(f"Failed to upload to cloud storage: {e}")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Cloud storage upload error: {str(e)}",
                )

        # Fallback to local development storage
        destination_path = os.path.join(settings.UPLOAD_DIR, unique_filename)
        with open(destination_path, "wb") as f:
            f.write(content)

        return destination_path, unique_filename

    @classmethod
    def resolve_image_url(cls, image_path: str) -> str:
        """
        Converts an image reference to an accessible URL.
        If already a full HTTP(S) URL, returns directly.
        If an s3:// URI, generates a presigned secure URL.
        If a local filename, returns /api/reports/image/{filename}.
        """
        if image_path.startswith("http://") or image_path.startswith("https://"):
            return image_path

        if image_path.startswith("s3://"):
            try:
                parts = image_path.replace("s3://", "").split("/", 1)
                bucket = parts[0]
                key = parts[1]
                s3 = cls._get_s3_client()
                presigned_url = s3.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": bucket, "Key": key},
                    ExpiresIn=3600,
                )
                return presigned_url
            except Exception as e:
                logger.error(f"Error generating presigned URL for {image_path}: {e}")
                return image_path

        filename = os.path.basename(image_path)
        return f"/api/reports/image/{filename}"
