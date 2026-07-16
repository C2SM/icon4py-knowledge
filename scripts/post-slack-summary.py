#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Post a text file to a Slack incoming webhook.

Usage:
    SLACK_WEBHOOK_URL=https://hooks.slack.com/.../... \\
        ./scripts/post-slack-summary.py weekly_slack_summary.md
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def post(webhook_url: str, text: str) -> None:
    payload = json.dumps({"text": text}).encode("utf-8")
    request = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            _ = response.read()
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(
            f"Slack webhook request failed ({exc.code}): {exc.reason}\n{error_body}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Slack webhook request failed: {exc.reason}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Post a text file to a Slack webhook.")
    parser.add_argument("file", type=Path, help="Path to the file to post.")
    args = parser.parse_args(argv)

    webhook_url = os.environ.get("SLACK_WEBHOOK_URL")
    if not webhook_url:
        print("Error: SLACK_WEBHOOK_URL is not set.", file=sys.stderr)
        return 1

    path = args.file.expanduser()
    if not path.is_file():
        print(f"Error: file not found: {path}", file=sys.stderr)
        return 1

    text = path.read_text(encoding="utf-8")
    if not text.strip():
        print(f"Error: file is empty: {path}", file=sys.stderr)
        return 1

    post(webhook_url, text)
    print(f"Posted {len(text)} characters to Slack.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
