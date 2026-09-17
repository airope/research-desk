FROM python:3.12.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends bubblewrap \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv==0.11.2
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev
ENV PATH="/opt/venv/bin:$PATH"
COPY . .
RUN useradd --create-home --uid 10001 srr && python manage.py collectstatic --noinput
ENV APP_ENV=production
USER srr
EXPOSE 8000
CMD ["gunicorn", "srr.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2", "--access-logfile", "-"]
