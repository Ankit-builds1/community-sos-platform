#!/bin/sh
# Web container start-up. Works for Docker Compose and for Render (single container).
set -e

echo "==> Applying database migrations"
python manage.py migrate --noinput

echo "==> Creating the database cache table (used when there is no Redis)"
python manage.py createcachetable

if [ ! -f firstaid/index/piece_to_doc.npy ]; then
  echo "==> Building the first-aid RAG index"
  python manage.py build_firstaid_index
fi

if [ "$DEMO_MODE" = "1" ]; then
  echo "==> Demo mode: making sure demo users and society exist"
  python manage.py seed_demo
fi

# Admin account from env vars (Render free has no shell for createsuperuser)
if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ]; then
  echo "==> Ensuring admin user exists"
  python manage.py createsuperuser --noinput 2>/dev/null || echo "    (admin already exists)"
fi

PORT="${PORT:-8000}"
WORKERS="${WEB_CONCURRENCY:-2}"
echo "==> Starting gunicorn on :$PORT ($WORKERS workers)"
exec gunicorn config.wsgi:application --bind "0.0.0.0:$PORT" --workers "$WORKERS" \
     --threads 4 --timeout 60 --access-logfile -
