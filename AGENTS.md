# icon4py Knowledge Base — Agent Instructions

This repository collects **design ideas and proposals** for
[icon4py](https://github.com/C2SM/icon4py). It is a low-barrier place to drop a
design, sketch, or proposal so that anyone — human or agent — can cross-check a
new idea against what already exists and spot overlaps or conflicts early.

It is **not** the icon4py source tree and **not** the formal ADR record. It is a
[Quartz](https://quartz.jzhao.xyz/) digital garden: all Markdown under
`content/` is published to GitHub Pages by `.github/workflows/deploy.yml` on
push to `main` (the workflow clones Quartz at build time — nothing is vendored
here). No local build is needed to author; just edit Markdown.

## Skills

Repository-specific agent skills live in `.agents/skills/` (`.claude/skills` is a
symlink to it). If your agent does not discover them automatically, read the relevant
`SKILL.md` directly — they carry the procedures this file only summarizes:

| Skill | Use it when |
|---|---|
| `drafting-a-proposal` | writing up a new idea, or restructuring/superseding an existing one |
| `cross-checking-proposals` | asking how a proposal relates to what already exists |
| `reviewing-a-proposal` | judging whether a proposal's design is sound and what it trades away |
| `keeping-one-vocabulary` | introducing, renaming, or disputing a domain term |
| `graduating-a-proposal` | moving a proposal to `shared/`, changing its status, or retiring it |

See [`.agents/skills/README.md`](.agents/skills/README.md) for how they compose and how
their triggers are evaluated.

## Layout

```
content/
  index.md              # landing page = the keyworded, hierarchical index (see below)
  glossary.md           # shared vocabulary: one term, one meaning
  knowledge/            # written for humans — agents do not read it
  personal/
    <person>/                   # one subdirectory per contributor
      <proposal>.md             # a single-file proposal/idea
      <proposal>/               # a multi-file proposal/idea (REQUIRED if >1 file)
        <proposal>.md           # the main proposal/idea
        <proposal>_research.md  # optional appendix: background, research, prior art
        <proposal>_<topic>.md   # optional further appendices
  shared/               # proposals accepted and implementation-ready (only touch with PR review)
  templates/            # idea template (NOT published — see ignorePatterns)
```

- **`index.md`** — the map of everything here; every add, rename, move or removal
  updates it in the same change (see *Keep the index useful*).
- **`glossary.md`** — the shared vocabulary: one term, one meaning. Both humans
  and agents read **and** write it; it is a registry of the terms actually in
  use, not advice. Changes only through reviewed pull requests.
- **`knowledge/`** — reference material written for humans. **Agents must not
  read, cite, or apply it**, and no skill may depend on it. Shared human/agent
  artifacts live outside it — hence `glossary.md` at the root.
- **`personal/<person>/`** — your working area. Use your GitHub handle as the
  directory name. Filenames are free-form kebab-case slugs; no numbering.
- **`shared/`** — flat directory of proposals the group broadly agrees, which
  should be concrete enough to implement in icon4py; a proposal can be moved here
  only with PR review.
- **`templates/`** — the idea skeleton to copy when authoring. Not published.
- An accepted idea that becomes concrete graduates to real work in icon4py (a PR,
  or a formal ADR in the icon4py repo); it can then be retired from here.

## Authoring a proposal

1. Copy `content/templates/idea.md` to `content/personal/<your-handle>/<slug>.md`.
   If the proposal later grows beyond one file (appendices, implementation
   sketches, etc.), move it into a dedicated `content/personal/<your-handle>/<slug>/`
   directory and rename the main note to `<slug>/<slug>.md`.
2. Fill the frontmatter:
   ```yaml
   ---
   title: Human-readable title
   author: <your-handle>
   tags: [keyword1, keyword2]   # the topics this document discusses
   created: 2026-06-11
   status: draft
   ---
   ```
   The `status` field can be any of:
   - `draft` — still taking shape; AI-generated content should stay here until a human
      reviews the content.
   - `reviewed` — at least one person (e.g. the author) has reviewed the content.
   - `final` — clear proposal that could be implemented, but should still be reviewed
      by another person.

3. Before writing, **skim the index and existing proposals** for overlap; link
   related/conflicting documents with `[[wikilinks]]` and call out the conflict
   explicitly. Surfacing conflicts is the whole point of this repo.
4. Cross-reference other notes with Obsidian-style `[[path/to/note|label]]`
   links — Quartz resolves them.
5. **Update `content/index.md`** (next section). This is required.

## Python version assumptions

- Proposals **may freely assume Python 3.11+**, matching icon4py's supported
  Python versions. If a design benefits from Python 3.12+ features, note the
  minimum version explicitly.
- If features of **Python 3.13 or newer** would simplify or improve a design,
  **include them** in the design (note the minimum version they require) rather
  than designing around their absence.

## Keep the index useful

`content/index.md` is the map of everything here and the first thing readers
and agents consult. It must stay current and keyword-rich:

- **Every** time you add, rename, move, or remove a document, update its index
  entry in the same change.
- Each entry is a wikilink plus a short **keywords** list naming the topics the
  document actually discusses — e.g.
  `- [[personal/havogt/field-origin|Field origin rework]] — keywords: fields, domain, origin, embedded`.
  Keywords are what let people scan for overlapping ideas, so make them specific
  and honest about the content.
- Keep an entry's keywords **in sync with the document's `tags` frontmatter**
  (same vocabulary; Quartz also builds tag pages from `tags`).
- Group entries under a `### <person>` subsection of **Personal**. Index
  **only the main proposal** document — do **not** add index entries for its
  appendices (`<slug>_research.md`, `<slug>_<topic>.md`) or implementation
  subdirs. Reference those from within the proposal document itself (with
  `[[wikilinks]]`), so the index stays a flat map of proposals.
- Proposals that are actively being considered by the team should be moved from
  `personal/<person>/` to `shared/`, and must only be changed with reviewed PRs.
  At this point, a shared proposal cannot go back to the `draft` status. Also,
  move its index entry from **Personal** to **Shared**, keeping the keywords.
  After a proposal is implemented and merged to icon4py, delete the file and its
  index entry.
- Documents under `content/knowledge/` go under **Knowledge**, and `glossary.md`
  under **Glossary**. Neither is a proposal: they never move to **Shared** and are
  not retired when a proposal graduates.
- Prefer one consistent keyword vocabulary across entries (e.g. reuse `dace`,
  `unstructured`, `type-system`) so related ideas cluster and conflicts surface.

## Publishing notes

- `baseUrl` in `quartz.config.ts` must match the final GitHub Pages URL of this
  repo; update it if the repo moves.
- Anything under `templates/`, `private/`, or `.obsidian/` is excluded from the
  published site (`ignorePatterns`). Use `draft: true` in frontmatter to keep an
  in-progress note out of the published site while still committing it.
