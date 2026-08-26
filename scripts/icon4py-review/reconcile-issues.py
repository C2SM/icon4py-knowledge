#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Apply orchestrator output to the Markdown issue files.

Reads accepted findings and fixedness verdicts (both JSON written by the
orchestrator), plus the existing issue files, and creates, updates, or marks
issues. The orchestrator makes every LLM decision; this script only does the
deterministic bookkeeping (fingerprint matching, stable ids, frontmatter
assembly, human-field preservation, history) that the LLM does unreliably.

Input contract:
- accepted.json: a flat list of accepted findings (fingerprint matched this run).
- fixedness.json: a flat list, one entry per existing open issue that was NOT
  matched this run. Each entry has fingerprint and verdict in
  {fixed, persists, unknown, not-detected}. "not-detected" means the reviewers
  saw the same commit and missed it; "unknown" means the panel could not decide
  (possibly stale). Only "fixed" marks an issue fixed.

Human authority:
- issue_status: invalid is preserved and never reopened.
- human_note is preserved across body regeneration.
- A human-marked fixed issue is reopened only if the same fingerprint is
  detected again; a fixedness verdict alone never reopens a human dismissal.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

ID_RE = re.compile(r"^icon4py-\d{4}-\d{2}-\d{2}-[a-z0-9]{7}$")
STATUS_VALUES = {"open", "fixed", "invalid"}
VERDICT_VALUES = {"fixed", "persists", "unknown", "not-detected"}
REQUIRED_FINDING_FIELDS = {
    "title",
    "severity",
    "confidence",
    "description",
    "evidence",
    "file",
    "lines",
    "symbol",
    "suggested_fix",
    "reviewer",
    "fingerprint",
}


@dataclass(frozen=True)
class Source:
    repo: str
    ref: str
    commit_sha: str
    file: str
    lines: list[int]
    symbol: str

    def as_dict(self) -> dict:
        return {
            "repo": self.repo,
            "ref": self.ref,
            "commit_sha": self.commit_sha,
            "file": self.file,
            "lines": self.lines,
            "symbol": self.symbol,
        }


@dataclass
class Issue:
    path: Path
    frontmatter: dict
    body: str

    @property
    def id(self) -> str | None:
        return self.frontmatter.get("id")

    @property
    def fingerprint(self) -> str | None:
        return self.frontmatter.get("fingerprint")

    @property
    def status(self) -> str:
        return self.frontmatter.get("issue_status", "open")

    def write(self) -> None:
        text = "---\n" + yaml.safe_dump(self.frontmatter, sort_keys=False, allow_unicode=True) + "---\n" + self.body
        self.path.write_text(text, encoding="utf-8")


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


def load_issues(issues_dir: Path) -> dict[str, Issue]:
    issues: dict[str, Issue] = {}
    for path in issues_dir.glob("*.md"):
        if path.name == ".gitkeep":
            continue
        text = path.read_text(encoding="utf-8")
        result = split_frontmatter(text)
        if result is None:
            continue
        frontmatter, body = result
        fp = frontmatter.get("fingerprint")
        if fp:
            issues[fp] = Issue(path=path, frontmatter=frontmatter, body=body)
    return issues


def issue_id(date: str, fingerprint: str) -> str:
    suffix = hashlib.sha256(fingerprint.encode()).hexdigest()[:7]
    return f"icon4py-{date}-{suffix}"


def issue_body(finding: dict) -> str:
    sections = [
        "## Summary\n\n" + finding.get("description", ""),
    ]
    impact = finding.get("impact")
    if impact:
        sections.append("## Impact\n\n" + impact)
    sections.append("## Evidence\n\n" + finding.get("evidence", ""))
    sections.append("## Suggested fix\n\n" + finding.get("suggested_fix", ""))
    human_note = finding.get("human_note")
    if human_note:
        sections.append("## Human note\n\n" + human_note)
    return "\n\n".join(sections) + "\n"


def update_issue(issue: Issue, finding: dict, date: str, run_id: str, commit_sha: str) -> None:
    fm = issue.frontmatter
    new_source = Source(
        repo="C2SM/icon4py",
        ref="main",
        commit_sha=commit_sha,
        file=finding["file"],
        lines=list(finding.get("lines", [0, 0])),
        symbol=finding.get("symbol", ""),
    )

    # Preserve human-owned fields.
    human_note = fm.get("human_note")
    previous_status = fm.get("issue_status", "open")

    fm["title"] = finding["title"]
    fm["severity"] = finding["severity"]
    fm["confidence"] = finding["confidence"]
    existing_tags = set(fm.get("tags", []))
    if "tags" in finding and isinstance(finding["tags"], list):
        existing_tags.update(finding["tags"])
    fm["tags"] = sorted(existing_tags)
    fm["updated"] = date
    fm["last_seen"] = date
    fm["source"] = new_source.as_dict()
    fm["found_by"] = list(dict.fromkeys(fm.get("found_by", []) + [finding["reviewer"]]))
    fm["run_id"] = run_id

    history = fm.setdefault("history", [])

    # Reopen a human-marked fixed issue if the same fingerprint is detected
    # again. A human-marked invalid issue is never reopened.
    if previous_status == "fixed":
        fm["issue_status"] = "open"
        history.append(
            {
                "date": date,
                "event": "reopened",
                "run_id": run_id,
                "commit_sha": commit_sha,
                "reason": "same fingerprint detected again",
            }
        )

    history.append(
        {
            "date": date,
            "event": "sighting",
            "run_id": run_id,
            "commit_sha": commit_sha,
            "note": "fingerprint matched this run",
        }
    )

    # Regenerate the body from the current finding, preserving a human note.
    body_finding = dict(finding)
    if human_note:
        body_finding["human_note"] = human_note
    issue.body = issue_body(body_finding)
    issue.write()


