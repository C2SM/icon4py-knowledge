#!/usr/bin/env bash
set -euo pipefail

# Run the icon4py weekly review end to end. This is the single entry point for
# both local testing and CI. In CI, pass --commit-and-pr to commit and open a
# pull request; locally it just produces changes for inspection.
#
# Requires:
#   - pi and bwrap installed and on PATH
#   - ICON4PY_CHECKOUT pointing to a clone of C2SM/icon4py
#
# Auth: pi authenticates from auth.json in the review config dir (local
# testing) or CSCS_INFERENCE_API_KEY (CI, forwarded into the sandbox). run.sh
# does not check auth; pi fails loudly if neither is available.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PI_CONFIG_DIR="$REPO_ROOT/scripts/icon4py-review"
COMMIT_AND_PR=0
for arg in "$@"; do
    case "$arg" in
        --commit-and-pr) COMMIT_AND_PR=1 ;;
    esac
done

if [[ -z "${ICON4PY_CHECKOUT:-}" ]]; then
    echo "Error: ICON4PY_CHECKOUT is not set." >&2
    exit 1
fi

if [[ ! -d "$ICON4PY_CHECKOUT/.git" ]]; then
    echo "Error: ICON4PY_CHECKOUT does not point to a git clone: $ICON4PY_CHECKOUT" >&2
    exit 1
fi

command -v pi >/dev/null || { echo "Error: pi not found on PATH." >&2; exit 1; }
command -v bwrap >/dev/null || { echo "Error: bwrap not found on PATH." >&2; exit 1; }
pi --version
bwrap --version | head -1

ICON4PY_SHA="$(git -C "$ICON4PY_CHECKOUT" rev-parse HEAD)"
TODAY="$(date +%Y-%m-%d)"
RUN_ID="weekly-$(date +%G-W%V)"
echo "icon4py commit: $ICON4PY_SHA"
echo "review date: $TODAY  run id: $RUN_ID"

REPORTS_DIR="$REPO_ROOT/content/review/reports"
ISSUES_DIR="$REPO_ROOT/content/review/issues"
FINDINGS_DIR="$(mktemp -d)"
SANDBOX_REPORTS_DIR="$(mktemp -d)"
trap 'rm -rf "$FINDINGS_DIR" "$SANDBOX_REPORTS_DIR"' EXIT

mkdir -p "$REPORTS_DIR" "$ISSUES_DIR"

# Pre-step: collect existing open issues into JSON the orchestrator can read.
echo "Collecting existing open issues..."
"$REPO_ROOT/scripts/icon4py-review/collect-open-issues.py" "$ISSUES_DIR" "$FINDINGS_DIR/open-issues.json"

