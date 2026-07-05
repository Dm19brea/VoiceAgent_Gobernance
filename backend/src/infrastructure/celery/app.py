from celery import Celery

from src.infrastructure.config import settings

celery_app = Celery(
    "governance",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["src.infrastructure.celery.tasks"],
)


@celery_app.task(name="ping")
def ping() -> str:
    """Trivial task to prove the Celery + Redis wiring runs."""
    return "pong"
