# icon4py weekly review

An automated weekly review of [C2SM/icon4py](https://github.com/C2SM/icon4py).
It runs on a schedule in CI and can be run locally for testing.

The review is currently limited to performance and correctness issues,
high-severity issues, and will only be reported if all three of a three-member
skeptic panel verifies the issue as real. This is tuned to avoid reduce noise
from too many issues being reported and to avoid false positives. This can be
tuned over time to include lower severity issues and different types of issues.

## What it does

Each run reviews the icon4py checkout at a given commit and writes accepted
findings as issue files under `content/review/issues/`, plus an overview report
under `content/review/reports/`. The workflow is defined in
[`SKILL.md`](SKILL.md) and executed by an isolated `pi` orchestrator:

1. **Reviewers.** `icon4py-correctness-reviewer` and
   `icon4py-performance-reviewer` search the checkout. They read
   `open-issues.json` (existing issues, so they do not re-report them) and
   `changes.diff` (code changed since the last review, so they prioritize it).
2. **Skeptic panel.** Each candidate finding gets three `icon4py-finding-skeptic`
   votes. A finding is accepted only if all three vote `PASS`; any `REJECT`
   rejects it; matching `DUPLICATE` votes merge it into an existing issue.
3. **Fixedness.** Existing open issues not matched by a new finding get three
   `icon4py-fixedness-checker` votes (`fixed`, `persists`, `unknown`) to track
   whether known problems are still present.
4. **Reconcile and publish.** `reconcile-issues.py` writes accepted findings as
   issue files and updates fixedness. `update-index.py` regenerates
   `content/review/index.md`.

```
 host (run.sh)                  sandbox (pi orchestrator)
 --------------                  ----------------------
 open-issues.json -------------+-> reviewers --> correctness.json
 changes.diff -----------------+              performance.json
                                               |
                                               v
                                        finding-skeptic x3 --> votes/.../*.json
                                               |
                                               v
                         fixedness-checker x3 (only issues not matched
                           by a new finding, with a changed commit)
                                               |
                                               v
                           accepted.json  duplicates.json  fixedness.json
                           <-----------   overview report <----------

 reconcile-issues.py --> content/review/issues/<id>.md
 update-index.py     --> content/review/index.md
```

Reviewers and checkers cannot run `git` or `bash`: they run in a `bwrap`
sandbox with a read-only checkout and a narrow writable findings directory. The
host generates `open-issues.json` and `changes.diff` and places them where the
sandbox can read them.

## Inputs and secrets

- `CSCS_INFERENCE_API_KEY`: API key for the inference provider. Required.
- `GITHUB_TOKEN`: used only by `commit-and-pr.sh`, outside the sandbox, to open
  the pull request. Not forwarded into the sandbox.
- `ICON4PY_CHECKOUT`: absolute path to a clone of `C2SM/icon4py`. Required for
  local runs; set by the workflow in CI.

## Run locally

```bash
ICON4PY_CHECKOUT=/path/to/icon4py ./scripts/icon4py-review/run.sh
```

This produces changes for inspection without committing. Add `--commit-and-pr`
to commit the result and open a pull request (requires `gh` and `GITHUB_TOKEN`).

## Files

```
.github/workflows/
  icon4py-weekly-review.yml   # the GitHub Actions workflow
scripts/icon4py-review/
  run.sh                      # entry point: collects inputs, runs the sandbox,
                              # reconciles, validates, regenerates the index
  SKILL.md                    # the orchestrator workflow definition
  agents/                     # correctness, performance, skeptic, fixedness
  settings.json               # pi provider and package config
  models.json                 # model definitions (keys come from env)
  README.md                   # this document
  collect-open-issues.py      # writes open-issues.json from content/review/issues/
  extract-report-commit.py    # reads the previous report's icon4py_commit
  reconcile-issues.py         # writes accepted issues and fixedness verdicts
  validate-issues.py          # checks issue files are well-formed
  update-index.py             # regenerates content/review/index.md
  commit-and-pr.sh            # commits the result and opens a PR (CI only)
scripts/pi-sandboxed.sh       # bwrap sandbox wrapper for pi
```

Each review report records its `icon4py_commit` in the frontmatter. The next run
uses that commit as the diff baseline, so review attention moves forward with
the code while existing issues are tracked separately for fixedness.
