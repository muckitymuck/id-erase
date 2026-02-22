FROM python:3.11-slim AS base

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 erasure
WORKDIR /app

COPY pyproject.toml .
RUN pip install --no-cache-dir .

# Install Playwright browsers
RUN pip install playwright && playwright install chromium --with-deps

COPY src/ src/
COPY alembic.ini .

RUN chown -R erasure:erasure /app
USER erasure

ENV PYTHONPATH=/app/src
EXPOSE 8080

CMD ["uvicorn", "erasure_executor.main:app", "--host", "0.0.0.0", "--port", "8080"]
