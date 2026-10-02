FROM python:3.12-slim
WORKDIR /app
COPY requirements.lock pyproject.toml README.md LICENSE THIRD_PARTY_NOTICES.md ./
RUN pip install --no-cache-dir --require-hashes -r requirements.lock
COPY src ./src
RUN pip install --no-cache-dir --no-deps . \
    && useradd --uid 10001 --create-home agentdms \
    && mkdir /data && chown agentdms:agentdms /data
USER 10001:10001
VOLUME ["/data"]
EXPOSE 8765
ENTRYPOINT ["agent-dms"]
CMD ["serve", "--data-dir", "/data/state", "--host", "0.0.0.0", "--allow-remote", "--allowed-host", "127.0.0.1:8765", "--allowed-host", "localhost:8765"]
