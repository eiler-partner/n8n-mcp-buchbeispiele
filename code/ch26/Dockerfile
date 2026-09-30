FROM python:3.12-slim
WORKDIR /lab
COPY requirements.txt /lab/requirements.txt
RUN pip install --no-cache-dir -r /lab/requirements.txt
COPY data /lab/data
COPY prompts /lab/prompts
COPY src /lab/src
ENV PYTHONPATH=/lab/src PYTHONDONTWRITEBYTECODE=1
EXPOSE 8126
CMD ["python", "-m", "ch26_lab.cli", "serve"]
