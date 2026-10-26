import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from app.core.config import settings

logger = logging.getLogger("database")

connect_args = {}
engine_kwargs = {
    "pool_pre_ping": True,  # Verifies connections before checkout (vital for cloud timeouts)
}

if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}
else:
    # Managed Cloud PostgreSQL (Neon, Supabase, AWS RDS)
    engine_kwargs["pool_recycle"] = 300  # Recycle connections every 5 minutes to prevent cloud disconnects

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    **engine_kwargs
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
