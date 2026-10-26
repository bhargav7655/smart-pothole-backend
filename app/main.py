from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.core.config import settings
from app.core.database import Base, engine
from app.routers import auth_router, reports_router, admin_router
from app.services.yolo_service import YoloPotholeDetector

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("pothole_api")

# Auto-create tables on startup (for rapid local deployment and testing)
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Backend API for AI-Based Smart Pothole Detection and Reporting System",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS configuration allowing requests from Android emulator, local dev, and admin web dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event():
    logger.info("Initializing Pothole Detection Backend Service...")
    # Preload YOLO model once on startup
    detector = YoloPotholeDetector.get_instance()
    logger.info(f"YOLO detector initialization status: loaded={detector.is_loaded}")


@app.get("/")
def root():
    return {
        "project": settings.PROJECT_NAME,
        "version": "1.0.0",
        "status": "online",
        "docs": "/docs",
        "confidence_threshold": settings.POTHOLE_CONFIDENCE_THRESHOLD,
        "duplicate_radius_meters": settings.DUPLICATE_RADIUS_METERS,
    }


# Include Routers
app.include_router(auth_router, prefix=settings.API_V1_STR)
app.include_router(reports_router, prefix=settings.API_V1_STR)
app.include_router(admin_router, prefix=settings.API_V1_STR)
