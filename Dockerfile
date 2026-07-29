FROM node:22-bookworm-slim AS frontend-build

WORKDIR /frontend
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html tsconfig.json vite.config.ts postcss.config.js tailwind.config.js ./
COPY src ./src
COPY public ./public
RUN npm run build

FROM python:3.11-slim AS runtime

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DEFAULT_TIMEOUT=180 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
    set -eux; \
    apt-get -o Acquire::Retries=8 -o Acquire::http::Timeout=120 update; \
    installed=0; \
    for attempt in 1 2 3; do \
      if apt-get -o Acquire::Retries=8 -o Acquire::http::Timeout=120 install -y --no-install-recommends \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libcairo2 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
        ffmpeg \
        tesseract-ocr \
        tesseract-ocr-eng; then \
        installed=1; \
        break; \
      fi; \
      sleep $((attempt * 5)); \
    done; \
    test "$installed" = 1

COPY requirements.txt requirements-production.txt ./
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --retries=8 -r requirements-production.txt
COPY . .
COPY --from=frontend-build /frontend/dist ./dist
RUN mkdir -p /data /app/output

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:8000/live', timeout=3)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
