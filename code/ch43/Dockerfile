FROM python:3.12-slim
WORKDIR /lab
COPY core.py mcp_stdio.py server.py ./
COPY data/ ./data/
CMD ["python", "server.py"]
