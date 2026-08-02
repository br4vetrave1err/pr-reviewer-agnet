# PR Review Agent image — REQ-CN-002 toolchain: Python 3.11+, FastAPI, git,
# gitleaks, and the opencode CLI (npm-installed). Vendored skills (REQ-CN-003)
# are copied into the image under /app/.agents/skills/.

FROM node:22-bookworm-slim AS opencode-cli
RUN npm install -g opencode-ai

FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

# Toolchain: git + gitleaks (REQ-CN-002)
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates curl \
    && GITLEAKS_VERSION=$(curl -s https://api.github.com/repos/gitleaks/gitleaks/releases/latest | grep '"tag_name"' | sed -E 's/.*"v?([0-9.]+)".*/\1/') \
    && curl -sSL -o /usr/local/bin/gitleaks "https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}/gitleaks_${GITLEAKS_VERSION}_linux_x64.tar.gz" \
    && tar -xzf /usr/local/bin/gitleaks -C /usr/local/bin gitleaks \
    && chmod +x /usr/local/bin/gitleaks \
    && apt-get purge -y curl && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# opencode CLI (REQ-CN-002, npm-installed)
COPY --from=opencode-cli /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=opencode-cli /usr/local/bin/opencode /usr/local/bin/opencode
RUN npm_config_prefix=/usr/local npm link opencode-ai --prefix /usr/local >/dev/null 2>&1 || true

WORKDIR /app

# Application code
COPY pyproject.toml ./
COPY src ./src

# Vendored agent skills (REQ-CN-003)
COPY .agents/skills/ ./.agents/skills/

# Config: example shipped; real config.yaml + .env are mounted at runtime
COPY config.yaml.example ./config.yaml.example

RUN pip install --no-cache-dir -e .

EXPOSE 8080

# Entrypoint builds opencode auth.json from OPENCODE_GO_TOKEN at boot
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
CMD ["uvicorn", "webhook.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8080"]