def create_issue(
    issues_dir: Path,
    finding: dict,
    date: str,
    run_id: str,
    commit_sha: str,
) -> Issue:
    fp = finding["fingerprint"]
    new_id = issue_id(date, fp)
    path = issues_dir / f"{new_id}.md"

    source = Source(
        repo="C2SM/icon4py",
        ref="main",
        commit_sha=commit_sha,
        file=finding["file"],
        lines=list(finding.get("lines", [0, 0])),
        symbol=finding.get("symbol", ""),
    )

    tags = finding.get("tags") or []
    fm = {
        "id": new_id,
        "title": finding["title"],
        "issue_status": "open",
        "severity": finding["severity"],
        "confidence": finding["confidence"],
        "fingerprint": fp,
        "tags": sorted(set(tags)) if isinstance(tags, list) else [],
        "created": date,
        "updated": date,
        "last_seen": date,
        "source": source.as_dict(),
        "found_by": [finding["reviewer"]],
        "run_id": run_id,
        "history": [
            {
                "date": date,
                "event": "detected",
                "run_id": run_id,
                "commit_sha": commit_sha,
            }
        ],
    }

    issue = Issue(path=path, frontmatter=fm, body=issue_body(finding))
    issue.write()
    return issue


def apply_fixedness(issue: Issue, verdict: str, date: str, run_id: str, commit_sha: str) -> str:
    """Return the resulting issue_status after applying a fixedness verdict."""
    fm = issue.frontmatter
    fm["updated"] = date
    fm["run_id"] = run_id
    history = fm.setdefault("history", [])

    note = {
        "fixed": "fixedness panel confirmed the issue is resolved",
        "persists": "fixedness panel confirmed the issue still exists",
        "unknown": "fixedness panel could not decide; possibly stale",
        "not-detected": "reviewers saw the same commit and did not reproduce",
    }.get(verdict, verdict)

    if verdict == "fixed":
        fm["issue_status"] = "fixed"
        history.append({"date": date, "event": "fixed", "run_id": run_id, "commit_sha": commit_sha, "note": note})
    else:
        # persist / unknown / not-detected all leave the issue open.
        history.append({"date": date, "event": verdict, "run_id": run_id, "commit_sha": commit_sha, "note": note})

    issue.write()
    return fm["issue_status"]


def load_json_list(path: Path, label: str) -> list:
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error: failed to parse {label} ({path}): {exc}", file=sys.stderr)
        raise SystemExit(1)
    if not isinstance(data, list):
        print(f"Error: {label} ({path}) must be a JSON list, not {type(data).__name__}", file=sys.stderr)
        raise SystemExit(1)
    return data


