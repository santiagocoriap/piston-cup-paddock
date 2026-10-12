# Stage 1: build the React frontend.
FROM node:24-alpine AS frontend
WORKDIR /app
RUN corepack enable
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY frontend/package.json frontend/
COPY e2e/package.json e2e/
RUN pnpm install --frozen-lockfile --filter @paddock/frontend
COPY frontend/ frontend/
RUN pnpm --filter @paddock/frontend build

# Stage 2: the Django app. The web and worker services both use this image.
FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:0.9.12 /uv /bin/uv
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    FRONTEND_DIST=/app/frontend-dist
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY backend/ ./
COPY --from=frontend /app/frontend/dist /app/frontend-dist
RUN DJANGO_SECRET_KEY=build-only POSTGRES_PASSWORD=build-only python manage.py collectstatic --noinput
RUN useradd --create-home paddock && mkdir -p /app/media && chown -R paddock /app
USER paddock
EXPOSE 8000
