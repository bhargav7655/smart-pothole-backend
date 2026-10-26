import enum
from datetime import datetime, timezone
from sqlalchemy import Column, Integer, Float, String, DateTime, Enum, Index
from sqlalchemy.orm import relationship

from app.core.database import Base


class ReportStatus(str, enum.Enum):
    PROCESSING = "PROCESSING"
    SUBMITTED = "SUBMITTED"
    DUPLICATE_LINKED = "DUPLICATE_LINKED"
    BELOW_THRESHOLD = "BELOW_THRESHOLD"
    PROCESSING_FAILED = "PROCESSING_FAILED"
    UNDER_REVIEW = "UNDER_REVIEW"


class PotholeReport(Base):
    __tablename__ = "pothole_reports"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    latitude = Column(Float, nullable=False, index=True)
    longitude = Column(Float, nullable=False, index=True)
    location_accuracy = Column(Float, nullable=True)  # in meters
    capture_time = Column(DateTime, nullable=False)
    server_receipt_time = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    primary_image_path = Column(String(500), nullable=False)
    yolo_confidence = Column(Float, nullable=False)  # Highest pothole confidence score 0.0 - 1.0
    detection_result = Column(String(100), nullable=False, default="pothole")
    
    status = Column(Enum(ReportStatus), default=ReportStatus.SUBMITTED, nullable=False, index=True)
    observation_count = Column(Integer, default=1, nullable=False)
    
    last_reported_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    observations = relationship("ReportObservation", back_populates="canonical_report", cascade="all, delete-orphan", order_by="desc(ReportObservation.server_receipt_time)")

    __table_args__ = (
        Index("idx_reports_lat_long", "latitude", "longitude"),
    )
