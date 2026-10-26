import sys
import os

# Add parent directory to path so script can run directly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.config import settings
from app.core.database import SessionLocal, Base, engine
from app.core.security import get_password_hash
from app.models.user import User, UserRole
from app.models.report import PotholeReport
from app.models.observation import ReportObservation


def seed_admin():
    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    try:
        admin_email = settings.ADMIN_EMAIL.lower().strip()
        existing_admin = db.query(User).filter(User.email == admin_email).first()

        if existing_admin:
            print(f"[*] Admin account already exists: {existing_admin.email} (Role: {existing_admin.role.value})")
            if existing_admin.role != UserRole.ADMIN:
                print(f"[*] Upgrading account {existing_admin.email} to ADMIN role...")
                existing_admin.role = UserRole.ADMIN
                db.commit()
            return

        print(f"[*] Creating initial administrator account: {admin_email}")
        new_admin = User(
            full_name=settings.ADMIN_NAME,
            email=admin_email,
            hashed_password=get_password_hash(settings.ADMIN_PASSWORD),
            role=UserRole.ADMIN,
            is_active=True,
        )
        db.add(new_admin)
        db.commit()
        db.refresh(new_admin)
        print(f"[+] Administrator account created successfully with ID: {new_admin.id}")
        print(f"[+] Login at /api/auth/login or via the Admin Login screen using: {admin_email}")

    except Exception as e:
        print(f"[-] Error seeding administrator: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_admin()
