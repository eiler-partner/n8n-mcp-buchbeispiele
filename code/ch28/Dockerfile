FROM python:3.12-slim
WORKDIR /lab
COPY data /lab/data
COPY src /lab/src
ENV PYTHONPATH=/lab/src PYTHONDONTWRITEBYTECODE=1
EXPOSE 8128
CMD ["python", "-m", "ch28_lab.cli", "serve", "--host", "0.0.0.0"]
