---
name: reviewing-a-proposal
description: Use when asked to review, critique, or sanity-check a design proposal in the icon4py knowledge base — "review this proposal", "is this design sound?", "run the red flags over content/personal/...", "what is wrong with this spec?" — or when reviewing a pull request that adds or edits a document under content/. Runs content/knowledge/software-engineering/principles.md and its red-flag checklist over the document (shallow abstraction, information leakage, temporal decomposition, special-general mixture, vocabulary drift, unstated requirements), names every principle the proposal knowingly trades away, and recommends a status of draft, reviewed, or final. Do not use to write or restructure a proposal, to compare proposals for overlap, or to review icon4py source code.
---

# Reviewing a proposal

`AGENTS.md` promises contributors that the red-flag checklist in
`content/knowledge/software-engineering/principles.md` "is what a reviewer will run
over your proposal". This skill is that reviewer.

The subject is a **design**, not code and not prose. The question is never "is this
well written" but "does this design hide the right decisions, and does it say what it
is trading away".

## Read the checklist from the file, every time

Open `content/knowledge/software-engineering/principles.md` and work from **its**
current text. Do not review from memory and do not copy the checklist into this skill —
one rule set, one source. If that file is absent from the branch you are on, say so and
stop; the review has no standard without it.

The sections you will use most:

- **§2 Modules and interfaces** — depth, information hiding, leakage, decomposition
- **§3 Domain modelling** — ubiquitous language, explicit concepts, anemic models
- **§4 Architecture and strategy** — goals, constraints, bounded contexts, trajectory
- **§6 Red-flag checklist** — the pass a reviewer runs last

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

Walk §2–§4, translated for a design document rather than a diff:

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

### 4. The red-flag pass

Run §6 item by item over the design. For each flag that fires, cite the section of the
proposal and state the consequence in terms of icon4py, not in the abstract.

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

- The checklist was read from `principles.md` on this branch, not from memory.
- Findings cite a section of the proposal and a named principle.
- Consequences are stated in icon4py terms, not as abstract violations.
- Knowing trades are separated from silent violations.
- The status was recommended, not changed.
- No rewriting of the proposal — that is `drafting-a-proposal`.
