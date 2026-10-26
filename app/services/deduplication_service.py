import math
from datetime import datetime, timezone
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.models.report import PotholeReport, ReportStatus
from app.models.observation import ReportObservation


def haversine_distance_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Computes great-circle distance between two GPS points in meters using the Haversine formula.
    """
    R = 6371000.0  # Earth radius in meters

    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = (
        math.sin(delta_phi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2.0) ** 2
    )
    c = 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    return R * c


class DeduplicationService:
    @staticmethod
    def find_and_link_or_create(
        db: Session,
        user_id: int,
        latitude: float,
        longitude: float,
        location_accuracy: Optional[float],
        capture_time: datetime,
        image_path: str,
        confidence_score: float,
        detection_result: str,
        passed_threshold: bool,
    ) -> Tuple[PotholeReport, ReportObservation, bool]:
        """
        Processes a report submission:
        - If NOT passed_threshold (< 0.30): creates an unconfirmed/below-threshold record,
          not merged into any canonical report and excluded from the actionable queue.
        - If passed_threshold (>= 0.30): performs concurrency-safe proximity check within DUPLICATE_RADIUS_METERS.
          - If nearby active canonical report found, links as duplicate observation and increments counter.
          - Otherwise, creates new canonical report.

        Returns: (canonical_report, observation, is_duplicate)
        """
        now = datetime.now(timezone.utc)
        radius_meters = settings.DUPLICATE_RADIUS_METERS

        # CASE 1: Below detection threshold
        if not passed_threshold:
            # Create a standalone record flagged as BELOW_THRESHOLD
            report = PotholeReport(
                latitude=latitude,
                longitude=longitude,
                location_accuracy=location_accuracy,
                capture_time=capture_time,
                server_receipt_time=now,
                primary_image_path=image_path,
                yolo_confidence=confidence_score,
                detection_result=detection_result,
                status=ReportStatus.BELOW_THRESHOLD,
                observation_count=1,
                last_reported_at=now,
            )
            db.add(report)
            db.flush()

            obs = ReportObservation(
                canonical_report_id=report.id,
                user_id=user_id,
                image_path=image_path,
                latitude=latitude,
                longitude=longitude,
                location_accuracy=location_accuracy,
                capture_time=capture_time,
                server_receipt_time=now,
                yolo_result=detection_result,
                confidence_score=confidence_score,
                is_canonical=True,
                distance_to_canonical_meters=0.0,
            )
            db.add(obs)
            db.commit()
            db.refresh(report)
            db.refresh(obs)
            return report, obs, False

        # CASE 2: Passed threshold (>= 0.30) -> Geospatial Proximity Deduplication
        # Calculate bounding box for fast database index pruning:
        # 1 degree latitude ~ 111,139 meters. 25 meters ~ 0.000225 deg lat.
        lat_delta = (radius_meters / 111139.0) * 1.5
        lon_delta = (radius_meters / (111139.0 * max(0.1, math.cos(math.radians(latitude))))) * 1.5

        min_lat = latitude - lat_delta
        max_lat = latitude + lat_delta
        min_lon = longitude - lon_delta
        max_lon = longitude + lon_delta

        # Query candidate active canonical reports within bounding box
        # Concurrency safety: For PostgreSQL/supported backends, acquire row-level lock
        query = (
            db.query(PotholeReport)
            .filter(
                PotholeReport.status.in_([ReportStatus.SUBMITTED, ReportStatus.DUPLICATE_LINKED, ReportStatus.UNDER_REVIEW]),
                PotholeReport.latitude.between(min_lat, max_lat),
                PotholeReport.longitude.between(min_lon, max_lon),
            )
        )

        # Apply row-level lock if supported by database dialect (PostgreSQL)
        if db.bind and db.bind.dialect.name == "postgresql":
            query = query.with_for_update()

        candidates = query.all()

        closest_report = None
        min_distance = float("inf")

        for cand in candidates:
            dist = haversine_distance_meters(latitude, longitude, cand.latitude, cand.longitude)
            if dist <= radius_meters and dist < min_distance:
                min_distance = dist
                closest_report = cand

        if closest_report is not None:
            # Found existing canonical report within 25m: Link as duplicate observation
            closest_report.observation_count += 1
            closest_report.last_reported_at = now
            if closest_report.status == ReportStatus.SUBMITTED:
                closest_report.status = ReportStatus.DUPLICATE_LINKED

            obs = ReportObservation(
                canonical_report_id=closest_report.id,
                user_id=user_id,
                image_path=image_path,
                latitude=latitude,
                longitude=longitude,
                location_accuracy=location_accuracy,
                capture_time=capture_time,
                server_receipt_time=now,
                yolo_result=detection_result,
                confidence_score=confidence_score,
                is_canonical=False,
                distance_to_canonical_meters=round(min_distance, 2),
            )
            db.add(obs)
            db.commit()
            db.refresh(closest_report)
            db.refresh(obs)
            return closest_report, obs, True

        else:
            # No existing report within 25m: Create new canonical report
            new_report = PotholeReport(
                latitude=latitude,
                longitude=longitude,
                location_accuracy=location_accuracy,
                capture_time=capture_time,
                server_receipt_time=now,
                primary_image_path=image_path,
                yolo_confidence=confidence_score,
                detection_result=detection_result,
                status=ReportStatus.SUBMITTED,
                observation_count=1,
                last_reported_at=now,
            )
            db.add(new_report)
            db.flush()

            obs = ReportObservation(
                canonical_report_id=new_report.id,
                user_id=user_id,
                image_path=image_path,
                latitude=latitude,
                longitude=longitude,
                location_accuracy=location_accuracy,
                capture_time=capture_time,
                server_receipt_time=now,
                yolo_result=detection_result,
                confidence_score=confidence_score,
                is_canonical=True,
                distance_to_canonical_meters=0.0,
            )
            db.add(obs)
            db.commit()
            db.refresh(new_report)
            db.refresh(obs)
            return new_report, obs, False
