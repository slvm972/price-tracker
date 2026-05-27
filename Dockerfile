FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
WORKDIR /app

# Install runtime deps
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Copy project
COPY . /app

# Ensure entrypoint is executable
RUN chmod +x ./entrypoint.sh || true

# Use non-root user when possible
RUN useradd -m appuser || true
USER appuser

ENTRYPOINT ["/app/entrypoint.sh"]
