FROM python:3.12-slim

RUN pip install --no-cache-dir uv==0.11.2
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY src ./src
RUN uv sync --frozen --no-dev

ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["uv", "run", "policy-mcp"]
