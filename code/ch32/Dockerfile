FROM python:3.12-slim
WORKDIR /app
COPY data/ /app/data/
COPY src/ /app/src/
ENV PYTHONPATH=/app/src
CMD ["python", "-m", "ch32_lab.server"]
