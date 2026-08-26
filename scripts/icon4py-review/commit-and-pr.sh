#!/usr/bin/env bash
set -euo pipefail

# Commit review changes to a dated branch and open a pull request.
# The PR description is the overview report itself.
#
# Usage: commit-and-pr.sh <report.md>
# Intended to run from GitHub Actions only.

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$REPO_ROOT"

report="${1:?usage: commit-and-pr.sh <report.md>}"
if [[ ! -f "$report" ]]; then
    echo "Error: report not found: $report" >&2
    exit 1
fi

if [[ -z "${GITHUB_TOKEN:-}" ]]; then
    echo "Error: GITHUB_TOKEN is not set." >&2
    exit 1
fi

if ! git diff --cached --quiet 2>/dev/null; then
    echo "Error: there are already staged changes. This script stages content/review/ itself." >&2
    exit 1
fi

# Use -c to avoid modifying the user's local git config.
git -c user.name="icon4py-review-bot" \
    -c user.email="icon4py-review-bot@users.noreply.github.com" \
    add content/review/

if git -c user.name="icon4py-review-bot" -c user.email="icon4py-review-bot@users.noreply.github.com" diff --cached --quiet; then
    echo "No review changes to commit."
    exit 0
fi

week=$(date +%G-W%V)
branch="review/week-${week}-$(date +%s%N)"
# The commit lands on HEAD, which is detached in CI (actions/checkout on a
# pull_request event), so create the branch first or the push below has
# nothing to push.
git checkout -b "$branch"
git -c user.name="icon4py-review-bot" \
    -c user.email="icon4py-review-bot@users.noreply.github.com" \
    commit -m "review(week ${week}): update icon4py findings"

if ! git push origin "$branch"; then
    echo "Error: failed to push branch $branch" >&2
    exit 1
fi

if ! gh pr create \
    --title "icon4py week ${week} review" \
    --body-file "$report" \
    --base main \
    --head "$branch"; then
    echo "Error: failed to create pull request" >&2
    exit 1
fi
