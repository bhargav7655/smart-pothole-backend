from app.routers.auth import router as auth_router
from app.routers.reports import router as reports_router
from app.routers.admin import router as admin_router

__all__ = ["auth_router", "reports_router", "admin_router"]
