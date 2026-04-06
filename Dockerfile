# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Install Node.js for the frontend build
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# --- Python deps ---
COPY pyproject.toml .
RUN pip install --no-cache-dir -e "."

# --- Frontend build ---
COPY frontend/package*.json ./frontend/
RUN cd frontend && npm ci --quiet

COPY frontend/ ./frontend/
RUN cd frontend && npm run build

# --- Backend source ---
COPY backend/ ./backend/
COPY main.py .

# Data directory (SQLite will be written here at runtime)
RUN mkdir -p data

EXPOSE 3000

CMD ["python", "main.py"]
