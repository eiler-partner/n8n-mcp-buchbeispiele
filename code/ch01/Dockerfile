FROM python:3.12-slim

WORKDIR /app
COPY email_lab.py emails.json fixtures.json ./
COPY tests ./tests

CMD ["python", "-m", "unittest", "discover", "-s", "tests", "-v"]
