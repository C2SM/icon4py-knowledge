---
title: Model state
author: jcanton
tags: [state, model-state, components, fields, registry, metadata, duplication, allocation, lazy-evaluation, labels, halo-exchange, restart, icon-sc, contracts, prior-art]
created: 2026-07-29
status: reviewed
---

> **TL;DR** Four incompatible designs for "how components get their fields" are open
> at once and none states its requirements. This proposes the requirements first, then
> argues the container should be a **setup-time wiring step that emits ordinary typed
> dataclasses** — not a global bucket passed around at run time. The mechanisms are
> separated so they can be adopted one at a time; only one of them genuinely needs
> run-time state, and even that one is cheaper than expected.

## Why now

Five designs for the same problem are in flight, mutually unaware:

| Design | Component signature | State shape |
|---|---|---|
| [PR 1301](https://github.com/C2SM/icon4py/pull/1301) / [1360](https://github.com/C2SM/icon4py/pull/1360) | `__call__(dict[str, DataField], datetime) -> dict` | per-process `PhysicsState` gather/scatter adapter |
| [[personal/egparedes/layered-architecture-refactor\|egparedes architecture refactor]] (draft) | `__call__(state: ModelState, step: StepInfo) -> None` | one shared `ModelState`, in-place writes |
| [[personal/msimberg/revive-components/revive-components_spec\|msimberg spec]] | `run(state: InputT, dtime) -> OutputT` | typed frozen dataclass both ways |
| [[personal/OngChia/physics-driver-and-components\|OngChia design]] | `__call__(state: StateView, time) -> dict` | run-time `StateProvider` + freshness |

These are not variations; they are incompatible. Reconciling them is a precondition for
any of them, and it cannot be done without agreeing what the design must *achieve*.


## What the rigid boxes have already cost

Verified in `main` (details and file:line in [[personal/jcanton/model-state/model-state_evidence|the evidence appendix]]):

| # | Defect | Severity |
|---|---|---|
| E1 | `PrepAdvection` and `AdvectionPrepAdvState` held the same 3 quantities, allocated separately, with **nothing copying one into the other** — standalone-driver tracer advection ran on zero trajectory velocity and mass fluxes. **Fixed 2026-07-30 by PR 1404** — see below | correctness (fixed) |
| E2 | Their `mass_flx_ic` disagreed on vertical extent (`nlev+1` vs `nlev`), so even adding a copy would not have been shape-compatible. Fixed with E1 | correctness (fixed) |
| E3 | `T`/`Tv`/`p` derived in ≥3 places with **different hydrometeor inputs** — IO uses permanently-zero hydrometeors, physics uses real tracers. The temperature written to output is not the temperature physics computed with | science |
| E4 | `vn → u,v` computed 3× with different domain bounds; one path omits the halo exchange | correctness |
| E5 | `dycore.InterpolationState`'s 16 fields are a strict superset of `DiffusionInterpolationState`'s 8; `geofac_div` declared in 3 containers; `ddqz_z_full` in 3 | duplication |
| E6 | ~90 `.get()` calls of hand-mapping factory outputs into granule dataclasses, replicated at **7** further sites — 5 in tests, **2 in the production Fortran binding wrappers** | boilerplate |
| E7 | Three live wrong-key bugs of two kinds in the *replicated* hand-maps (`fac1_mc` into `fac2_mc`; edge-normal into a dual-normal slot) — all type-check. `driver_utils` itself is correct, which is the argument for deleting the replication | correctness |
| E8 | Location is recorded **three** times: name string, `dims=(CellDim, KHalfDim)`, and `is_on_half_levels: bool` | drift |
| E9 | Five parallel namespaces per field, four disjoint metadata dicts, ~0/49 metrics entries are real CF names, `units=""` for most | drift |
| E10 | PR 1360 adds **seven** new state dataclasses for one component; `TmxInputState` re-declares `qv…qg`, `rho`, `w` | trend |

E10 is the important one: the duplication is currently being created faster than it is
being removed, because every new component pays the full adapter-stack tax.

**E1/E2 were fixed on 2026-07-30 ([PR 1404](https://github.com/C2SM/icon4py/pull/1404),
`3c8c69342`) — and the fix is itself the argument.** It added `initialize_prep_tracer_advection`,
a hand-written function whose whole job is to alias three buffers into a second container, plus
an identity test asserting the aliasing holds. Both are now permanent maintained surface. Under
M1 neither would need to exist, and the *class* of defect would be unrepresentable rather than
fixed once — the same function's no-dycore branch still allocates fresh zeros, and every future
producer→consumer pair starts from the same footing.

Per msimberg, this list is **not a migration bill** — it is the requirement source. The
more places break, the better specified the design is.

## Requirements


| # | Requirement | Forced by |
|---|---|---|
| R1 | A cross-granule producer→consumer handoff must be *expressible*, so it cannot silently become two allocations | E1 |
| R2 | One quantity → one buffer; shape and placement declared once | E2, E5, E8 |
| R3 | A derivation (`vn→u,v`, `theta_v,exner→T,p`) must have exactly one implementation, with its domain and halo semantics part of the declaration (more complex options can be designed when real use cases are implemented (see different microphysics schemes)) | E3, E4 |
| R4 | The container must **adopt externally-owned buffers** — at `solve_nh_run` ICON owns the memory | Fortran-embedded path |
| R5 | Whatever reaches a `gtx.program` must be a static named collection | gt4py (see below) |
| R6 | Absence must be first-class — optional IAU increments, inactive tracers — not a zero allocation | `dummy_field_factory` |
| R7 | Multi-buffer/time-level must be expressible, at *different rates* (dyn substep vs tracer step) | `TimeStepPair`, PR 1404 |
| R8 | Cross-cutting sweeps (output, restart, halo sets) must be queries, not hand-written lists | restart lists hand-picked; tracers have no IO path |
| R9 | Granule call sites must keep naming their actual inputs | havogt/msimberg objection; also R5 |
| R10 | No new per-stencil-call overhead | ~100 stencil calls per 20–50 ms timestep |
| R11 | A field's **role is not implied by which container it sits in** — some diagnostics must be checkpointed, some prognostics need no halo, most fields need neither | restart inventory (below) |

### Restart is the requirement that settles R8 and R11

[[personal/msimberg/checkpoint-restart/checkpoint-restart|msimberg's checkpoint/restart doc]] is
the best-specified consumer we have, and it decides two arguments.

State of play (verified; msimberg's doc cites some pre-rename paths — `model/driver/` is now
egg-info only and `TimeLoop.restart_mode` is gone):

- `main` has a **read** path — `read_restart_from_file` (`initial_condition/from_file.py:142`),
  serialbox-based, restoring prognostics + `exner_pr` + the predictor/corrector advective
  tendencies. No **write** path.
- `origin/ibm_02` has a serial prototype writer: `io/restart.py`, `RestartManager`, pickle,
  two-file rolling scheme.

**R11 comes straight out of the restart inventory.** The fields that must be checkpointed are
prognostics *plus* the dycore diagnostics carried across steps — `exner_pr`,
`ddt_vn_apc_pc`, `ddt_w_adv_pc` — while metrics, interpolation coefficients and compiled
stencils must not be. So "is this restartable" is **orthogonal** to "is this in the prognostic
or the diagnostic container". The current prog/diag split cannot express it, and `ibm_02` is
consequently forced to hand-pick three specific `DiagnosticStateNonHydro` members by name. That
is precisely the hand-written list ICON's `in_group('dwd_fg_atm_vars')` abolishes — declared by
the field's owner, at the field's definition site. It is the strongest concrete argument in this
document for per-field labels over container-membership-as-role, and for `restart: bool` being
in M2's metadata from the start rather than retrofitted.

Three more constraints the doc surfaces:

- **Exact vs scientific restart is a per-field decision.** Exact needs every time-dependent
  quantity (tendencies, previous-step fields, random seeds); scientific needs prognostics plus a
  date. Either way the answer is a label set, chosen once, not a code path.
- **Restart needs to allocate fields that do not exist yet**, which is the one thing reading
  metadata off a live field cannot do — see the evidence appendix. This is the
  `QuantityFactory`/`GridSizer` argument (M2 + M1) arriving from a second direction.
- **Tracer restart fails today for a naming reason, not a technical one.** `from_file.py:162`:
  *"the solve-nonhydro savepoints do not carry them, they are in the advection-init savepoint of
  the same date."* A grouping problem, stated as a `NotImplementedError`.

Also note what the container should **not** own: `ndyn_substeps_var`, CFL-watch mode, elapsed
time and random seeds are all restart state but are not fields. The container holds fields; the
integration control state is someone else's problem, and conflating them is a scope error.

## The central question: is the container a compiler or a runtime?

The objection from havogt and msimberg — "one global bucket passed around in its entirety
when only part of it would be enough" — is correct, and stronger than it sounds. It is
[stamp coupling](https://en.wikipedia.org/wiki/Coupling_(computer_programming)) escalating
to common coupling, and the lazy-shared-store part is the Blackboard pattern, whose own
POSA liabilities list reads: *difficulty of testing, difficulty of establishing a control
strategy, low efficiency, no support for parallelism.*

**But the objection does not apply to the mechanism — only to the run-time bucket.** The
decisive observation:

> Every defect E1–E10 is decided **once, before the time loop starts**. Not one of them
> recurs per timestep. The fix therefore belongs at setup time, and a setup-time fix needs
> no global mutable bucket at all.

So: the container consumes *declarations* and emits *bindings*. Three tests for any proposal:

1. **Freeze test** — can the *schema* be settled before the time loop? For icon4py yes: the
   tracer set is a pure function of `TracerConfig`, the output set of the namelist, the
   component set of config. But a **hard freeze is not required** — see below.
2. **Reachability test** — can a **granule** reach the container? If yes you have built MPAS's
   pools, which MPAS-Ocean deleted for GPU ("a large user-defined type did not perform well on
   GPUs") and whose successor Omega dropped entirely.
3. **Emission test** — is the output an ordinary dataclass gt4py accepts?

Two earlier versions of these tests were **too strong, and ICON-sc's working system refutes
them** ([[personal/jcanton/model-state/model-state_icon-sc|appendix]]):

- *"If any object it created is still reachable when the first stencil runs, it has failed"* —
  ICON-sc's vault **is** live at run time, and for two load-bearing reasons: something must hold
  the buffers so a time-level swap can retarget the public view, and something must carry the
  staleness counters so a stale wiring raises instead of silently binding dead buffers. The
  correct test is narrower: *nothing a **component** can reach; what survives is index-addressed
  only, holds no names on the step path, and is an instance rather than a module-level global.*
- *Two-phase lock with a hard freeze* (CCPP `lock_table`/`lock_data`, ICON's fatal post-`add_var`,
  NUOPC advertise→realize). ICON-sc shows a **staleness guard beats a freeze**: mutation stays
  legal, and running against a stale wiring raises. That forbids nothing and costs ~100 LOC.
  See M6 below and open question 8.

### gt4py already forces the answer

`gt4py/next/named_collections.py:34-48` — `CustomDataclassNamedCollectionABC.__subclasshook__`
requires `dataclasses.is_dataclass(subclass)` and, for every field,
`default is MISSING and default_factory is MISSING`. Checked against the live tree:

```
dict                        : False     # can NEVER cross the stencil boundary
PrognosticState             : False     # tracer: TracerState = field(default_factory=...)
DiagnosticStateNonHydro     : True
PrepAdvection               : True
```

A name-keyed map is structurally barred from being a program argument. Whatever is built,
the last mile is always an explicit typed dataclass — so R9 is not a compromise, it is
mandatory. (Incidentally: PR 1404 removing the `tracer` field flips `PrognosticState` to
conformant.)

**Do not argue this on speed.** ICON-sc measured its entire negotiation/execution split at
**6.7 %** of step time on a real model (JW R02B04×35, gtfn_cpu, 3.68 → 3.43 s/step); the
eye-catching 64–101× figures are from a kernel-free toy. Its architecture doc is blunt about
why: *"a dict lookup is ~40–60 ns and slotted attribute access ~20–40 ns, but those were never
the real cost."* The case for typed dataclasses rests on the structural prohibition above (R5),
on Fortran buffer adoption (R4), and on type-checkability and explicit ownership — **not** on
lookup cost.

**The strongest objection to this document comes from the same source** and deserves answering
head-on. egparedes, with our exact use case in view: *"The schema is configuration-dependent
(the tracer set alone varies), so **no static dataclass can be the public state type**."* That
is correct about a *static* type and beside the point for a setup-time **emitter** — but only if
**M11 (conditional allocation from config predicates) is real**. M11 is entirely absent from
ICON-sc. Leaving it as a one-line row in the table below does not defuse the objection; it is
the load-bearing mechanism for the whole thesis.

The same conclusion is reached independently by everyone who has shipped this:

- **ICON** registers every field twice (typed member *and* `add_var`), pays ~15k lines of
  boilerplate — and the **compute path never queries the registry**. Only 8 group-query
  sites exist model-wide, all I/O-ish.
- **CCPP** resolves everything at build time; the framework is not in the executable.
- **NDSL/Pace** — the *only other GT4Py model* — kept rigid dataclasses and put the
  intelligence in `dataclasses.field(metadata=...)` + a generic allocator. Existence proof
  that the fix is orthogonal to dynamism.
- **ClimaAtmos** built the dynamic bag and is [migrating back](https://github.com/CliMA/ClimaAtmos.jl/issues/2217)
  to explicit structs ("over 60 fields accumulated through splatting, unpacking and merging").
- **LFRic** built exactly the global keyed store, and its own retrospective says: *"an ever
  expanding pool of global scope data… becoming unwieldy… doesn't meet our aspiration to
  adopt an object approach with tight cohesion and loose coupling."*

**Political corollary:** the setup-time reading changes **no granule call signature**. The
whole intervention lands in `driver_utils.initialize_granules`, `driver_states.assemble_driver_states`
and the test-side repacking — precisely the code that is already triplicated and already
contains two shipped bugs (E6, E7).

## Mechanisms

Separated so they can be adopted independently. **Bucket?** = needs a globally reachable
mutable name→field map at run time.

| # | Mechanism | Phase | Bucket? | Requires | Cost |
|---|---|---|---|---|---|
| M2 | Metadata on dataclass fields (`standard_name`, `units`, `dims`, `intent`, `scope`, `restart`) | setup | No | — | S mech / **L vocabulary** |
| M10 | Scope/lifetime tag + granule-private `Local` scratch type | setup | No | M2 | S |
| M11 | Conditional allocation from config predicates | setup | No | M2 | S |
| M3 | Declared I/O used for **validation only** | setup | No | M2 | S |
| M1 | Canonical allocation registry, signatures unchanged | setup, frozen | No | (M10) | M |
| M4 | Declared I/O → automatic wiring (emit the dataclass) | setup | No | M2 | M |
| M7 | Labels/groups, materialized at setup | setup | No | M2 | S / M vocab |
| M8 | Units: validate, don't convert | setup | No | M2 | S |
| **M12** | **Declared handoff + single-consumer arity check** | setup | No | M1, M2 | S (~90 LOC) |
| **M14** | **Parameters as a structure distinct from state** | setup | No | M2 | S/M |
| M5 | Lazy derived-field computation | run | No | M2, M6 | **H** |
| M6 | Staleness / generation counters | **run** | **Yes** | M1, M2 | M / H discipline |
| M9 | Automatic regridding as registered rules | run | No | M2, M5, M6 | **H** |

Notes on the ones that matter most:

- **M1 kills E1 by construction.** One buffer named `vn_traj`, two references — the
  disjoint-allocation bug becomes *unrepresentable*. Half of it already works: `FieldSource.get`
  memoizes, so the driver path already aliases. The gap is that the *time-varying* half of
  the state never touches the factory, and the savepoint test path copies instead of aliasing.
- **M3 is the highest value per line** (~150 lines) and is the one thing both existing specs
  already agree on. The current protocol is completely inert: zero classes subclass
  `Component`, it is not `@runtime_checkable`, both its TODOs (unit matching, dimension
  consistency) are unimplemented, and `inputs_properties` is never consulted at runtime anywhere.
- **M10 covers the larger memory number.** Granule-private scratch (~29 full 3D fields across
  `SolveNonhydro`/`Diffusion`/`VelocityAdvection`) exceeds the duplication. A shared container
  *without* a scope tag makes memory strictly worse, by making every private buffer globally
  reachable and never freed. NDSL's `Local` poisons the buffer at init, sets DaCe
  `transient=True` so the compiler can elide it, and enforces scope at run time.
- **M6 splits in two, and only one half is worth building.** *Structural* staleness — "is my
  wiring still valid?" — is cheap, has prior art, and replaces the freeze requirement entirely.
  ICON-sc uses three separate invalidation domains in ~100 LOC: `epoch` (a field identity changed
  ⇒ the wiring is stale ⇒ **raise**), `generation` (a swap changed the view ⇒ only cached views
  drop), `schema_hash` (the slot set changed), plus a debug-build `renegotiate_and_diff` that
  re-runs the wiring every N steps and diffs it line by line. In-place value writes stale
  nothing — *"values are the user's business, identities are the plan's."* **Adopt this.**
  *Scientific* staleness — "is this derived field still consistent with its inputs?" — is the one
  with no prior art (ICON, MPAS, CAM `pbuf` and NDSL track nothing; sympl's only mechanism is
  wall-clock interval; ClimaAtmos replaced it with one explicit barrier). It can never be a
  correctness guarantee: gt4py's `Field` has no immutability concept and `.ndarray` hands out a
  writable buffer. **Defer it**; M5-lite's barrier removes the need.
- **M12 gives R1 a mechanism.** R1 has been a requirement with no mechanism. Declare each
  producer→consumer handoff and check the arity at setup: 0 consumers *or* ≥2 both reject —
  *"a dangling tendency silently loses physics, a double consumer double-applies it."* No runtime
  object; the check runs once and no data ever passes through it. **It catches E1 only under
  one-quantity ⇒ one-name ⇒ one-buffer (M1+M2)** — without those, `PrepAdvection.vn_traj` and
  `AdvectionPrepAdvState.vn_traj` are two legitimate slots and the check is decorative. Note
  ICON-sc's own hole: it never checks *publisher* count, while ICON genuinely sums multiple
  publishers into `ddt_*`, so publisher multiplicity must be declared rather than assumed.
- **M14 keeps calibration constants out of state.** Tunable scheme parameters (entrainment
  coefficients, autoconversion thresholds) declared as a structure *separate from* state, so they
  are never smuggled through state fields. Needs zero JAX despite originating in ICON-sc's
  differentiability work; equally right for ensembles, perturbed physics, and namelist provenance.
- **M5/M9 carry the loudest warnings.** CCPP has wanted `theta_v,exner→T,p` derivation for
  years, has not built it, and scopes the issue "*this is not an open-ended task!*". The
  `theta_v,exner ↔ T,p` cycle is real (ClimaAtmos documents the identical `ᶜK↔ᶜT↔ᶜp` cycle and
  breaks it with a physical approximation, not a solver). **Ship M5-lite instead**: one named,
  profiled `update_derived_quantities()` barrier over a closed, enumerated set. That removes
  E3 and E4 at ~10% of the cost and stays compatible with full M5 later.

### On "unlimited labels"

ICON validates the idea and bounds it. The label is declared **at the field's definition
site, by the field's owner** — new field + right group string ⇒ it appears automatically in
output, restart-analysis, IAU, LBC prefetch, meteograms, ComIn. No central list to edit. That
is why each of those services is ~200 lines instead of ~5000. The namelist even gets set
algebra: `'group:atmo_ml_vars', '-qg', 'group:precip_vars'`.

Three amendments from ICON's own scars:

1. Unknown label must **raise**. ICON's `group_id` auto-creates on first use
   (`mo_var_groups.f90:193`) — a documented typo trap. MPAS's equivalent default is
   silent-null, a bug class that shipped for a decade.
2. **Materialize buckets at setup, never query per call.** Filtering 300 fields by label
   measures ~4 µs; at 100 call sites that is ~400 µs/timestep for zero physics. ICON's answer
   after 20 years is a fixed bitset with O(1) membership and only 8 query sites.
3. Groups in ICON **never drive computation** and never express placement — `cell vs edge` is
   `hgrid`, a scalar enum. Labels are a selection mechanism, not an addressing mechanism.

### On naming and placement

Recommendation: key on `(quantity, placement)` where `placement` is the dims
tuple, and treat the flat string `theta_v_at_cells_on_half_levels` as its
*rendering*, not the primary key. This makes `dims` and `is_on_half_levels`
derived rather than independently maintained (fixes E8), and makes regridding
an edge over a fixed quantity — `theta_v@(Cell,K) → theta_v@(Edge,K)` — which
is impossible if placement is welded into an opaque string. CF names stay as
output metadata only.

Escape hatch required: not everything factorises (`rbf_vec_coeff_e` on `(Edge, E2C2E)`; `vn`
vs `u,v` differ by more than placement). Those stay plain named fields with no derivation rules.

## Recommended order

Each step independently shippable, each with standalone value.

0. **Free wins, no design commitment required.** Add the coverage test (hand-map keys ≡
   `dataclasses.fields(Target)`, ~10 lines per site) so E6/E7 drift turns red *today*; adopt
   units-as-identity-validation (~110 LOC, no dependencies); adopt the `icon:`-namespace
   two-way invariant. All three are lifted from ICON-sc and commit us to nothing —
   see [[personal/jcanton/model-state/model-state_icon-sc|the ICON-sc appendix]], §Adopt now.
1. **M2** — metadata on dataclass fields (NDSL's form), plus start the name file. Unblocks
   everything, breaks nothing, gt4py-safe (`metadata=` sets no default). Include `origin`/K-domain
   from the start: gt4py fields carry a *domain*, not a shape, and that omission cost ICON-sc two
   work units of misdiagnosis.
2. **M10 + M11** — scope tag and config-predicate allocation. The only two mechanisms that
   *reduce* memory, both prevent the rest from regressing it — and **M11 is what answers the
   strongest objection to this whole document** (see the gt4py section).
3. **M3** — validation, at class creation rather than first call. Highest value/line; already
   agreed by both existing specs.
4. **M1** — canonical allocation, settled at setup. Kills E1 by construction. No signature changes.
5. **M12** — handoff arity check. Cheap once M1+M2 exist, and it is what makes E1 *unrepresentable*
   rather than merely fixed once.
6. **M4** — auto-wiring, **gated on M2's vocabulary being real**. Deletes E6.
7. **M7** — labels. Unlocks output/restart/checkpoint sets; gives tracers an IO path at all.
8. **M5-lite** — one derived-quantities barrier over a closed set. Kills E3 and E4.
9. **M6-structural** (`epoch`/`generation`/`schema_hash` + debug renegotiate-and-diff) — adopt
   whenever setup-time wiring lands; it replaces the freeze requirement.
10. **M14** — parameters separate from state. Independent of everything else.
11. **M6-scientific, M9, M5-full** — defer; each needs a written justification.

Acceptance criterion for the whole sequence, from ICON-sc: **the old and new wiring must agree
bitwise, as a release blocker, never a tolerance to widen.** They demonstrated exactly this over
288 composed steps / 1440 dycore substeps.

Step 5 has a hard dependency worth repeating: **auto-wiring keyed on today's vocabulary will
silently bind the wrong field.** `metrics_attributes.py:106` already declares two distinct
fields (cell and edge) under one `standard_name`.

## What this does not solve

- **Granule scratch**, the larger memory number — fixed by a *type* (M10), not a container.
- **`nlev` vs `nlev+1`** — `fa.CellKField[float]` cannot express it and `KHalfDim` is erased
  to `KDim` at allocation (`factory.py:544`, "*remove once gt4py supports vertically staggered
  dimension*"). That is a type-system gap; no container fixes it.
- **Halo-exchange placement** — needs declared *access* (PSyclone derives exchanges statically
  from `gh_read/gh_write/gh_inc` × function space). Neither existing spec records `intent`.
- **The prognostic double buffer** — intentional and already optimal; `swap` is a pointer rebind.
- **Bit-reproducibility** — laziness makes evaluation order data-dependent, and bit-comparison
  against ICON savepoints is the entire validation strategy.

## Conflicts with existing proposals

- **msimberg's spec is already the setup-time design** — `convert_state(...)` returns an
  ordinary frozen dataclass and no bucket appears anywhere. That is the strongest point of
  agreement with the evidence. Gaps: it says nothing about M1 (who allocates), so **E1
  survives it intact**; `AC14`'s `ndarray.setflags(write=False)` does not exist on cupy, so
  GPU read-only enforcement silently evaporates; and `kind` is doing the job of two orthogonal
  fields — split into `intent` and `role`, which also dissolves its open questions O1/O4/O5.
- **OngChia's design is the only one requiring a run-time container.** Two specific problems:
  its rule "each component derives its own inputs" is precisely what produced E3 (CCPP ran the
  same experiment and got 66% interstitial glue); and `is_fresh` answers "was this written
  recently", not "is this consistent" — a hole he documents himself. Its per-component call
  frequency and Jacobi/Gauss-Seidel selection are genuinely not covered elsewhere and should
  be kept.
- **[[personal/egparedes/layered-architecture-refactor|The layered-architecture refactor]]**
  independently reaches the same duplication finding and proposes merging
  `PrepAdvection` into a shared `ModelState`. Its `-> None` in-place contract is the most
  GPU-honest of the four.
- **Neither existing spec covers**: allocation, scope/lifetime, conditional allocation, labels,
  halo exchange, time levels (how does a component say `now` vs `next`?), or the vocabulary —
  and all of them assume CF standard names work, which they do not.

## Open questions for humans

Design/science/political, not answerable by more investigation:

1. Is the Fortran-embedded path permanent? If yes, the ABI stays flat pointers forever and
   the container is a host-side convenience only. *(Confirmed hard requirement — stated here
   so reviewers can challenge it.)*
2. Has standalone-driver tracer advection ever produced validated results, given E1? Who signs that off?
3. **PR 1301/1360 vs [[personal/egparedes/layered-architecture-refactor|the layered-architecture refactor]] vs the two specs: which protocol wins?** Four open signatures is the
   real blocker. Reconciling them is a precondition, not a follow-up.
4. Is `mass_flx_ic` on half or full levels? The two containers disagree and PR 1404 does not
   resolve it. Science question.
5. When IO and physics disagree, which temperature is *the* model temperature? (E3)
6. ~~Do we require bitwise reproducibility across the refactor?~~ **Answered — yes, and it is
   achievable.** ICON-sc demonstrated old-wiring ≡ new-wiring bitwise over 288 composed steps
   against a real dycore. Adopt it as a release blocker, never a tolerance to widen. It does
   *not* rule out setup-time derivation; it rules out **lazy** derivation, whose evaluation order
   is data-dependent.
7. What per-timestep Python overhead is acceptable, **as a number**? Still open, but now with a
   datapoint: ICON-sc's entire negotiation/execution split bought **6.7 %** on a real model, and
   its author states dict-vs-attribute lookup "was never the real cost". Whatever we build should
   not be justified on this axis.
8. ~~Do we accept a hard declare → bind → freeze → run lifecycle?~~ **Answered — no, and we
   don't need to.** A staleness guard beats a freeze: mutation stays legal, and running against
   a stale wiring raises. ~100 LOC, forbids nothing (M6-structural).
9. Do we commit to a controlled name vocabulary, and **which domain scientist owns it**? The
   *shape* is now settled — unprefixed ⇒ claims CF identity, no CF name ⇒ must be `icon:<name>`,
   both directions enforced at registration. ICON-sc's measured split is **18 CF / 72 `icon:`**:
   80 % of an atmospheric model has no CF name, which is the argument to take to the domain
   scientists. **Ownership remains open.**
10. **Exact or scientific restart?** This is the highest-leverage open question in the list,
    because it is the only one that forces a per-field decision on every field in the model
    (R11), and because [[personal/msimberg/checkpoint-restart/checkpoint-restart|the restart doc]]
    has a 2-week appetite while this design does not. If restart ships first with a hand-picked
    field list, that list becomes the de-facto role vocabulary — so it is worth spending one
    conversation on `restart: bool` as metadata *before* the restart work starts, even if
    nothing else here is adopted.

## Appendices

- [[personal/jcanton/model-state/model-state_walkthrough|Walkthrough]] — the proposal explained concretely, as before/after pseudocode over icon4py's actual pipeline. **Start here if the mechanism list reads as abstract.**
- [[personal/jcanton/model-state/model-state_evidence|Evidence]] — verified defects with file:line, and claims that could not be verified.
- [[personal/jcanton/model-state/model-state_prior-art|Prior art]] — ICON, MPAS, CCPP, sympl, NDSL, ClimaAtmos, LFRic, WRF, CAM, MAPL, NUOPC; steal/avoid lists.
- [[personal/jcanton/model-state/model-state_icon-sc|What ICON-sc settles]] — egparedes' prototype: what it confirms, what it refutes, what to lift, and 12 unfiled upstream icon4py bugs.

Related: [[personal/msimberg/revive-components/revive-components|Revive components]],
[[personal/OngChia/physics-driver-and-components|Physics driver and component design]],
[[personal/msimberg/checkpoint-restart/checkpoint-restart|Checkpoint/restart]],
[[personal/egparedes/layered-architecture-refactor|Layered architecture refactor]].
