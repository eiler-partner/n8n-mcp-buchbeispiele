FROM python:3.12-slim
WORKDIR /lab
COPY data /lab/data
COPY src /lab/src
ENV PYTHONPATH=/lab/src PYTHONDONTWRITEBYTECODE=1
EXPOSE 8125
CMD ["python", "-m", "ch25_lab.cli", "serve"]
