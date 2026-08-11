---
name: drafting-a-proposal
description: Use when a contributor wants to write up, restructure, or supersede a design idea in the icon4py knowledge base — "I want to propose X", "write up an idea about Y", "add a note under content/personal/", "write spec v3", "this is too long to review, distill it" — or when a draft names a mechanism without stating the need, users, ranked goals, and non-goals it serves. Establishes requirements before mechanism, forces at least one genuine alternative, and applies this repo's authoring mechanics: the content/templates/idea.md skeleton, frontmatter, [[wikilinks]], appendix layout, supersession headers, and the required content/index.md entry. Do not use to judge whether an existing proposal is well designed, to search for proposals that overlap this one, or to write icon4py source code, tests, or ADRs.
---

# Drafting a proposal

This repository exists so that ideas for icon4py can be cross-checked against each
other before anyone writes code. A proposal earns its place here by being
**reactable**: someone else must be able to disagree with it precisely. That needs a
stated need, named users, ranked goals, and at least one alternative considered and
rejected.

Read `content/knowledge/software-engineering/principles.md` first. It is the
vocabulary this repo argues in; §6 is the checklist a reviewer will run over the
result.

## Workflow

### 1. Separate the need from the mechanism

Requests usually arrive as a mechanism — "let's use a registry", "components should
get a `StateView`". Before writing anything into the document, establish:

- **Need** — what hurts today, with a concrete instance. *"Four incompatible designs
  for how components get their fields are open at once"* is a need. *"We need a
  registry"* is a mechanism wearing a need's clothes.
- **Users** — who is affected: component authors, the standalone driver, the dycore,
  downstream ICON users, people writing tests. Name them, and mark assumptions **as**
  assumptions. Better wrong than vague: a stated assumption can be corrected, an
  unspoken one cannot.
- **Goals, ranked** — when two goals collide, which wins? An unranked list hides the
  decision that matters.
- **Non-goals** — what this deliberately does not attempt.
- **Constraints, audited** — separate *real* (gt4py semantics, Fortran interop via
  py2fgen, restart requirements, Python ≥ 3.11) from *assumed* (habit, the shape of
  today's code). The assumed ones are usually where the design space is hiding.
- **Budgeted resource** — the thing this design spends and must not overspend:
  runtime, memory, developer attention, review capacity, compile time.

If the request cannot be restated as a need, stop and ask the contributor. Do not
invent one.

### 2. Design it twice

Produce at least two materially different approaches before committing to one. Two
variants of the same idea do not count — they must differ in where the complexity
lives. Write down the one you rejected and why; the comparison teaches even when the
first idea wins, and a reviewer cannot tell a considered design from a first draft
without it.

### 3. Check what already exists

Before writing prose, use the `cross-checking-proposals` skill. Surfacing conflicts is
the point of this repo, and a proposal that silently re-opens a settled question wastes
everyone's review. Carry its findings into the document's *Open questions / conflicts*
section as `[[wikilinks]]`, in both directions.

### 4. Name things once

If the proposal introduces or redefines a domain term — *component*, *model state*,
*registry*, *field factory*, *tendency*, *carry*, *step* — use the
`keeping-one-vocabulary` skill before writing. Two proposals using one word for
different things is the most expensive kind of conflict here, because it hides.

### 5. Write the document

Copy `content/templates/idea.md` and fill it. The mechanics — frontmatter fields,
file layout, appendix naming, index entry format, status semantics — are in
[references/authoring-mechanics.md](references/authoring-mechanics.md). Read it before
creating files.

Keep the main document reviewable. Evidence, benchmarks, prior art and transcripts go
into appendices; the main note carries the decisions and their rationale. A proposal
nobody finishes reading has not been proposed.

### 6. Leave the open questions open

End with what you do not know, and what conflicts you could not resolve. A proposal
that answers everything is usually hiding its weakest part. Address unresolved
disagreements to humans explicitly — do not pick a winner on the team's behalf.

## Restructuring or superseding an existing proposal

Same skill, different entry point: the content exists and the problem is its shape.

1. **Split, don't summarize.** Move background, evidence and prior art into
   `<slug>_research.md` or `<slug>_<topic>.md`; keep decisions and rationale in the
   main note. More than one file means the proposal must live in its own `<slug>/`
   directory with the main note at `<slug>/<slug>.md`.
2. **Declare the supersession.** A new version states plainly what it replaces, and —
   more important — **what was dropped and why**. A design's trajectory is worth as
   much as its endpoint; a v3 that silently loses v2's constraints has lost the
   argument that produced them.
3. **Never delete the superseded version silently.** Mark it, link it, and let
   `graduating-a-proposal` handle retirement.
4. **Re-sync the surface**: `status`, `tags`, and the `content/index.md` entry. Only
   the main proposal is indexed — appendices are referenced from inside the document.

## Output

- The proposal file(s) under `content/personal/<handle>/`, with valid frontmatter and
  `status: draft`.
- An updated `content/index.md` entry whose keywords match the document's `tags`.
- Reciprocal `[[wikilinks]]` in every proposal this one overlaps or contradicts.
- A short summary to the contributor: the need as you understood it, the alternative
  you rejected, and the open questions you left for humans.

## Quality bar

- The Problem section names a need, not a solution.
- Users are explicit, and assumptions are labelled as assumptions.
- Goals are ranked; non-goals exist.
- At least one alternative is named and rejected with a reason.
- Every conflict found is recorded in **both** documents.
- `status: draft` stays until a human reviews it — AI-generated content does not
  promote itself.
- The main note can be read end to end in one sitting.
