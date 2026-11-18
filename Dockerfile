FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt requirements-aws.txt ./
# Set INSTALL_AWS=1 at build time to include boto3 for the Bedrock provider.
ARG INSTALL_AWS=0
RUN if [ "$INSTALL_AWS" = "1" ]; then pip install -r requirements-aws.txt; else pip install -r requirements.txt; fi

COPY incident_intel ./incident_intel
COPY frontend ./frontend

# Run as a non-root user; /app/data holds the SQLite history (mount a volume to keep it).
RUN useradd --create-home app && mkdir -p /app/data && chown -R app /app/data
USER app
ENV DATABASE_PATH=/app/data/incidents.db PORT=8000
EXPOSE 8000

# Shell form so $PORT (set by most hosting platforms) is honoured.
CMD gunicorn -w 2 -b 0.0.0.0:${PORT} "incident_intel.app:create_app()"
