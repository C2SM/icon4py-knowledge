---
name: icon4py-weekly-review
description: "Run the weekly automated review of C2SM/icon4py and write accepted findings and a fixedness assessment."
---

# Weekly icon4py review

You are the orchestrator. Spawn read-only subagents to review the code and
verify findings, then write three JSON files to the findings directory and one
overview report to the reports directory.

## What your task prompt provides

- `icon4py_checkout`: absolute path to the icon4py clone (read-only).
- `icon4py_commit`: the commit being reviewed.
- `review_date`: `YYYY-MM-DD` (report filename, issue metadata).
- `run_id`: the run identifier (history entries).
- `requested_severity`: tell reviewers to report only this severity.
- `findings_dir`: writable directory for your JSON outputs.
- `reports_dir`: writable directory for the overview report.

Pass these values to each subagent in its task prompt.

Existing open issues are in `<findings_dir>/open-issues.json`, a flat list with
one entry each:

```json
[{"id": "icon4py-...", "fingerprint": "...", "file": "<relative>", "commit_sha": "...", "title": "...", "description": "...", "suggested_fix": "...", "lines": [s,e], "symbol": "..."}]
```

## Thresholds

- Acceptance: a finding becomes a **new** issue only if all three skeptics vote
  `PASS`. A valid finding that duplicates an existing issue is merged into that
  issue instead. Any `UNCERTAIN` vote prevents a new issue from being created.
- Fixedness: an existing open issue is marked `fixed` only if at least two of
  the three fixedness checkers vote `fixed`. Otherwise the verdict is the
  majority of the three votes, or `unknown` if there is no majority, and the
  issue stays open.

## Step 1: Run the reviewers

Run both reviewers and collect all findings before continuing:

- `icon4py-correctness-reviewer`, output `<findings_dir>/correctness.json`
- `icon4py-performance-reviewer`, output `<findings_dir>/performance.json`

Each task prompt gives `icon4py_checkout`, `requested_severity`, `output_path`,
and `findings_dir`. Pass `findings_dir` so reviewers can read `open-issues.json`
(already-tracked issues to avoid re-reporting) and `changes.diff` (code changed
since the last review) from there.

If a reviewer fails or its output is missing or malformed, record the failure
in the overview report and treat that reviewer's findings as empty. Continue.

## Step 2: Verify findings with the skeptic panel

Combine all findings. For each finding, run three `icon4py-finding-skeptic`
subagents. Each task prompt gives:
- `icon4py_checkout`
- the full `finding` object
- `open_issues`: the list from `<findings_dir>/open-issues.json`
- `output_path` under `<findings_dir>/votes/<fingerprint>/1.json`, `2.json`, `3.json`

Each skeptic returns `verdict` in `PASS|REJECT|DUPLICATE|UNCERTAIN` and,
for `DUPLICATE`, a `duplicate_of` issue id.

A missing or malformed vote counts as `UNCERTAIN`.

Classify each finding based on the three verdicts, in this order:

- **Rejected**: any verdict is `REJECT`. Record in the report; do not create an issue.
- **New issue** (`accepted.json`): all three verdicts are `PASS`.
- **Duplicate merge** (`duplicates.json`): at least one verdict is `DUPLICATE`
  and the others are `PASS`. All `DUPLICATE` votes must name the same
  `duplicate_of` issue id; split targets are uncertain, not a merge.
  `confidence` is `high` for 3x `DUPLICATE`, `medium` for 2x, `low` for 1x
  `DUPLICATE` with the other two `PASS`.
- **Uncertain/ambiguous**: anything else (e.g., `UNCERTAIN`, split `DUPLICATE`
  targets, or `PASS` mixed with `UNCERTAIN`). Record these in the report but do
  not create an issue.

Record missing or malformed votes and the classification of each finding in
the overview report.

## Step 3: Write accepted.json and duplicates.json

### 3.1 accepted.json

