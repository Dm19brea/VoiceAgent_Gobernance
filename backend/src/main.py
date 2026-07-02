from fastapi import FastAPI

from src.adapters.rest.routes import router

app = FastAPI(title="Governance Platform")
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
