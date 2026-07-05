FROM python:3.12-slim

# Bring in the uv binary from its official image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Make src importable (project uses package = false, so it is not installed)
ENV PYTHONPATH=/app

# Install dependencies first for better layer caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

# Copy application source and migration tooling
COPY src ./src
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

EXPOSE 8000

# Start the API server. Railway injects a dynamic $PORT; shell form is required
# so ${PORT} is expanded at runtime.
CMD uv run --no-dev uvicorn src.main:app --host 0.0.0.0 --port ${PORT:-8000}
