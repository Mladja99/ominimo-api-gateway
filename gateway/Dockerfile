FROM python:3.11-slim

# Fast, clean Python
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VERSION=1.8.3

WORKDIR /app

# Minimal system deps (for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
RUN pip install --no-cache-dir "poetry==$POETRY_VERSION"

# Copy only dependency files first for better caching
# (poetry.lock is optional; the wildcard won't fail if it's missing)
COPY pyproject.toml poetry.lock* /app/

# Install deps into the system site-packages (no virtualenv inside container)
RUN poetry config virtualenvs.create false \
    && poetry install --no-interaction --no-ansi --only main

# Now copy the whole repo so /app/gateway exists (package root)
COPY . /app

# Ensure runtime dirs (will also be bind-mounted by compose)
RUN mkdir -p /app/logs /app/config

EXPOSE 8000

# Health check hits your FastAPI /health route
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/health || exit 1

# Run with the full package path (same as local)
CMD ["uvicorn", "gateway.app.main:app", "--host", "0.0.0.0", "--port", "8000"]