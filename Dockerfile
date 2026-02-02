# Multi-stage build for production-ready FastAPI application
# Stage 1: Builder - Install dependencies
FROM python:3.11-slim AS builder

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

WORKDIR /app

COPY pyproject.toml ./
COPY uv.lock* ./


# Using --system to install globally, compatible with multi-stage build
RUN uv pip install --system --no-cache -e .

FROM python:3.11-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 appuser && \
    mkdir -p /app /app/logs && \
    chown -R appuser:appuser /app

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# ----------------------------
# IMPORTANT: Layer ordering
# ----------------------------
# We intentionally run heavy, rarely-changing steps (model pre-download) BEFORE copying frequently-changing code (src/).
# Otherwise, any code change would invalidate the cache and re-download models every build.

# Only copy what's needed for preloading models (keeps the model layer cache stable)
COPY --chown=appuser:appuser scripts/setup/preload_models.py ./scripts/setup/preload_models.py
# preload_models.py reads config/settings.yaml, so copy it (not the whole config/) before preloading
COPY --chown=appuser:appuser config/settings.yaml ./config/settings.yaml

# Pre-download ML models during build (optional, skip in CI to save time/space)
# Set PRELOAD_MODELS=false to skip model download (useful for CI builds)
# Models will be downloaded on first use if not pre-loaded
ARG PRELOAD_MODELS=true
RUN if [ "$PRELOAD_MODELS" = "true" ]; then \
      echo "📥 Pre-downloading models..." && \
      mkdir -p /app/.cache/huggingface && \
      python scripts/setup/preload_models.py || echo "⚠️  Model pre-download failed, will download on first use" && \
      chown -R appuser:appuser /app/.cache; \
    else \
      echo "⏭️  Skipping model pre-download (PRELOAD_MODELS=false)" && \
      mkdir -p /app/.cache/huggingface && \
      chown -R appuser:appuser /app/.cache; \
    fi

# Copy application code LAST (changes often; should not invalidate model cache)
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser config/ ./config/
COPY --chown=appuser:appuser pyproject.toml ./

ENV HF_HOME=/app/.cache/huggingface
ENV TRANSFORMERS_CACHE=/app/.cache/huggingface
ENV HF_HUB_CACHE=/app/.cache/huggingface

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["sh", "-c", "uvicorn src.api.main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-1}"]

