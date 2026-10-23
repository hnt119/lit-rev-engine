# Official multi-architecture manifests resolved 2026-10-23. No model downloads.
FROM node:24.19.0-bookworm-slim@sha256:a9f5f7c91a432850b2a8a7797adf5eadb6c733ceed61167806cee7ea7fbc29df AS web-build
ENV NEXT_TELEMETRY_DISABLED=1
RUN npm install --global pnpm@10.20.0
WORKDIR /app/apps/web
COPY apps/web/package.json apps/web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY apps/web/ ./
COPY apps/streamlit/theme/tokens.css /app/apps/streamlit/theme/tokens.css
RUN pnpm build && pnpm prune --prod

FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c AS python-build
WORKDIR /build
COPY requirements-hosted.txt requirements-web-lock.txt ./
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --no-cache-dir -r requirements-hosted.txt

FROM python:3.12.12-slim-bookworm@sha256:593bd06efe90efa80dc4eee3948be7c0fde4134606dd40d8dd8dbcade98e669c AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 NEXT_TELEMETRY_DISABLED=1 NODE_ENV=production \
    MVP_DEPLOYMENT_MODE=hosted MVP_PERSISTENT_ROOT=/var/data MVP_WEB_DATA_DIR=/var/data/litrev \
    MVP_API_HOST=127.0.0.1:8765 MVP_API_ORIGIN=http://127.0.0.1:8765 PORT=10000 \
    MVP_MAP_ENABLED=0 MVP_PROPOSALS_ENABLED=0 MVP_SEARCH_PLANNER_ENABLED=0 PATH=/opt/venv/bin:$PATH
COPY --from=python-build /opt/venv /opt/venv
COPY --from=web-build /usr/local/bin/node /usr/local/bin/node
COPY --from=web-build /usr/lib/*/libstdc++.so.6* /usr/local/lib/
COPY --from=web-build /usr/lib/*/libgcc_s.so.1 /usr/local/lib/
WORKDIR /app
COPY src/ ./src/
COPY scripts/run_hosted.py scripts/hosted_backup.py ./scripts/
COPY examples/mvp/offline_microbiome_30_v1/ ./examples/mvp/offline_microbiome_30_v1/
COPY --from=web-build /app/apps/web/.next ./apps/web/.next
COPY --from=web-build /app/apps/web/node_modules ./apps/web/node_modules
COPY --from=web-build /app/apps/web/package.json /app/apps/web/next.config.ts ./apps/web/
COPY apps/streamlit/theme/tokens.css ./apps/streamlit/theme/tokens.css
RUN groupadd --gid 10001 litrev \
    && useradd --uid 10001 --gid 10001 --create-home --home-dir /home/litrev --shell /bin/sh litrev \
    && chmod 0700 /home/litrev \
    && install -d -o litrev -g litrev -m 0700 /home/litrev/.ssh \
    && mkdir -p /var/data && chown litrev:litrev /var/data
USER 10001:10001
EXPOSE 10000
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/readyz', timeout=3)" || exit 1
ENTRYPOINT ["python", "scripts/run_hosted.py"]
