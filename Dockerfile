# syntax=docker/dockerfile:1

# =========================
# 1. Frontend build (Vite)
# =========================
FROM node:20-bookworm-slim AS frontend-build
WORKDIR /frontend

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ ./

# Cloud Run same-origin API
ENV VITE_API_BASE_URL=""
RUN npm run build


# =========================
# 2. Backend runtime
# =========================
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# install dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# copy backend code
COPY backend/ ./backend/

# copy frontend build to backend static
COPY --from=frontend-build /frontend/dist ./backend/static

# important: correct module path
WORKDIR /app/backend

EXPOSE 8080

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
