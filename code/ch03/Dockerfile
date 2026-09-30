FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY api.py validate_response.py *.json ./
RUN mkdir /data
ENV DATA_DIR=/data HOST=0.0.0.0 PORT=8080
EXPOSE 8080
HEALTHCHECK --interval=10s --timeout=3s --start-period=3s \
  CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8080/health', timeout=2)" || exit 1
CMD ["python", "api.py"]
