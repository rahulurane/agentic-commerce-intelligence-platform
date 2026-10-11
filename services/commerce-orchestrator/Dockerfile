# commerce-orchestrator image (docs/07 §1): slim, non-root, uv-installed.
FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY libs/acip-common ./libs/acip-common
COPY services/commerce-orchestrator ./services/commerce-orchestrator

RUN uv sync --frozen --no-dev --package commerce-orchestrator

RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8000
CMD ["uvicorn", "commerce_orchestrator.main:app", "--host", "0.0.0.0", "--port", "8000"]
