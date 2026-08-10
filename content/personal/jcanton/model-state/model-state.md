---
title: Model state
author: jcanton
tags: [state, model-state, components, fields, registry, metadata, duplication, allocation, lazy-evaluation, labels, halo-exchange, restart, icon-sc, contracts, prior-art, constraints, goals]
created: 2026-07-29
updated: 2026-08-10
status: draft
---

> **TL;DR** Four incompatible designs for "how components get their fields" are open at
> once and none states its requirements. This states them first — as **constraints** that
> a design must not violate and **ranked goals** it should buy — then argues the container
> should be a **setup-time wiring step that emits ordinary typed dataclasses**, not a
> global bucket passed around at run time. The mechanisms are separated so they can be
> adopted one at a time, and the honest stopping point (declare-and-*check*, no registry)
> is on the page next to the full design.

> **How to read this.** This revision consolidates the former `_specV2` review appendix
> into the main text, adopts its constraints/goals split, and re-verifies every claim
> against `origin/main` at `4c858a6a` (2026-08-06) — four days newer than the previous
> verification point. Corrections to earlier claims are marked **[corrected]**; things
> confirmed for the first time are marked **[newly verified]**. `status` is back to
> `draft` because the rewrite has not been reviewed by a human.
>
> Evidence tiers used throughout: **verified** = run against a local checkout;
> **reported** = taken from a source that could not be re-run here; **unverified** =
> stated in an earlier revision, still unchecked.

## 1. Why this document exists

Four designs for the same problem are in flight, mutually unaware:

