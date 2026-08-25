---
name: graduating-a-proposal
description: Use when deciding whether a proposal in the icon4py knowledge base is ready to move from content/personal/<handle>/ to content/shared/, to change status from draft to reviewed or final, or to graduate into real work in icon4py as a pull request or ADR — "is this ready for shared?", "promote this proposal", "turn this into an icon4py ADR", "can we implement this now?", "can we retire this note?". Checks the readiness evidence (open questions resolved, conflicts recorded, alternatives named, scope implementable, a human has reviewed), then performs the move, the status change, and the index update. Do not use for a first draft, for design-quality review, or to open or manage pull requests in the icon4py repository.
---

# Graduating a proposal

A proposal's life here is: `content/personal/<handle>/` → `content/shared/` → real
work in icon4py → retired. Each step is one-way. This skill is the gate.

The gate exists because the moves are cheap to make and expensive to undo: a proposal
in `shared/` can never return to `draft`, and a proposal deleted after graduation takes
its rationale with it.

## The moves

| Move | What it asserts | Who decides |
|---|---|---|
| `status: draft → reviewed` | A person has read it | A human, not an agent |
| `status: reviewed → final` | Clear enough to implement | The author, after review |
| `personal/ → shared/` | The group broadly agrees; implementation-ready | The team, via PR review |
| graduate to icon4py | It is now a PR or an ADR in the source repo | The icon4py maintainers |
| retire | It has landed in icon4py | Whoever merged it |

## Workflow

### 1. Check the readiness evidence

Each item is verifiable in the document. Report the ones that fail; do not fill them in
yourself.

- **A human has reviewed it.** `status` is not `draft`. AI-generated content does not
  promote itself, and this check is not satisfiable by the agent performing it.
- **Open questions are resolved or explicitly deferred.** An unresolved question that
  blocks implementation blocks the move. A question deferred *with a reason* does not.
- **Conflicts are recorded, in both directions.** Run `cross-checking-proposals` if the
  document has no conflicts section, or if proposals have landed since it was written.
  Promoting one side of an unrecorded conflict into `shared/` is how the group ends up
  agreeing to two incompatible things.
- **Vocabulary is settled.** No contested terms left unmarked — see
  `keeping-one-vocabulary`.
- **An alternative is named and rejected**, with a reason. A design nobody compared is
  not implementation-ready, however detailed.
- **Scope is implementable.** Someone could start on Monday: interfaces named,
  boundaries drawn, first step obvious. "Concrete enough to implement in icon4py" is the
  stated bar for `shared/`.
- **Appendices are appendices.** The main note carries the decisions; research and
  evidence sit in `<slug>_research.md`.

If the design has never been reviewed, run `reviewing-a-proposal` first and attach its
verdict. A promotion without a review is a promotion on vibes.

### 2. Perform the move

**To `content/shared/`:**

- `shared/` is flat: `content/shared/<slug>.md`, or `content/shared/<slug>/<slug>.md`
  if the proposal has appendices. Move the whole directory, not just the main note.
- Move the index entry from **Personal** to **Shared**, keeping the keywords verbatim.
- Fix inbound `[[wikilinks]]` in other documents — the path changed, and Quartz will not
  resolve the old one.
- Raise `status` if the move justifies it. It can never go back to `draft`.
- This is a reviewed pull request, always. Say so, and open it as a PR rather than
  pushing.

**To icon4py:**

- The deliverable in the source repo is a pull request or a formal ADR — this
  repository is neither. Prepare the content; the icon4py maintainers own the merge.
- Carry the *decision and its rationale*, not the exploration. The ADR wants context,
  decision, alternatives, consequences.
- Link back to the proposal with a **commit-pinned permalink** — `.../blob/<full-sha>/`
  followed by the proposal's path *as it is at that commit*, which is usually
  `content/shared/...` by the time anything graduates. Do not assume
  `content/personal/`, and do not use a branch link: retirement deletes the path, so
  the exploration stays findable only if the link names a commit that still contains
  it.

**Retiring:**

- Delete the file (and its directory) and its index entry, in the same change, once the
  work is merged in icon4py.
- Check for inbound wikilinks first and repoint them at the icon4py PR or ADR. A
  retired proposal that other documents still link to leaves dead ends on the published
  site.
- `content/knowledge/` and `content/glossary.md` are never retired this way — they are
  reference material and a term registry, not proposals.

### 3. Stop at the human boundary

Prepare the change; do not merge it. `personal/ → shared/` and any icon4py change are
human decisions made through review. Present the readiness evidence, make the edits on
a branch, and hand over.

## Output

- **Verdict**: ready, or not — with the failing evidence named.
- **Evidence table**: each readiness item, pass/fail, and where you checked.
- **Changes made**: files moved, index entries updated, wikilinks repointed, status
  changed.
- **Left to a human**: the review, the merge, and anything you declined to decide.

## Quality bar

- Every readiness item was checked against the document, not assumed.
- The "a human has reviewed it" check was never self-satisfied by the agent.
- Index and inbound wikilinks were updated in the same change as the move.
- `status` never moved backwards, and never toward `draft` from `shared/`.
- Nothing was merged, and nothing was deleted before it had actually landed in icon4py.
