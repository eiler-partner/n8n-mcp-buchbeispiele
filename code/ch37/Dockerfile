FROM python:3.12-slim
WORKDIR /lab
COPY decide.py server.py mcp_stdio.py ./
COPY data/ ./data/
CMD ["python", "server.py"]
