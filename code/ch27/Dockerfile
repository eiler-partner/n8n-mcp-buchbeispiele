FROM python:3.12-slim
WORKDIR /lab
COPY src /lab/src
ENV PYTHONPATH=/lab/src PYTHONDONTWRITEBYTECODE=1 CH27_DB=/data/ch27.sqlite
EXPOSE 8127
CMD ["python", "-m", "ch27_lab.server", "--host", "0.0.0.0"]
