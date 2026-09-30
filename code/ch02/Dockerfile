FROM python:3.12-slim
WORKDIR /lab
COPY architecture.json validate.py ./
COPY tests/ ./tests/
CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
