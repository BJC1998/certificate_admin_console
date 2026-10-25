from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.routers.health import router as health_router
from app.routers.certificates import router as certificates_router
from app.routers.tenants import router as tenants_router
from app.routers.courses import router as courses_router

app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-Tenant-ID"],
)
app.include_router(health_router)
app.include_router(tenants_router)
app.include_router(certificates_router)
app.include_router(courses_router)
