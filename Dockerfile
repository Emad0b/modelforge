FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml .
COPY src ./src
COPY configs ./configs
RUN pip install --no-cache-dir .
COPY scripts ./scripts
ENV MODELFORGE_PROJECT_ROOT=/app MODELFORGE_HOME=/runtime
CMD ["uvicorn","modelforge.serving.main:app","--host","0.0.0.0","--port","8100"]