Write truly new findings to `<findings_dir>/accepted.json` as a flat JSON list.
Each entry is the reviewer's raw finding object (fingerprint, title, severity,
description, evidence, file, lines, symbol, suggested_fix) enriched by the
orchestrator with `reviewer` (the reviewer name), `confidence` (`high`, from
all-3-PASS), and `tags` (derived from the title and defect type; format below).
Skip a malformed entry with a note in the overview report rather than aborting.

`tags` is a list of 3-6 short kebab-case keywords that help someone scan the
tracker for related issues. Do not include the reviewer name, the date, or any
string longer than a short phrase.

### 3.2 duplicates.json

Write findings that duplicate an existing open issue to `<findings_dir>/duplicates.json` as a flat list:

```json
[
  {
    "finding": {... accepted finding object ...},
    "duplicate_of": "icon4py-YYYY-MM-DD-XXXXXXX",
    "duplicate_of_fingerprint": "...",
    "confidence": "high|medium|low",
    "reasoning": "..."
  }
]
```

`confidence` follows the duplicate-merge classification above: `high` for 3x
`DUPLICATE`, `medium` for 2x, `low` for 1x `DUPLICATE` with the others `PASS`.
Any other case is not a duplicate merge; record it as uncertain in the report.

## Step 4: Assess fixedness of existing open issues

Let `accepted_fingerprints` be the set of fingerprints in `accepted.json`. Let
`duplicate_matched_existing` be the set of `duplicate_of_fingerprint` values in
`duplicates.json`.

For each entry in `open-issues.json` whose fingerprint is NOT in
`accepted_fingerprints` AND NOT in `duplicate_matched_existing`:

- If the entry's `commit_sha` equals `icon4py_commit` (the reviewers saw the
  same code and did not reproduce it), write `{"fingerprint": "...", "verdict": "not-detected"}`
  directly. Do not spawn a panel.
- If the commit changed, run three `icon4py-fixedness-checker` subagents
  against `<icon4py_checkout>/<entry.file>`. Each task prompt gives
  `icon4py_checkout`, the issue (id, title, description, file, lines, symbol,
  suggested_fix), and an `output_path`.

  **Merge the three verdicts into exactly one entry per issue.** Apply this
  fixedness threshold:
  - `fixed`: at least two of the three votes are `fixed`.
  - `persists`: at least two of the three votes are `persists`.
  - `unknown`: no majority (e.g., one vote each, or two `unknown`).
  A missing or malformed vote counts as `unknown`.

Write `<findings_dir>/fixedness.json` as a flat list with **exactly one entry
per unmatched open issue**:

```json
[{"fingerprint": "...", "verdict": "fixed|persists|unknown|not-detected"}]
```

Do not write one entry per checker vote. If an issue has three checker
verdicts, they must be merged into a single entry before writing the file.

A missing entry for an unmatched open issue leaves it open with a warning.
`unknown` means the panel could not decide (possibly stale) and leaves the
issue open.

## Step 5: Write the overview report

Write the overview document to `<reports_dir>/<review_date>-<HHMM>.md`
(e.g. `2026-08-05-2114.md`) so same-day runs do not conflict. The report is
Markdown with this frontmatter:

```yaml
---
title: "Weekly icon4py review <review_date>"
tags:
- review
created: <review_date>
icon4py_commit: <icon4py_commit>
---
```

The `icon4py_commit` frontmatter field lets the next run's `run.sh` compute a
diff baseline from this report. Put the same commit in the body metadata too.

The body includes:

- Run metadata: date, run id, icon4py commit.
- Summary counts: total findings reviewed, findings submitted to the panel,
  new accepted findings, merged duplicates, rejected findings, uncertain
  findings, and the fixedness outcome for existing open issues.
- A table of new accepted findings keyed by `fingerprint`, with title,
  severity, confidence, and file.
- A table of merged duplicates: new finding title, existing issue id, and
  confidence.
- A table of rejected findings with title, the skeptic verdicts, and the file.
- A table of uncertain/ambiguous findings with title, verdicts, and note.
- A table of fixedness outcomes: issue id, verdict, and a note.
- Notes on any reviewer, skeptic, or fixedness failures.
