import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.core.config import settings
from app.core.database import engine, Base
from sqlalchemy import text


def test_cloud_database():
    print("\n" + "=" * 60)
    print("[1] TESTING DATABASE CONNECTION")
    print("=" * 60)
    print(f"Target Database URL: {settings.DATABASE_URL.split('@')[-1] if '@' in settings.DATABASE_URL else settings.DATABASE_URL}")

    start_time = time.time()
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT 1")).scalar()
            elapsed_ms = (time.time() - start_time) * 1000
            print(f"[+] Database connection successful! (Ping: {elapsed_ms:.1f}ms)")
            print(f"[+] Connected dialect: {engine.dialect.name}")

            # Ensure tables
            Base.metadata.create_all(bind=engine)
            print("[+] Verified all tables exist in database.")
    except Exception as e:
        print(f"[-] Database connection failed: {e}")
        return False
    return True


def test_cloud_storage():
    print("\n" + "=" * 60)
    print("[2] TESTING CLOUD OBJECT STORAGE")
    print("=" * 60)
    print(f"Storage Backend: {settings.STORAGE_BACKEND}")

    if settings.STORAGE_BACKEND != "s3" or not settings.S3_BUCKET_NAME:
        print("[*] Cloud S3/R2 storage is not currently active (running on local storage).")
        print("[*] To activate cloud storage, set STORAGE_BACKEND=s3 and S3_BUCKET_NAME in your .env")
        return True

    print(f"Target Bucket: {settings.S3_BUCKET_NAME}")
    print(f"Endpoint URL: {settings.S3_ENDPOINT_URL or 'AWS Default'}")

    try:
        from app.services.cloud_storage_service import CloudStorageService
        s3 = CloudStorageService._get_s3_client()

        test_key = "test_probe.txt"
        print(f"[*] Testing write operation to bucket '{settings.S3_BUCKET_NAME}'...")
        s3.put_object(
            Bucket=settings.S3_BUCKET_NAME,
            Key=test_key,
            Body=b"Cloud probe write test successful.",
            ContentType="text/plain",
        )
        print("[+] Write test succeeded!")

        print("[*] Generating presigned URL...")
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_BUCKET_NAME, "Key": test_key},
            ExpiresIn=300,
        )
        print(f"[+] Presigned URL generated: {url[:60]}...")

        print("[*] Cleaning up probe file...")
        s3.delete_object(Bucket=settings.S3_BUCKET_NAME, Key=test_key)
        print("[+] Cloud storage validation complete!")
    except Exception as e:
        print(f"[-] Cloud storage test failed: {e}")
        return False
    return True


if __name__ == "__main__":
    db_ok = test_cloud_database()
    storage_ok = test_cloud_storage()
    print("\n" + "=" * 60)
    if db_ok and storage_ok:
        print("[SUCCESS] All configured services are online and ready!")
    else:
        print("[NOTICE] Review connection issues above.")
    print("=" * 60)
