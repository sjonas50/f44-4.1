FROM python:3.11-slim AS base

WORKDIR /app

# Install uv for fast dependency management
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY src/ src/

# Layer 1: Trust & Identity
FROM base AS layer1
EXPOSE 8001
CMD ["uv", "run", "uvicorn", "src.layer1.app:app", "--host", "0.0.0.0", "--port", "8001"]

# Layer 3: Provenance
FROM base AS layer3
EXPOSE 8003
CMD ["uv", "run", "uvicorn", "src.layer3.app:app", "--host", "0.0.0.0", "--port", "8003"]

# Behavioral Analysis Worker
FROM base AS behavioral-worker
CMD ["uv", "run", "python", "-m", "src.layer1.behavioral.consumer"]
