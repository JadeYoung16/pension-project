# syntax=docker/dockerfile:1

# ===== Base image =====
# python:3.11-slim is a minimal Debian-based image with Python 3.11 pre-installed.
# "slim" = no build tools or extras (~150MB vs ~1GB for full image).
# We add only what we need on top.
FROM python:3.11-slim

# ===== Environment variables =====
# PYTHONDONTWRITEBYTECODE: don't write .pyc files inside the container
# PYTHONUNBUFFERED: print() and logs flush immediately (important for Docker logs)
# PIP_NO_CACHE_DIR: don't cache pip downloads (smaller image)
# PIP_DISABLE_PIP_VERSION_CHECK: skip the "new pip version available" message on every install
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# ===== System packages =====
# build-essential: gcc/g++ etc., needed if any Python package compiles C extensions
# libpq-dev: PostgreSQL client library headers (needed to install psycopg2 from source)
# postgresql-client: provides `psql` CLI inside the container, useful for debugging
# curl: handy for healthchecks and ad-hoc downloads
# We clean apt lists at the end to keep the image small.
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        postgresql-client \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# ===== Working directory =====
# All subsequent commands run from /app inside the container.
# Our project will be mounted here at runtime via docker-compose.
WORKDIR /app

# ===== Python dependencies =====
# Copy requirements.txt FIRST (before code) so Docker caches this layer.
# If only code changes (not requirements), pip install is skipped on rebuild.
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# ===== Default command =====
# When the container starts, drop into a bash shell by default.
# In docker-compose we'll override this with `tail -f /dev/null` so the container
# stays running idle, and we exec into it when we want to run scripts.
CMD ["bash"]
