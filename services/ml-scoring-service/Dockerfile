# ml-scoring-service image (docs/07 §1): slim, non-root, uv-installed.
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# LightGBM needs libgomp at runtime.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock ./
COPY libs/acip-common ./libs/acip-common
COPY services/ml-scoring-service ./services/ml-scoring-service

RUN uv sync --frozen --no-dev --package ml-scoring-service

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV PATH="/app/.venv/bin:${PATH}"
# Compose mounts ml/models read-only here (FEAT-004); the loader resolves artifacts
# via <ML_MODELS_DIR>/model_card.json. Absent artifacts -> heuristic (docs/05 §5).
ENV ML_MODELS_DIR=/app/ml/models

EXPOSE 8000
CMD ["uvicorn", "ml_scoring_service.main:app", "--host", "0.0.0.0", "--port", "8000"]