| Design | Component signature | State shape |
|---|---|---|
| [PR 1301](https://github.com/C2SM/icon4py/pull/1301) / [1360](https://github.com/C2SM/icon4py/pull/1360) | `__call__(dict[str, DataField], datetime) -> dict` | per-process `PhysicsState` gather/scatter adapter |
| [[personal/egparedes/layered-architecture-refactor\|egparedes architecture refactor]] | `__call__(state: ModelState, step: StepInfo) -> None` | one shared `ModelState`, in-place writes |
| [[personal/msimberg/revive-components/revive-components_spec_v3\|msimberg spec v3]] | `run(state: InputT) -> OutputT` + combinators | shared mutable `Carry`, `CarrySpec`-declared slots |
| [[personal/OngChia/physics-driver-and-components\|OngChia design]] | `__call__(state: StateView, time) -> dict` | run-time `StateProvider` + per-field freshness |

These are not variations; they are incompatible. Reconciling them is a precondition for
any of them, and it cannot be done without agreeing what the design must *achieve*.

## 2. What the current shape has already cost

All rows below were re-checked against `origin/main` at `4c858a6a`. File:line detail is in
[[personal/jcanton/model-state/model-state_evidence|the evidence appendix]].

| # | Defect | Status | Severity |
|---|---|---|---|
| E1 | `PrepAdvection` and `AdvectionPrepAdvState` held the same three quantities, allocated separately, with **nothing copying one into the other** — standalone-driver tracer advection ran on zero trajectory velocity and mass fluxes | fixed by [PR 1404](https://github.com/C2SM/icon4py/pull/1404) | correctness |
| E2 | Their `mass_flx_ic` disagreed on vertical extent (`nlev+1` vs `nlev`), so even adding a copy would not have been shape-compatible | fixed with E1 | correctness |
| E3 | `T`/`Tv`/`p` derived in ≥4 places from **different inputs**: `driver_io` runs the diagnosis fully dry — `qv` *and* all hydrometeors permanently zero — while muphys uses the real tracers | live, verified | science |
| E4 | `vn → u,v` computed twice into two different buffers; **one path halo-exchanges and one does not** | live, verified | correctness |
| E5 | `dycore.InterpolationState`'s 16 fields are a strict superset of `DiffusionInterpolationState`'s 8 (same 8, same order); `AdvectionInterpolationState`'s 4 are a strict subset; `geofac_div` in 3 containers; `ddqz_z_full` in 3 live + 1 dead; `MetricStateSaturationAdjustment` and `MetricStateIconGraupel` are byte-identical one-field dataclasses | live, verified | duplication |
| E6 | 89 `.get()` calls of hand-mapping factory outputs into granule dataclasses in `driver_utils.initialize_granules` (`:221-487`), replicated at **13 further sites** — 11 in tests, **2 in the production Fortran binding wrappers** | live, verified | boilerplate |
| E7 | Three live wrong-key bugs of two kinds in the *replicated* hand-maps — all type-check, all still present | live, verified | correctness |
| E8 | Location is recorded **three** times (name string, `dims`, `is_on_half_levels`) — and the redundancy is now pinned by a unit test that restates it deliberately | live, verified | drift |
| E9 | Five parallel namespaces per field; five disjoint metadata dicts; a live `standard_name` collision; `units=""` for 45/46 metrics and 23/23 interpolation entries | live, verified | drift |
| E10 | The TMX branch adds **seven** state dataclasses and 92 declared fields for one component | live, verified | trend |

**Sharpenings and corrections to the earlier ledger:**

- **E3 [corrected, and it is worse than stated].** `driver_io.py:146-147` allocates
  `qv, qc, qi, qr, qs, qg` once with the comment *"dry air: all hydrometeors stay zero
  (never written, so allocated once)"* — and `qv` is in that list. So on the output path
  `virtual_temperature ≡ temperature` identically, and the temperature icon4py publishes
  is a **dry-air** temperature that no physics component ever uses. The earlier framing
  ("different hydrometeor inputs") understated this.
- **E4 [corrected].** There are **two** production call sites on `main`, not three
  (`driver_states.py:290`, `driver_io.py:199`). They do **not** differ in domain bounds —
  both run `lateral_boundary_level_2 → END` — and the `offset_provider` difference is not
  semantic. What actually differs, and is the whole defect, is that they write to
  different buffers (`diagnostic_state.u/.v` vs `driver_io`'s private `_u/_v`) and
  **`driver_states` halo-exchanges the result at `:302` while `driver_io` does not.**
  `driver_io.py:115` already carries the fix as a TODO.
- **E6 [corrected upward].** The earlier count of 7 replication sites was low. Taking the
  union of every file constructing a granule interpolation/metric/least-squares container:
  13 sites besides `driver_utils`, of which 2 are the production binding wrappers.
- **E7 [verified live].** `test_benchmark_solve_nonhydro.py:163` assigns
  `d2dexdz2_fac2_mc` from `D2DEXDZ2_FAC1_MC` (`:162` correctly assigns `fac1` from the
  same key); `test_benchmark_solve_nonhydro.py:98` and `test_benchmark_diffusion.py:105`
  assign `dual_normal_vert_y` from `EDGE_NORMAL_VERTEX_V` where the tangent was meant.
  The intended mapping is confirmed independently in three places
  (`driver_utils.py:259/261`, `test_diffusion.py:77/81`,
  `test_parallel_geometry.py:64/69`). These are **filable today** with the evidence above.
- **E8 [newly verified, and now load-bearing].** `is_on_half_levels` is read at
  `driver_io.py:83` and `:242`, and `test_driver_io.py:74` carries a docstring stating
  that `dims` and `is_on_half_levels` are *"stated independently"* of the source. The
  triplication is no longer merely present; it is **tested into place**.
- **E9 [corrected].** `metrics_attributes.py:104` declares `standard_name=DDQZ_Z_FULL` on
  the `DDQZ_Z_FULL_E` entry, so a cell field `(CellDim, KDim)` and an edge field
  `(EdgeDim, KDim)` advertise one standard name; `io/writers.py:246`
  (`filter_by_standard_name`) resolves variable identity by `standard_name` equality, so
  they would alias into one netCDF variable. The `units=""` claim was too broad: it holds
  for metrics (45/46) and interpolation (23/23) but **not** for geometry (11/51).
- **E10 [verified on `origin/physics_driver_tmx`, 2026-08-05].** Seven dataclasses,
  92 fields: `TmxMetricState` (17), `TmxInterpolationState` (9), `TmxInputState` (16),
  `TmxSurfaceFluxState` (5), `TmxDiagnosticState` (31), `TmxNewState` (7),
  `TmxTendencyState` (7). `TmxInputState` re-declares **all six** fields of the common
  `DiagnosticState`, all six tracers, and `rho`/`w`; `TmxMetricState` re-declares
  `ddqz_z_full`, `wgtfac_c`, `wgtfacq_c`, `wgtfac_e`, `wgtfacq_e`;
  `TmxInterpolationState` makes `geofac_div` a **fourth** container.

### The fix to E1 is the argument

E1/E2 were fixed on 2026-07-30 by PR 1404. The fix added
`driver_states.initialize_prep_tracer_advection` — a hand-written function whose entire
job is to alias three buffers into a second container — plus an identity test asserting
the aliasing holds. Both are now permanent maintained surface.

The fallback branch is the sharper point. When there is no dycore, the same function
allocates fresh zeros, and to get `mass_flx_ic` right it **restates** the half-level
extent in a second file, with a comment explaining why:

```python
# vertical mass flux at cell half levels: one more level than KDim, like the
# dycore's dynamical_vertical_mass_flux_at_cells_on_half_levels it stands in for
mass_flx_ic=data_alloc.zero_field(grid, dims.CellDim, dims.KDim,
                                  extend={dims.KDim: 1}, allocator=allocator),
```

That is E2's knowledge — one quantity's vertical extent — represented a third time, and
it was *created by the fix*. The class of defect is not retired by fixing one instance:
every future producer→consumer pair starts from the same footing.

E10 is the other half of the trend. Duplication is currently being created faster than it
is being removed, because every new component pays the full adapter-stack tax.

Per msimberg, this ledger is **not a migration bill** — it is the requirement source. The
more places break, the better specified the design is.

## 3. Constraints and ranked goals

The earlier revision listed R1–R11 flat, unweighted, with no separation between "violating
this makes the design wrong" and "we would like this". That shape has a name in
[[knowledge/software-engineering/principles|the working principles]] — *advocate-less wish
list* — and the fix is the vocabulary the same document supplies.

### Constraints — non-negotiable

| # | Constraint | was | Source |
|---|---|---|---|
| **C1** | Whatever reaches a `gtx.program` must be a static named collection | R5 | gt4py, structural (§4.2) |
| **C2** | The container must **adopt externally-owned buffers** — at `solve_nh_run` ICON owns the memory | R4 | Fortran-embedded path |
| **C3** | Granule call sites must keep naming their actual inputs | R9 | the havogt/msimberg objection; also implied by C1 |
| **C4** | No new per-stencil-call overhead | R10 | ~100 stencil calls per 20–50 ms timestep |

**C2 is well-founded but should be re-asked.** Verified: py2fgen's whole type model is
`ParamDescriptor = ArrayParamDescriptor | ScalarParamDescriptor`
(`py2fgen/_definitions.py:63`) — there is no record descriptor, so no struct can cross the
ABI; `solve_nh_run` takes ~45 flat positional arguments and rebuilds five containers on
**every** call (`dycore_wrapper.py:358-426`); and
`bindings/tests/bindings/test_codegen_references.py` is a golden-file test of generated
Fortran/C bindings, so any signature change breaks a checked-in artifact. C2 therefore
holds *today* with high confidence. What is unexamined is whether the embedded path is
**permanent** — if it ever stops being, the design gets materially simpler, so it is worth
stating that this was a choice.

**C4 is real but is the wrong axis to argue on.** For the setup-time reading it is
satisfied by construction — nothing is added to the step path at all. Listing it as a
peer constraint invites a performance debate the design does not need and cannot win on
(see §4.3).

### Goals — ranked

| rank | # | was | Goal |
|---|---|---|---|
| 1 | **G1** | R2 | One quantity → one buffer; shape and placement declared once |
| 2 | **G2** | R1 | A cross-granule producer→consumer handoff must be *expressible*, so it cannot silently become two allocations |
| 3 | **G3** | R3 | A derivation (`vn→u,v`, `theta_v,exner→T,p`) must have exactly one implementation, with its domain and halo semantics part of the declaration |
| 4 | **G4** | R8 | Cross-cutting sweeps (output, restart, halo sets) must be queries, not hand-written lists |
| 5 | **G5** | R11 | A field's **role is not implied by which container it sits in** |
| 6 | **G6** | R6 | Absence must be first-class — optional IAU increments, inactive tracers — not a zero allocation |
| 7 | **G7** | R7 | Multi-buffer/time-level must be expressible, at *different rates* (dyn substep vs tracer step) |

**Why this ranking.** G1 first because it is the only goal that makes a defect class
*unrepresentable* rather than merely detected, and because G2, G4 and G5 all lean on it.
G7 last because `TimeStepPair` already works and nothing there is broken. The point of
ranking is that someone can now say "we are taking G1–G3 and stopping" and have that be a
coherent position rather than an abandonment.

G6 is not hypothetical: the bindings already fake absence with a **dummy allocation**
(`wrapper_common.cached_dummy_field_factory`, used for `hdef_ic`/`div_ic`/`dwdx`/`dwdy`
and the optional IAU increments `vn_incr`/`rho_incr`/`exner_incr`).

### The budgeted resource is reviewer attention, not runtime

*"Identify the actual budgeted resource (rarely money — latency, bytes, schedule,
attention), track it publicly, and let one person control it."*

Here it is attention. PR 1360 is reported as +28110/−6228 with **zero reviews**; PR 1301
has been open since 2026-06-04 with reviewer requests unaddressed (both *reported*, not
re-checked here). Two consequences the design must respect:

- the **adoption order matters more than the end state**, because each rung has to survive
  review independently;
- arguing the design on runtime overhead spends the scarce resource on the wrong debate.

### Who this is for

*Better wrong than vague — an articulated guess can be corrected, an unspoken assumption
cannot.*

> The user is a **physics or dynamics developer adding or modifying a scheme** — fluent in
> ICON and gt4py stencils, not a software architect, and not someone who will read a
> framework manual first. Success means adding a field edits **one** place, and a mistake
> fails at setup naming the field rather than producing wrong numbers at timestep 3000.
>
> A second user is easy to forget: the **reviewer**, who must be able to answer "who
> writes this field?" from the diff.

The second one is load-bearing — it is the entire justification for recording `intent`.

### Restart is the requirement that settles G4 and G5

[[personal/msimberg/checkpoint-restart/checkpoint-restart|msimberg's checkpoint/restart doc]]
is the best-specified consumer we have, and it decides two arguments. (Verified against
the tree; his doc cites some pre-rename paths — `model/driver/` no longer exists and
`TimeLoop.restart_mode` is gone.)

- `main` has a **read** path — `read_restart_from_file` (`initial_condition/from_file.py:147`),
  serialbox-based, restoring prognostics + `exner_pr` + the predictor/corrector advective
  tendencies. There is no **write** path; `origin/ibm_02` has a serial pickle prototype.
- **G5 comes straight out of the restart inventory.** What must be checkpointed is
  prognostics *plus* the dycore diagnostics carried across steps — `exner_pr`,
  `ddt_vn_apc_pc`, `ddt_w_adv_pc` — while metrics, interpolation coefficients and compiled
  stencils must not be. "Is this restartable" is therefore **orthogonal** to "is this in
  the prognostic or the diagnostic container". The current split cannot express it, so
  `ibm_02` is forced to hand-pick three `DiagnosticStateNonHydro` members by name. That is
  exactly the hand-written list ICON's `in_group('dwd_fg_atm_vars')` abolishes.
- **Restart needs to allocate fields that do not exist yet**, which is the one thing
  reading metadata off a live field cannot do — `ibm_02`'s `_store_field` reads `dims` off
  the live field at write time because there is no declaration to read them from, making
  it a sixth independent re-derivation of field metadata. This is the
  `QuantityFactory`/`GridSizer` argument arriving from a second direction.
- **Tracer restart fails today for a naming reason, not a technical one.** Verbatim from
  `from_file.py:168`: *"the solve-nonhydro savepoints do not carry them, they are in the
  advection-init savepoint of the same date."* A grouping problem, stated as a
  `NotImplementedError`.

Note what the container should **not** own: `ndyn_substeps_var`, CFL-watch mode, elapsed
time and random seeds are all restart state but are not fields. Conflating them is a scope
error.

## 4. The central question: is the container a compiler or a runtime?

### 4.1 The objection, and what it actually rules out

The objection from havogt and msimberg — *"one global bucket passed around in its entirety
when only part of it would be enough"* — is correct, and stronger than it sounds. It is
[stamp coupling](https://en.wikipedia.org/wiki/Coupling_(computer_programming)) escalating
to common coupling, and the lazy-shared-store variant is the Blackboard pattern, whose own
POSA liabilities list reads: *difficulty of testing, difficulty of establishing a control
strategy, low efficiency, no support for parallelism.*

**But the objection applies to the run-time bucket, not to the mechanism.** Almost every
defect above is *decided* once, before the time loop starts:

> E1, E2, E5, E6, E7, E8, E9 and E10 are wiring facts fixed in setup. A fix that lives in
> setup needs no globally reachable mutable state at all.

So the container consumes *declarations* and emits *bindings*. Three tests for any
proposal:

1. **Freeze test** — can the *schema* be settled before the time loop? For icon4py yes:
   the tracer set is a pure function of `TracerConfig`, the output set of the namelist, the
   component set of config. But a hard freeze is not required — see M6 below.
2. **Reachability test** — can a **granule** reach the container? If yes you have built
   MPAS's pools, which MPAS-Ocean deleted for GPU (*"a large user-defined type did not
   perform well on GPUs"*) and whose successor Omega dropped entirely.
3. **Emission test** — is the output an ordinary dataclass gt4py accepts?

Two earlier framings were too strong and are **refuted by ICON-sc's working system** (see
[[personal/jcanton/model-state/model-state_prior-art|prior art]], §ICON-sc):

- *"If any object it created is still reachable when the first stencil runs, it has
  failed."* ICON-sc's vault **is** live at run time, for two load-bearing reasons:
  something must hold the buffers so a time-level swap can retarget the public view, and
  something must carry staleness counters so a stale wiring raises instead of silently
  binding dead buffers. The correct test is narrower: *nothing a **component** can reach;
  what survives is index-addressed only, holds no names on the step path, and is an
  instance rather than a module-level global.*
- *A two-phase lock with a hard freeze* (CCPP `lock_table`/`lock_data`, ICON's fatal
  post-`add_var`, NUOPC advertise→realize). A **staleness guard beats a freeze**: mutation
  stays legal, and running against a stale wiring raises. That forbids nothing and costs
  ~100 LOC.

### 4.2 What gt4py actually forces [corrected]

`gt4py/next/named_collections.py:35-49`, `CustomDataclassNamedCollectionABC.__subclasshook__`,
run against the live tree. The full rule is stricter than earlier revisions stated — it
requires `dataclasses.is_dataclass(subclass)`, a non-gt4py module, **at least one field**,
and per entry of `__dataclass_fields__`: `init is True`, `default is MISSING`,
`default_factory is MISSING`, **and `_field_type is dataclasses._FIELD`**.

Empirically (verified in icon4py's own venv):

```
dict                                    : False   # can NEVER cross the stencil boundary
dataclass with a ClassVar               : False   # <-- newly verified
dataclass with any defaulted field      : False
empty dataclass                         : False   # <-- newly verified
dataclass with `x: int | None` (no default) : True    # <-- corrects an earlier claim
dataclass with field(metadata=...) only : True
```

Three consequences:

1. **A name-keyed map is structurally barred from being a program argument.** C3 is not a
   compromise, it is mandatory; the last mile is always an explicit typed dataclass.
2. **[newly verified] A `ClassVar` disqualifies a container.** `__dataclass_fields__`
   retains ClassVar/InitVar pseudo-fields, and the `_field_type` check rejects them. Any
   design that attaches class-level metadata *to the state dataclass* — as opposed to the
   component — silently loses named-collection status. Both msimberg specs put
   `inputs_properties`/`outputs_properties` as `ClassVar` on the **Component**, which is
   safe; putting them on `InputT` would not be.
3. **[corrected] `| None` does not disqualify anything.** The hook never inspects
   annotations. What disqualifies `TracerState` today is `= None` **defaults**
   (`tracer_states.py:107-118`), and what disqualified `PrognosticState` was
   `tracer: TracerState = field(default_factory=...)`, which PR 1404 removed — verified:
   `PrognosticState` now has exactly `rho, w, vn, exner, theta_v` and is conformant.

   This matters for M11. A `TracerState` written as `qv: Field | None = spec(...)` with no
   default is *structurally* a valid named collection whose *instances* are sometimes
   unusable, because `None` is not a field value. The failure therefore moves from class
   definition to call time — which is the wrong direction. **Whether a container is a
   wiring object or a program argument must be part of its declaration, checked at
   `seal()`, not discovered when gt4py rejects a value.**

### 4.3 Do not argue this on speed

ICON-sc measured its entire negotiation/execution split at **6.7 %** of step time on a
real model (JW R02B04×35, gtfn_cpu, 3.68 → 3.43 s/step); the eye-catching 64–101× figures
are from a kernel-free toy. Its architecture doc is blunt: *"a dict lookup is ~40–60 ns and
slotted attribute access ~20–40 ns, but those were never the real cost."* The case for
typed dataclasses rests on C1 (structural prohibition), C2 (Fortran buffer adoption), and
type-checkability and explicit ownership — **not** on lookup cost.

### 4.4 The strongest objection, and the mechanism that answers it

egparedes, with our exact use case in view: *"The schema is configuration-dependent (the
tracer set alone varies), so **no static dataclass can be the public state type**."*

That is correct about a *static type* and beside the point for a setup-time **emitter** —
the type is fixed while the allocation set is config-dependent — **but only if M11
(conditional allocation from config predicates) is real**. M11 is entirely absent from
ICON-sc, and per §4.2 it also has to answer *how* an inactive slot is represented without
producing a container that type-checks and then fails at a program call. Leaving M11 as a
one-line row does not defuse the objection; it is the load-bearing mechanism for the whole
thesis, which is why it sits at step 2 of the adoption order.

### 4.5 The one honest exception to "setup-time is enough"

E3 and E4 are *not* fully setup-time defects. What is fixed at setup is which buffers
exist and who writes them; the divergent values are produced **every step**. No amount of
setup-time wiring makes `driver_io`'s dry temperature agree with muphys's moist one — that
needs a run-time barrier that recomputes a closed set of derived quantities from the
current prognostics.

This is M5-lite, and it is the single place where the design admits a per-step mechanism.
It should be stated plainly rather than absorbed into the "no run-time object" claim: the
setup-time reading kills E1/E2/E5/E6/E7/E8/E9/E10 by construction, and E3/E4 need one
named, profiled `update_derived_quantities()` call over an enumerated set.

### 4.6 Everyone who shipped this reached the same conclusion

| System | What it did | What it cost |
|---|---|---|
| **ICON** | registers every field twice (typed member *and* `add_var`) | ~15k lines of boilerplate — and the **compute path never queries the registry**; only 8 group-query sites model-wide, all I/O-ish |
| **CCPP** | resolves everything at build time | the framework is not in the executable; but its #1 regret is the *vocabulary*, and forbidding shared derivation produced **66 % interstitial glue** |
| **NDSL/Pace** | the *only other GT4Py model* — kept rigid dataclasses, put the intelligence in `field(metadata=...)` + a generic allocator | existence proof that the fix is orthogonal to dynamism |
| **ClimaAtmos** | built the dynamic bag | [migrating back](https://github.com/CliMA/ClimaAtmos.jl/issues/2217) to explicit structs (*"over 60 fields accumulated through splatting, unpacking and merging"*) |
| **LFRic** | built exactly the global keyed store | its own retrospective: *"an ever expanding pool of global scope data… becoming unwieldy… doesn't meet our aspiration to adopt an object approach with tight cohesion and loose coupling"* |
| **MPAS** | dynamic string-keyed pools | successor (Omega) dropped them entirely; silent-null lookup shipped as a bug class for a decade |

**Political corollary:** the setup-time reading changes **no granule call signature**. The
whole intervention lands in `driver_utils.initialize_granules`,
`driver_states.assemble_driver_states` and the test-side repacking — precisely the code
that is already replicated 13× and already contains three shipped wrong-key bugs.

## 5. Mechanisms

Separated so they can be adopted independently. **Bucket?** = needs a globally reachable
mutable name→field map at run time.

| # | Mechanism | Phase | Bucket? | Requires | Cost |
|---|---|---|---|---|---|
| M2 | Metadata on dataclass fields (`standard_name`, `units`, `dims`, `intent`, `scope`, `restart`) | setup | No | — | S mech / **L vocabulary** |
| M10 | Scope/lifetime tag + granule-private `Local` scratch type | setup | No | M2 | S |
| M11 | Conditional allocation from config predicates | setup | No | M2 | S |
| M3 | Declared I/O used for **validation only** | setup | No | M2 | S |
| M1 | Canonical allocation registry, signatures unchanged | setup, **sealed** | No | (M10) | M |
| M4 | Declared I/O → automatic wiring (emit the dataclass) | setup | No | M2 | M |
| M7 | Labels/groups, materialized at setup | setup | No | M2 | S / M vocab |
| M8 | Units: validate, don't convert | setup | No | M2 | S |
| M12 | Declared handoff + consumer arity check | setup | No | M1, M2 | S (~90 LOC) |
| M13 | Ordering constraints as declared data (`must_follow` / `must_precede`) | setup | No | M2 | S |
| M14 | Parameters as a structure distinct from state | setup | No | M2 | S/M |
| M5 | Lazy derived-field computation | run | No | M2, M6 | **H** |
| M6 | Staleness / generation counters | **run** | **Yes** | M1, M2 | M / H discipline |
| M9 | Automatic regridding as registered rules | run | No | M2, M5, M6 | **H** |

Notes on the ones that carry weight:

- **M1 kills E1 by construction.** One buffer named `vn_traj`, two references — the
  disjoint-allocation bug becomes *unrepresentable*. Half of it already works:
  `FieldSource.get` memoizes, so the driver path already aliases the static half. The gap
  is that the *time-varying* half never touches the factory, and the savepoint test path
  copies instead of aliasing. M1's phase is **sealed, not frozen** — see M6.
- **M3 is the highest value per line** (~150 lines) and is the one thing both existing
  specs already agree on. The current protocol is inert: zero classes *inherit*
  `Component`, it is not `@runtime_checkable`, both TODOs (unit matching, dimension
  consistency) are unimplemented, `Component.__call__` has no body and no `...` (so a
  class that forgets to implement it silently returns `None`), and the documented
  `IncompleteStateError` is raised by exactly one site — the IO monitor (`io.py:324`).
  **[corrected]** One real component does declare the contract: `muphys/component.py:49-50`
  sets `inputs_properties`/`outputs_properties` as plain class attributes. Nothing in
  production reads them — so M3 has a first consumer waiting, not a greenfield.
- **M10 covers the larger memory number.** Granule-private scratch (~29 full 3D fields
  across `SolveNonhydro`/`Diffusion`/`VelocityAdvection`) exceeds the cross-granule
  duplication. A shared container *without* a scope tag makes memory strictly worse, by
  making every private buffer globally reachable and never freed. NDSL's `Local` poisons
  the buffer at init, sets DaCe `transient=True` so the compiler can elide it, and enforces
  scope at run time.
- **M6 splits in two, and only one half is worth building.** *Structural* staleness — "is
  my wiring still valid?" — is cheap and replaces the freeze requirement entirely. ICON-sc
  uses three invalidation domains in ~100 LOC: `epoch` (a field identity changed ⇒ the
  wiring is stale ⇒ **raise**), `generation` (a swap changed the view ⇒ only cached views
  drop), `schema_hash` (the slot set changed), plus a debug `renegotiate_and_diff` that
  re-runs the wiring every N steps and diffs it. In-place value writes stale nothing —
  *"values are the user's business, identities are the plan's."* **Adopt this.**
  *Scientific* staleness — "is this derived field still consistent with its inputs?" — has
  no prior art anywhere (ICON, MPAS, CAM `pbuf`, NDSL track nothing; sympl's only mechanism
  is a wall-clock interval; ClimaAtmos replaced it with one explicit barrier) and can never
  be a correctness guarantee: gt4py's `Field` has no immutability concept and `.ndarray`
  hands out a writable buffer. **Defer it**; M5-lite's barrier removes the need.
  Verified: `grep -Ei "invalidat|stale|dirty|recompute"` over `states/` and `geometry.py`
  returns **zero** hits, and once `provider._fields[k] is not None` the value is returned
  forever — there is no evict API and `get()` takes only `(field_name, type_)`.
- **M12 gives G2 a mechanism.** Declare each producer→consumer handoff and check the
  arity at setup: 0 consumers *or* ≥2 both reject — *a dangling tendency silently loses
  physics, a double consumer double-applies it.* No runtime object; the check runs once and
  no data passes through it. **It catches E1 only under one-quantity ⇒ one-name ⇒ one-buffer
  (M1+M2)** — without those, `PrepAdvection.vn_traj` and `AdvectionPrepAdvState.vn_traj`
  are two legitimate slots and the check is decorative. Note ICON-sc's hole: it never checks
  *publisher* count, while ICON genuinely sums multiple publishers into `ddt_*`, so
  publisher multiplicity must be declared rather than assumed.
- **M13 (restored) — ordering constraints as declared data.** ICON's fast-physics ordering
  carries implicit contracts: saturation adjustment appears twice per step, surface transfer
  must run last, turbulence expects old-time-level inputs. Today those live in tutorial
  prose; declared, they become a build-time assertion. **This is the safety net
  [[personal/OngChia/physics-driver-and-components|OngChia's configurable component order]]
  needs and does not have**, and equally the one msimberg's freely-recomposable graph needs
  — reordering components is structurally easy and scientifically treacherous. Caveat from
  ICON-sc: it matches on free-form strings, so a typo in `must_follow` silently passes. Use
  references, not strings.
- **M14 keeps calibration constants out of state.** Tunable scheme parameters (entrainment
  coefficients, autoconversion thresholds) declared as a structure *separate from* state, so
  they are never smuggled through state fields. Needs zero JAX despite originating in
  ICON-sc's differentiability work; equally right for ensembles, perturbed physics, and
  namelist provenance.
- **M5/M9 carry the loudest warnings.** CCPP has wanted `theta_v,exner→T,p` derivation for
  years, has not built it, and scopes the issue *"(this is not an open-ended task!)"*. The
  `theta_v,exner ↔ T,p` cycle is real — ClimaAtmos documents the identical `ᶜK↔ᶜT↔ᶜp` cycle
  and breaks it with a physical approximation, not a solver. **Ship M5-lite instead**: one
  named, profiled `update_derived_quantities()` barrier over a closed, enumerated set. That
  removes E3 and E4 at ~10 % of the cost and stays compatible with full M5 later.

### On "unlimited labels"

ICON validates the idea and bounds it. The label is declared **at the field's definition
site, by the field's owner** — new field + right group string ⇒ it appears automatically in
output, restart-analysis, IAU, LBC prefetch, meteograms, ComIn. No central list to edit.
That is why each of those services is ~200 lines instead of ~5000. The namelist even gets
set algebra: `'group:atmo_ml_vars', '-qg', 'group:precip_vars'`.

Three amendments from ICON's own scars:

1. **Unknown label must raise.** ICON's `group_id` auto-creates on first use
   (`mo_var_groups.f90:193`) — a documented typo trap. MPAS's equivalent default is
   silent-null, a bug class that shipped for a decade.
2. **Materialize buckets at setup, never query per call.** Filtering 300 fields by label
   measures ~4 µs; at 100 call sites that is ~400 µs/timestep for zero physics. ICON's
   answer after 20 years is a fixed bitset with O(1) membership and only 8 query sites.
3. **Labels select; they do not address.** Groups in ICON never drive computation and never
   express placement — `cell vs edge` is `hgrid`, a scalar enum.

### On naming and placement

Key on `(quantity, placement)` where `placement` is the dims tuple, and treat the flat
string `theta_v_at_cells_on_half_levels` as its *rendering*, not the primary key. This
makes `dims` and `is_on_half_levels` derived rather than independently maintained (fixes
E8), and makes regridding an edge over a fixed quantity —
`theta_v@(Cell,K) → theta_v@(Edge,K)` — which is impossible if placement is welded into an
opaque string. CF names stay as output metadata only.

Escape hatch required: not everything factorises (`rbf_vec_coeff_e` on `(Edge, E2C2E)`;
`vn` vs `u,v` differ by more than placement). Those stay plain named fields with no
derivation rules.

## 6. Design it twice

The design above is A. B belongs on the page, because it is where the adoption order
already sits after step 3.

**Alternative B — declare and *check*, never generate.** Add per-field metadata (M2) and a
validator (M3), then **keep `driver_utils` exactly as it is**. The hand-written wiring stays
and becomes checked: a field whose declared `dims` contradict another container's raises at
startup, and a field-coverage test catches drift. No registry, no `build`, no change to
allocation.

| | A — emit the wiring | B — check the wiring |
|---|---|---|
| E7 (wrong keys) | yes — no keyword list survives | yes — the check catches it |
| E2/E8/E9 (contradictions) | yes | yes |
| E6 (boilerplate × 13 sites) | yes | **no** — all of it stays |
| E1's *class* | yes — one buffer per quantity makes it unrepresentable | **no** — a checker can report that two containers disagree; it cannot make them one buffer |
| E3/E4 | needs M5-lite either way | needs M5-lite either way |
| Cost | M1 + M4, a few hundred declaration lines, allocation moves | M2 + M3 only |
| Risk | new machinery on the setup path | almost none |

**B is not a straw man — it is the honest stopping point.** If the team never goes past M3
that is a coherent outcome: the correctness defects are fixed and the boilerplate remains.
A wins only if E6 and E1's *class* are judged worth the extra machinery. Stating this makes
the A-vs-B choice deliberate instead of something that happens by drift.

## 7. Recommended order

Each step independently shippable, each with standalone value.

0. **Free wins, no design commitment.** Add a field-coverage test per hand-map site (assert
   the keyword set equals `{f.name for f in dataclasses.fields(Target)}`, ~10 lines) so
   E6/E7 drift turns red *today*; **file E7's three wrong-key bugs now** — they are verified,
   live, and one-line fixes; adopt units-as-identity-validation (~110 LOC, no dependencies);
   adopt the `icon:`-namespace two-way invariant. All commit us to nothing.
1. **M2** — metadata on dataclass fields (NDSL's form), plus start the name file. Unblocks
   everything, breaks nothing, gt4py-safe (`metadata=` sets no default — verified). Include
   `origin`/K-domain from the start: gt4py fields carry a *domain*, not a shape, and that
   omission cost ICON-sc two work units of misdiagnosis. Reuse the `kind` key that
   `states/model.py` already defines rather than inventing a parallel one.
2. **M10 + M11** — scope tag and config-predicate allocation. The only two mechanisms that
   *reduce* memory, and **M11 is what answers the strongest objection to this whole
   document** (§4.4). M11 must also settle the wiring-object-vs-program-argument
   declaration (§4.2).
3. **M3** — validation, at class creation rather than first call. Highest value/line;
   already agreed by both existing specs; muphys is the ready-made first consumer.
4. **M1** — canonical allocation, settled at setup. Kills E1 by construction. No signature
   changes.
5. **M12** — handoff arity check. Cheap once M1+M2 exist, and it is what makes E1
   *unrepresentable* rather than merely fixed once.
6. **M4** — auto-wiring, **gated on M2's vocabulary being real**. Deletes E6. Hard
   dependency worth repeating: *auto-wiring keyed on today's vocabulary will silently bind
   the wrong field* — `metrics_attributes.py:104` already declares two distinct fields
   under one `standard_name`.
7. **M7** — labels. Unlocks output/restart/checkpoint sets; gives tracers an IO path at all
   (today `PROGNOSTIC_VARIABLES`/`DIAGNOSTIC_VARIABLES` are two hardcoded 5-element lists
   and tracers appear in neither).
8. **M5-lite** — one derived-quantities barrier over a closed set. Kills E3 and E4. This is
   the only run-time addition in the list (§4.5).
9. **M6-structural** (`epoch`/`generation`/`schema_hash` + debug renegotiate-and-diff) —
   adopt whenever setup-time wiring lands; it replaces the freeze requirement.
10. **M13 + M14** — declared ordering constraints and parameters separate from state.
    Independent of everything else; M13 should land *with* whichever composition layer wins.
11. **M6-scientific, M9, M5-full** — defer; each needs a written justification.

Acceptance criterion for the whole sequence, from ICON-sc: **the old and new wiring must
agree bitwise, as a release blocker, never a tolerance to widen.** They demonstrated exactly
this over 288 composed steps / 1440 dycore substeps.

## 8. What this does not solve

- **Granule scratch**, the larger memory number — fixed by a *type* (M10), not a container.
- **`nlev` vs `nlev+1`** — `fa.CellKField[float]` cannot express it and `KHalfDim` is erased
  to `KDim` at allocation (`factory.py:821-823`, *"remove once gt4py supports vertically
  staggered dimension"*). That is a type-system gap; no container fixes it, and it is why a
  half-level field's live domain reports `K` with length nlev+1 — which is what defeats
  reading metadata off a live field for restart.
- **Halo-exchange placement** — needs declared *access* (PSyclone derives exchanges
  statically from `gh_read`/`gh_write`/`gh_inc` × function space). No existing icon4py spec
  records `intent`. Recommended position: **record it now, consume it later** — recording is
  one word per field; building the consumer is a project, and ICON-sc is the cautionary tale
  (it declared the analogous halo metadata and never built a consumer, so the annotation
  sits inert).
- **The prognostic double buffer** — intentional and already optimal; `swap` is a pointer
  rebind.
- **Bit-reproducibility under laziness** — laziness makes evaluation order data-dependent,
  and bit-comparison against ICON savepoints is the entire validation strategy.
- **Module boundaries.** **[newly verified]** `tach check` currently enforces **nothing**:
  it reports "does not depend on" for *every* module, i.e. it resolves zero first-party
  imports. This confirms the tach ≥0.27 namespace-package regression documented in
  [[personal/egparedes/layered-architecture-refactor|the layered-architecture refactor]]'s
  Phase 0. Any argument of the form "the boundary check will stop a shared container from
  landing in the wrong package" is false today.

## 9. Conflicts with the other proposals

- **msimberg's spec has moved, and the agreement has inverted. [corrected]** Earlier
  revisions of this document said *"msimberg's spec is already the setup-time design —
  `convert_state(...)` returns an ordinary frozen dataclass and no bucket appears
  anywhere."* That was true of **v2** and is **false of
  [[personal/msimberg/revive-components/revive-components_spec_v3|v3]]**, which supersedes
  it. v3's D1/D2 introduce a shared mutable **`Carry`** that every step reads and writes in
  place, plus `sampler`'s recycle cache — precisely the run-time bucket the reachability
  test rejects. v3 concedes the consequence itself: *"the framework still cannot, in
  general, prove a component did not mutate a field it declared read-only; read-only is a
  debugging aid… not a hard guarantee on a shared mutable carry."* Three notes:
  - v3's `FlowKind` (prognostic/tendency/diagnostic/in_place/parameter) partly answers the
    old criticism that `kind` was doing two jobs, but still conflates **role**
    (prognostic/tendency/diagnostic) with **intent** (in_place) with **arity** (parameter).
    Splitting `intent` from `role` remains the right move and dissolves v3's Q1.
  - v2's AC14 (`ndarray.setflags(write=False)`) is already relaxed in v3 to best-effort. The
    old objection that `setflags` does not exist on cupy therefore no longer bites — and it
    remains **unverified** here (cupy is not installed in this checkout); worth a one-line
    check before citing.
  - v3's whole-graph `validate()` and M13 are the same idea approached from two directions
    and should be built once.
- **OngChia's design is the other one requiring a run-time container.** Two specific
  problems: its rule "each component derives its own inputs" is precisely what produced E3
  (CCPP ran the same experiment and got 66 % interstitial glue); and `is_fresh` answers "was
  this written recently", not "is this consistent" — a hole the document acknowledges
  itself, and one with no prior art anywhere. Its per-component call frequency and
  Jacobi/Gauss-Seidel selection are genuinely not covered elsewhere and should be kept.
- **[[personal/egparedes/layered-architecture-refactor|The layered-architecture refactor]]**
  independently reaches the same duplication findings and proposes merging `PrepAdvection`
  into a shared `ModelState`. Its `-> None` in-place contract is the most GPU-honest of the
  four. The conflict is that its `ModelState` is passed whole to every component at run
  time; its own conflicts section flags this, and it also flags that `ModelState` carries no
  per-field metadata with which to express G5.
- **None of the four covers**: allocation, scope/lifetime, conditional allocation, labels,
  halo exchange, or the vocabulary — and all of them assume CF standard names work for
  model-internal fields, which they do not (measured elsewhere at ~18 CF / 72 `icon:`;
  metrics coverage here is ~0/46).

## 10. Open questions for humans

Design/science/political, not answerable by more investigation.

1. **Which protocol wins?** Four open signatures is the real blocker — **and it is unlikely
   to be settled by merging the four.** *"Conceptual integrity comes from one empowered
   chief designer (or a two-person team) with genuine design authority, not from committee
   negotiation."* The productive question is therefore **who decides**, not whose design is
   best. Four authors each holding an effective veto is the failure mode.
2. **Exact or scientific restart?** The highest-leverage question in this list, because it
   is the only one forcing a per-field decision on every field in the model (G5), and
   because the restart doc has a 2-week appetite while this design does not. If restart ships
   first with a hand-picked field list, that list becomes the de-facto role vocabulary — so
   spend one conversation on `restart: bool` as metadata **before** the restart work starts,
   even if nothing else here is adopted.
3. **Is the Fortran-embedded path permanent?** If yes, the ABI stays flat pointers forever
   and the container is a host-side convenience only. Currently treated as a hard
   requirement (C2); stated here so reviewers can challenge it, because removing it
   simplifies the design materially.
4. **When IO and physics disagree, which temperature is *the* model temperature?** (E3.)
   Today the published one is dry.
5. **Is `mass_flx_ic` on half or full levels?** The two containers disagreed; PR 1404 chose
   half levels for the fallback branch but did not resolve the declaration. Science question.
6. **Has standalone-driver tracer advection ever produced validated results, given E1?**
   Who signs that off?
7. **Do we commit to a controlled name vocabulary, and which domain scientist owns it?** The
   *shape* is settled — unprefixed ⇒ claims CF identity, no CF name ⇒ must be `icon:<name>`,
   both directions enforced at registration. **Ownership remains open**, and it is CCPP's
   documented #1 regret.
8. ~~Do we require bitwise reproducibility across the refactor?~~ **Answered — yes, and it
   is achievable.** ICON-sc demonstrated old-wiring ≡ new-wiring bitwise over 288 composed
   steps. Adopt as a release blocker. It does *not* rule out setup-time derivation; it rules
   out **lazy** derivation.
9. ~~Do we accept a hard declare → bind → freeze → run lifecycle?~~ **Answered — no, and we
   don't need to.** A staleness guard beats a freeze (M6-structural), ~100 LOC, forbids
   nothing.
10. ~~What per-timestep Python overhead is acceptable?~~ **Withdrawn as a design axis.** The
    datapoint (6.7 % for an entire negotiation/execution split, with its own author saying
    lookup cost "was never the real cost") says this is the wrong debate to spend reviewer
    attention on.

## 11. Recurring failure mode of this document set

Three separate defects in earlier revisions — a count stated in four places and updated in
two, a `frozen` phase left standing after the freeze requirement was dropped, and a
"msimberg's spec agrees with us" claim that survived the spec being superseded — are the
same failure: **one fact represented in several documents and updated in some**. It is the
DRY violation the principles doc names, applied to prose.

The mitigation, adopted here: **counts, line numbers and file:line evidence live in exactly
one document (the evidence appendix) and are cross-referenced, not restated.** Where this
document quotes a number it is because the number *is* the argument.

## Appendices

- [[personal/jcanton/model-state/model-state_walkthrough|Walkthrough]] — the proposal
  explained concretely, as before/after pseudocode over icon4py's actual pipeline. **Start
  here if the mechanism list reads as abstract.** (Note: its Part 4 claim that `| None`
  disqualifies a gt4py named collection is superseded by §4.2 above.)
- [[personal/jcanton/model-state/model-state_evidence|Evidence]] — verified defects with
  file:line, the twelve unrelated icon4py defects found along the way (U1–U12, none yet
  filed), and the claims that could not be verified.
- [[personal/jcanton/model-state/model-state_prior-art|Prior art]] — ICON-sc, ICON, MPAS,
  CCPP, sympl, NDSL, ClimaAtmos, LFRic, WRF, CAM, MAPL, NUOPC; steal/avoid lists.

Related: [[personal/msimberg/revive-components/revive-components|Revive components]],
[[personal/OngChia/physics-driver-and-components|Physics driver and component design]],
[[personal/msimberg/checkpoint-restart/checkpoint-restart|Checkpoint/restart]],
[[personal/egparedes/layered-architecture-refactor|Layered architecture refactor]],
[[knowledge/software-engineering/principles|Working Principles]].
