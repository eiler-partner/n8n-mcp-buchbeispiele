FROM python:3.12-alpine
WORKDIR /lab
COPY policy.py server.py ./
RUN mkdir /data && chown 65532:65532 /data
USER 65532:65532
EXPOSE 8141
CMD ["python", "server.py"]
