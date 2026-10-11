# payment-processor-sim image (docs/07 §1): slim, non-root, uv-installed.
FROM python:3.11-slim

# uv is copied from its official distroless image (pinned) — no network install step.
COPY --from=ghcr.io/astral-sh/uv:0.5.4 /uv /uvx /bin/

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy the workspace manifests + the shared lib and this service, then sync. The
# service is a uv workspace member depending on acip-common by workspace path.
COPY pyproject.toml uv.lock ./
COPY libs/acip-common ./libs/acip-common
COPY services/payment-processor-sim ./services/payment-processor-sim

RUN uv sync --frozen --no-dev --package payment-processor-sim

# Drop privileges: run as a non-root user (docs/07 §1).
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8000
CMD ["uvicorn", "payment_processor_sim.main:app", "--host", "0.0.0.0", "--port", "8000"]
