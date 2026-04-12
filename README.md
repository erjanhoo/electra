# Electra Backend (Django)

Production-ready Django backend with Docker support for Railway deployment.

## Railway Deploy Notes

This backend is configured to run in Docker using `gunicorn` and automatic migrations on startup.

### Required Environment Variables

- `DJANGO_SECRET_KEY`: strong secret key for production.
- `DJANGO_DEBUG`: use `False` in production.
- `DJANGO_ALLOWED_HOSTS`: comma-separated hosts, for example:
  - `your-service.up.railway.app,127.0.0.1,localhost`
- `CORS_ALLOWED_ORIGINS`: comma-separated frontend origins, for example:
  - `https://your-frontend-domain.com`
- `CSRF_TRUSTED_ORIGINS`: comma-separated trusted origins, for example:
  - `https://your-frontend-domain.com,https://your-service.up.railway.app`
- `DATABASE_URL`: Railway Postgres connection string.

Optional:

- `ELECTRA_ADMIN_EMAILS`: comma-separated admin emails.
- `ELECTRA_BOOTSTRAP_ADMIN_EMAIL`: admin email to auto-create/update on startup.
- `ELECTRA_BOOTSTRAP_ADMIN_PASSWORD`: password for bootstrap admin (required with email).
- `ELECTRA_BOOTSTRAP_ADMIN_FIRST_NAME`: optional first name.
- `ELECTRA_BOOTSTRAP_ADMIN_LAST_NAME`: optional last name.
- `ELECTRA_BOOTSTRAP_ADMIN_RESET_PASSWORD`: set to `true` if you want password reset on every deploy.

## Docker Behavior

On container start, the app runs:

1. `python manage.py migrate`
2. `python manage.py bootstrap_admin`
3. `gunicorn electra_api.wsgi:application --bind 0.0.0.0:${PORT:-8000}`

Static files are collected during image build.
