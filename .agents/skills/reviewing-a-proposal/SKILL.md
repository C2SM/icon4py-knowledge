---
name: reviewing-a-proposal
description: Use when asked to review, critique, or sanity-check a design proposal in the icon4py knowledge base — "review this proposal", "is this design sound?", "what is wrong with this spec?", "critique my draft before the team reads it" — or when reviewing a pull request that adds or edits a proposal under content/personal/ or content/shared/. Checks that the document is answerable (need, users, ranked goals, non-goals, constraints), walks the design defects that recur in this repository, separates trade-offs the author made knowingly from defects the author appears unaware of, and recommends a status of draft, reviewed, or final. Do not use to write or restructure a proposal, to compare proposals for overlap, to review the index or reference material, or to review icon4py source code.
---

# Reviewing a proposal

The subject is a **design**, not code and not prose. The question is never "is this
well written" but "does this design hide the right decisions, and does it say what it
is trading away".

## Scope

Review **proposals**: documents under `content/personal/<handle>/` and
`content/shared/`. The rest of `content/` is not a proposal and this workflow does not
apply to it — `content/index.md` is a map, `content/glossary.md` is a term registry,
and `content/templates/` is a skeleton. If asked to review one of those, say which it
is and review it as ordinary documentation instead.

`content/knowledge/` is written for humans and is not an agent's to read, cite, or
apply — including here. Decline to review it and say why.

## The standard is in this skill

Work from the passes below. They are this repository's review gate, and they are
deliberately self-contained: a review must not depend on any document that a
contributor is free to rewrite between one review and the next.

## Workflow

### 1. Establish what is being proposed

Restate, in your own words: the problem, the decision, and the interface the proposal
introduces. If you cannot restate the decision in one sentence, that is finding
number one — record it and continue. Obscurity is a design defect, not a writing one.

### 2. The requirements pass

Before any design critique, check what the design is answerable to:

- Is there a **need**, with a concrete instance, or only a mechanism?
- Are the **users** named, and are assumptions marked as assumptions?
- Are **goals ranked**, so a reader can tell which one loses in a conflict?
- Are **non-goals** stated?
- Are **constraints** separated into real and assumed?
- What **resource** does this design budget, and does it say when it has overspent it?

A proposal that fails this pass cannot be reviewed on its merits — there is nothing to
hold the design to. Report it as such rather than critiquing a mechanism against
requirements you invented.

### 3. The design pass

Each of these is asked of a design document, not of a diff:

- **Depth** — is the proposed interface simpler than what it hides, or is it a
  relabelling of the implementation? Watch for interfaces whose every parameter is a
  detail of the current code.
- **Information hiding and leakage** — which decision does each module own? A decision
  that appears in three places in the proposal will appear in three places in the code.
- **Decomposition by knowledge, not time** — a live risk here: designs that follow the
  time-loop phase order rather than what each part knows.
- **General over special** — is a special case being solved with a general mechanism it
  does not need, or a general problem with a special-cased mechanism that will not
  extend?
- **Errors defined out of existence** — does the design make invalid states
  unrepresentable, or does it add a validation pass to catch them later?
- **Ubiquitous language** — does the proposal use the terms the rest of the repo uses?
  A new word for an existing concept is a model smell; hand it to
  `keeping-one-vocabulary`.
- **Design it twice** — is an alternative named and rejected with a reason, or is this a
  first idea presented as a conclusion?
- **Trajectory** — does the document record *why*, or only *what*? Rationale is what
  survives contact with the next contributor.

### 4. The recurring-defect pass

These are the failures this repository actually produces, as opposed to the ones design
literature warns about in general. Run them last, when you know the design well enough
to tell a real instance from a superficial match:

- **The mechanism is the requirement.** The document opens with a registry, a
  `StateView`, a protocol — and the need is reverse-engineered to fit it.
- **Phase-ordered decomposition.** The structure follows the time loop's execution
  order rather than what each part knows. Endemic here, because the model has a
  natural phase order to be seduced by.
- **The interface is the implementation, relabelled.** Every parameter is a detail of
  today's code; nothing is hidden, so nothing can change.
- **One decision, three homes.** A choice restated in three places in the proposal will
  be restated in three places in the code, and will drift.
- **A word doing two jobs.** *State*, *component*, *registry*, *field* used with a
  meaning the rest of the repo does not share. Hand it to `keeping-one-vocabulary`.
- **The conflict that is not recorded.** The proposal re-opens a question another
  document settled, without saying so. Hand it to `cross-checking-proposals`.
- **Rationale-free.** The document says what, never why. It cannot survive the next
  contributor, who will not know which constraints are load-bearing.
- **One idea, presented as a conclusion.** No alternative named, so a reader cannot
  tell a considered design from a first draft.
- **Unfalsifiable.** Nothing in the proposal could be shown to be wrong. There is no
  point at which it says "if this is true, we chose badly".

For each that fires, cite the section of the proposal and state the consequence in
terms of icon4py, not in the abstract. A flag you cannot make concrete is a flag you
should drop.

### 5. Name the trades

A proposal is allowed to violate any principle — knowingly and out loud. Separate:

- **traded knowingly**: the proposal names the principle and its reason. Acceptable;
  record it so it stays visible.
- **violated silently**: the proposal appears unaware. This is the finding.

The second list is the review's core value.

### 6. Recommend a status — do not set it

Recommend `draft`, `reviewed`, or `final` with the reason. **Changing the status is a
human act**: AI-generated content stays `draft` until a person reviews it, and moving a
document toward `shared/` is `graduating-a-proposal`. Recommend; never flip.

## Output

1. **What is proposed** — the decision, restated in one sentence.
2. **Requirements pass** — pass, or the specific gaps.
3. **Findings**, most severe first: `severity · section of the proposal · principle ·
   consequence for icon4py`.
4. **Traded knowingly** — principles the proposal consciously gives up, with its stated
   reason.
5. **Status recommendation**, with the reason.
6. **What would change the verdict** — the evidence or decision that would resolve the
   biggest finding.

Keep it short enough to be acted on. A review longer than the proposal is a review
nobody will use.

## Quality bar

- The document reviewed is a proposal, not the index, a template, or reference material.
- Findings cite a section of the proposal and a named defect.
- Consequences are stated in icon4py terms, not as abstract violations.
- Knowing trades are separated from silent violations.
- The status was recommended, not changed.
- No rewriting of the proposal — that is `drafting-a-proposal`.
