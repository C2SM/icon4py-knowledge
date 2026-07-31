---
title: Model state — walkthrough
author: jcanton
tags: [state, model-state, walkthrough, pseudocode, registry, contracts, wiring]
created: 2026-07-30
status: draft
---

> Appendix to [[personal/jcanton/model-state/model-state|Model state]]. The proposal explained
> concretely, as before/after pseudocode over icon4py's actual pipeline.
> **None of the code below runs.** Real call sites are cited so you can check the "before"
> against `main`; the "after" is deliberately sketchy where the design is still open.
>
> Checked against `origin/main` at `f94d2d44e` (2026-07-30). **E1 and E2 were fixed the same day**
> by [PR 1404](https://github.com/C2SM/icon4py/pull/1404) (`3c8c69342`) — they are kept below
> because *how* they were fixed is the argument, see Part 3.

## The idea in one sentence

Today the wiring between fields and granules is **hand-written** in `driver_utils.py`; the
proposal is to **declare** what each granule needs and have the wiring **generated at setup**.

The objection this has to survive, from havogt and msimberg: *one global bucket passed around in
its entirety when only part of it would be enough.* That objection is about a **run-time** bucket.
This proposal has none — the registry is a factory floor, not a warehouse. It assembles the typed
containers granules already take, then it is done.

Two names used throughout:

- **ICON-sc** ([[personal/jcanton/model-state/model-state_prior-art|prior art]], §ICON-sc) —
  egparedes' prototype, the only working system in this space we can measure against.
- **named collection** — gt4py's term for something it will accept as a `gtx.program` argument.
  A plain dataclass qualifies; a `dict` never does; **a dataclass with any defaulted field does
  not** (`named_collections.py:34-48`). This constrains the design more than anything else here.

## Part 1 — what happens today

Three phases. The defect labels (E1…E10) point at
[[personal/jcanton/model-state/model-state_evidence|the evidence appendix]].

```python
# ═══ PHASE A: static fields ══════════════════════ setup, once ═══
# driver_utils.py:209 — a NamedTuple of three field sources
static = static_fields.StaticFieldFactories(geometry_field_source,
                                            interpolation_field_source,
                                            metrics_field_source)
# Each source is already lazy and memoized (factory.py:214-256).
# This half of the problem is solved.


# ═══ PHASE B: hand-wire the granule containers ═══ setup, once ═══
# driver_utils.initialize_granules spans 215-458 on origin/main; the wiring
# block is ~90 `.get()` calls of pure hand-typed keyword mapping.
# Replicated in 7 more places: 5 test sites (diffusion fixtures, dycore utils,
# 2 benchmarks, advection utils) AND 2 production sites — the Fortran binding
# wrappers `dycore_wrapper.py:197,238` and `diffusion_wrapper.py:215,233`.

diffusion_interp = diffusion_states.DiffusionInterpolationState(
    e_bln_c_s   = interpolation_source.get(interpolation_attributes.E_BLN_C_S),
    geofac_div  = interpolation_source.get(interpolation_attributes.GEOFAC_DIV),
    ...                                          # 8 fields, all hand-typed
)
dycore_interp = dycore_states.InterpolationState(
    c_lin_e     = interpolation_source.get(interpolation_attributes.C_LIN_E),
    geofac_div  = interpolation_source.get(interpolation_attributes.GEOFAC_DIV),
    ...                                          # 16 fields
)
# ↑ E5: dycore's 16 dataclass fields are a strict superset of diffusion's 8 —
#       the overlap is EXACTLY those 8. (At class level diffusion also has two
#       cached_property members the dycore has no counterpart for.)
#       `geofac_div` is declared in three containers: here, dycore, advection.
#       The buffers ARE shared, because the factory memoizes — but nothing
#       says so, and nothing checks it.
#
# ↑ E7: this exact keyword-list idiom has produced wrong-key bugs. Three live
#       occurrences of two kinds — `d2dexdz2_fac2_mc=...get(D2DEXDZ2_FAC1_MC)`
#       (test_benchmark_solve_nonhydro.py:163) and an edge-normal in a
#       dual-normal slot (same file :98, test_benchmark_diffusion.py:105).
#       Both type-check, both run. NOTE: they live in the *replicated*
#       benchmark sites, not in driver_utils, which is correct at :252,:340 —
#       which is the argument for deleting the replication, not for distrusting
#       this file.
#
# ↑ E6: adding one field to MetricStateNonHydro (32 members) means editing
#       ≥3 call sites in 3 packages.


# ═══ PHASE C: allocate the mutable state ═════════ setup, once ═══
# driver_states.assemble_driver_states — as it was BEFORE 2026-07-30:
prep_adv        = dycore_states.initialize_prep_advection(grid, allocator)
tracer_prep_adv = tracer_advection_states.AdvectionPrepAdvState(
    vn_traj     = data_alloc.zero_field(grid, EdgeDim, KDim, allocator=allocator),
    mass_flx_me = data_alloc.zero_field(grid, EdgeDim, KDim, allocator=allocator),
    mass_flx_ic = data_alloc.zero_field(grid, CellDim, KDim, allocator=allocator),
)
# ↑ E1: the same three physical quantities, allocated TWICE, and no code
#       anywhere copied or aliased one into the other. FIXED by PR 1404.
# ↑ E2: and `mass_flx_ic` disagreed on vertical extent — the dycore's is
#       nlev+1 (`extend={KDim: 1}`), advection's was nlev, so even a copy
#       would not have fit. (`vn_traj`/`mass_flx_me` matched.) FIXED with it.
# ↑ E8: `mass_flx_ic` here vs
#       `dynamical_vertical_mass_flux_at_cells_on_half_levels` there.
#       Same quantity, two names. STILL TRUE.


# ═══ PHASE D: the time loop ══════════════════════ every step ════
# standalone_driver._integrate_one_time_step
for step in range(nsteps):

    # the dycore is itself a loop: _do_dyn_substepping, :352-378
    for substep in range(ndyn_substeps_var):
        solve_nonhydro.time_step(          # keyword-only (solve_nonhydro.py:1114)
            diagnostic_state_nh=diagnostic_state_nh,
            prognostic_states=prognostic_states,
            prep_adv=prep_adv,             # ← dycore ACCUMULATES here, every substep
            lprep_adv=..., at_first_substep=..., at_last_substep=..., ...)
        if not last_substep:
            prognostic_states.swap()       # :376 — inner swap

    diffusion.run(diffusion_diag, prognostic_states.next, dtime)

    tracer_advection.run(diagnostic_state=adv_diag,
                         prep_adv=tracer_prep_adv,   # ← advection READS ONCE per step
                         p_tracer_now=..., p_tracer_new=..., dtime=dtime)
    prognostic_states.swap()               # :295 — outer swap
```

The substep loop is why E1 mattered: the dycore *accumulates* into `prep_adv` across
`ndyn_substeps_var` substeps, and advection reads the accumulated result once. Two disconnected
buffers meant advection consumed zeros.

The important observation, and the whole basis of the proposal:

> **Every one of E1–E10 is decided in phases B and C. Not one of them recurs in phase D.**

The bugs are wiring bugs. They happen once, before the model starts. So the fix belongs there
too — and a fix that lives in phases B and C does not need to exist in phase D at all.

## Part 2 — what is proposed

Same four phases. Phase D is **unchanged**.

```python
# ═══ PHASE A′: DECLARE ═══════════ written once, next to each granule ═══
# The container classes stay exactly what they are — frozen dataclasses that
# granules take as arguments. The only change: each field says what it IS.
# (M2. This is NDSL/Pace's mechanism, verbatim; it is not speculative.)

@dataclasses.dataclass(frozen=True)
class DiffusionInterpolationState:
    e_bln_c_s: gtx.Field = spec(
        quantity  = "e_bln_c_s",             # the canonical name — ONE per quantity
        icon_name = "e_bln_c_s",             # the ICON Fortran name, for the bindings (Part 5)
        dims      = (CellDim, C2EDim),       # placement, single source of truth  → fixes E8
        units     = "1",
        intent    = READ,                    # READ | WRITE | READWRITE — see Part 4
        scope     = STATIC,                  # STATIC (computed once, never rewritten)
                                             # | PERSISTENT (lives across steps, gets written)
                                             # | SCRATCH (granule-private temporary)
        restart   = False,
    )
    geofac_div: gtx.Field = spec(
        quantity = "geofac_div",             # ← same string dycore's container uses
        dims     = (CellDim, C2EDim), units="1", intent=READ, scope=STATIC)
    ...

# `spec(...)` is a thin wrapper over `dataclasses.field(metadata={...})`: it attaches
# metadata and leaves the field with NO DEFAULT VALUE. That matters because gt4py
# refuses any dataclass with a defaulted field as a program argument — so the
# annotation is free, legality-wise. Verified empirically.


# ═══ PHASE B′: REGISTER + EMIT ═══════════════════════ setup, once ═══
#
#   adopt_sources  take already-computed fields from the memoized factories
#   declare        collect a container's schema, so contradictions between
#                  containers are visible at seal()
#   declare_handoff  assert "X is produced here, consumed there"
#   seal           no NEW quantities after this point (existing ones may still
#                  be rebound — see Part 4). Records the schema.
#   build          instantiate ONE declared container. Nothing can be built
#                  that was not declared.
#   adopt_buffers  wrap externally-owned memory (the Fortran path, Part 5)

reg = FieldRegistry(grid, vertical_grid, allocator)

reg.adopt_sources(static_sources)      # metrics/interpolation/geometry are already
                                       # memoized — adopt, do not re-allocate.      (R4)
reg.declare(PrognosticState, TracerState, DiagnosticStateNonHydro,
            DiffusionInterpolationState, dycore_states.InterpolationState,
            PrepAdvection, AdvectionPrepAdvState, ...)

reg.declare_handoff("vn_traj", producer="dycore", consumer="advection")     # M12
reg.declare_handoff("mass_flx_me", producer="dycore", consumer="advection")
reg.declare_handoff("mass_flx_ic", producer="dycore", consumer="advection")

reg.seal()

# ── the 175 hand-written lines collapse to this ──                          (M4)
diffusion_interp = reg.build(DiffusionInterpolationState)
dycore_interp    = reg.build(dycore_states.InterpolationState)
prep_adv         = reg.build(PrepAdvection)
tracer_prep_adv  = reg.build(AdvectionPrepAdvState)
diffusion_diag   = reg.build(DiffusionDiagnosticState)
...

# What `reg.build` returns is an ordinary frozen dataclass — the same type of
# object the granule takes today. The registry is not in it.


# ═══ PHASE C′: gone ═══════════════════════════════════════════════
# Allocation happened inside `reg.build`, once per quantity.


# ═══ PHASE D′: the time loop ═══════════════ IDENTICAL to today ═══
for step in range(nsteps):
    for substep in range(ndyn_substeps_var):
        solve_nonhydro.time_step(diagnostic_state_nh=diagnostic_state_nh,
                                 prognostic_states=prognostic_states,
                                 prep_adv=prep_adv, ...)
        if not last_substep:
            prognostic_states.swap()
    diffusion.run(diffusion_diag, prognostic_states.next, dtime)
    tracer_advection.run(diagnostic_state=adv_diag, prep_adv=tracer_prep_adv, ...)
    prognostic_states.swap()
```

**Phase D′ is the punchline.** It is the same code, calling the same granules, with the same
signatures, on the same kind of objects. `reg` is not mentioned. No lookup happens. No dict
crosses a stencil boundary. Nothing is lazy.

## Part 3 — what each defect costs now

| Defect | What kills it |
|---|---|
| **E1** (`vn_traj` allocated twice, never connected) | `reg` allocates **one buffer per quantity**. `PrepAdvection.vn_traj` and `AdvectionPrepAdvState.vn_traj` name the same quantity, so they receive the same object. The bug becomes **unrepresentable**, not merely fixed (M1). M12's arity check catches "declared handoff with 0 producers" even before that |
| **E2** (`mass_flx_ic` nlev vs nlev+1) | `dims` is declared once per quantity. Two containers claiming different extents for one quantity is a **contradiction the registry can see** at `seal()` (M3) |

**E1 and E2 were fixed on 2026-07-30 by PR 1404, and the fix is the argument.** It added
`initialize_prep_tracer_advection` — a hand-written ~30-line function whose entire job is to
alias three buffers into a second container, plus an identity test asserting
`prep_tracer_adv.mass_flx_ic is prep_adv.dynamical_vertical_mass_flux_at_cells_on_half_levels`:

```python
return tracer_advection_states.AdvectionPrepAdvState(
    vn_traj     = prep_adv.vn_traj,
    mass_flx_me = prep_adv.mass_flx_me,
    mass_flx_ic = prep_adv.dynamical_vertical_mass_flux_at_cells_on_half_levels,
)
```

That function is now permanent maintained surface, and the test exists to stop the aliasing from
silently regressing. Under M1 neither would need to exist — one quantity, one buffer, and the
identity is a property of the wiring rather than something a reviewer has to remember. **The
class of bug is not retired by fixing one instance of it**; the fallback branch in the same
function still allocates fresh zeros, and every future producer→consumer pair starts from the
same footing.
| **E5** (`geofac_div` in 3 containers) | Still declared in 3 containers — that is fine and stays typed. But it is now *provably* one buffer, because they name one quantity |
| **E6** (~90 hand-typed mappings × 8 sites) | Deleted. `reg.build(T)` is one line per container |
| **E7** (wrong-key bugs) | `reg.build` fills by declared quantity name, not by hand-typed keyword. There is no keyword list left to mistype |
| **E8** (placement in 3 places) | `dims` in the declaration is the only source; the name string and `is_on_half_levels` become derived |

### What it costs — the honest side

The "before" above is annotated with defects and the "after" with none, which is not a fair
comparison. The costs:

- **One `spec()` per field, across the whole model.** `MetricStateNonHydro` alone is 32;
  the dycore/diffusion/advection containers together are a few hundred lines of declaration.
  This is real work and it is not free.
- **But it replaces more than it adds.** Those declarations delete ~90 hand-typed keyword
  mappings in `driver_utils`, the same again across 7 replication sites, and the ~50-line repack
  in each binding wrapper. The declaration is written **once per field**; the mapping was written
  **once per field per site**.
- **A wrong `spec` fails at `seal()`**, not at timestep 3000. That is the entire point: a
  mis-declared `dims` contradicts another container's declaration of the same quantity and the
  registry says so before the model starts. Today the same mistake is `E7` — it type-checks,
  runs, and produces wrong numbers.
- **Is `reg.declare(...)` just E6 relocated?** No: E6 is one line *per field per site*; this is
  one line *per container*, once. And a container omitted from `declare` raises at `build`
  rather than silently producing an unwired object.

**Tests keep working untouched.** `DiffusionInterpolationState(e_bln_c_s=..., ...)` remains an
ordinary constructor — fixtures and benchmarks that hand-build containers from synthetic or
savepoint fields are unaffected. `reg.build` is an **additional** path, not a replacement
constructor. That matters given ~269 test files.

## Part 4 — the pieces that need explaining

### `intent` — the cheapest thing with the biggest payoff

One extra word per field: does this granule `READ` it, `WRITE` it, or both?

Nobody in icon4py records this today, and neither existing proposal does. It is what lets you
answer *"who writes `vn_ie`?"* mechanically, and it is what PSyclone uses to derive halo exchanges
statically instead of hand-placing them.

Recommended position: **record it now, consume it later.** Recording is one word per field.
Building the consumer is a project — and ICON-sc is the cautionary tale here: it declared the
analogous halo metadata and never built a consumer, so the annotation sits inert in its tree.

### `seal()` is not a freeze

A hard lock — declare → bind → freeze → run, nothing addable afterwards — is what CCPP, ICON
and NUOPC all do. It is unnecessary. Two counters do the same job without forbidding anything:

```python
reg.epoch       # bumped when a field's IDENTITY changes (rebound to a different array)
reg.generation  # bumped by a time-level swap

# Emitted containers record the EPOCH they were built at, never the generation.
# Using one against a bumped epoch  -> raise StaleWiringError.
```

So the `prognostic_states.swap()` in Phase D′ bumps `generation` and **invalidates nothing** —
emitted containers do not consult it. `generation` exists only so a debug check can catch code
that cached a raw pointer to `now` across a swap. If you do not want that check, drop the
counter; `epoch` alone carries the argument.

The rule: **values are the caller's business, identities are the wiring's.** Writing into a
field in place stales nothing — that is normal model execution.
Rebinding a field to a *different array* invalidates the wiring, and you get an exception instead
of silently computing on a dead buffer.

This costs ~100 lines and forbids nothing.

Optional and cheap: in debug builds, re-run the wiring every N steps and diff it against the one
in use — ICON-sc does this and it catches a class of bug nothing else does.

### The handoff declaration (M12)

`declare_handoff("vn_traj", producer="dycore", consumer="advection")` asserts a fact that is
currently only true by accident, and checks the arity at `seal()`:

- **0 consumers** → a produced field nobody reads: silently lost physics.
- **≥2 consumers** → double-applied.
- **0 producers** → E1 exactly: something reads a buffer nothing ever writes.

One caveat carried over from ICON-sc, which got this wrong: **do not assume one producer.** ICON
genuinely sums several publishers into a single `ddt_*` slot, so publisher multiplicity has to be
declared rather than assumed.

### Conditional allocation (M11) — the load-bearing one

This is the mechanism that answers the strongest objection to the whole proposal. egparedes:
*"The schema is configuration-dependent (the tracer set alone varies), so no static dataclass can
be the public state type."* Correct — about a *static* type.

The answer is that the registry is an **emitter**, and it evaluates config predicates before it
emits:

```python
class TracerState:
    qv: gtx.Field | None = spec(quantity="qv", ..., active_when=lambda cfg: cfg.tracers.qv)
    qc: gtx.Field | None = spec(quantity="qc", ..., active_when=lambda cfg: cfg.tracers.qc)
    ...

state = reg.build(TracerState, config=cfg)
# state.qv -> a real buffer      (cfg.tracers.qv is True)
# state.qc -> None               (inactive: NO buffer allocated, and reading it
#                                 fails immediately instead of returning zeros)  → R6
```

So the **type** is fixed while the **allocation set** is config-dependent. That is the distinction
the objection collapses on, and it only works if M11 is actually built — which is why it sits at
step 2 of the adoption order rather than being a footnote. ICON-sc has no equivalent at all.

**A real tension to be honest about.** `| None` is exactly what `TracerState` already does today
(`tracer_states.py:106-116`) — but an optional field means the container **cannot** be a gt4py
named collection, so `TracerState` can never be passed to a `gtx.program` as a whole. That is
fine, and it is already how icon4py works: `tracer_advection.run` takes `p_tracer_now` as a
single field, not the container. The rule that falls out: **containers that model optionality are
wiring objects, not program arguments.** Which of the two a container is should be part of its
declaration, not something discovered when gt4py rejects it.

## Part 5 — the Fortran-embedded path survives

The hard constraint: at `solve_nh_run`, **ICON owns the memory**. The registry must never
allocate there. It doesn't have to — the emit step is the same, only the source of the buffers
changes:

```python
# bindings/.../dycore_wrapper.py — today ~55 hand-written lines, EVERY timestep
def solve_nh_run(rho_now, exner_now, theta_v_ic, exner_pr, mass_flx_ic, ...):
    prep_adv = dycore_states.PrepAdvection(vn_traj=vn_traj, mass_flx_me=mass_flx_me, ...)
    diagnostic_state_nh = nonhydro_states.DiagnosticStateNonHydro(
        theta_v_at_cells_on_half_levels = theta_v_ic,        # ← the ICON↔icon4py name map,
        perturbed_exner_at_cells_on_model_levels = exner_pr, #   hand-maintained, 3rd copy
        ...)                                                 # 18 more
    granule.solve_nh.time_step(...)

# proposed: the same map, but READ FROM THE DECLARATIONS
reg.adopt_buffers({                       # wraps Fortran pointers, zero-copy
    "theta_v_ic": theta_v_ic, "exner_pr": exner_pr, ...   # keyed by spec's icon_name
})
diagnostic_state_nh = reg.build(DiagnosticStateNonHydro)
```

### This is where the thesis and the code appear to disagree — they don't, but say why

`solve_nh_run` is called **every timestep**, so `adopt_buffers` + `build` would run every
timestep too. Doesn't that make the registry a run-time object, and doesn't rebinding identities
every step bump `epoch` and stale everything?

No, because **the embedded path and the standalone driver have different lifetimes, and only one
of them holds anything across calls:**

- **Standalone driver** — `build` runs once; the emitted containers are held for the whole run.
  Staleness tracking matters, because something long-lived could go stale.
- **Embedded (`solve_nh_run`)** — nothing is held across calls *today either*; the wrapper
  already rebuilds all five containers on every call. Under the proposal it still does. There is
  no long-lived wiring to invalidate, so `epoch` is not consulted on this path at all.

What changes is only that the ~50 hand-written mapping lines become a table walk over the
declarations. The per-call cost is the same handful of object constructions it already is.

If ICON's pointers turn out to be stable across calls — they are module-level allocatables, so
they very likely are — this becomes memoizable on pointer identity and the per-call cost drops to
a comparison. **That is an optimization, not a requirement**, and it should be measured before
being claimed. Note the binding already has the right shape for it: `solve_nh_init` /
`solve_nh_run` is already a declare-then-run split.

Two things make this work, both already true:

1. **The name map already exists in several places** — this wrapper, the `icon_var_name`
   metadata key used across the `*_attributes.py` vocabularies (consumed at `driver_io.py:79`),
   and the container docstrings. M2 makes it one machine-readable table, and this wrapper becomes
   a consumer of it instead of another copy.
2. **Zero-copy wrapping is already icon4py's own technique.** `gtx.as_field` copies;
   `gtx_common._field(buffer, domain=...)` aliases with write-through. icon4py already uses it in
   `icon4py_export.py:96`, `states/factory.py:93` and `solve_nonhydro.py:1030`.

Consequence for the design, and it is a real constraint: **the registry must be able to adopt
buffers it did not allocate.** That rules out any version that insists on owning allocation —
including ICON-sc's, which allocates every unclaimed output and therefore does not solve this.

## Part 6 — what this deliberately does not do

- **No lazy evaluation in the time loop.** Prognostics change every substep, so the cache-hit
  rate on the time-varying half is structurally near zero; and lazy evaluation makes execution
  order data-dependent, which breaks bit-reproducibility and can reorder MPI collectives. The
  existing factory keeps its laziness for the compute-once static half, where it already works.
- **No automatic regridding.** Deriving `theta_v@edges` from `theta_v@cells` on demand is a
  general planner; CCPP has wanted one for years and explicitly warns against it. Instead:
  one named, profiled `update_derived_quantities()` barrier over a closed,
  enumerated set of derivations. That kills E3 and E4 at ~10 % of the cost.
- **No change to granule signatures and no new per-step overhead.** Phase D′ proves both; the
  first is also forced, because a dict can never be a `gtx.program` argument.
- **No global object.** `reg` is an instance, created and consumed in setup. There is no
  `get_registry()`.

## Part 7 — the smallest useful first step

If none of the above is agreed, three things are worth doing anyway. They commit to nothing and
they make the rest measurable:

1. **A field-coverage test** per hand-map site: assert the keyword set equals
   `{f.name for f in dataclasses.fields(TargetState)}`. ~10 lines. E6 drift becomes a red test
   *today*.
2. **Units as identity-validation** — one canonical unit per quantity, checked where it is
   declared. ~110 lines, no dependencies, and it replaces `units=""` with something enforceable.
3. ~~Fix E1~~ — **done**, by PR 1404 on 2026-07-30. Note what it cost: a permanent hand-written aliasing function plus an identity test to keep it honest.

And whatever is eventually built, the acceptance criterion should be the one ICON-sc
demonstrated: **the old wiring and the new wiring agree bitwise, as a release blocker, never a
tolerance to widen.**
