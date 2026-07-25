FROM debian:trixie-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl git \
    && curl -fsSL https://deb.nodesource.com/setup_26.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && npm install -g mcp-proxy@6.4.3 pnpm@10.14.0 \
    && curl -LsSf https://astral.sh/uv/install.sh | UV_INSTALL_DIR="/usr/local/bin" sh \
    && uv python install 3.13 --default --preview \
    && ln -s $(uv python find) /usr/local/bin/python \
    && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

WORKDIR /app

COPY . .

ENV PATH="/app/node_modules/.bin:$PATH"

RUN (uv pip install --system --break-system-packages -e .)

CMD ["mcp-proxy", "--", "uv", "run", "src/main_server.py"]
