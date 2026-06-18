FROM python:3.12-slim

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js for MJML compilation at build time
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies first (layer cache)
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install MJML for email template compilation
RUN npm install -g mjml

# Copy application code
COPY backend/ .

# Compile MJML templates to HTML at build time
RUN if [ -d "app/templates/mjml" ]; then \
        mkdir -p app/templates/compiled && \
        for f in app/templates/mjml/*.mjml; do \
            [ -f "$f" ] && mjml "$f" -o "app/templates/compiled/$(basename ${f%.mjml}.html)"; \
        done; \
    fi

# Create non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser
USER appuser

EXPOSE 8000

# Default: run the FastAPI API server
# Override CMD in docker-compose for celery worker / beat
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
