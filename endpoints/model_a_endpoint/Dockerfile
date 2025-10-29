FROM python:3.11-slim AS base
ENV POETRY_HOME="/opt/poetry" \
    POETRY_VERSION="1.8.3" \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_IN_PROJECT=true

# System deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends git openssh-client curl && \
    rm -rf /var/lib/apt/lists/*

RUN mkdir -p -m 0755 /etc/ssh && \
    ssh-keyscan -t rsa,ecdsa,ed25519 github.com >> /etc/ssh/ssh_known_hosts

# Poetry
RUN curl -sSL https://install.python-poetry.org | python3 - --version ${POETRY_VERSION} && \
    ln -s ${POETRY_HOME}/bin/poetry /usr/local/bin/poetry

WORKDIR /app

# Copy deps first for caching
COPY pyproject.toml ./
ENV POETRY_VIRTUALENVS_IN_PROJECT=true

# Install deps
RUN --mount=type=ssh poetry install --no-interaction --no-ansi --only main

# App code
COPY main.py ./main.py

# Create log dir
RUN mkdir -p /app/logs

# Expose and healthcheck
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
  CMD curl -f http://localhost:8001/health || exit 1

# Activate the Poetry venv on PATH so uvicorn is found
ENV PATH="/app/.venv/bin:${PATH}"

# Run the app
CMD ["uvicorn","main:app","--host","0.0.0.0","--port","8001"]
