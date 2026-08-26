#!/usr/bin/env bash
set -euo pipefail

# Run pi inside a bwrap sandbox with a dedicated config directory.
#
# Usage:
#   CSCS_INFERENCE_API_KEY=... ./scripts/pi-sandboxed.sh <pi-config-dir> <skill-path> <prompt>
#
# Optional environment variables:
#   PI_SANDBOX_CHDIR        - working directory inside the sandbox (default: current cwd)
#   PI_SANDBOX_REPORTS_DIR  - path bound writable to /tmp/review-reports (overview report sink)
#   PI_SANDBOX_FINDINGS_DIR - host path bound writable to /tmp/icon4py-review-findings
#   PI_SANDBOX_EXTRA_BINDS  - semicolon-separated src;dst pairs for additional binds
#   PI_SANDBOX_ENABLE_GITHUB_TOKEN - if set, forward GITHUB_TOKEN into the sandbox
#   PI_SANDBOX_TOOLS        - comma-separated tool allowlist (default: read,write,bash)
#
# Isolation:
# - The whole host filesystem is mounted read-only.
# - /tmp is a fresh tmpfs.
# - Only PI_SANDBOX_REPORTS_DIR, PI_SANDBOX_FINDINGS_DIR, and extra binds are writable.
# - The pi config directory is copied to a fresh writable location inside
#   the sandbox so the original cannot be modified. auth.json, if present,
#   is a local auth source and is kept in the copy.
# - .git directories under PI_SANDBOX_CHDIR and ICON4PY_CHECKOUT are hidden.
# - Network is shared (--share-net): the only thing an agent without bash can
#   reach is the inference provider. Adding bash to PI_SANDBOX_TOOLS reopens
#   arbitrary network access and must be reconsidered.

PI_CONFIG_DIR="${1:?pi config directory required}"
SKILL_PATH="${2:?skill path required}"
PROMPT="${3:?prompt required}"
PI_BIN="${PI_BIN:-$(command -v pi 2>/dev/null || true)}"
if [[ -z "$PI_BIN" ]]; then
    echo "Error: pi binary not found. Install pi or set PI_BIN." >&2
    exit 1
fi

if [[ ! -d "$PI_CONFIG_DIR" ]]; then
    echo "Error: pi config directory not found: $PI_CONFIG_DIR" >&2
    exit 1
fi

if [[ ! -f "$PI_CONFIG_DIR/settings.json" ]]; then
    echo "Error: settings.json not found in $PI_CONFIG_DIR" >&2
    exit 1
fi

# Copy config dir to a writable temp location so the original cannot be
# modified. Auto-installed packages (e.g. @gotgenes/pi-subagents) are
# installed into this copy by pi at startup. auth.json, if present, is a
# local auth source and is intentionally kept.
TMP_CONFIG="$(mktemp -d /tmp/pi-config-XXXXXX)"
trap 'rm -rf "$TMP_CONFIG"' EXIT
cp -a "$PI_CONFIG_DIR"/. "$TMP_CONFIG/"
mkdir -p "$TMP_CONFIG/sessions"

BWRAP_ARGS=(
    bwrap
    --die-with-parent
    --clearenv
    --ro-bind / /
    --tmpfs /tmp
    --bind "$TMP_CONFIG" /tmp/pi-config
)

# Writable sink for the overview report (narrow: only reports/, never issues/).
if [[ -n "${PI_SANDBOX_REPORTS_DIR:-}" ]]; then
    if [[ ! -d "$PI_SANDBOX_REPORTS_DIR" ]]; then
        echo "Error: reports directory not found: $PI_SANDBOX_REPORTS_DIR" >&2
        exit 1
    fi
    BWRAP_ARGS+=(--bind "$PI_SANDBOX_REPORTS_DIR" /tmp/review-reports)
fi

# Writable sink for intermediate findings shared with the caller.
if [[ -n "${PI_SANDBOX_FINDINGS_DIR:-}" ]]; then
    if [[ ! -d "$PI_SANDBOX_FINDINGS_DIR" ]]; then
        echo "Error: findings directory not found: $PI_SANDBOX_FINDINGS_DIR" >&2
        exit 1
    fi
    BWRAP_ARGS+=(--bind "$PI_SANDBOX_FINDINGS_DIR" /tmp/icon4py-review-findings)
