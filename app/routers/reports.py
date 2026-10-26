from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.models.user import User, UserRole
from app.models.report import PotholeReport, ReportStatus
from app.models.observation import ReportObservation
from app.schemas.report import ReportResponse, UserObservationItem, CanonicalReportDetail, ObservationSummary
from app.services.storage_service import StorageService
from app.services.cloud_storage_service import CloudStorageService
from app.services.yolo_service import YoloPotholeDetector
from app.services.deduplication_service import DeduplicationService

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post("", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
async def submit_report(
    file: UploadFile = File(..., description="Pothole photograph captured directly via in-app camera"),
    latitude: float = Form(..., description="GPS Latitude in decimal degrees"),
    longitude: float = Form(..., description="GPS Longitude in decimal degrees"),
    location_accuracy: Optional[float] = Form(None, description="GPS accuracy in meters"),
    capture_time: Optional[str] = Form(None, description="ISO format capture timestamp from camera"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    # Validate GPS latitude and longitude
    if not (-90.0 <= latitude <= 90.0) or not (-180.0 <= longitude <= 180.0):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid GPS coordinates supplied.",
        )

    # Parse capture time
    if capture_time:
        try:
            parsed_time = datetime.fromisoformat(capture_time.replace("Z", "+00:00"))
        except Exception:
            parsed_time = datetime.utcnow()
    else:
        parsed_time = datetime.utcnow()

    # Save and validate image (supports both Cloud S3/R2 and Local storage)
    reference_path, unique_filename = await CloudStorageService.validate_and_save_image(file)

    # Execute YOLO inference
    detector = YoloPotholeDetector.get_instance()
    inference_result = detector.detect_potholes(reference_path)

    confidence = inference_result["highest_confidence"]
    passed_threshold = inference_result["passed_threshold"]
    detection_label = inference_result["detection_result"]

    # Run Deduplication & Persistence
    report, observation, is_duplicate = DeduplicationService.find_and_link_or_create(
        db=db,
        user_id=current_user.id,
        latitude=latitude,
        longitude=longitude,
        location_accuracy=location_accuracy,
        capture_time=parsed_time,
        image_path=reference_path,
        confidence_score=confidence,
        detection_result=detection_label,
        passed_threshold=passed_threshold,
    )

    if not passed_threshold:
        msg = f"Detection confidence ({confidence * 100:.1f}%) is below the 30% threshold. Report recorded as unconfirmed."
    elif is_duplicate:
        msg = f"Nearby active pothole report #{report.id} detected within 25m. Your photo was merged as additional evidence (Observation #{observation.id})."
    else:
        msg = f"New canonical pothole report #{report.id} created successfully with {confidence * 100:.1f}% confidence."

    return ReportResponse(
        report_id=report.id,
        observation_id=observation.id,
        status=report.status,
        is_duplicate=is_duplicate,
        canonical_report_id=report.id,
        yolo_confidence=confidence,
        passed_threshold=passed_threshold,
        detection_result=detection_label,
        latitude=latitude,
        longitude=longitude,
        message=msg,
        observation_count=report.observation_count,
    )


@router.get("/my", response_model=List[UserObservationItem])
def get_my_reports(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    observations = (
        db.query(ReportObservation)
        .filter(ReportObservation.user_id == current_user.id)
        .order_by(ReportObservation.server_receipt_time.desc())
        .all()
    )

    result = []
    for obs in observations:
        rep = obs.canonical_report
        result.append(
            UserObservationItem(
                observation_id=obs.id,
                canonical_report_id=obs.canonical_report_id,
                latitude=obs.latitude,
                longitude=obs.longitude,
                capture_time=obs.capture_time,
                server_receipt_time=obs.server_receipt_time,
                confidence_score=obs.confidence_score,
                image_url=CloudStorageService.resolve_image_url(obs.image_path),
                report_status=rep.status if rep else ReportStatus.PROCESSING,
                is_canonical=obs.is_canonical,
                observation_count=rep.observation_count if rep else 1,
            )
        )
    return result


@router.get("/{report_id}", response_model=CanonicalReportDetail)
def get_report_detail(
    report_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    report = db.query(PotholeReport).filter(PotholeReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    if current_user.role != UserRole.ADMIN:
        has_access = any(obs.user_id == current_user.id for obs in report.observations)
        if not has_access:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied to this report")

    obs_summaries = []
    for obs in report.observations:
        obs_summaries.append(
            ObservationSummary(
                id=obs.id,
                user_id=obs.user_id,
                submitting_user_name=obs.user.full_name if obs.user else "Unknown User",
                image_url=CloudStorageService.resolve_image_url(obs.image_path),
                latitude=obs.latitude,
                longitude=obs.longitude,
                location_accuracy=obs.location_accuracy,
                capture_time=obs.capture_time,
                server_receipt_time=obs.server_receipt_time,
                confidence_score=obs.confidence_score,
                is_canonical=obs.is_canonical,
                distance_to_canonical_meters=obs.distance_to_canonical_meters,
            )
        )

    return CanonicalReportDetail(
        id=report.id,
        latitude=report.latitude,
        longitude=report.longitude,
        location_accuracy=report.location_accuracy,
        capture_time=report.capture_time,
        server_receipt_time=report.server_receipt_time,
        primary_image_url=CloudStorageService.resolve_image_url(report.primary_image_path),
        yolo_confidence=report.yolo_confidence,
        detection_result=report.detection_result,
        status=report.status,
        observation_count=report.observation_count,
        last_reported_at=report.last_reported_at,
        created_at=report.created_at,
        updated_at=report.updated_at,
        observations=obs_summaries,
    )


@router.get("/image/{filename}")
def get_report_image(filename: str):
    safe_path = StorageService.get_file_path(filename)
    return FileResponse(safe_path)
