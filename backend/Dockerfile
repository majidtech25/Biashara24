FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY alembic_migrations ./alembic_migrations
COPY app ./app

RUN useradd --create-home --uid 1000 biashara && chown -R biashara /app
USER biashara

EXPOSE 8000
# One process: the login limiter keeps its counts in memory, and start-up runs the
# database upgrade, which must not run twice at the same time.
# Proxy headers are trusted because only the Caddy container can reach this port.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
