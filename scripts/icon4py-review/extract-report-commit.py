#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Extract the icon4py commit recorded in a review report's frontmatter.

`run.sh` calls this on the newest report in content/review/reports/ to find the
commit the previous review ran against. That commit is the diff baseline for
the next run's `changes.diff`. Prints nothing (and exits 0) if the report has
no `icon4py_commit` frontmatter field, so older reports fall back gracefully.
"""

from __future__ import annotations

import argparse
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract the icon4py_commit from a review report's frontmatter."
    )
    parser.add_argument("report", type=Path, help="Path to a review report .md file")
    args = parser.parse_args(argv)

    if not args.report.is_file():
        print(f"Error: not a file: {args.report}", file=sys.stderr)
        return 1

    result = split_frontmatter(args.report.read_text(encoding="utf-8"))
    if result is None:
        return 0
    frontmatter, _ = result
    commit = frontmatter.get("icon4py_commit")
    if commit:
        print(commit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
