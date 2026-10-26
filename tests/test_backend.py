import io
import os
import pytest
from datetime import datetime, timezone
from PIL import Image
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import Base, get_db
from app.core.security import get_password_hash, create_access_token
from app.models.user import User, UserRole
from app.models.report import PotholeReport, ReportStatus
from app.models.observation import ReportObservation
from app.services.deduplication_service import haversine_distance_meters, DeduplicationService
from app.main import app

# Setup test database
TEST_DB_URL = "sqlite:///./test_potholes.db"
test_engine = create_engine(TEST_DB_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)


def override_get_db():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


def create_sample_image_bytes(format="JPEG", color="blue"):
    file_bytes = io.BytesIO()
    img = Image.new("RGB", (100, 100), color=color)
    img.save(file_bytes, format=format)
    file_bytes.seek(0)
    return file_bytes


@pytest.fixture(scope="module", autouse=True)
def setup_database():
    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)
    if os.path.exists("./test_potholes.db"):
        try:
            os.remove("./test_potholes.db")
        except Exception:
            pass


def test_haversine_distance():
    # Test distance between two known points (approx 111 meters for 0.001 deg lat at equator)
    dist = haversine_distance_meters(0.0, 0.0, 0.001, 0.0)
    assert 110.0 <= dist <= 112.0

    # Same coordinates should have 0 distance
    assert haversine_distance_meters(18.5204, 73.8567, 18.5204, 73.8567) == 0.0

    # 10 meters distance
    # 0.00009 deg lat is approx 10 meters
    dist_10m = haversine_distance_meters(18.5204, 73.8567, 18.52049, 73.8567)
    assert dist_10m < 15.0


def test_user_registration_and_login():
    # Register user
    reg_payload = {
        "full_name": "Citizen Alice",
        "email": "alice@example.com",
        "password": "StrongPassword123!",
    }
    res = client.post("/api/auth/register", json=reg_payload)
    assert res.status_code == 201
    data = res.json()
    assert data["email"] == "alice@example.com"
    assert data["role"] == "USER"
    assert "hashed_password" not in data

    # Attempt duplicate registration with same email
    res_dup = client.post("/api/auth/register", json=reg_payload)
    assert res_dup.status_code == 400

    # Login with valid credentials
    login_res = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "StrongPassword123!"})
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "access_token" in login_data
    assert login_data["role"] == "USER"

    # Login with invalid password
    bad_login = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "WrongPassword"})
    assert bad_login.status_code == 401


def test_role_enforcement_and_admin_security():
    # Create an admin user directly in DB
    db = TestingSessionLocal()
    admin_user = User(
        full_name="Admin Chief",
        email="chief@admin.gov",
        hashed_password=get_password_hash("AdminSecret789!"),
        role=UserRole.ADMIN,
        is_active=True,
    )
    db.add(admin_user)
    db.commit()
    db.refresh(admin_user)
    db.close()

    # Login as admin
    admin_login = client.post("/api/auth/login", json={"email": "chief@admin.gov", "password": "AdminSecret789!"})
    assert admin_login.status_code == 200
    admin_token = admin_login.json()["access_token"]

    # Login as regular user Alice
    user_login = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "StrongPassword123!"})
    user_token = user_login.json()["access_token"]

    # Regular user attempting to access Admin endpoint must receive 403 Forbidden
    res_forbidden = client.get("/api/admin/reports", headers={"Authorization": f"Bearer {user_token}"})
    assert res_forbidden.status_code == 403

    # Admin accessing Admin endpoint must receive 200 OK
    res_allowed = client.get("/api/admin/reports", headers={"Authorization": f"Bearer {admin_token}"})
    assert res_allowed.status_code == 200

    # Unauthenticated request must receive 401 Unauthorized
    res_unauth = client.get("/api/admin/reports")
    assert res_unauth.status_code == 401


def test_image_validation():
    user_login = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "StrongPassword123!"})
    user_token = user_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {user_token}"}

    # Upload non-image text file
    fake_file = io.BytesIO(b"not an image file")
    res = client.post(
        "/api/reports",
        headers=headers,
        data={"latitude": 18.5204, "longitude": 73.8567},
        files={"file": ("test.txt", fake_file, "text/plain")},
    )
    assert res.status_code == 400
    assert "Unsupported file format" in res.json()["detail"]


