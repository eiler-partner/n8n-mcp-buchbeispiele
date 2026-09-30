FROM n8nio/runners:2.40.7
USER root
RUN uv pip install --python /opt/runners/task-runner-python/.venv/bin/python pandas==3.0.6
COPY runner-config.json /etc/n8n-task-runners.json
USER runner
