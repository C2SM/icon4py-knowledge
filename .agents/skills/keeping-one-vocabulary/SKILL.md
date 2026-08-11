---
name: keeping-one-vocabulary
description: Use when a proposal in the icon4py knowledge base introduces, renames, or disputes a domain term — component, model state, registry, field factory, tendency, carry, step, driver, granule — or when two documents use one word for different things or different words for one thing. Also use for "what should we call this?", "is this term already taken?", "these proposals mean different things by state". Checks the term against the shared glossary and existing proposals, settles on one meaning per term, updates the glossary, and records every collision as an explicit conflict in the affected documents. Do not use to rename symbols in icon4py source code, to choose file or directory names, or for general prose or grammar editing.
---

# Keeping one vocabulary

One term, one meaning — in discussion, in proposals, and eventually in icon4py.

This is the cheapest conflict to fix and the most expensive to leave, because it
hides. Two proposals using *state* for different things read as if they agree. A
reviewer, a newcomer, and a future implementer each pay for that agreement being
false.

The glossary is `content/knowledge/glossary.md`. It is reference material, indexed
under **Knowledge**, and — like `principles.md` — it changes only through reviewed
pull requests.

## Bootstrap: if the glossary does not exist

On first use, create `content/knowledge/glossary.md` from
[references/glossary-template.md](references/glossary-template.md), then add its index
entry under **Knowledge** in `content/index.md`:

```markdown
- [[knowledge/glossary|Glossary]] — keywords: glossary, vocabulary, ubiquitous-language, naming, terms
```

Seed it **only from terms already in use**, each with the document that uses it. Do not
invent definitions for contested terms — record the competing meanings as contested and
leave the resolution to humans. A glossary that asserts a winner nobody agreed to is
worse than no glossary.

## Workflow

### 1. Collect every meaning in use

Search `content/` for the term and its obvious variants. For each hit, record:

- the document and author,
- the meaning **as used there**, in one line,
- whether it names a *thing*, a *role*, or an *operation*.

Search the concept, not only the string: `StateView`, `StateProvider`, `ModelState` and
"the container" may all be the same concept under four names. That is the same finding
in mirror image.

### 2. Diagnose which failure this is

| Failure | Shape | Fix |
|---|---|---|
| **Collision** | One word, several meanings | Give each concept its own word. The incumbent meaning usually keeps the word. |
| **Synonyms** | Several words, one meaning | Pick one. Record the others as *deprecated aliases* so search still finds them. |
| **Missing word** | A concept discussed only in circumlocution ("the thing that owns field lifetimes") | Name it. An awkward phrase repeated across documents is a concept demanding a name. |
| **Borrowed word** | A term from ICON, gt4py, or CF conventions used with a local twist | Say which meaning applies here, and cite the source of the other. Do not silently redefine an upstream term. |

A phrase that is hard to say in a design discussion is a model smell, not a wording
problem. Fixing the word usually means the model was fuzzy.

### 3. Propose one meaning per term

For each affected term write the glossary entry: the term, one-sentence definition,
the document that anchors it, and — where the term is borrowed — the upstream source
it aligns with or departs from.

Where the meaning is genuinely contested between open proposals, do **not** resolve it.
Record it under *Contested terms* with each meaning, its document, and what decision
would settle it. Then treat it as a conflict.

### 4. Record collisions as conflicts

A vocabulary collision is a model conflict. In each affected document, add a line under
`## Open questions / conflicts` naming the collision and linking the other document with
`[[wikilinks]]` — in both directions, exactly as `cross-checking-proposals` requires.

### 5. Keep the surface in sync

- Glossary entry added or updated.
- `tags` and index keywords use the settled term (and not its deprecated aliases).
- Affected proposals updated *only* to add the cross-reference — do not rewrite another
  contributor's argument. Renaming their term is their call, not yours; propose it in
  the pull request.

## Output

- The term(s), each meaning found, and the document behind it.
- The diagnosis: collision, synonyms, missing word, or borrowed word.
- The proposed single meaning, or an explicit *contested* record with what would settle
  it.
- The glossary diff and the cross-references added.

## Quality bar

- Every meaning is evidenced by a document, never asserted from general knowledge.
- Contested terms are recorded as contested, not silently resolved.
- Upstream terms (ICON, gt4py, CF standard names) are not redefined without saying so.
- Collisions appear in both documents.
- The glossary stays a list of terms — arguments belong in proposals.
