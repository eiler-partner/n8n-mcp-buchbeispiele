FROM python:3.12.11-slim
WORKDIR /app
COPY analyzer.py /app/analyzer.py
COPY fixtures/ /app/fixtures/
EXPOSE 8055
CMD ["python", "/app/analyzer.py"]
