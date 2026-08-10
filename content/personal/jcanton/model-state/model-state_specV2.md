---
title: Model state — spec v2 (proposed revision)
author: jcanton
tags: [state, model-state, spec, requirements, constraints, goals, design-principles, review]
created: 2026-07-31
status: draft
---

> Appendix to [[personal/jcanton/model-state/model-state|Model state]].
> **Proposed** revision of the main document — nothing here has been applied to it. Two inputs:
> a consistency review of the whole doc set, and
> [[knowledge/software-engineering/principles|Working Principles]].
> Split out rather than edited in so the reviewed document stays stable and the changes can be
> argued individually.

## A. Consistency defects in the current doc set

Mechanical, uncontroversial, apply whenever.

| # | Where | Defect |
|---|---|---|
| A1 | `model-state.md:9` vs `:18` | TL;DR says "Four incompatible designs", body says "**Five** designs". The table has four rows, and `:392` says "Four open signatures". Body should read four |
| A2 | `model-state.md` mechanism table | **M13 is missing.** It existed only in the ICON-sc appendix; folding that into prior-art left a gap between M12 and M14, which reads as an editing error. Restore it — see §C |
| A3 | `model-state.md` M1 row | Still says phase `setup, **frozen**` after the freeze requirement was dropped in favour of a staleness guard. Should read `setup, sealed` |
| A4 | `model-state_walkthrough.md:259` | Stale figure "175 lines × ≥3 sites" — corrected elsewhere to ~90 hand-typed mappings × 8 sites. *(Already applied; listed for completeness.)* |

