#!/usr/bin/env bash
set -euo pipefail

# Generate the weekly Slack activity summary for icon4py-knowledge in a sandbox
# and post it to Slack. Single entry point for both local testing and CI.
#
# Requires:
#   - pi and bwrap installed and on PATH
#   - CSCS_INFERENCE_API_KEY exported (local auth, or auth.json in the skill dir)
#   - GITHUB_TOKEN exported (read-only, for gh CLI inside the sandbox)
#   - SLACK_WEBHOOK_URL exported (to post the summary)
#
# Auth: pi authenticates from auth.json in the skill config dir (local testing)
# or CSCS_INFERENCE_API_KEY (CI, forwarded into the sandbox). run.sh does not
# check auth; pi fails loudly if neither is available.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SKILL_DIR="$REPO_ROOT/.github/workflows/weekly-slack-summary"
SUMMARY_FILE="$REPO_ROOT/weekly_slack_summary.md"

command -v pi >/dev/null || { echo "Error: pi not found on PATH." >&2; exit 1; }
command -v bwrap >/dev/null || { echo "Error: bwrap not found on PATH." >&2; exit 1; }
pi --version
bwrap --version | head -1

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
    echo "Error: GITHUB_TOKEN is not set." >&2
    exit 1
fi

if [[ -z "${SLACK_WEBHOOK_URL:-}" ]]; then
    echo "Error: SLACK_WEBHOOK_URL is not set." >&2
    exit 1
fi

# The summary is written through a temp file bound over the repo path so the
# sandbox can write exactly one file without write access to the repo root.
TMP_SUMMARY="$(mktemp)"
touch "$SUMMARY_FILE"
trap 'rm -f "$TMP_SUMMARY"' EXIT

echo "Generating weekly summary in sandbox..."
PI_SANDBOX_CHDIR="$REPO_ROOT" \
PI_SANDBOX_EXTRA_BINDS="$TMP_SUMMARY;$SUMMARY_FILE" \
PI_SANDBOX_ENABLE_GITHUB_TOKEN=1 \
CSCS_INFERENCE_API_KEY="${CSCS_INFERENCE_API_KEY:-}" \
GITHUB_TOKEN="$GITHUB_TOKEN" \
    "$REPO_ROOT/scripts/pi-sandboxed.sh" \
        "$SKILL_DIR" \
        "$SKILL_DIR" \
        "Generate the weekly Slack activity summary for icon4py-knowledge and write it to weekly_slack_summary.md"

if [[ ! -s "$SUMMARY_FILE" ]]; then
    echo "Error: missing or empty summary: $SUMMARY_FILE" >&2
    exit 1
fi

echo "Posting summary to Slack..."
"$REPO_ROOT/scripts/post-slack-summary.py" "$SUMMARY_FILE"
echo "Done."
