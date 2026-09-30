FROM python:3.12-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends poppler-utils tesseract-ocr tesseract-ocr-deu fonts-dejavu-core \
 && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir reportlab==4.4.3 Pillow==11.3.0
WORKDIR /app
COPY data/ /app/data/
COPY scripts/ /app/scripts/
RUN python /app/scripts/build_fixtures.py
COPY src/ /app/src/
ENV PYTHONPATH=/app/src
CMD ["python", "-m", "ch31_lab.server"]
