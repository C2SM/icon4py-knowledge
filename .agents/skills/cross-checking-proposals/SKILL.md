---
name: cross-checking-proposals
description: Use when someone asks whether an idea for icon4py already exists or clashes with an existing one — "does this overlap with anything?", "has anyone proposed this?", "check this against the other component and state proposals", "what conflicts with model-state?" — and before any proposal in this knowledge base is reviewed, moved to content/shared/, or merged. Scans content/index.md keywords and document tags, reads candidate TL;DRs, classifies each relation as duplicate, conflicting decision, or complementary, and records the conflict explicitly in both documents with [[wikilinks]]. Do not use to judge whether a single proposal is well designed, for literature or web research, or to find duplicated code in the icon4py source tree.
---

# Cross-checking proposals

Surfacing overlaps and conflicts early is the entire reason this repository exists.
The failure it prevents is the one already visible in the content: several
incompatible designs for the same problem, each written as if it were the only one.

This skill answers one question — **how does this document relate to the others?** —
and refuses the adjacent ones. Whether a proposal is any good is
`reviewing-a-proposal`. What a term means is `keeping-one-vocabulary`.

## Workflow

### 1. Extract the claim, not the topic

From the document (or the contributor's description), write down:

- the **problem** it addresses, in one line;
- the **decision** it makes about that problem, in one line;
- the **terms** it uses for the moving parts.

Two proposals about "components" are not necessarily related. Two proposals that
decide *where field lifetimes are owned* are, whatever they call it.

### 2. Shortlist from the index

`content/index.md` is a keyword map precisely so this step is cheap. Intersect the
document's `tags` and problem terms with the index keywords, and read across **all**
sections — Personal, Shared, and Knowledge.

Widen once, deliberately: search for the *concept* under other names. A proposal about
`StateProvider` will not match the keyword `model-state`, and that mismatch is itself a
finding for `keeping-one-vocabulary`.

### 3. Read narrowly

Proposals here run to tens of thousands of words. For each shortlisted candidate read
only:

- the frontmatter (`status`, `tags`, `author`),
- the `> **TL;DR**` block,
- any `## Conflicts`, `## Related proposals`, or `## Open questions` section.

Open the full document only when the TL;DR is genuinely ambiguous about the decision.
Reading everything is not thoroughness here; it is how the check stops being run.

### 4. Classify every relation

| Class | Test | What it obliges |
|---|---|---|
| **Duplicate** | Same problem, same decision | One should be retired or merged. Say which, and why. |
| **Conflicting decision** | Same problem, incompatible decisions | Must be named in **both** documents. This is the finding that matters. |
| **Overlapping scope** | Different problems, but one constrains the other | Record the dependency and its direction. |
| **Vocabulary collision** | Same term, different meanings | Hand off to `keeping-one-vocabulary`. |
| **Complementary** | Different problems, shared vocabulary | Link, no action. |

"Related" is not a class. If you cannot say which of these it is, you have not read
enough of the decision.

### 5. Record it in both directions

A conflict recorded in one document only is half-recorded: the other author never
learns of it, and a reviewer coming from the other side sees a clean proposal.

For every **conflicting decision** and **duplicate**:

- add an entry under `## Open questions / conflicts` (or a `## Conflicts with existing
  proposals` section) in the new document, and
- add the reciprocal entry in the other document,
- both with `[[wikilinks]]` and one sentence naming *what is incompatible* — not
  "overlaps with X" but "X owns field lifetimes at run time; this owns them at setup
  time; both cannot hold".

Editing another contributor's file under `content/personal/` is a change to their work:
make it a separate, clearly-described commit in the pull request, and never alter their
argument — only add the cross-reference. Documents in `content/shared/` change only
through reviewed PRs.

### 6. Escalate, do not adjudicate

Where two proposals genuinely disagree, the resolution is a human decision. State the
disagreement precisely, name what evidence would settle it, and leave it under
`## Open questions for humans`. Do not declare a winner.

## Output

A relation table:

| Document | Class | What is incompatible / shared | Action taken |
|---|---|---|---|

plus the reciprocal edits made, and any vocabulary collisions handed off.

If nothing related exists, say so plainly and name the keywords you searched — a
negative result is only useful if its coverage is visible.

## Quality bar

- Every relation is classified, not just listed.
- Conflicts are recorded in both documents, with the incompatibility stated.
- The search terms used are reported, including the widened ones.
- No proposal was judged on quality, and no conflict was resolved unilaterally.
- Candidates were read by TL;DR first — context spent is proportional to the finding.
