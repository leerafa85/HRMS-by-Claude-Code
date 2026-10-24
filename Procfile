release: python manage.py migrate --noinput && python manage.py inicializar
web: gunicorn config.wsgi --bind 0.0.0.0:${PORT:-8000} --workers 3 --timeout 60
