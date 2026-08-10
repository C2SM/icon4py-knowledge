#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Validate review issue files under content/review/issues/."""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

import yaml

REQUIRED_FIELDS = {
    "id",
    "title",
    "issue_status",
    "severity",
    "confidence",
    "fingerprint",
    "tags",
    "created",
    "updated",
    "last_seen",
    "source",
    "found_by",
    "run_id",
    "history",
}

SOURCE_FIELDS = {"repo", "ref", "commit_sha", "file", "lines", "symbol"}
STATUS_VALUES = {"open", "fixed", "invalid"}
SEVERITY_VALUES = {"high", "medium", "low"}
CONFIDENCE_VALUES = {"high", "medium", "low"}
ID_RE = re.compile(r"^icon4py-\d{4}-\d{2}-\d{2}-[a-z0-9]{7}$")


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


def validate_issue(path: Path) -> list[str]:
    errors: list[str] = []
    text = path.read_text(encoding="utf-8")
    result = split_frontmatter(text)
    if result is None:
        errors.append(f"{path}: malformed frontmatter")
        return errors

    frontmatter, _body = result

    missing = REQUIRED_FIELDS - set(frontmatter.keys())
    if missing:
        errors.append(f"{path}: missing required fields: {sorted(missing)}")

    issue_id = frontmatter.get("id")
    if issue_id and not ID_RE.match(issue_id):
        errors.append(f"{path}: id {issue_id!r} does not match pattern icon4py-YYYY-MM-DD-XXXXXXX")

    expected_filename = f"{issue_id}.md" if issue_id else None
    if expected_filename and path.name != expected_filename:
        errors.append(f"{path}: filename {path.name!r} does not match id {expected_filename!r}")

    # Verify id suffix matches fingerprint hash.
    fingerprint = frontmatter.get("fingerprint")
    if fingerprint and issue_id:
        expected_suffix = hashlib.sha256(fingerprint.encode()).hexdigest()[:7]
        actual_suffix = issue_id.rsplit("-", 1)[-1]
        if actual_suffix != expected_suffix:
            errors.append(
                f"{path}: id suffix {actual_suffix!r} does not match fingerprint hash {expected_suffix!r}"
            )

    if frontmatter.get("issue_status") not in STATUS_VALUES:
        errors.append(f"{path}: issue_status must be one of {STATUS_VALUES}")

    if frontmatter.get("severity") not in SEVERITY_VALUES:
        errors.append(f"{path}: severity must be one of {SEVERITY_VALUES}")

    if frontmatter.get("confidence") not in CONFIDENCE_VALUES:
        errors.append(f"{path}: confidence must be one of {CONFIDENCE_VALUES}")

    source = frontmatter.get("source") or {}
    missing_source = SOURCE_FIELDS - set(source.keys())
    if missing_source:
        errors.append(f"{path}: source missing fields: {sorted(missing_source)}")

    lines = source.get("lines")
    if lines is not None and (not isinstance(lines, list) or len(lines) != 2 or not all(isinstance(x, int) for x in lines)):
        errors.append(f"{path}: source.lines must be a two-element integer list")

    history = frontmatter.get("history")
    if history is not None and not isinstance(history, list):
        errors.append(f"{path}: history must be a list")

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate review issue files.")
    parser.add_argument("issues_dir", type=Path, help="Path to content/review/issues/")
    args = parser.parse_args(argv)

    if not args.issues_dir.is_dir():
        print(f"Error: not a directory: {args.issues_dir}", file=sys.stderr)
        return 1

    all_errors: list[str] = []
    fingerprints: dict[str, Path] = {}
    count = 0
    for path in sorted(args.issues_dir.glob("*.md")):
        if path.name == ".gitkeep":
            continue
        count += 1
        all_errors.extend(validate_issue(path))
        result = split_frontmatter(path.read_text(encoding="utf-8"))
        if result is None:
            continue
        frontmatter, _ = result
        fingerprint = frontmatter.get("fingerprint")
        if fingerprint:
            if fingerprint in fingerprints:
                all_errors.append(
                    f"{path}: duplicate fingerprint {fingerprint!r} "
                    f"(also in {fingerprints[fingerprint]})"
                )
            fingerprints[fingerprint] = path

    if all_errors:
        print("Validation failed:", file=sys.stderr)
        for error in all_errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print(f"Validated {count} issue file(s). OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
