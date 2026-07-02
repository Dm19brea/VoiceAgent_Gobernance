from fastapi import FastAPI

from src.adapters.rest.routes import router
from src.adapters.rest.vapi import router as vapi_router
from src.infrastructure.logging_config import configure_logging

configure_logging()

app = FastAPI(title="Governance Platform")
app.include_router(router)
app.include_router(vapi_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
