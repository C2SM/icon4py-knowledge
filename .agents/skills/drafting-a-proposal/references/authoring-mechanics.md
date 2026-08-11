# Authoring mechanics

Everything file-shaped about a proposal in this repository. The judgment lives in
`SKILL.md`; this is the part a script would do if we had one.

## File layout

```
content/personal/<handle>/
  <slug>.md                    # single-file proposal
  <slug>/                      # REQUIRED as soon as there is more than one file
    <slug>.md                  # the main proposal — same name as the directory
    <slug>_research.md         # background, prior art, evidence
    <slug>_<topic>.md          # further appendices
```

- `<handle>` is your GitHub handle.
- `<slug>` is free-form kebab-case. No numbering, no dates.
- Growing past one file means **moving** into a `<slug>/` directory and renaming the
  main note to `<slug>/<slug>.md`. Do not leave a stray sibling file.
- Illustrative implementations, scripts and images live inside the `<slug>/`
  directory.

## Frontmatter

```yaml
---
title: Human-readable title
author: <handle>
tags: [keyword1, keyword2]   # the topics this document actually discusses
created: YYYY-MM-DD
status: draft
---
```

- `updated: YYYY-MM-DD` is optional and used by some proposals for revised specs.
- `draft: true` (distinct from `status`) keeps a note out of the published site while
  still committing it.
- `tags` must use the same vocabulary as the index keywords — reuse existing terms
  (`dace`, `unstructured`, `type-system`, `components`, `model-state`) rather than
  inventing synonyms, so related ideas cluster.

### `status` semantics

| Value | Meaning |
|---|---|
| `draft` | Still taking shape. **AI-generated content stays here until a human reviews it.** |
| `reviewed` | At least one person has reviewed the content. |
| `final` | Clear enough to implement, but should still be reviewed by another person. |

A proposal in `content/shared/` can never return to `draft`.

## The TL;DR

The template opens with `> **TL;DR** One sentence on what this proposes.` Treat it as
load-bearing: it is what `cross-checking-proposals` reads when scanning candidates, and
what a reviewer reads before deciding to read the rest. State the *decision*, not the
topic.

## Cross-references

Obsidian-style wikilinks, resolved by Quartz:

```markdown
[[personal/jcanton/model-state/model-state|Model state]]
[[knowledge/software-engineering/principles|Working Principles]]
```

Paths are relative to `content/`. Always give a label after `|` — bare paths read
badly on the published site.

## The index entry

`content/index.md` is the map of everything here and the first thing readers and
agents consult. **Every** add, rename, move or removal updates it in the same change.

```markdown
### <handle>

- [[personal/<handle>/<slug>|Title]] — keywords: keyword1, keyword2, keyword3
```

- Group under a `### <person>` subsection of **Personal**.
- Index **only the main proposal** — never its appendices or implementation subdirs.
- Keywords must match the document's `tags`.
- Documents under `content/knowledge/` are indexed under **Knowledge**; they are
  reference material, never move to **Shared**, and are not retired when a proposal
  graduates.

## Supersession header

When a document replaces an earlier version, open it with an explicit block:

```markdown
> **Supersedes** [[personal/<handle>/<slug>/<slug>_specV2|spec v2]].
> **Dropped:** the global mutable container (v2 §4) — incompatible with restart, see
> [[personal/jcanton/model-state/model-state#Restart is the requirement that settles R8 and R11]].
> **Carried forward:** the field-metadata contract, unchanged.
```

What was dropped and why is the part that matters. A new version that silently loses
the old one's constraints has lost the argument that produced them.

## Python version assumptions

Proposals may freely assume **Python 3.11+**. If a design benefits from 3.12+
features, note the minimum version explicitly. If features of **3.13 or newer** would
simplify the design, include them (noting the version) rather than designing around
their absence.

## Publishing

- Anything under `templates/`, `private/` or `.obsidian/` is excluded from the site.
- No local build is needed to author — push to `main` deploys via
  `.github/workflows/deploy.yml`.
