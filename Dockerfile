# Python 3.11 base image
FROM python:3.11-slim

# System dependencies including Ghostscript
RUN apt-get update && apt-get install -y \
    ghostscript \
    && rm -rf /var/lib/apt/lists/*

# Working directory
WORKDIR /app

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Create temp directory
RUN mkdir -p /tmp/uploads /tmp/compressed

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD curl -f http://localhost:5000/health || exit 1

# Start command - OPTIMIZED FOR RENDER.COM FREE TIER
# Single worker, reduced timeout, memory efficient
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:5000", "--timeout", "120", "--workers", "2"] 