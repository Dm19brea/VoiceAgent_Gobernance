from src.infrastructure.celery.app import celery_app, ping


def test_ping_task_runs_eagerly() -> None:
    celery_app.conf.task_always_eager = True

    result = ping.delay()

    assert result.get() == "pong"
