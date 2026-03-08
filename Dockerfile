FROM python:3.10-slim

WORKDIR /app

# System dependencies for asyncpg and lxml
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc g++ \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY pyproject.toml .
RUN pip install --no-cache-dir . 2>/dev/null || pip install --no-cache-dir -e .

# Copy application code
COPY src/ src/
COPY scripts/ scripts/

EXPOSE 8000

CMD ["uvicorn", "avukat.web.app:create_app", "--host", "0.0.0.0", "--port", "8000", "--factory"]
