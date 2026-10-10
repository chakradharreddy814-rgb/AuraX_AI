# ---- AuraX AI Backend ----
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Run as non-root
RUN useradd --create-home appuser
USER appuser

EXPOSE 5000

# Gunicorn via the checked-in config (120s timeout for slow Gemini calls)
CMD ["gunicorn", "-c", "gunicorn_config.py", "app:app"]
