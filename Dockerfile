# One image for every host: Docker Compose (web / worker / beat) and Render (single container).
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

# Bake the embedding model + first-aid index into the image, so containers start fast
# and free hosts don't download ~250 MB on every wake-up. Needs no database or secrets.
RUN DJANGO_DEBUG=1 python manage.py build_firstaid_index \
 && DJANGO_DEBUG=1 python manage.py collectstatic --noinput
# Fine-tuned triage model (offline fallback) from the Hugging Face Hub, ~118 MB int8 ONNX.
# If the download fails the image still builds; the agent then falls back to rules.
RUN DJANGO_DEBUG=1 python manage.py triage_model pull || echo "triage model not downloaded"

# Run as a normal user, not root
RUN useradd --create-home app && mkdir -p /models && chown -R app:app /app /models
USER app

EXPOSE 8000
CMD ["sh", "docker/entrypoint-web.sh"]
