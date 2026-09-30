FROM python:3.12-alpine
WORKDIR /lab
COPY core.py mcp_stdio.py server.py ./
EXPOSE 8140
CMD ["python", "server.py"]
