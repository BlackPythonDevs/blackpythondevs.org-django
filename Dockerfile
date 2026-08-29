# syntax=docker/dockerfile:1

FROM python:3.14-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/usr/local

RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      libpq-dev \
      libjpeg-dev \
      zlib1g-dev \
      libwebp-dev \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app


# ── Development: includes dev dependencies, source is bind-mounted ────────
FROM base AS dev

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-install-project 2>/dev/null || uv sync --no-install-project

COPY . .

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]


# ── Production: runtime deps only, static collected, non-root ─────────────
FROM base AS production

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project 2>/dev/null || uv sync --no-dev --no-install-project

COPY . .

# collectstatic needs a settings module that imports cleanly without a database.
RUN SECRET_KEY=build-only DJANGO_SETTINGS_MODULE=bpd.settings.production \
    DATABASE_URL=postgres://build:build@localhost/build \
    python manage.py collectstatic --noinput --clear

RUN useradd --create-home --uid 1000 bpd && chown -R bpd:bpd /app
USER bpd

EXPOSE 8000
CMD ["gunicorn", "bpd.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--threads", "2", \
     "--timeout", "60", \
     "--access-logfile", "-"]
