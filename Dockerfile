# TalkBack: one container serves the website and the voice backend.
# Built by Render (render.yaml) or locally: docker build -t talkback .

# 1. Build the website.
FROM node:24-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json frontend/.npmrc ./
RUN npm ci
COPY frontend/ ./
# The replay mode bundles the shared demo fixture.
COPY docs/fixtures /app/docs/fixtures
RUN npm run build

# 2. Run the backend, serving the built website.
FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/skills ./skills
COPY --from=web /app/frontend/dist /app/frontend/dist
ENV FRONTEND_DIST=/app/frontend/dist
# Run as a normal user, not root.
RUN useradd --create-home talkback && mkdir -p data && chown talkback data
USER talkback
# Render sets PORT. --proxy-headers so per-visitor limits see the real IP,
# not Render's proxy (SECURITY.md T8).
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --ws-max-size 65536 --proxy-headers --forwarded-allow-ips='*'"]
