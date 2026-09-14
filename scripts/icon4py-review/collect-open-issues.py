#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Collect existing open issues into a small JSON list for the orchestrator.

The orchestrator runs inside a sandbox with no access to content/review/issues/.
This pre-step reads those files and writes one entry per open issue (id,
fingerprint, source file, last-seen commit, lines, symbol) to a findings dir.
The orchestrator then decides, purely from this JSON, which open issues to send
to the fixedness panel.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml


def split_frontmatter(text: str) -> tuple[dict, str] | None:
    if not text.startswith("---\n"):
        return None
    rest = text[4:]
    parts = rest.split("\n---\n", 1)
    if len(parts) < 2:
        return None
    try:
        frontmatter = yaml.safe_load(parts[0]) or {}
    except yaml.YAMLError:
        return None
    return frontmatter, parts[1]


def section(body: str, heading: str) -> str:
    # Extract the text under a `## heading` until the next `## ` or end.
    marker = f"## {heading}\n"
    start = body.find(marker)
    if start == -1:
        return ""
    start += len(marker)
    nxt = body.find("\n## ", start)
    return body[start:nxt].strip() if nxt != -1 else body[start:].strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Collect existing open issues for the orchestrator.")
    parser.add_argument("issues_dir", type=Path, help="Path to content/review/issues/")
    parser.add_argument("output", type=Path, help="Path to write open-issues.json")
    args = parser.parse_args(argv)

    if not args.issues_dir.is_dir():
        print(f"Error: not a directory: {args.issues_dir}", file=sys.stderr)
        return 1

    entries: list[dict] = []
    for path in sorted(args.issues_dir.glob("*.md")):
        if path.name == ".gitkeep":
            continue
        result = split_frontmatter(path.read_text(encoding="utf-8"))
        if result is None:
            print(f"Warning: skipping {path}, malformed frontmatter", file=sys.stderr)
            continue
        fm, body = result
        if fm.get("issue_status", "open") != "open":
            continue
        source = fm.get("source") or {}
        entries.append(
            {
                "id": fm.get("id", path.stem),
                "fingerprint": fm.get("fingerprint", ""),
                "file": source.get("file", ""),
                "commit_sha": source.get("commit_sha", ""),
                "lines": source.get("lines", [0, 0]),
                "symbol": source.get("symbol", ""),
                "title": fm.get("title", ""),
                "description": section(body, "Summary"),
                "suggested_fix": section(body, "Suggested fix"),
            }
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(entries, indent=2) + "\n", encoding="utf-8")
    print(f"Collected {len(entries)} open issue(s) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
