# --- Build stage ---
FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml README.md ./
COPY apps/ apps/
COPY services/ services/
COPY domain/ domain/
COPY policies/ policies/
COPY database/ database/
COPY scripts/ scripts/
COPY tests/ tests/
COPY alembic.ini .

RUN pip install --no-cache-dir --upgrade pip hatchling \
    && pip install --no-cache-dir .[dev]

# --- Production stage ---
FROM python:3.12-slim AS production

# Security: non-root user
RUN groupadd -r mercury && useradd -r -g mercury -d /app -s /sbin/nologin mercury

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code & tests
COPY apps/ apps/
COPY services/ services/
COPY domain/ domain/
COPY policies/ policies/
COPY database/ database/
COPY scripts/ scripts/
COPY tests/ tests/
COPY alembic.ini .

RUN chown -R mercury:mercury /app

# Ensure non-root
USER mercury

EXPOSE 8000

CMD ["uvicorn", "apps.api.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