**The pattern behind A1, A3 and A4 is worth more than the fixes.** All three are the same fact
stated in several files and updated in only some — a DRY failure across documents, which the
principles doc names directly ("every piece of knowledge has one authoritative representation —
in code, schema, docs, and build alike"). The earlier freeze-vs-staleness contradiction between
the main doc and prior-art was the same failure. **This will recur**, and the mitigation is to
keep counts and figures in exactly one document and cross-reference rather than restate.

## B. Requirements are an unranked wish list

The single largest finding. `model-state.md` lists R1–R11 flat, with no ranking and no separation
between "violating this makes the design wrong" and "we would like this". The principles doc names
that shape twice — as a red flag (*"advocate-less wish list — requirements accreted by committee,
unweighted, with nobody advocating for the product as a whole"*) and as a rule (*"requirements
need weights and an advocate … rank goals"*). It also supplies the vocabulary to fix it: **goal,
desiderata, constraints, budgeted resource**.

### B1. Split into constraints and ranked goals

**Constraints** — non-negotiable; violating one makes a design wrong, not merely worse.

| # | Constraint | was | Source |
|---|---|---|---|
| C1 | Whatever reaches a `gtx.program` must be a static named collection | R5 | gt4py, structural |
| C2 | The container must **adopt externally-owned buffers** — at `solve_nh_run` ICON owns the memory | R4 | Fortran-embedded path |
| C3 | Granule call sites must keep naming their actual inputs | R9 | the havogt/msimberg objection; also implied by C1 |
| C4 | No new per-stencil-call overhead | R10 | ~100 stencil calls per 20–50 ms timestep |

**Goals** — ranked.

| rank | # | was | Goal |
|---|---|---|---|
| 1 | G1 | R2 | One quantity → one buffer; shape and placement declared once |
| 2 | G2 | R1 | A cross-granule producer→consumer handoff must be *expressible*, so it cannot silently become two allocations |
| 3 | G3 | R3 | A derivation (`vn→u,v`, `theta_v,exner→T,p`) must have exactly one implementation, with its domain and halo semantics part of the declaration |
| 4 | G4 | R8 | Cross-cutting sweeps (output, restart, halo sets) must be queries, not hand-written lists |
| 5 | G5 | R11 | A field's **role is not implied by which container it sits in** |
| 6 | G6 | R6 | Absence must be first-class — optional IAU increments, inactive tracers — not a zero allocation |
| 7 | G7 | R7 | Multi-buffer/time-level must be expressible, at *different rates* |

**Why this ranking.** G1 first because it is the only goal that makes defects *unrepresentable*
rather than merely detected, and because G2, G4 and G5 all lean on it. G7 last because
`TimeStepPair` already works and nothing there is broken.

Applying this means renumbering ~23 references across the four documents. Cheap, and it is the
prerequisite for anyone being able to say "we are taking G1–G3 and stopping".

### B2. Name the budgeted resource

The principles doc: *"Identify the actual budgeted resource (rarely money — latency, bytes,
schedule, attention), track it publicly, and let one person control it."*

**It is reviewer attention, not runtime.** PR 1360 is +28110/−6228 with **zero reviews**; PR 1301
has been open since 2026-06-04 with reviewer requests still unaddressed. Consequences the main
document should state:

- the adoption order matters more than the end state, because each rung has to survive review
  independently;
- **6.7 % was the wrong axis to argue on** — and arguing on it spends the scarce resource on the
  wrong debate.

### B3. Make the user model explicit

*"Better wrong than vague — an articulated guess can be corrected, an unspoken assumption cannot."*
Currently unstated. Proposed:

> The user is a **physics or dynamics developer adding or modifying a scheme** — fluent in ICON
> and gt4py stencils, not a software architect, and not someone who will read a framework manual
> first. Success means adding a field edits **one** place, and a mistake fails at setup naming the
> field rather than producing wrong numbers at timestep 3000.
>
> A second user is easy to forget: the **reviewer**, who must be able to answer "who writes this
> field?" from the diff.

The second one is load-bearing — it is the entire justification for recording `intent`.

### B4. Flag C2 as an unexamined constraint

Red flag: *"designing around a constraint nobody has re-validated"*; and §4: *"list constraints
explicitly up front so you notice when one disappears — sometimes the breakthrough is removing a
constraint, not designing around it."*

C2 (the Fortran-embedded path) is held on the basis that the embedded path is permanent. It shapes
everything: it is why the registry may not own allocation, and why the adopt-external seam exists.
**If it ever stops being true the design gets materially simpler.** Worth re-asking before
committing, and worth stating so a reader knows it was a choice.

## C. Restore M13

Ordering constraints as declared data — `must_follow` / `must_precede` on the component they
belong to, validated when the composition is built.

| | |
|---|---|
| Phase | setup |
| Needs a run-time bucket? | no |
| Requires | M2 |
| Cost | S |

ICON's fast-physics ordering carries implicit contracts: saturation adjustment appears twice per
step, surface transfer must run last, turbulence expects old-time-level inputs. Today those live
in tutorial prose. Declared, they become a build-time assertion.

**This is the safety net [[personal/OngChia/physics-driver-and-components|OngChia's configurable
component order]] needs and does not have** — reordering components is structurally easy and
scientifically treacherous. Caveat from ICON-sc's implementation: it matches on free-form strings,
so a typo in `must_follow` silently passes. Use references, not strings.

## D. Design it twice

*"Sketch at least two genuinely different decompositions before committing; the comparison teaches
even when the first idea wins."* The main document presents one design and defends it. The
alternative belongs on the page.

**Alternative B — declare and *check*, never generate.** Add per-field metadata (M2) and a
validator (M3), then **keep `driver_utils` exactly as it is**. The hand-written wiring stays and
becomes checked: a field whose declared `dims` contradict another container's raises at startup,
and a field-coverage test catches drift. No registry, no `build`, no change to allocation.

| | A — emit the wiring | B — check the wiring |
|---|---|---|
| E7 (wrong keys) | yes — no keyword list survives | yes — the check catches it |
| E2/E8 (contradictions) | yes | yes |
| E6 (boilerplate × 8 sites) | yes | **no** — all of it stays |
| E1's *class* | yes — one buffer per quantity makes it unrepresentable | **no** — a checker can report that two containers disagree; it cannot make them one buffer |
| Cost | M1 + M4, a few hundred declaration lines, allocation moves | M2 + M3 only |
| Risk | new machinery on the setup path | almost none |

**B is not a straw man — it is the honest stopping point**, and it is exactly where the main
document's own adoption order sits after step 3. If the team never goes past M3 that is a coherent
outcome: the correctness defects are fixed and the boilerplate remains. A wins only if E6 and E1's
class are judged worth the extra machinery.

Stating this makes the A-vs-B choice deliberate instead of something that happens by drift.

## E. Open question 3 needs a different kind of answer

Currently: *"PR 1301/1360 vs the layered-architecture refactor vs the two specs: which protocol
wins? Four open signatures is the real blocker."*

The principles doc: *"Guard conceptual integrity — unity, economy, clarity. It comes from one
empowered chief designer (or a two-person team) with genuine design authority, not from committee
negotiation."*

So the question as posed may be unanswerable. **Four drafts merged by negotiation will not produce
a coherent protocol**, and four authors each holding an effective veto is the failure mode. The
productive question is **who decides**, not whose design is best. Proposed rewording:

> Four open signatures is the real blocker — **and it is unlikely to be settled by merging the
> four.** Conceptual integrity comes from one person with genuine design authority over the
> component protocol. The useful question is therefore *who decides*, not *whose design is best*.

## F. Vocabulary that sharpens existing findings

Small, but each replaces a paragraph of description with a name the reader may already hold.

| Finding | Name | Why it fits |
|---|---|---|
| E5 | **Coincidental correctness** | The interpolation buffers *are* shared, because the factory memoizes — but nothing declares it and nothing checks it. It works and nobody can say why. The savepoint test path already breaks the sharing |
| E9 | **Language drift** | Five parallel namespaces per field; the code vocabulary has diverged from any single ubiquitous language |
| E8 | **Repetition** — knowledge represented twice (three times here) | placement in the name string, in `dims`, and in `is_on_half_levels` |
| M1's "unrepresentable" | **Define errors out of existence** | The principle already has a name: redesign so the exceptional case cannot arise, rather than detecting it |
| E7 | **Broken windows** | known-bad code left standing, licensing further decay — three occurrences of two kinds, all still live |

## G. Not proposed

Recorded so it is clear these were considered and rejected:

- **Renaming M-mechanisms to match the principles vocabulary.** The M-numbers are cited across
  four documents and two other people's proposals; churn is not worth it.
- **Restructuring the doc set around the principles' section order.** The current
  problem → requirements → design → mechanisms → order shape is fine, and the principles are a
  review lens, not a template.
- **Changing appendix `status:` to match the main doc's `reviewed`.** That is the author's call.
  Noting only that the appendices hold the evidence for the reviewed claims, so the mismatch is
  slightly odd.