# Pre-step: write the full diff since the previous review, if a baseline exists.
# Reviewers cannot run git themselves (no bash, .git hidden in the sandbox), so
# the host generates the diff. On the first run, or if the previous report has
# no icon4py_commit frontmatter, skip the diff and let reviewers review as they
# see fit.
echo "Generating diff since previous review..."
# Find the newest report by mtime. nullglob makes an empty reports/ expand to
# nothing instead of the literal glob, which would fail `ls` under `set -euo
# pipefail`.
shopt -s nullglob
reports=("$REPORTS_DIR"/*.md)
shopt -u nullglob
PREV_COMMIT=""
if (( ${#reports[@]} > 0 )); then
    latest_report="$(ls -t "${reports[@]}" | head -1)"
    PREV_COMMIT="$("$REPO_ROOT/scripts/icon4py-review/extract-report-commit.py" "$latest_report" 2>/dev/null || true)"
fi
if [[ -n "$PREV_COMMIT" ]]; then
    # The diff is a best-effort prioritization hint, not a gate. If the
    # baseline commit is not present in the local checkout (shallow clone,
    # pruned history), fall back to an empty changes.diff and let reviewers
    # review as they see fit rather than aborting the whole run under set -e.
    if git -C "$ICON4PY_CHECKOUT" diff "$PREV_COMMIT..$ICON4PY_SHA" > "$FINDINGS_DIR/changes.diff" 2>/dev/null; then
        echo "Wrote changes.diff ($PREV_COMMIT..$ICON4PY_SHA), $(wc -l < "$FINDINGS_DIR/changes.diff") lines."
    else
        : > "$FINDINGS_DIR/changes.diff"
        echo "Warning: git diff $PREV_COMMIT..$ICON4PY_SHA failed (commit not local?); wrote empty changes.diff." >&2
    fi
else
    echo "No previous review commit found; skipping changes.diff."
fi

# Run the orchestrator in the sandbox. It has no access to the issues
# directory; it reads open-issues.json and writes accepted.json,
# fixedness.json, and the overview report.
echo "Running isolated pi review..."
PI_SANDBOX_CHDIR="/tmp" \
PI_SANDBOX_REPORTS_DIR="$SANDBOX_REPORTS_DIR" \
PI_SANDBOX_FINDINGS_DIR="$FINDINGS_DIR" \
PI_SANDBOX_TOOLS="subagent,get_subagent_result,read,ls,write,edit" \
ICON4PY_CHECKOUT="$ICON4PY_CHECKOUT" \
    "$REPO_ROOT/scripts/pi-sandboxed.sh" \
        "$PI_CONFIG_DIR" \
        "$PI_CONFIG_DIR" \
        "Run the weekly icon4py review. icon4py_checkout=$ICON4PY_CHECKOUT. icon4py_commit=$ICON4PY_SHA. review_date=$TODAY. run_id=$RUN_ID. requested_severity=high. findings_dir=/tmp/icon4py-review-findings. reports_dir=/tmp/review-reports. See the skill for the workflow."

# The orchestrator writes the report inside the sandbox. Pull it into the repo.
# The filename includes hour-minute (e.g. 2026-08-05-2114.md) so same-day runs
# do not conflict. Glob for the newest one.
report="$(ls -t "$SANDBOX_REPORTS_DIR"/*.md 2>/dev/null | head -1)"
if [[ -z "$report" || ! -s "$report" ]]; then
    echo "Error: missing or empty overview report in $SANDBOX_REPORTS_DIR" >&2
    exit 1
fi
mv "$report" "$REPORTS_DIR/$(basename "$report")"

if [[ -f "$FINDINGS_DIR/accepted.json" && -f "$FINDINGS_DIR/fixedness.json" ]]; then
    echo "Reconciling accepted findings and fixedness verdicts..."
    duplicates_arg=""
    if [[ -f "$FINDINGS_DIR/duplicates.json" ]]; then
        duplicates_arg="--duplicates $FINDINGS_DIR/duplicates.json"
    fi
    "$REPO_ROOT/scripts/icon4py-review/reconcile-issues.py" \
        "$FINDINGS_DIR/accepted.json" \
        "$FINDINGS_DIR/fixedness.json" \
        "$ISSUES_DIR" \
        --date "$TODAY" \
        --run-id "$RUN_ID" \
        --commit-sha "$ICON4PY_SHA" \
        $duplicates_arg
else
    echo "Warning: accepted.json or fixedness.json missing; skipping reconciliation." >&2
fi

echo "Validating issues..."
"$REPO_ROOT/scripts/icon4py-review/validate-issues.py" "$ISSUES_DIR"
echo "Regenerating index..."
"$REPO_ROOT/scripts/icon4py-review/update-index.py" "$ISSUES_DIR" "$REPO_ROOT/content/review/index.md"

# The newest report (glob for the hour-minute file we moved in).
report="$(ls -t "$REPORTS_DIR"/*.md 2>/dev/null | head -1)"

if [[ "$COMMIT_AND_PR" -eq 1 ]]; then
    echo "Committing and opening pull request..."
    "$REPO_ROOT/scripts/icon4py-review/commit-and-pr.sh" "$report"
else
    echo "Done. Inspect changes with: git status --short content/review/"
fi
