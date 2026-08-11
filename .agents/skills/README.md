# Agent skills

Repository-specific skills for agents working in the icon4py knowledge base. They
encode *this repository's* workflow — its artifacts, its index, its status gates — and
are not general software-engineering advice. Each is self-contained: the standard a
skill applies lives in the skill.

## What is not an agent's to read

`content/knowledge/` is written **for humans** — material a person consults while
deciding how to write or judge a design. No skill reads it, cites it, or depends on it:
guidance a human weighs is not a procedure an agent executes, and an agent reciting a
checklist over every proposal produces the appearance of review rather than review.

The rule takes no exceptions, which is what makes it applicable without judgement: if
a document lives under `content/knowledge/`, a skill does not touch it. Artifacts both
humans and agents maintain live outside that directory — which is why the shared
vocabulary is `content/glossary.md`. When adding a document, that placement *is* the
decision about who reads it; there is no second decision to make later.

## Location

Skills live in `.agents/skills/`, the vendor-neutral location. `.claude/skills` is a
symlink to it, so Claude Code discovers them without a second copy. Other clients that
look elsewhere can be pointed here the same way — add a symlink, never a copy.

## The set

| Skill | Answers |
|---|---|
| [drafting-a-proposal](drafting-a-proposal/) | I have an idea — how do I write it up here? (also: restructure or supersede one) |
| [cross-checking-proposals](cross-checking-proposals/) | How does this relate to what already exists? |
| [reviewing-a-proposal](reviewing-a-proposal/) | Is this design sound, and what does it trade away? |
| [keeping-one-vocabulary](keeping-one-vocabulary/) | What do we call this, and does anyone else already use that word? |
| [graduating-a-proposal](graduating-a-proposal/) | Is this ready to move to `shared/`, or into icon4py? |

They compose: drafting calls cross-checking and vocabulary; graduating calls reviewing
and cross-checking. Each stands alone.

### Boundaries

The pair most likely to be confused is **cross-checking** (many documents, relations
between them) and **reviewing** (one document, its quality). Each names the other as a
non-goal in its description; that boundary is what the trigger evals stress hardest.

## Triggering

A skill only helps if it activates, and the `description` field carries the whole
burden — agents see nothing else until they load it. The descriptions here follow the
[Agent Skills guidance](https://agentskills.io/skill-creation/optimizing-descriptions):
third person, imperative "Use when…", user intent rather than mechanism, explicit
negative triggers, under the 1024-character limit.

They deliberately name repository-specific things — `content/personal/`,
`content/index.md`, `status: draft`, `[[wikilinks]]`, and real icon4py terms — so they
do not fire when an agent is working in the icon4py source tree.

## Evaluating the triggers

Each skill ships `evals/trigger-queries.json`: realistic prompts labelled
`should_trigger`, half of them near-misses that share vocabulary with the skill but need
something else. Weak negatives ("write a fibonacci function") test nothing; the useful
ones are the neighbouring skill's queries.

The loop, per the guidance above:

1. Run each query 3× and compute a trigger rate; a query passes at a rate above 0.5.
2. Split the set ~60/40 into train and validation. Optimize against train only.
3. Revise the description — broaden if should-trigger queries miss, add specificity or
   sharpen the non-goals if should-not-trigger queries fire.
4. Select the iteration with the best *validation* pass rate, which is often not the
   last one.

Avoid adding failed queries' keywords verbatim; that is overfitting. Address the
category they represent.

Also run the five sets **together**, not just per skill: with all descriptions loaded,
the right skill must win. Per-skill evals cannot catch the cross-checking/reviewing
confusion.

Tooling worth using rather than hand-rolling:

- [`skill-creator`](https://github.com/anthropics/skills/tree/main/skills/skill-creator)
  — automates the split, the parallel trigger evaluation, and description revision.
- [`skillgrade`](https://github.com/mgechev/skillgrade) — grades *outcomes*; fits
  drafting and graduating, which produce inspectable files, less so reviewing, whose
  output is a judgment.

## Adding a skill

Keep the set small and the boundaries sharp. A new skill needs a question none of the
five already answers, a description that names its non-goals, and an eval set whose
negatives are the existing skills' positives.

What is mechanical does not belong here: index currency, frontmatter validity, and
keyword/`tags` drift want a checker in CI, not a skill. A skill that has an agent
repeat what a script could do reliably is a skill in the wrong place.

Neither does anything `AGENTS.md` already says. It is loaded into every agent's context
in this repository, so a skill restating its frontmatter fields, `status` semantics or
index rules is not progressive disclosure — it is a second copy of something already
present, and the two drift. Carry only what `AGENTS.md` does not, and point at it for
the rest. A `references/` file earns its place when the material is genuinely extra and
genuinely occasional; `keeping-one-vocabulary`'s glossary template is the example.
