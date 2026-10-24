FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_DEBUG=False \
    DJANGO_MEDIA_ROOT=/data/media \
    PORT=8000

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN DJANGO_SECRET_KEY=build-only python manage.py collectstatic --noinput \
    && useradd --create-home hrms && mkdir -p /data/media && chown -R hrms /data /app
USER hrms
VOLUME ["/data"]
EXPOSE 8000
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py inicializar && gunicorn config.wsgi --bind 0.0.0.0:${PORT} --workers 3 --timeout 60"]
