#!/usr/bin/env bash
#
# Serve this repo's Quartz site locally for browser preview.
#
# Mirrors .github/workflows/deploy.yml: clones Quartz v4, copies the content
# and the config, builds, and serves on http://localhost:8080 (override with
# -p; if the port is busy the script picks the next free one). The Quartz
# checkout and node_modules live in $XDG_CACHE_HOME (or ~/.cache), so repeat
# runs are fast; content and config are re-synced on every run, and a
# background loop keeps the server's copy of content/ in sync, so edits to
# this repo show up on refresh.
#
# Requirements: bash, git, node/npm/npx. On a NixOS box without node the
# script re-runs itself inside `nix-shell -p nodejs`.
#
# Usage: scripts/serve-quartz.sh [-p PORT] [-o | -n] [-c] [-h]

set -euo pipefail

QUARTZ_REF="${QUARTZ_REF:-v4}"
QUARTZ_URL="https://github.com/jackyzha0/quartz.git"
PORT="${QUARTZ_PORT:-8080}"
OPEN_BROWSER=1
CLEAN=0

usage() {
    sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'
    echo
    echo "Options:"
    echo "  -p PORT   serve on this port (default: 8080; bumps if busy)"
    echo "  -o        open the browser once the server is up (default)"
    echo "  -n        do not open the browser"
    echo "  -c        rebuild the cached Quartz checkout from scratch"
    echo "  -h        show this help"
    exit "${1:-0}"
}

while getopts "p:onc:h" opt; do
    case "$opt" in
        p) PORT="$OPTARG" ;;
        o) OPEN_BROWSER=1 ;;
        n) OPEN_BROWSER=0 ;;
        c) CLEAN=1 ;;
        h) usage 0 ;;
        *) usage 1 ;;
    esac
done

if ! command -v node >/dev/null 2>&1 || ! command -v npm >/dev/null 2>&1; then
    if [ "${QUARTZ_PREVIEW_IN_NIX:-}" != "1" ] && command -v nix-shell >/dev/null 2>&1; then
        echo "node/npm not found; re-running inside nix-shell -p nodejs"
        QUARTZ_PREVIEW_IN_NIX=1 exec nix-shell -p nodejs --run "bash '$0' $*"
    fi
    echo "error: node and npm are required (on NixOS: nix-shell -p nodejs)" >&2
    exit 1
fi

port_busy() {
    if command -v ss >/dev/null 2>&1; then
        ss -tlnH 2>/dev/null | awk '{print $4}' | grep -qE "(:|\\.)$1$"
    elif command -v lsof >/dev/null 2>&1; then
        lsof -i ":$1" >/dev/null 2>&1
    else
        (exec 3<>"/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1
    fi
}

while port_busy "$PORT"; do
    PORT=$((PORT + 1))
done
if [ "$PORT" != "${QUARTZ_PORT:-8080}" ]; then
    echo "port ${QUARTZ_PORT:-8080} is busy, using $PORT"
fi

CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/icon4py-knowledge-quartz"
WORK="$CACHE/quartz"

if [ "$CLEAN" = "1" ]; then
    rm -rf "$CACHE"
fi

if [ ! -d "$WORK/.git" ]; then
    echo "cloning Quartz $QUARTZ_REF into $WORK"
    mkdir -p "$CACHE"
    git clone --depth 1 --branch "$QUARTZ_REF" "$QUARTZ_URL" "$WORK"
fi

if [ ! -d "$WORK/node_modules" ]; then
    echo "installing Quartz dependencies (first run only)"
    (cd "$WORK" && npm ci)
fi

echo "syncing content and config"
if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete content/ "$WORK/content/"
else
    rm -rf "$WORK/content"
    mkdir -p "$WORK/content"
    cp -r content/* "$WORK/content/"
fi
cp quartz.config.ts quartz.layout.ts "$WORK/"

port_open() {
    if command -v curl >/dev/null 2>&1; then
        curl -fsS "http://localhost:$PORT" >/dev/null 2>&1
    else
        (exec 3<>"/dev/tcp/localhost/$PORT") >/dev/null 2>&1
    fi
}

echo "serving on http://localhost:$PORT (Ctrl-C to stop)"
(cd "$WORK" && exec npx quartz build --serve --port "$PORT") &
SERVER_PID=$!

# keep the server's copy of content/ in sync, so edits to this repo show up
# on refresh (the server watches its own copy, not the repo)
while true; do
    sleep 2
    if command -v rsync >/dev/null 2>&1; then
        rsync -a --delete content/ "$WORK/content/"
    else
        cp -r content/. "$WORK/content/"
    fi
done &
SYNC_PID=$!
trap 'kill "$SERVER_PID" "$SYNC_PID" 2>/dev/null || true' EXIT INT TERM

ready=0
for _ in $(seq 1 120); do
    if port_open; then
        ready=1
        break
    fi
    sleep 1
done

if [ "$ready" -ne 1 ]; then
    echo "error: server did not come up on port $PORT" >&2
    exit 1
fi

if [ "$OPEN_BROWSER" = "1" ]; then
    if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "http://localhost:$PORT" >/dev/null 2>&1 || true
    elif command -v open >/dev/null 2>&1; then
        open "http://localhost:$PORT"
    fi
fi

wait "$SERVER_PID"
