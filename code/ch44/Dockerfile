FROM python:3.12-slim
WORKDIR /lab
COPY pipeline.py source_io.py mcp_stdio.py server.py fixture_server.py ./
COPY data/ ./data/
CMD ["python", "server.py"]
