from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_role
from app.models.user import User, UserRole
from app.models.report import PotholeReport, ReportStatus
from app.models.observation import ReportObservation
from app.schemas.report import CanonicalReportDetail, ObservationSummary
from app.services.storage_service import StorageService
from app.services.cloud_storage_service import CloudStorageService

router = APIRouter(prefix="/admin", tags=["Administrator Desk"])


@router.get("/reports", response_model=List[CanonicalReportDetail])
def list_admin_reports(
    status_filter: Optional[str] = Query(None, description="Filter by status: ALL, ACTIONABLE, SUBMITTED, DUPLICATE_LINKED, BELOW_THRESHOLD"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    current_admin: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    query = db.query(PotholeReport)

    if status_filter and status_filter.upper() == "ACTIONABLE":
        query = query.filter(PotholeReport.status.in_([ReportStatus.SUBMITTED, ReportStatus.DUPLICATE_LINKED, ReportStatus.UNDER_REVIEW]))
    elif status_filter and status_filter.upper() != "ALL":
        try:
            status_enum = ReportStatus(status_filter.upper())
            query = query.filter(PotholeReport.status == status_enum)
        except ValueError:
            pass

    reports = query.order_by(PotholeReport.last_reported_at.desc()).offset(skip).limit(limit).all()

    result = []
    for report in reports:
        obs_summaries = [
            ObservationSummary(
                id=obs.id,
                user_id=obs.user_id,
                submitting_user_name=obs.user.full_name if obs.user else "Citizen",
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
            for obs in report.observations
        ]

        result.append(
            CanonicalReportDetail(
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
        )
    return result


@router.get("/reports/{report_id}", response_model=CanonicalReportDetail)
def get_admin_report_detail(
    report_id: int,
    current_admin: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    report = db.query(PotholeReport).filter(PotholeReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Report not found")

    obs_summaries = [
        ObservationSummary(
            id=obs.id,
            user_id=obs.user_id,
            submitting_user_name=obs.user.full_name if obs.user else "Citizen",
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
        for obs in report.observations
    ]

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


@router.get("/observations/{observation_id}/image")
def get_admin_observation_image(
    observation_id: int,
    current_admin: User = Depends(require_role(["ADMIN"])),
    db: Session = Depends(get_db),
):
    obs = db.query(ReportObservation).filter(ReportObservation.id == observation_id).first()
    if not obs:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Observation not found")

    if obs.image_path.startswith("http://") or obs.image_path.startswith("https://"):
        return RedirectResponse(obs.image_path)
    if obs.image_path.startswith("s3://"):
        url = CloudStorageService.resolve_image_url(obs.image_path)
        return RedirectResponse(url)

    safe_path = StorageService.get_file_path(obs.image_path)
    return FileResponse(safe_path)
