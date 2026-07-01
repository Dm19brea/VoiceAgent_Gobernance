from fastapi import FastAPI

app = FastAPI(title="Governance Platform")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
