from fastapi import FastAPI

from app.api.routes import router

app = FastAPI(
    title="Mneme Ingestion API",
    version="0.1.0",
    description="A lightweight FastAPI scaffold for an ingestion pipeline.",
)

app.include_router(router)


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "Mneme ingestion service is up"}
