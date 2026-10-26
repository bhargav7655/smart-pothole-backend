from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict
from app.models.report import ReportStatus


class ObservationSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    submitting_user_name: Optional[str] = None
    image_url: str
    latitude: float
    longitude: float
    location_accuracy: Optional[float] = None
    capture_time: datetime
    server_receipt_time: datetime
    confidence_score: float
    is_canonical: bool
    distance_to_canonical_meters: float


class ReportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    report_id: int
    observation_id: int
    status: ReportStatus
    is_duplicate: bool
    canonical_report_id: int
    yolo_confidence: float
    passed_threshold: bool
    detection_result: str
    latitude: float
    longitude: float
    message: str
    observation_count: int


class CanonicalReportDetail(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    latitude: float
    longitude: float
    location_accuracy: Optional[float]
    capture_time: datetime
    server_receipt_time: datetime
    primary_image_url: str
    yolo_confidence: float
    detection_result: str
    status: ReportStatus
    observation_count: int
    last_reported_at: datetime
    created_at: datetime
    updated_at: datetime
    observations: List[ObservationSummary] = []


class UserObservationItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    observation_id: int
    canonical_report_id: int
    latitude: float
    longitude: float
    capture_time: datetime
    server_receipt_time: datetime
    confidence_score: float
    image_url: str
    report_status: ReportStatus
    is_canonical: bool
    observation_count: int
