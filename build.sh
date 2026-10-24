#!/usr/bin/env bash
# Script de build/arranque usado por Render y otros PaaS.
set -o errexit
pip install -r requirements.txt
python manage.py collectstatic --noinput
python manage.py migrate --noinput
python manage.py inicializar
