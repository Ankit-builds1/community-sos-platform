# One image for the web server, the Celery worker and Celery beat.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FASTEMBED_CACHE_PATH=/models

WORKDIR /app

# Install dependencies first: this layer is cached until requirements.txt changes
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Then the project code
COPY . .

# Run as a normal user, not root
RUN useradd --create-home app && mkdir -p /models && chown -R app:app /app /models
USER app

EXPOSE 8000
CMD ["sh", "docker/entrypoint-web.sh"]
