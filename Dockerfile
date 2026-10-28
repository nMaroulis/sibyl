FROM node:22-bookworm-slim AS dashboard
WORKDIR /app
COPY package.json package-lock.json ./
COPY frontend/package.json frontend/package.json
COPY docs/package.json docs/package.json
RUN npm ci --no-audit --no-fund
COPY frontend frontend
RUN npm run build

FROM python:3.12-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src src
ARG SIBYL_EXTRAS=""
RUN uv sync --frozen --no-dev ${SIBYL_EXTRAS}
COPY --from=dashboard /app/frontend/dist frontend/dist
RUN useradd --create-home --uid 10001 sibyl && mkdir /data && chown sibyl:sibyl /data
USER sibyl
ENV SIBYL_HOST=0.0.0.0 SIBYL_DATA_DIR=/data PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=3)"
CMD ["sibyl"]
