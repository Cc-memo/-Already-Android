#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   REPO_URL=git@github.com:OWNER/REPO.git \
#   BRANCH=dev \
#   TARGET_DIR=/opt/hotel-crawler \
#   bash deploy.sh

REPO_URL="${REPO_URL:-git@github.com:OWNER/REPO.git}"
BRANCH="${BRANCH:-dev}"
TARGET_DIR="${TARGET_DIR:-/opt/hotel-crawler}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.yml}"

if ! command -v git >/dev/null 2>&1; then
  echo "git not found; install it first." >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker not found; install it first." >&2
  exit 1
fi

if [ ! -d "$TARGET_DIR/.git" ]; then
  mkdir -p "$TARGET_DIR"
  git clone -b "$BRANCH" "$REPO_URL" "$TARGET_DIR"
else
  git -C "$TARGET_DIR" fetch origin
  git -C "$TARGET_DIR" checkout "$BRANCH"
  git -C "$TARGET_DIR" pull --ff-only origin "$BRANCH"
fi

cd "$TARGET_DIR"

if [ ! -f .env ] && [ -f .env.example ]; then
  cp .env.example .env
fi

if docker compose version >/dev/null 2>&1; then
  docker compose -f "$COMPOSE_FILE" up -d --build
else
  docker-compose -f "$COMPOSE_FILE" up -d --build
fi

echo "Deploy complete."