def load_duplicates(path: Path | None) -> list[dict]:
    """Load duplicates.json if provided; return an empty list otherwise."""
    if path is None or not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        print(f"Error: failed to parse duplicates ({path}): {exc}", file=sys.stderr)
        raise SystemExit(1)
    if not isinstance(data, list):
        print(f"Error: duplicates ({path}) must be a JSON list", file=sys.stderr)
        raise SystemExit(1)
    return data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply accepted findings and fixedness verdicts to issue files.")
    parser.add_argument("accepted", type=Path, help="Path to accepted.json")
    parser.add_argument("fixedness", type=Path, help="Path to fixedness.json")
    parser.add_argument("issues_dir", type=Path, help="Path to content/review/issues/")
    parser.add_argument("--date", required=True, help="Review date YYYY-MM-DD")
    parser.add_argument("--run-id", required=True, help="Run identifier")
    parser.add_argument("--commit-sha", required=True, help="icon4py commit SHA")
    parser.add_argument("--duplicates", type=Path, help="Path to duplicates.json")
    args = parser.parse_args(argv)

    for p in (args.accepted, args.fixedness):
        if not p.exists():
            print(f"Error: not found: {p}", file=sys.stderr)
            return 1

    args.issues_dir.mkdir(parents=True, exist_ok=True)

    accepted = load_json_list(args.accepted, "accepted.json")
    fixedness = load_json_list(args.fixedness, "fixedness.json")
    duplicate_entries = load_duplicates(args.duplicates)

    existing = load_issues(args.issues_dir)

    # Build lookup of existing issues by id, used for duplicate merges.
    existing_by_id: dict[str, Issue] = {}
    for issue in existing.values():
        issue_id = issue.id
        if issue_id:
            existing_by_id[issue_id] = issue

    created = 0
    updated = 0
    merged_duplicates = 0
    marked_fixed = 0
    other = 0

    # 1. Apply duplicate merges: update existing issues with a history note.
    for entry in duplicate_entries:
        if not isinstance(entry, dict):
            continue
        finding = entry.get("finding") or {}
        target_id = entry.get("duplicate_of")
        target_fp = entry.get("duplicate_of_fingerprint")
        issue = existing_by_id.get(target_id) if target_id else None
        if issue is None and target_fp:
            issue = existing.get(target_fp)
        if issue is None:
            print(
                f"Warning: duplicate entry targets missing issue {target_id!r} ({target_fp!r}); skipping",
                file=sys.stderr,
            )
            continue

        fm = issue.frontmatter
        fm["updated"] = args.date
        fm["last_seen"] = args.date
        fm["run_id"] = args.run_id
        # Merge tags from the new finding without rewriting the body.
        if "tags" in finding and isinstance(finding["tags"], list):
            existing_tags = set(fm.get("tags", []))
            existing_tags.update(finding["tags"])
            fm["tags"] = sorted(existing_tags)

        history = fm.setdefault("history", [])
        history.append(
            {
                "date": args.date,
                "event": "re-detected",
                "run_id": args.run_id,
                "commit_sha": args.commit_sha,
                "note": f"weekly review detected the same issue again as {finding.get('fingerprint', '<no fingerprint>')}",
            }
        )
        issue.write()
        merged_duplicates += 1
        # Do not apply fixedness to this existing issue.
        existing.pop(issue.fingerprint, None)

    # 2. Apply accepted findings.
    for finding in accepted:
        if not isinstance(finding, dict):
            print("Warning: skipping non-dict accepted entry", file=sys.stderr)
            continue
        missing = REQUIRED_FINDING_FIELDS - set(finding.keys())
        if missing:
            fp = finding.get("fingerprint", "<no fingerprint>")
            print(f"Warning: skipping accepted entry {fp!r} missing fields: {sorted(missing)}", file=sys.stderr)
            continue
        fp = finding["fingerprint"]
        issue = existing.get(fp)
        if issue is None:
            create_issue(args.issues_dir, finding, args.date, args.run_id, args.commit_sha)
            created += 1
        else:
            update_issue(issue, finding, args.date, args.run_id, args.commit_sha)
            updated += 1
            # An accepted finding re-confirms an open issue; do not also apply
            # a fixedness verdict to the same fingerprint below.
            existing.pop(fp, None)

    # 3. Apply fixedness verdicts to the remaining (unmatched) open issues.
    # Defensive merge: if the orchestrator writes one entry per checker vote
    # instead of one entry per issue, aggregate the votes here.
    votes_by_fp: dict[str, list[str]] = {}
    for entry in fixedness:
        if not isinstance(entry, dict):
            continue
        fp = entry.get("fingerprint")
        verdict = entry.get("verdict")
        if not fp or verdict not in VERDICT_VALUES:
            print(f"Warning: skipping fixedness entry {fp!r} verdict {verdict!r}", file=sys.stderr)
            continue
        votes_by_fp.setdefault(fp, []).append(verdict)

    def merge_fixedness_votes(votes: list[str]) -> str:
        counts = {v: votes.count(v) for v in VERDICT_VALUES}
        if counts.get("fixed", 0) >= 2:
            return "fixed"
        if counts.get("persists", 0) >= 2:
            return "persists"
        return "unknown"

    verdict_by_fp: dict[str, str] = {}
    for fp, votes in votes_by_fp.items():
        if len(votes) > 1:
            print(f"Note: merging {len(votes)} fixedness entries for {fp!r}", file=sys.stderr)
        verdict_by_fp[fp] = merge_fixedness_votes(votes)

    for fp, issue in existing.items():
        if issue.status != "open":
            continue
        verdict = verdict_by_fp.get(fp)
        if verdict is None:
            # Not in accepted and not in fixedness: the orchestrator should not
            # leave this case, but if it does, do not silently mark fixed.
            print(f"Warning: open issue {issue.id!r} ({fp!r}) has no accepted or fixedness entry", file=sys.stderr)
            continue
        result = apply_fixedness(issue, verdict, args.date, args.run_id, args.commit_sha)
        if result == "fixed":
            marked_fixed += 1
        else:
            other += 1

    print(
        f"Reconciled: {created} created, {updated} updated, "
        f"{merged_duplicates} duplicates merged, "
        f"{marked_fixed} marked fixed, {other} left open (persists/unknown/not-detected)."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
