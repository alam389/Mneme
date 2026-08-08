from fastapi import FastAPI

from app.api.routes import router
from app.config import settings

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="A lightweight FastAPI scaffold for an ingestion pipeline.",
    debug=settings.debug,
)

app.include_router(router, prefix=settings.api_prefix)




@app.get("/")
def read_root() -> dict[str, str]:
    return {
        "message": "Mneme ingestion service is up",
        "environment": settings.environment,
        "app_name": settings.app_name,
    }
