# DBPilot backend.
FROM python:3.11-slim

# psycopg's binary wheel needs no build toolchain; curl is for the healthcheck.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencies first, so a code change does not reinstall the world.
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

COPY . .

ENV PYTHONUNBUFFERED=1 PORT=8000
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

# run.py, not `uvicorn app.main:app`: it sets the event loop policy psycopg 3
# needs before uvicorn can build its own loop. See README.
CMD ["sh", "-c", "python -m alembic upgrade head && python run.py --host 0.0.0.0 --port ${PORT}"]
