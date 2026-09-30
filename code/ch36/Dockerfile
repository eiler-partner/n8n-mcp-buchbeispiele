FROM python:3.12-slim
WORKDIR /lab
COPY evaluate.py server.py mcp_stdio.py ./
COPY data/ ./data/
CMD ["python", "server.py"]
