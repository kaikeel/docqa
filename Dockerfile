# Kaikeel DocQA: API + sample widget. Build: docker build -t docqa .

# --- build stage: uv resolves the locked dependencies into /app/.venv -----------------
FROM python:3.12-slim AS build

# uv pinned to the same version that wrote uv.lock. It stays in this stage only.
COPY --from=ghcr.io/astral-sh/uv:0.6.3 /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1

WORKDIR /app

# Dependencies first (cached layer), then the project itself (installed, not editable).
COPY pyproject.toml uv.lock README.md LICENSE.md ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev --no-editable

# --- runtime stage: Python, the virtual environment and the sample documents ----------
FROM python:3.12-slim

RUN useradd --create-home --uid 10001 docqa && mkdir -p /data && chown docqa:docqa /data

WORKDIR /app
COPY --from=build /app/.venv /app/.venv
# Sample documents for the demo; the index lives in /data (mount a volume to keep it).
COPY examples ./examples

# DOCQA_DB must stay in /data: /app belongs to root and is read-only for the docqa user.
ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    DOCQA_DB=/data/docqa.db \
    DOCQA_INGEST_ROOT=/app

USER docqa
EXPOSE 8000
# ANTHROPIC_API_KEY is passed at runtime (-e or --env-file), never baked into the image.
CMD ["uvicorn", "docqa.api:app", "--host", "0.0.0.0", "--port", "8000"]