fi

# Optional extra binds; format is semicolon-separated src;dst pairs.
if [[ -n "${PI_SANDBOX_EXTRA_BINDS:-}" ]]; then
    IFS=';' read -ra EXTRA_BIND_ARRAY <<< "$PI_SANDBOX_EXTRA_BINDS"
    if (( ${#EXTRA_BIND_ARRAY[@]} % 2 != 0 )); then
        echo "Error: PI_SANDBOX_EXTRA_BINDS must have an even number of semicolon-separated entries" >&2
        exit 1
    fi
    for ((i = 0; i < ${#EXTRA_BIND_ARRAY[@]}; i += 2)); do
        BWRAP_ARGS+=(--bind "${EXTRA_BIND_ARRAY[i]}" "${EXTRA_BIND_ARRAY[i+1]}")
    done
fi

# Bind the icon4py checkout read-only at its own path. --tmpfs /tmp above
# hides /tmp/<checkout> inside the sandbox, so without this the reviewers'
# icon4py_checkout points at a directory that does not exist and every read
# fails. Then hide .git under that checkout so no checkout credentials leak.
if [[ -n "${ICON4PY_CHECKOUT:-}" && -d "$ICON4PY_CHECKOUT" ]]; then
    BWRAP_ARGS+=(--ro-bind "$ICON4PY_CHECKOUT" "$ICON4PY_CHECKOUT")
    if [[ -d "$ICON4PY_CHECKOUT/.git" ]]; then
        BWRAP_ARGS+=(--tmpfs "$ICON4PY_CHECKOUT/.git")
    fi
fi

BWRAP_ARGS+=(
    --proc /proc
    --dev /dev
    --share-net
    --setenv HOME /tmp
    --setenv PI_CODING_AGENT_DIR /tmp/pi-config
    # Forward the host PATH so the setup-node npm and node are reachable inside
    # the sandbox (needed for pi's package auto-install and its wrapper). All of
    # / is read-only, so no binary becomes newly writable.
    --setenv PATH "$PATH"
    --setenv TZ "${TZ:-Europe/Zurich}"
    --setenv CSCS_INFERENCE_API_KEY "${CSCS_INFERENCE_API_KEY:-}"
    --setenv ICON4PY_CHECKOUT "${ICON4PY_CHECKOUT:-}"
    --setenv PI_SANDBOX_REPORTS_DIR "${PI_SANDBOX_REPORTS_DIR:+/tmp/review-reports}"
    --setenv PI_SANDBOX_FINDINGS_DIR "${PI_SANDBOX_FINDINGS_DIR:+/tmp/icon4py-review-findings}"
)

if [[ -n "${PI_SANDBOX_ENABLE_GITHUB_TOKEN:-}" ]]; then
    BWRAP_ARGS+=(--setenv GITHUB_TOKEN "${GITHUB_TOKEN:-}")
fi

if [[ -n "${PI_SANDBOX_CHDIR:-}" ]]; then
    BWRAP_ARGS+=(--chdir "$PI_SANDBOX_CHDIR")
fi

PI_SANDBOX_TOOLS="${PI_SANDBOX_TOOLS:-read,write,bash}"

# Invoke pi through bwrap with the assembled args. Earlier this exec'd pi
# directly, bypassing the sandbox entirely (the env leaked, global extensions
# like AFT/memory loaded, and pi never exited). The BWRAP_ARGS array
# (--clearenv, --ro-bind / /, --setenv PI_CODING_AGENT_DIR /tmp/pi-config,
# --setenv HOME /tmp, etc.) only takes effect when bwrap is the entry point.
BWRAP_ARGS+=(
    "$PI_BIN"
    -p --approve
    --tools "$PI_SANDBOX_TOOLS"
    --skill "$SKILL_PATH"
    "$PROMPT"
)

exec "${BWRAP_ARGS[@]}"
