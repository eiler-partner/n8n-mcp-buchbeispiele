FROM python:3.12-slim
RUN pip install --no-cache-dir 'psycopg[binary]==3.2.6'
WORKDIR /lab
COPY lab.py server.py mcp_stdio.py ./
COPY data/ ./data/
CMD ["python", "server.py"]
