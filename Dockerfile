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


# ── Production builder: compiles deps into a venv; never shipped ──────────
FROM base AS builder

ENV UV_PROJECT_ENVIRONMENT=/opt/venv

COPY pyproject.toml uv.lock* ./
RUN uv sync --frozen --no-dev --no-install-project 2>/dev/null || uv sync --no-dev --no-install-project


# ── Production: runtime only — no compilers, no uv, no apt lists ──────────
# psycopg[binary] and Pillow ship wheels with their own native libs, so the
# build toolchain from `base` is not needed at runtime.
FROM python:3.14-slim AS production

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home --uid 1000 bpd && mkdir /app && chown bpd:bpd /app

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=bpd:bpd . .

# collectstatic needs a settings module that imports cleanly without a database.
# Runs as bpd so STATIC_ROOT lands owned correctly without a recursive chown
# (which would duplicate every file in a new layer).
USER bpd
RUN SECRET_KEY=build-only DJANGO_SETTINGS_MODULE=bpd.settings.production \
    DATABASE_URL=postgres://build:build@localhost/build \
    python manage.py collectstatic --noinput --clear

EXPOSE 8000
CMD ["gunicorn", "bpd.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--threads", "2", \
     "--timeout", "60", \
     "--access-logfile", "-"]