def test_report_submission_and_deduplication():
    # User Alice logs in
    user_login = client.post("/api/auth/login", json={"email": "alice@example.com", "password": "StrongPassword123!"})
    user_token = user_login.json()["access_token"]
    headers = {"Authorization": f"Bearer {user_token}"}

    # Create another citizen Bob
    client.post(
        "/api/auth/register",
        json={"full_name": "Bob Smith", "email": "bob@example.com", "password": "BobPassword123!"},
    )
    bob_login = client.post("/api/auth/login", json={"email": "bob@example.com", "password": "BobPassword123!"})
    bob_token = bob_login.json()["access_token"]
    bob_headers = {"Authorization": f"Bearer {bob_token}"}

    # Admin token for verifying dashboard
    admin_login = client.post("/api/auth/login", json={"email": "chief@admin.gov", "password": "AdminSecret789!"})
    admin_token = admin_login.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    db = TestingSessionLocal()

    # Test Deduplication logic directly with mock confidence values
    # Submission 1: Alice reports pothole at (18.520400, 73.856700) with confidence 0.85 (>= 0.30 threshold)
    rep1, obs1, is_dup1 = DeduplicationService.find_and_link_or_create(
        db=db,
        user_id=1,
        latitude=18.520400,
        longitude=73.856700,
        location_accuracy=5.0,
        capture_time=datetime.now(timezone.utc),
        image_path="test_img_1.jpg",
        confidence_score=0.85,
        detection_result="pothole",
        passed_threshold=True,
    )
    assert not is_dup1
    assert rep1.observation_count == 1
    assert rep1.status == ReportStatus.SUBMITTED
    canonical_id = rep1.id

    # Submission 2: Bob reports the same pothole 10 meters away at (18.520480, 73.856700) with confidence 0.72
    rep2, obs2, is_dup2 = DeduplicationService.find_and_link_or_create(
        db=db,
        user_id=2,
        latitude=18.520480,
        longitude=73.856700,
        location_accuracy=4.0,
        capture_time=datetime.now(timezone.utc),
        image_path="test_img_2.jpg",
        confidence_score=0.72,
        detection_result="pothole",
        passed_threshold=True,
    )
    # Must be identified as DUPLICATE and linked to canonical report 1
    assert is_dup2
    assert rep2.id == canonical_id
    assert rep2.observation_count == 2
    assert rep2.status == ReportStatus.DUPLICATE_LINKED
    assert obs2.is_canonical is False
    assert obs2.distance_to_canonical_meters < 25.0

    # Submission 3: Another report 500 meters away at (18.525000, 73.856700)
    rep3, obs3, is_dup3 = DeduplicationService.find_and_link_or_create(
        db=db,
        user_id=1,
        latitude=18.525000,
        longitude=73.856700,
        location_accuracy=6.0,
        capture_time=datetime.now(timezone.utc),
        image_path="test_img_3.jpg",
        confidence_score=0.65,
        detection_result="pothole",
        passed_threshold=True,
    )
    # Must NOT be merged into report 1 because distance > 25m
    assert not is_dup3
    assert rep3.id != canonical_id
    assert rep3.observation_count == 1

    # Submission 4: Report below 0.30 threshold (e.g. confidence 0.15)
    rep4, obs4, is_dup4 = DeduplicationService.find_and_link_or_create(
        db=db,
        user_id=1,
        latitude=18.520400,
        longitude=73.856700,
        location_accuracy=5.0,
        capture_time=datetime.now(timezone.utc),
        image_path="test_img_4.jpg",
        confidence_score=0.15,
        detection_result="no_pothole_detected",
        passed_threshold=False,
    )
    # Must be marked BELOW_THRESHOLD and NOT linked into canonical active queue
    assert rep4.status == ReportStatus.BELOW_THRESHOLD
    assert rep4.id != canonical_id

    db.close()

    # Verify Admin actionable filter excludes BELOW_THRESHOLD reports
    actionable_res = client.get("/api/admin/reports?status_filter=ACTIONABLE", headers=admin_headers)
    assert actionable_res.status_code == 200
    actionable_reports = actionable_res.json()
    report_statuses = [r["status"] for r in actionable_reports]
    assert "BELOW_THRESHOLD" not in report_statuses

    # Verify Report Detail endpoint displays canonical report with both observations
    detail_res = client.get(f"/api/admin/reports/{canonical_id}", headers=admin_headers)
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert detail_data["observation_count"] == 2
    assert len(detail_data["observations"]) == 2
