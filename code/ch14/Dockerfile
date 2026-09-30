FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/src

WORKDIR /app
RUN pip install --no-cache-dir uv==0.11.2
COPY pyproject.toml uv.lock ./
COPY src ./src
COPY tests ./tests
COPY traces ./traces
RUN uv sync --frozen --dev

USER 65532:65532
CMD ["/app/.venv/bin/python", "-m", "pytest", "-p", "no:cacheprovider", "tests", "-q"]
