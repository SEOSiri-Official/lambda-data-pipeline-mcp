#!/usr/bin/env bash
set -euo pipefail

if [ ! -f ".env" ]; then
  echo "ERROR: .env not found. Copy .env.example to .env and fill in real values first."
  exit 1
fi

echo "==> Building image from local working directory (Dockerfile.local)..."
docker build -f Dockerfile.local -t mcp-server-local .

echo "==> Running container with secrets from .env, port 8080 published to host..."
docker run -it --rm --env-file .env -p 8080:8080 mcp-server-local
