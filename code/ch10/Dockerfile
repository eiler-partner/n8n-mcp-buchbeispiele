FROM python:3.12.11-slim
WORKDIR /app
COPY contract.py service.py ./
RUN groupadd --system lab && useradd --system --gid lab lab && mkdir /data && chown lab:lab /data
USER lab
CMD ["python", "service.py"]
