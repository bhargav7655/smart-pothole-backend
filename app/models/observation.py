from datetime import datetime, timezone
from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime, ForeignKey, Index
from sqlalchemy.orm import relationship

from app.core.database import Base


class ReportObservation(Base):
    __tablename__ = "report_observations"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    canonical_report_id = Column(Integer, ForeignKey("pothole_reports.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    
    image_path = Column(String(500), nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    location_accuracy = Column(Float, nullable=True)  # in meters
    
    capture_time = Column(DateTime, nullable=False)
    server_receipt_time = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    
    yolo_result = Column(String(100), nullable=False, default="pothole")
    confidence_score = Column(Float, nullable=False)
    
    is_canonical = Column(Boolean, default=False, nullable=False)
    distance_to_canonical_meters = Column(Float, default=0.0, nullable=False)

    canonical_report = relationship("PotholeReport", back_populates="observations")
    user = relationship("User", back_populates="observations")

    __table_args__ = (
        Index("idx_obs_canonical_user", "canonical_report_id", "user_id"),
    )
