# ============================================================
# SCDRRMO FMSWGIS — Django Application Dockerfile
# Base: python:3.12-slim (Debian Bookworm) for minimal size
# ============================================================

FROM python:3.12-slim

# -------------------------------------------------------
# Build arguments (override at build time if needed)
# -------------------------------------------------------
ARG APP_HOME=/app

# -------------------------------------------------------
# Environment variables
# -------------------------------------------------------
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# -------------------------------------------------------
# System dependencies
# GDAL + GEOS: required by GeoDjango for spatial queries
# libpango + libcairo: required by WeasyPrint for PDF generation
# postgresql-client: used by entrypoint.sh DB health check
# -------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    # GeoDjango GIS libraries
    libgdal-dev \
    libgeos-dev \
    # PDF generation (WeasyPrint)
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libcairo2-dev \
    pkg-config \
    # Font support for PDFs
    fonts-liberation \
    # PostgreSQL client (for DB readiness check)
    postgresql-client \
    # Build tools (needed to compile some pip packages)
    gcc \
    && rm -rf /var/lib/apt/lists/*

# -------------------------------------------------------
# Create a non-root user for security
# Running as root inside a container is a security risk
# -------------------------------------------------------
RUN useradd --no-create-home --shell /bin/false appuser

# -------------------------------------------------------
# Set working directory
# -------------------------------------------------------
WORKDIR ${APP_HOME}

# -------------------------------------------------------
# Install Python dependencies first (Docker layer caching:
# if requirements.txt hasn't changed, this layer is reused)
# -------------------------------------------------------
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# -------------------------------------------------------
# Copy project source code
# -------------------------------------------------------
COPY . .

# -------------------------------------------------------
# Create necessary directories and set permissions
# -------------------------------------------------------
RUN mkdir -p staticfiles media logs \
    && chown -R appuser:appuser ${APP_HOME}

# -------------------------------------------------------
# Make entrypoint executable
# -------------------------------------------------------
RUN chmod +x entrypoint.sh

# -------------------------------------------------------
# Switch to non-root user
# -------------------------------------------------------
USER appuser

# -------------------------------------------------------
# Expose port (Gunicorn listens on 8000 inside container)
# -------------------------------------------------------
EXPOSE 8000

# -------------------------------------------------------
# Startup command
# -------------------------------------------------------
ENTRYPOINT ["./entrypoint.sh"]
