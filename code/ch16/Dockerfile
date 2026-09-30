FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/lab/src
WORKDIR /lab
RUN pip install --no-cache-dir uv==0.11.2
COPY pyproject.toml uv.lock ./
COPY src ./src
COPY tests ./tests
RUN uv sync --frozen --no-dev
USER 65532:65532
CMD ["/lab/.venv/bin/python", "-m", "mcp_transport_lab.verify"]
