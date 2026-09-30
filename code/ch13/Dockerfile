FROM python:3.12-slim

WORKDIR /app
COPY api.py /app/api.py
USER 65532:65532
EXPOSE 8080
CMD ["python", "api.py"]
