import os
from typing import List, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    PROJECT_NAME: str = "Smart Pothole Detection and Reporting System"
    DEBUG: bool = True
    API_V1_STR: str = "/api"

    # JWT Authentication
    SECRET_KEY: str = "insecure-dev-secret-key-change-in-production-env"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 hours

    # Database (Cloud PostgreSQL on Neon/Supabase or local SQLite fallback)
    DATABASE_URL: str = "sqlite:///./potholes_dev.db"

    # Cloud Object Storage (S3 / Cloudflare R2 / Supabase Storage)
    STORAGE_BACKEND: str = "local"  # "local" or "s3"
    S3_BUCKET_NAME: Optional[str] = None
    S3_ENDPOINT_URL: Optional[str] = None
    S3_ACCESS_KEY_ID: Optional[str] = None
    S3_SECRET_ACCESS_KEY: Optional[str] = None
    S3_REGION_NAME: str = "us-east-1"
    S3_PUBLIC_DOMAIN: Optional[str] = None

    # Local Storage Fallback
    UPLOAD_DIR: str = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
    MAX_UPLOAD_SIZE_MB: int = 10
    ALLOWED_IMAGE_TYPES: List[str] = ["image/jpeg", "image/png", "image/webp"]

    # YOLO Model
    YOLO_MODEL_PATH: str = "models/pothole_yolov8.pt"
    POTHOLE_CONFIDENCE_THRESHOLD: float = 0.30

    # Geospatial Deduplication
    DUPLICATE_RADIUS_METERS: float = 25.0

    # Seed Admin Defaults
    ADMIN_EMAIL: str = "admin@roads.gov"
    ADMIN_PASSWORD: str = "AdminPass123!"
    ADMIN_NAME: str = "System Administrator"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="allow",
    )


settings = Settings()

# Ensure uploads directory exists if using local storage
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
