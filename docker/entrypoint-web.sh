#!/bin/sh
# Web container start-up: prepare the database, static files and RAG index, then serve.
set -e

echo "==> Applying database migrations"
python manage.py migrate --noinput

echo "==> Collecting static files"
python manage.py collectstatic --noinput

echo "==> Building the first-aid RAG index (the model downloads once into the volume)"
python manage.py build_firstaid_index

echo "==> Starting gunicorn on :8000"
exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 2 --timeout 60 --access-logfile -
