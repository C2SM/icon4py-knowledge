---
title: Model state — v2 distillation
author: jcanton
tags: [state, model-state, components, fields, registry, metadata, duplication, allocation, labels, halo-exchange, restart, icon-sc, contracts, prior-art, constraints, goals]
created: 2026-08-10
status: draft
---

> **Provenance.** This is a proposed **v2 revision** of the
> [[personal/jcanton/model-state/model-state|Model state]] proposal: a distillation of its
> five-document set — the main document,
> [[personal/jcanton/model-state/model-state_evidence|evidence]],
> [[personal/jcanton/model-state/model-state_walkthrough|walkthrough]],
> [[personal/jcanton/model-state/model-state_prior-art|prior art]], and the
> [[personal/jcanton/model-state/model-state_specV2|spec-v2 review memo]] — into one
> self-contained document. The originals are left untouched alongside this file, the same
> convention the `_specV2` memo used: split out so the reviewed set stays stable and the
> revision can be argued as a whole. **Where this document and the original appendices
> disagree (the E3/E4/E6/E8/E9/E10 details in particular), the re-verified figures here
> supersede.** Every checkable claim was re-verified on
> **2026-08-10 against icon4py `origin/main` at `de151fad8`** — which matters, because the
> landscape moved since the originals were written: **PR 1301 merged on 2026-08-03**, PR 1404
> fixed the flagship defect, and several figures and characterizations below have been corrected
> accordingly. Corrections and disagreements with the original set are marked *(revised)*.
> This revision also **absorbs the verified findings of the parallel consolidation attempt
> (knowledge-base PR #18**, verified against `4c858a6a`, 2026-08-06**)** — its E3/E4/E6/E8/E9/E10
> sharpenings, the ClassVar consequence, the tach finding, and its reading of msimberg v3 —
> after independent re-verification here where possible, so that PR can be closed. Where a
> figure could not be re-run it is labelled *reported*; everything else is *verified*.
> Status is `draft` because this consolidation has not yet been human-reviewed; the
> pre-consolidation main document had been reviewed.
>
> A meta-lesson this document set keeps re-teaching, recorded so it survives the
> consolidation: every internal inconsistency found across its revisions (a count stated in
> four places and updated in two; a `frozen` phase outliving the freeze decision; a
> characterization of msimberg's spec outliving the spec) was **one fact represented in
> several places and updated in some** — the DRY principle applied to prose. The mitigation
> here: this document is self-contained, each count stated once, quoted only where the number
> *is* the argument — and against the originals kept alongside, the supersession note above
> applies. If this revision is accepted, the superseded originals should be retired rather
> than left to drift.

> **TL;DR** Several incompatible designs for "how components get their fields" have been in
> flight at once, none stating its requirements. This document states the requirements first —
> split into four non-negotiable **constraints** and seven **ranked goals** — then argues that
> the field container should be a **setup-time wiring step that emits ordinary typed
> dataclasses**, not a global bucket passed around at run time. The mechanisms are separated so
> they can be adopted one at a time, and an honest cheaper alternative ("declare and check,
> never generate") is presented next to the full design so the choice between them is
> deliberate.

## 1. The problem, and why now

Four designs for the component/state interface exist inside the icon4py orbit, mutually aware
only after the fact — and a fifth exists *outside* the tree as a working experimental
prototype (ICON-sc, §10):

| Design | Component signature | State shape | Status (2026-08-10) |
|---|---|---|---|
| [PR 1301](https://github.com/C2SM/icon4py/pull/1301) / [1360](https://github.com/C2SM/icon4py/pull/1360) | `__call__(dict[str, DataField], datetime) -> dict` | per-process `PhysicsState` gather/scatter adapter | **1301 merged 2026-08-03** (now `physics_driver` package on `main`); 1360 open, +17.5k lines, zero reviews |
| [[personal/egparedes/layered-architecture-refactor\|egparedes architecture refactor]] | `__call__(state: ModelState, step: StepInfo) -> None` | one shared typed `ModelState`, in-place writes | draft (PR 1358 closed; doc lives here) |
| [[personal/msimberg/revive-components/revive-components\|msimberg revive-components]] | v3: `run(state: InputT) -> OutputT`, `dtime` a field of `InputT` | typed frozen dataclasses + a graph-composition layer (`chain`/`loop`/`when`, `CarrySpec`) | **v3 spec** supersedes the v2 this document set originally argued against |
| [[personal/OngChia/physics-driver-and-components\|OngChia design]] | `__call__(state: StateView, time) -> dict` | run-time `StateProvider` + per-field freshness | draft |
| **ICON-sc** (egparedes) | sympl property contracts: components declare `input_properties`/`output_properties`, dict-based `array_call` | `dict[str, DataArray]` at the public boundary, compiled at **bind time** into a frozen execution plan over a slotted, index-addressed `StateVault` | **experimental architectural prototype**, hosting icon4py granules; published at [github.com/grAItools/ICON-sc](https://github.com/grAItools/ICON-sc/) — see §10 for references and lessons |

*(revised)* The original document called these "four incompatible designs" (and, inconsistently,
"five"). That framing conflates **two mostly orthogonal axes**:

- the **state axis** — who allocates fields, who wires them into containers, what metadata
  exists, who can query it;
- the **protocol axis** — what a component's call signature is and who orchestrates calls.

Rows 1 and 4 share the same dict signature and differ only in machinery; msimberg's v3 is
mostly an *orchestration* design (its `CarrySpec(..., initial=...)` takes caller-allocated
state and says nothing about who allocates it); ICON-sc spans both axes (its own state design
*and* a coupling algebra); and this proposal deliberately changes **no granule signature**
(§4). The genuine conflicts are narrower than "five incompatible designs": they are (a)
whether a run-time, component-reachable container exists at all — only OngChia's requires
one, egparedes' passes one whole, and ICON-sc keeps a run-time vault but proves components
cannot reach it and no name is resolved on the step path — and (b) **allocation, on which
the four in-tree designs are silent.** That silence is why the E1 class of defect survives
every one of them unchanged. (ICON-sc is the exception that proves the point: it *does* own
allocation — one buffer per contracted name — and thereby violates C2 instead; §10.)

Reconciling the protocol axis is still necessary — but it is a different decision, owned by
whoever owns the component protocol, and this proposal is compatible with any of the typed
outcomes. PR 1301's merge has meanwhile made the dict protocol the de-facto incumbent on
`main`; see open question 3.

## 2. Evidence: what the current shape has cost

Defects verified in icon4py `main`; status re-checked at `de151fad8` (2026-08-10). Paths
relative to the icon4py repo root. This list is **not a migration bill — it is the requirement
source**; each defect forces a requirement in §3.

| # | Defect | Status | Severity |
|---|---|---|---|
| E1 | `PrepAdvection` and `AdvectionPrepAdvState` held the same 3 quantities, allocated separately, with **nothing copying one into the other** — standalone-driver tracer advection ran on identically-zero trajectory velocity and mass fluxes | **fixed** by [PR 1404](https://github.com/C2SM/icon4py/pull/1404) (2026-07-30) — see below | correctness |
| E2 | Their `mass_flx_ic` disagreed on vertical extent (`nlev+1` vs `nlev`), so even a copy would not have been shape-compatible; `fa.CellKField[float]` cannot express the difference | **fixed** with E1; PR 1404's zero-field fallback now also allocates `extend={KDim: 1}`, settling the extent as half-levels | correctness |
| E3 | `T`/`Tv`/`p` derived in ≥4 places from **different inputs** — and worse than first stated: the IO path runs the diagnosis **fully dry**. `driver_io.py:146-147` allocates `qv, qc, qi, qr, qs, qg` once, all permanently zero (*"dry air: all hydrometeors stay zero (never written, so allocated once)"*) — `qv` included — so on the output path `virtual_temperature ≡ temperature` identically, and the temperature icon4py publishes is a **dry-air** temperature no physics component ever uses | **live** (`driver_io.py:181`, muphys `state.py`, `jablonowski_williamson.py`; PR 1360 adds a fourth) | science |
| E4 | `vn → u,v` computed at **two** production sites into two different buffers — `driver_states.py:290` writes `diagnostic_state.u/.v` and halo-exchanges after (`:302`); `driver_io.py:199` writes its private `_u/_v` and does **not**. The domain bounds do *not* differ (both run `lateral_boundary_level_2 → END`); the defect is the duplicated buffers plus the missing exchange. `driver_io.py:115` carries `TODO(kotsaloscv)` asking for exactly this refactor | **live** | correctness |
| E5 | `dycore.InterpolationState` (16 fields) is a strict superset of `DiffusionInterpolationState` (8); `geofac_div` declared in 3 containers; `ddqz_z_full` in 3; byte-identical one-field dataclasses in microphysics | **live** | duplication |
| E6 | `driver_utils.initialize_granules`: **91** hand-typed `.get()` mappings (count drifts upward with each merge), replicated at **~12 further sites** — the union of every file hand-constructing a granule interpolation/metric container (the earlier "7 sites" was an undercount; 11–13 depending on tree date and definition), of which **2 are the production Fortran binding wrappers** | **live** | boilerplate |
| E7 | Wrong-key bugs in exactly that replicated hand-mapping: `d2dexdz2_fac2_mc=…get(D2DEXDZ2_FAC1_MC)` and edge-normal into a dual-normal slot. The *intended* mapping is confirmed independently at three other sites (`driver_utils`, `test_diffusion`, `test_parallel_geometry`), so these are **filable today** with the evidence attached | **live** (`integration_tests/test_benchmark_solve_nonhydro.py:98,163`; `test_benchmark_diffusion.py`) — both type-check, both run; benchmark paths, not the production driver, and the *primary* site `driver_utils` is correct, which argues for deleting the replication rather than distrusting it | correctness |
| E8 | Placement recorded three times per field: name string (`…_at_cells_on_half_levels`), `dims=(CellDim, KHalfDim)`, `is_on_half_levels: bool` — the factory **rewrites `KHalfDim → KDim` at allocation** (`factory.py:540,545,823`, *"remove once gt4py supports vertically staggered dimension"*), so half-levelness survives only in a metadata tuple nothing validates. And the triplication is now **tested into place**: `is_on_half_levels` is read at `driver_io.py:83,242`, and a `test_driver_io` docstring states that `dims` and `is_on_half_levels` are *"stated independently"* — deliberately | **live** | drift |
| E9 | Five parallel namespaces per field (catalog key / CF name / ICON Fortran name / dataclass attribute / port name); four disjoint metadata dicts plus one orphan; ~0/49 metrics entries are real CF names; `units=""` for essentially all metrics and interpolation entries (though *not* geometry — the earlier "most" was too broad); and a **live collision**: `metrics_attributes.py:106-107` declares two distinct fields (cell and edge) under one `standard_name`, which the IO writer's `filter_by_standard_name` resolves variable identity by — they would silently alias into one netCDF variable | **live** | drift |
| E10 | The trend, verified on `origin/physics_driver_tmx` (2026-08-05): PR 1360 adds **seven** state dataclasses and **92 declared fields** for one component (`TmxDiagnosticState` 31, `TmxMetricState` 17, `TmxInputState` 16, …). `TmxInputState` re-declares all six fields of the common `DiagnosticState`, all six tracers, and `rho`/`w`; `TmxMetricState` re-declares five metrics fields; `TmxInterpolationState` makes `geofac_div` a **fourth** container; `gather_from_prognostic` re-derives `T`/`Tv`/`p` a fourth time | **live** (PR open) | trend |

E10 is the important row: duplication is being created faster than it is removed, because every
new component pays the full adapter-stack tax.

**E1/E2's fix is itself the strongest argument in this document.** PR 1404 added
`initialize_prep_tracer_advection` (`driver_states.py:222`): a hand-written function whose
whole job is to alias three of the dycore's buffers into a second container, plus an identity
test asserting the aliasing holds. Both are now permanent maintained surface, and every
future producer→consumer pair starts from the same footing. The fallback branch is the
sharper point: with no dycore, the same function allocates fresh zeros, and to get
`mass_flx_ic` right it must **restate the half-level extent in a second file**, with a
comment explaining why (*"one more level than KDim, like the dycore's … it stands in for"*)
— E2's knowledge, one quantity's vertical extent, now represented a third time, and that
representation was *created by the fix*. Under M1 (one quantity → one buffer, §5) neither
the function nor the test would need to exist, and the *class* of defect would be
unrepresentable rather than fixed once.

**Claims from the original investigation that remain unverified — treat with suspicion:**

- **All memory numbers** (~185 MB redundancy, ~290 MB granule scratch, etc.) were derived from
  an assumed grid not read from any file, and conflict with other estimates. Order-of-magnitude
  only. The load-bearing *relative* claim — granule-private scratch exceeds cross-granule
  duplication — should be measured before being cited.
- **Micro-benchmarks** (label filtering ~4 µs/300 fields, `gtx.as_field` copy cost) were
  measured on one laptop.
- **Prior-art line numbers** for sympl, climt, NDSL/Pace, ClimaAtmos, MPAS and CCPP are
  paraphrase-grade; only ICON, LFRic, gt4py and ICON-sc were read from local checkouts.
- A claimed tracer double-buffering bug tied to `ndyn_substeps_var` parity was derived by
  counting swaps; no test, no observed wrong answer.

## 3. Constraints and ranked goals

*(revised)* The original R1–R11 was a flat, unweighted list — the
[[knowledge/software-engineering/principles|Working Principles]]' "advocate-less wish list" red
flag. Split and ranked as the principles demand:

**Constraints** — non-negotiable; violating one makes a design wrong, not merely worse.

| # | Constraint | Forced by |
|---|---|---|
| C1 | Whatever reaches a `gtx.program` must be a static named collection | gt4py, structural — see §4 |
| C2 | The container must **adopt externally-owned buffers** — at `solve_nh_run` ICON owns the memory | the Fortran-embedded path |
| C3 | Granule call sites must keep naming their actual inputs | the havogt/msimberg stamp-coupling objection; also implied by C1 |
| C4 | No new per-stencil-call overhead | ~100 stencil calls per 20–50 ms timestep |

C2 holds *today* with high confidence — py2fgen's whole type model is
`ParamDescriptor = ArrayParamDescriptor | ScalarParamDescriptor` (no record descriptor, so
no struct can cross the ABI), and `bindings/tests/test_codegen_references.py` is a
golden-file test of the generated Fortran/C bindings, so any wrapper-signature change breaks
a checked-in artifact. What is **unexamined** is the assumption that the embedded path is
*permanent*: it is why the registry may not own allocation and why the adopt-external seam
exists, and if it ever stops being true the design gets materially simpler. Worth re-asking
explicitly before committing (open question 1).

C4 is real but is satisfied **by construction** in the setup-time reading — nothing is added
to the step path at all. Listing it as a peer constraint invites a performance debate the
design does not need and, per §4, should not be argued on.

**Goals** — ranked; a team taking "G1–G3 and stopping" is a coherent outcome.

| rank | # | Goal | Forced by |
|---|---|---|---|
| 1 | G1 | One quantity → one buffer; shape and placement declared once | E1, E2, E5, E8 |
| 2 | G2 | A cross-granule producer→consumer handoff must be *expressible*, so it cannot silently become two allocations | E1 |
| 3 | G3 | A derivation (`vn→u,v`; `theta_v,exner→T,p`) must have exactly one implementation, with domain and halo semantics part of the declaration | E3, E4 |
| 4 | G4 | Cross-cutting sweeps (output, restart, halo sets) must be queries, not hand-written lists | restart lists hand-picked; tracers have no IO path |
| 5 | G5 | A field's **role is not implied by which container it sits in** | the restart inventory, §9 |
| 6 | G6 | Absence must be first-class — optional IAU increments, inactive tracers — not a zero allocation | `dummy_field_factory` |
| 7 | G7 | Multi-buffer/time-level must be expressible, at different rates (dyn substep vs tracer step) | `TimeStepPair`, PR 1404 |

G1 ranks first because it is the only goal that makes defects *unrepresentable* rather than
merely detected, and because G2, G4 and G5 lean on it. G7 ranks last because `TimeStepPair`
already works and nothing there is broken. G6 is not hypothetical: the bindings already fake
absence with **dummy allocations** (`wrapper_common.cached_dummy_field_factory`, used for
`hdef_ic`/`div_ic`/`dwdx`/`dwdy` and the optional IAU increments
`vn_incr`/`rho_incr`/`exner_incr`).

**The budgeted resource is reviewer attention, not runtime.** PR 1301 took **two months and
102 review events** to merge; PR 1360 sits at +17.5k lines with **zero reviews**. Two
consequences: the adoption order matters more than the end state, because each rung must
survive review independently; and performance was the wrong axis to argue on (§4).

**The user model, stated explicitly** (better wrong than vague): the user is a physics or
dynamics developer adding or modifying a scheme — fluent in ICON and gt4py stencils, not a
software architect, and not someone who reads a framework manual first. Success means adding a
field edits **one** place, and a mistake fails at setup naming the field, not at timestep 3000
with wrong numbers. The second user is the **reviewer**, who must be able to answer "who writes
this field?" from the diff — that reviewer is the entire justification for recording `intent`
(§5, M2).

## 4. The design decision: the container is a setup-time emitter, not a run-time bucket

The objection from havogt and msimberg — *"one global bucket passed around in its entirety when
only part of it would be enough"* — is correct and stronger than it sounds: it is stamp
coupling escalating toward common coupling, and the lazy-shared-store variant is the Blackboard
pattern, whose own POSA liabilities list reads *"difficulty of testing, difficulty of
establishing a control strategy, low efficiency, no support for parallelism."*

But the objection applies to a **run-time** bucket. The decisive observation, checked defect by
defect:

> Every defect in §2 is created at setup time — in allocation and wiring code that runs once
> before the time loop. None of them requires run-time name resolution to fix. *(revised: the
> original said "not one of them recurs per timestep", which overstates E3/E4 — the duplicated
> derivations do execute every step; what is setup-time is the choice of which implementation
> and which inputs each site is wired to.)*

So the container consumes *declarations* and emits *bindings*: it assembles the typed
containers granules already take, then it is done — a factory floor, not a warehouse. Three
tests for any proposal in this space:

1. **Schema test** — can the schema be settled before the time loop? For icon4py yes: the
   tracer set is a pure function of `TracerConfig`, the output set of the namelist, the
   component set of config. A **hard freeze is not required**: ICON-sc (§10) shows a staleness
   guard beats a freeze — mutation stays legal, and running against a stale wiring raises
   (~100 LOC, forbids nothing).
2. **Reachability test** — can a **granule** reach a name-keyed store at run time? If yes with
   string lookups on the compute path, you have rebuilt MPAS's pools, which MPAS-Ocean deleted
   for GPU and whose successor Omega dropped entirely. *(revised)* A *typed* whole-state
   argument — egparedes' `ModelState` — is a different, milder failure: no string lookup, no
   dynamic hash, gt4py-compatible per member. What it violates is C3: the call site no longer
   names its inputs, so the reviewer cannot answer "what does this component read?" from the
   signature. Both fail the test, for different reasons of different weight.
3. **Emission test** — is the output an ordinary dataclass gt4py accepts?

### gt4py forces the last mile (verified from source)

`gt4py/next/named_collections.py:36-49` — `CustomDataclassNamedCollectionABC.__subclasshook__`
accepts a type only if it is a dataclass (outside `gt4py.*`) whose **every**
`__dataclass_fields__` entry has `init=True`, `default is MISSING`,
`default_factory is MISSING`, and is a regular field. Consequences, checked against the live
tree:

- A `dict` can never be a `gtx.program` argument. Whatever is built, the last mile is always
  an explicit typed collection — so C3 is not a compromise, it is mandatory.
- Any **defaulted field** disqualifies the container. `TracerState`
  (`tracer_states.py:106-116`, `qv: … | None = None` ×6) is disqualified today by its
  defaults; `PrognosticState` became conformant when PR 1404 removed its defaulted `tracer`
  field.
- *(revised — mechanics the original set had subtly wrong)* A `| None` **annotation alone does
  not disqualify** — the hook never inspects annotations, only defaults. And a `ClassVar`
  member **does** disqualify (the regular-field clause; `__dataclass_fields__` retains
  ClassVar pseudo-fields). Practical consequence: attaching class-level metadata *to a state
  dataclass* silently strips its named-collection status — the msimberg specs put
  `inputs_properties`/`outputs_properties` as `ClassVar` on the **Component**, which is safe;
  putting them on `InputT` would not be. And M11's optionality fails in the wrong place: a
  default-free container holding a `None` value passes the structural check and fails later,
  inside extraction — so **whether a container is a wiring object or a program argument must
  be part of its declaration, checked at `seal()`** (None-free at build for program
  arguments), not discovered when gt4py rejects a value (§5, M11).

**Do not argue this on speed.** ICON-sc measured the entire benefit of moving all
negotiation/lookup out of the step loop at **~6.8 % of step time on a real model** (JW
R02B04×35, gtfn_cpu, 3.68 → 3.43 s/step); the eye-catching 64–101× figures circulated earlier
are from a kernel-free toy, and ICON-sc's own architecture doc is blunt: *"a dict lookup is
~40–60 ns and slotted attribute access ~20–40 ns, but those were never the real cost."* The
case for typed dataclasses rests on the structural prohibition above (C1), on Fortran buffer
adoption (C2), and on type-checkability and explicit ownership — not on lookup cost.

### The strongest objection, answered

egparedes, with our exact use case in view: *"The schema is configuration-dependent (the tracer
set alone varies), so no static dataclass can be the public state type."* Correct about a
*static* type — and answered by a setup-time **emitter** only if M11 (conditional allocation
from config predicates) is actually built, which is why M11 sits at step 2 of the adoption
order rather than being a footnote. The type is fixed; the allocation set is config-dependent;
inactive means **no buffer and a build-time-checked absence**, not a zero field. The limit of
this answer should be stated too: it covers *closed* config spaces (the fixed `qv…qg` tracer
set). A genuinely open-ended tracer list (chemistry, ART aerosols) cannot be a fixed dataclass
and stays on the wiring side, with per-tracer fields extracted at call sites — which is
already how `tracer_advection.run(p_tracer_now=…)` works today.

### Everyone who shipped this converged on the same answer

- **ICON** registers every field twice (typed member *and* `add_var`), pays ~15k lines of
  boilerplate — and the compute path never queries the registry (8 group-query sites
  model-wide, all I/O-ish).
- **CCPP** resolves everything at build time; the framework is not in the executable.
- **NDSL/Pace** — the only other GT4Py model — kept rigid dataclasses and put the intelligence
  in `dataclasses.field(metadata=…)` plus a generic allocator.
- **ClimaAtmos** built the dynamic bag and is migrating back to explicit structs (*"over 60
  fields accumulated through splatting, unpacking and merging"*).
- **LFRic** built the global keyed store; its own retrospective calls it *"an ever expanding
  pool of global scope data… becoming unwieldy."*

**Political corollary:** the setup-time reading changes no granule call signature. The whole
intervention lands in `driver_utils.initialize_granules`, `driver_states.assemble_driver_states`
and the test-side repacking — precisely the code that is already replicated and already
contains the shipped wrong-key bugs (E6, E7).

## 5. Mechanisms

Separated so they can be adopted independently. **Bucket?** = needs a globally reachable
mutable name→field map at run time.

| # | Mechanism | Phase | Bucket? | Requires | Cost |
|---|---|---|---|---|---|
| M2 | Metadata on dataclass fields (`standard_name`, `icon_name`, `units`, `dims`, `origin`, `intent`, `scope`, `restart`) | setup | No | — | S mech / **L vocabulary** |
| M10 | Scope/lifetime tag + granule-private `Local` scratch type | setup | No | M2 | S |
| M11 | Conditional allocation from config predicates | setup | No | M2 | S |
| M3 | Declared I/O used for **validation only** | setup | No | M2 | S |
| M1 | Canonical allocation registry, signatures unchanged | setup, sealed | No | (M10) | M |
| M4 | Declared I/O → automatic wiring (emit the dataclass) | setup | No | M2 | M |
| M7 | Labels/groups, materialized at setup | setup | No | M2 | S / M vocab |
| M8 | Units: validate, don't convert | setup | No | M2 | S |
| M12 | Declared handoff + consumer/producer arity check | setup | No | M1, M2 | S (~90 LOC) |
| M13 | Ordering constraints as declared data (`must_follow` / `must_precede`) | setup | No | M2 | S |
| M14 | Parameters as a structure distinct from state | setup | No | M2 | S/M |
| M5 | Lazy derived-field computation | run | No | M2, M6 | **H** |
| M6 | Staleness / generation counters | **run** | **Yes** | M1, M2 | M / H discipline |
| M9 | Automatic regridding as registered rules | run | No | M2, M5, M6 | **H** |

Notes on the ones that matter most:

- **M1 kills the E1 class by construction.** One buffer named per `(quantity, placement)` key,
  however many container fields reference it. Half already works: the static-field factories
  memoize, so the driver path already aliases metrics/interpolation fields — but nothing
  declares that sharing and nothing checks it (*coincidental correctness*: the savepoint test
  path already breaks it by copying). The gap is that the time-varying half of the state never
  touches any factory.
- **M2 is the enabler for everything, and its hard part is not code.** The mechanism is
  NDSL's, verbatim: `spec(...)` wrapping `dataclasses.field(metadata=…)`, which sets no default
  and is therefore free under the named-collection rules (§4). Include `origin`/K-domain from
  the start — gt4py fields carry a *domain*, not a shape, and omitting it cost ICON-sc two work
  units of misdiagnosis. The **vocabulary** is the real cost: ~80 % of an atmospheric model's
  fields have no CF name (ICON-sc measured 18 CF / 72 `icon:`-namespaced). Adopt the two-way
  invariant — unprefixed ⇒ claims CF identity; no CF name ⇒ must be `icon:<name>` — enforced at
  registration. Who owns the vocabulary is open question 7.
- **M3 is the highest value per line** (~150 lines) and the one thing every proposal already
  agrees on. The current `Component` protocol's declared properties are completely inert —
  re-verified after PR 1301's merge: the shipped `physics_driver.run` never consults
  `inputs_properties`/`outputs_properties`; they remain decorative on `main` today, and the
  protocol's own TODOs (unit matching, dimension consistency) are still open. One nuance
  makes M3 cheaper than greenfield: `muphys/component.py:49` *does* declare both properties
  as plain class attributes — nothing reads them, so **M3 has a first consumer waiting**.
- **M10 covers the larger memory number.** Granule-private scratch (~29 full-3D fields across
  `SolveNonhydro`/`Diffusion`/`VelocityAdvection`) plausibly exceeds cross-granule duplication
  (unmeasured, §2). A shared container *without* a scope tag makes memory strictly worse by
  making every private buffer globally reachable and never freed. NDSL's `Local` poisons the
  buffer at init, sets DaCe `transient=True` so the compiler can elide it, and enforces scope
  at run time — the single most transferable idea in NDSL.
- **M11 answers the config-dependence objection** (§4) and, with M10, is one of only two
  mechanisms that *reduce* memory. Enforcement point *(revised)*: `reg.build(T, config=cfg)`
  allocates only fields whose `active_when` predicate holds, binds the rest to `None` — and a
  container declared as a program argument is validated **None-free at build**, because gt4py's
  structural check will not catch a None value, only a defaulted field.
- **M12 gives G2 a mechanism.** Declare each producer→consumer handoff; at seal, 0 consumers
  and ≥2 consumers both reject (*a dangling tendency silently loses physics; a double consumer
  double-applies it*), and 0 producers is E1 exactly. No runtime object — the check runs once.
  It catches the E1 class **only on top of M1+M2** (one quantity ⇒ one name ⇒ one buffer);
  without those, two same-named slots in different containers are both legitimate and the check
  is decorative. Do **not** assume one producer: ICON genuinely sums multiple publishers into
  `ddt_*` slots, so publisher multiplicity must be declared rather than assumed.
- **M13 is the safety net a configurable component order needs and does not have.** ICON's
  fast-physics ordering carries implicit contracts (saturation adjustment twice per step,
  surface transfer last, turbulence on old-time-level inputs) that live today in tutorial
  prose. Declared on the component (`must_follow`/`must_precede` as **references, not strings**
  — ICON-sc matched free-form strings, so a typo silently passes), they become a build-time
  assertion. Directly relevant to OngChia's user-configurable ordering and msimberg-v3's
  graph combinators, both of which make reordering structurally easy and scientifically
  treacherous.
- **M14 keeps calibration constants out of state.** Tunable scheme parameters (entrainment
  coefficients, autoconversion thresholds) declared as a structure separate from state, so they
  are never smuggled through state fields. Right for ensembles, perturbed physics and namelist
  provenance; needs none of the differentiability machinery it originated in.
- **M6 splits in two, and only one half is worth building.** *Structural* staleness — "is my
  wiring still valid?" — is cheap and replaces the freeze: `epoch` (a field's identity
  changed ⇒ wiring stale ⇒ raise), `generation` (a time-level swap ⇒ only cached views drop),
  plus a debug-build renegotiate-and-diff every N steps. The rule: **values are the caller's
  business, identities are the wiring's** — in-place writes stale nothing; rebinding raises
  instead of silently computing on a dead buffer. `prognostic_states.swap()` therefore
  invalidates nothing. *Scientific* staleness — "is this derived field consistent with its
  inputs?" — has no working prior art anywhere in the survey, can never be a correctness
  guarantee (gt4py fields hand out writable `.ndarray` buffers), and is deferred; M5-lite's
  barrier removes the need. For calibration, icon4py today has **zero invalidation machinery
  of either kind**: a grep for `invalidat|stale|dirty|recompute` over `states/` and the
  factories returns nothing, memoized providers return a cached field forever, and there is
  no evict API.
- **M5/M9 carry the loudest warnings.** CCPP has wanted `theta_v,exner→T,p` derivation for
  years, has not built it, and scopes its issue "*this is not an open-ended task!*"; the
  `theta_v,exner ↔ T,p` cycle is real (ClimaAtmos documents the identical cycle and breaks it
  with a physical approximation, not a solver). **Ship M5-lite instead**: one named, profiled
  `update_derived_quantities()` barrier over a closed, enumerated set of derivations. That
  kills E3 and E4 at ~10 % of the cost and stays compatible with full M5 later. Full laziness
  is additionally barred by bit-reproducibility (§8).

**On labels (M7), from ICON's twenty years:** the label is declared at the field's definition
site, by its owner — new field + right group string ⇒ it appears automatically in output,
restart-analysis, IAU, LBC prefetch, meteograms, plugins; no central list to edit; that is why
each of those services is ~200 lines instead of ~5000, and the namelist even gets set algebra
(`'group:atmo_ml_vars', '-qg'`). Three amendments from ICON's own scars: unknown label must
**raise** (ICON auto-creates on first use — a documented typo trap; MPAS's silent-null
equivalent shipped bugs for a decade); **materialize buckets at setup, never query per call**;
labels are a selection mechanism, never an addressing or placement mechanism.

**On naming and placement:** key on `(quantity, placement)` where placement is the dims tuple,
and treat the flat string `theta_v_at_cells_on_half_levels` as its *rendering*, not the primary
key. `dims` and `is_on_half_levels` become derived rather than independently maintained (fixes
E8), and regridding becomes an edge over a fixed quantity — impossible if placement is welded
into an opaque string. CF names stay as output metadata only. Escape hatch required: not
everything factorises (`rbf_vec_coeff_e`; `vn` vs `u,v` differ by more than placement) — those
stay plain named fields with no derivation rules.

## 6. Concretely

Today's pipeline has three setup phases and a loop; every §2 defect is created in the setup
phases. **The proposal changes only those.**

```python
# ─── TODAY ──────────────────────────────────────────────────────────
# A: static fields — three memoized factory sources (already lazy, already aliasing;
#    this half of the problem is solved, but nothing declares or checks the sharing)
# B: hand-wire granule containers — 91 hand-typed `.get()` keyword mappings in
#    driver_utils, replicated at ~12 sites  (E5, E6, E7)
# C: allocate mutable state — driver_states.assemble_driver_states; before PR 1404
#    this allocated the same three quantities twice, disconnected  (E1, E2, E8)
# D: the time loop — dycore accumulates into prep_adv over ndyn_substeps_var substeps;
#    advection reads it once per step; prognostic_states.swap()

# ─── PROPOSED ───────────────────────────────────────────────────────
# A′: DECLARE — the container classes stay exactly the frozen dataclasses granules
#     take today; each field additionally says what it IS (M2, NDSL's mechanism):
@dataclasses.dataclass(frozen=True)
class DiffusionInterpolationState:
    geofac_div: gtx.Field = spec(
        quantity="geofac_div",          # canonical name — ONE per quantity (same
                                        #   string the dycore's container uses)
        icon_name="geofac_div",         # the ICON Fortran name, for the bindings
        dims=(CellDim, C2EDim),         # placement, single source of truth → E8
        units="1", intent=READ, scope=STATIC,
    )
    ...

# B′: REGISTER + EMIT — setup, once:
reg = FieldRegistry(grid, vertical_grid, allocator)
reg.adopt_sources(static_sources)       # adopt the memoized factories, don't re-allocate
reg.declare(PrognosticState, DiagnosticStateNonHydro, PrepAdvection,
            AdvectionPrepAdvState, DiffusionInterpolationState, ...)
reg.declare_handoff("vn_traj", producer="dycore", consumer="advection")   # M12
reg.seal()                              # no NEW quantities after this; not a freeze

prep_adv        = reg.build(PrepAdvection)
tracer_prep_adv = reg.build(AdvectionPrepAdvState)   # same quantities ⇒ SAME buffers
...

# C′: gone — allocation happened inside build, once per quantity.
# D′: the time loop — IDENTICAL to today. `reg` is not mentioned; no lookup happens;
#     nothing is lazy; no dict crosses a stencil boundary.
```

What each defect costs then: E1's class becomes unrepresentable (one buffer per quantity —
`build` hands both containers the same object, no aliasing function, no identity test); E2/E8
become a contradiction the registry rejects at `seal()` (two containers claiming different
`dims` for one quantity); E6 collapses to one `build` line per container; E7 becomes
impossible (no keyword list left to mistype); E5's sharing becomes declared instead of
coincidental.

**The honest cost side:**

- One `spec()` per field across the model — `MetricStateNonHydro` alone is 32 fields; a few
  hundred declaration lines total. Real work. But it replaces more than it adds: the
  declaration is written once per field; the hand-mapping it deletes was written once per field
  *per site* (~12 sites), and the ~50-line repack in each Fortran binding wrapper becomes a
  table walk over the same declarations.
- A wrong `spec` fails at `seal()` naming the field — today the same mistake is E7: it
  type-checks, runs, and produces wrong numbers.
- **Tests keep working untouched.** The containers remain ordinary constructors;
  `reg.build` is an additional path, not a replacement. That matters across ~269 test files.
- New machinery on the setup path that must itself be reviewed and maintained.

**The Fortran-embedded path survives (C2).** At `solve_nh_run` (`dycore_wrapper.py:306`) ICON
owns the memory: 37 raw fields + 10 scalars under ICON Fortran names, re-packed into five
containers **on every call** (`:370-421`) — a third hand-maintained copy of the ICON↔icon4py
name map. Under the proposal the wrapper calls `reg.adopt_buffers({...})` (zero-copy wrapping
is already icon4py's own technique) and `build` reads the same declarations; nothing is held
across calls on this path today and nothing would be, so `epoch` is not consulted there. If
ICON's pointers are stable across calls — they are module-level allocatables, so very likely —
the rebuild is memoizable on pointer identity; that is an optimization to measure, not a
requirement. Two hard consequences stand: the registry must adopt buffers it did not allocate,
and no struct can cross the ABI (py2fgen has no record descriptor; the wrapper keeps
flattening).

### The alternative that must stay on the page: declare and *check*, never generate

Design-it-twice demands the genuine competitor, and it is not a straw man — it is the honest
stopping point, exactly where the adoption order (§7) sits after step 3:

**Alternative B.** Add per-field metadata (M2) and a validator (M3), then **keep
`driver_utils` exactly as it is**. The hand-written wiring stays and becomes checked: declared
`dims` that contradict another container's raise at startup; a ~10-line field-coverage test per
site catches drift.

| | A — emit the wiring | B — check the wiring |
|---|---|---|
| E7 (wrong keys) | yes — no keyword list survives | yes — the check catches it |
| E2/E8/E9 (contradictions) | yes | yes |
| E6 (boilerplate × ~12 sites) | yes | **no** — all of it stays |
| E1's *class* | yes — one buffer per quantity | **no** — a checker can report that two containers disagree; it cannot make them one buffer |
| E3/E4 (divergent derivations) | needs M5-lite either way | needs M5-lite either way |
| Cost | M1 + M4, a few hundred declaration lines, allocation moves | M2 + M3 only |
| Risk | new machinery on the setup path | almost none |

The E3/E4 row deserves its own sentence, because it bounds what *either* design can claim:
those two defects are not fully setup-time — the divergent values are produced every step —
so no amount of wiring, emitted or checked, fixes them. They need M5-lite's per-step barrier,
**the single place where this design admits a run-time mechanism.**

If the team never goes past B, that is a coherent outcome: the correctness defects are fenced
and the boilerplate remains. A wins only if E6 and E1's class are judged worth the extra
machinery. Stating this makes the A-vs-B choice deliberate instead of something that happens
by drift.

## 7. Adoption order

Each step independently shippable, each with standalone value — which is what the budgeted
resource (reviewer attention, §3) demands.

0. **Free wins, no design commitment.** File E7's wrong-key bugs now — verified, live, and
   one-line fixes; the per-site field-coverage test (~10 lines each — E6/E7 drift turns red
   today); units-as-identity-validation (~110 LOC, no dependencies); the `icon:` namespace
   two-way invariant.
1. **M2** — metadata on dataclass fields, `origin` included; start the name file. Reuse the
   `kind` key `states/model.py` already defines rather than inventing a parallel one.
2. **M10 + M11** — scope tag and config-predicate allocation: the only two mechanisms that
   *reduce* memory, and M11 is what answers the strongest objection (§4).
3. **M3** — validation at class creation. Highest value per line; agreed by every proposal.
   *— Alternative B stops here, coherently. —*
4. **M1** — canonical allocation, settled at setup. Kills the E1 class. No signature changes.
5. **M12** — handoff arity check; cheap once M1+M2 exist.
6. **M4** — auto-wiring, **gated on M2's vocabulary being real**: auto-wiring keyed on today's
   vocabulary will silently bind the wrong field (`metrics_attributes.py:106-107` already
   declares two distinct fields under one `standard_name`). Deletes E6.
7. **M7** — labels: unlocks output/restart/checkpoint sets; gives tracers an IO path at all.
8. **M5-lite** — one derived-quantities barrier over a closed set. Kills E3 and E4; the
   only run-time addition in the whole sequence.
9. **M6-structural** — adopt whenever setup-time wiring lands; it replaces the freeze.
10. **M13, M14** — independent of everything else. M14 lands opportunistically; M13 should
    land *with* whichever composition layer wins the protocol question.
11. **M6-scientific, M9, M5-full** — deferred; each needs a written justification.

**Acceptance criterion for every step, demonstrated feasible by ICON-sc over 288 composed
steps / 1440 dycore substeps: the old and new wiring agree bitwise, as a release blocker,
never a tolerance to widen.**

## 8. What this deliberately does not solve

- **Granule-private scratch** — the (plausibly) larger memory number — is fixed by a *type*
  (M10), not a container.
- **`nlev` vs `nlev+1`** — `fa.CellKField[float]` cannot express it and the factory erases
  `KHalfDim → KDim` at allocation (`factory.py:540,545,823`). A gt4py type-system gap; no
  container fixes it, M2's `dims`+`origin` metadata only fences it.
- **Halo-exchange placement** — needs declared *access* (PSyclone derives exchanges statically
  from access mode × function space). Record `intent` now (one word per field); building the
  consumer is a separate project — and ICON-sc is the cautionary tale, having declared halo
  metadata and never built its consumer.
- **The prognostic double buffer** — intentional and already optimal; `swap` is a pointer
  rebind.
- **Bit-reproducibility across refactors is kept, not solved**: laziness would make evaluation
  order data-dependent, which is one reason M5-full is deferred.
- **Integration control state** (`ndyn_substeps_var`, CFL-watch mode, elapsed time, random
  seeds) is restart state but not fields; the container holds fields, and conflating the two
  is a scope error.
- **Module boundaries.** `tach check` currently enforces **nothing**: it resolves zero
  first-party imports, the tach ≥ 0.27 namespace-package regression documented in
  [[personal/egparedes/layered-architecture-refactor|the layered-architecture refactor]]'s
  Phase 0 (re-confirmed by the parallel verification in PR #18). Any argument of the form
  "the boundary check will stop a shared container from landing in the wrong package" is
  false today.

## 9. Restart: the consumer that settles G4 and G5

[[personal/msimberg/checkpoint-restart/checkpoint-restart|msimberg's checkpoint/restart doc]]
is the best-specified consumer of field metadata we have, and it decides two arguments.

State of play (verified): `main` has a serialbox-based **read** path
(`initial_condition/from_file.py`) restoring prognostics + `exner_pr` + the advective
tendencies; no **write** path; `origin/ibm_02` has a serial pickle-based prototype writer.

- **G5 comes straight from the restart inventory.** What must be checkpointed is prognostics
  *plus* the dycore diagnostics carried across steps (`exner_pr`, `ddt_vn_apc_pc`,
  `ddt_w_adv_pc`) — while metrics, interpolation coefficients and compiled stencils must not
  be. "Is this restartable" is orthogonal to "which container is this in"; the prog/diag split
  cannot express it, and `ibm_02` is consequently forced to hand-pick three
  `DiagnosticStateNonHydro` members by name — precisely the hand-written list ICON's field
  groups abolish.
- **Exact vs scientific restart is a per-field decision** — a label set chosen once, not a
  code path.
- **Restart must allocate fields that do not exist yet**, which is the one thing reading
  metadata off a live field cannot do. `ibm_02`'s writer reads `dims` off the live field at
  write time (a sixth independent reinvention of field metadata), so it cannot restore into a
  fresh process, and half-levelness cannot reach the file because the factory already erased
  it (E8). This is the declare-`dims`-once argument arriving from a second direction.
- **Tracer restart fails today for a naming reason, not a technical one** — the savepoint
  grouping, stated as a `NotImplementedError`.

If restart ships first with a hand-picked field list, that list becomes the de-facto role
vocabulary. The restart doc has a 2-week appetite; this design does not. So the one
conversation worth having *before* that work starts is `restart: bool` in M2's metadata —
even if nothing else here is adopted (open question 8).

## 10. Prior art, compressed

One-line verdicts; steal/avoid distilled. Line numbers were read from local checkouts for
ICON, LFRic, gt4py and ICON-sc; the rest are paraphrase-grade.

| System | Container | Resolution | Verdict for icon4py |
|---|---|---|---|
| **ICON-sc** (egparedes' prototype) | boundary dict → slotted vault at run time | bind-time, frozen execution plan | closest test of this document's thesis: confirms it, and corrects it in three places (see the dedicated subsection below) |
| **ICON** (Fortran) | typed derived types **+** parallel `add_var` registry | run time, I/O only | steal metadata-at-definition-site + labels; never pay the dual declaration (~15k lines) |
| **MPAS** | string-keyed pools | run time | avoid — its own team deleted it for GPU; successor Omega dropped it |
| **CCPP** | host model's, unchanged | build time, generated glue | the framework is not in the executable; but its #1 regret is the *vocabulary*, and forbidding shared derivation made 66 % of one suite interstitial glue |
| **sympl / climt** | `dict[str, DataArray]` | run time, per call | icon4py's `Component` protocol descends from it; its maintainers abstracted the container away for performance |
| **NDSL / Pace** | rigid dataclasses + field `metadata` | setup | closest technical analogue — the other GT4Py model, and it stayed rigid; source of M2, M4 (~40 lines, no registry), M10's `Local`, and `QuantityFactory`/`GridSizer` |
| **ClimaAtmos** | prognostic `Y` + cache `p`, one explicit refresh barrier | — | migrating back to explicit structs; source of the M5-lite barrier pattern |
| **LFRic / PSyclone** | field collections + global store | compile time | steal declared-access → derived halo exchange (the biggest structural prize, needs `intent` not a container); its retrospective rejects the global store |
| **CAM `pbuf` / Omega** | runtime buffer | init-time index, run-time access | resolve names once into typed handles; never a string lookup in a kernel |
| **WRF Registry** | text table → generated types | build time | one declaration driving many services — as a bespoke DSL, the cautionary form of M4 |
| **NUOPC** | advertise → realize | init-time negotiation | unconnected exports cost zero memory (M11's shape); errors on ambiguity, never guesses |

### ICON-sc: an experimental architectural prototype, with its own model-state proposal

**What it is.** ICON-sc is an **experimental architectural prototype** of a full alternative
Python architecture for the ICON model — sympl/Tasmania-lineage composition (property-contracted
components, a dynamics–physics coupling algebra) over a zero-copy device-field boundary —
**hosting** icon4py granules rather than forking them. It was built in six agent-driven days
(work units 001–014, 2026-07-08→13). Because it was built against *our* exact problem on *our*
codebase, it is the only system in this survey whose evidence is directly transferable — and
the one whose claims need the most calibration (below).

**References.** The prototype is published: repository at
[github.com/grAItools/ICON-sc](https://github.com/grAItools/ICON-sc/), documentation site at
[graitools.github.io/ICON-sc](https://graitools.github.io/ICON-sc/). (The original doc set's
calibration claim "nothing pushed to any remote" is thereby outdated.) Pointers:

- [The architecture document](https://graitools.github.io/ICON-sc/architecture/icon-sc_architecture.html)
  (v1.3; source at `docs/architecture/icon-sc_architecture.md`) — the canonical description.
  For model state specifically: §2 *(state, fields, and the zero-copy protocol — the state
  dictionary, ingress adapters, contracts/canonical units, naming)* and §8.2 *(bind-time
  specialization: the negotiation vs execution split)*.
- [`plan/bind.py`](https://github.com/grAItools/ICON-sc/blob/main/packages/icon-sc-core/src/icon_sc/core/plan/bind.py)
  (~1730 lines) — the plan compiler;
  [`state/vault.py`](https://github.com/grAItools/ICON-sc/blob/main/packages/icon-sc-core/src/icon_sc/core/state/vault.py)
  (203 lines) — the run-time `StateVault`.
- [`development/REGISTRY.md`](https://github.com/grAItools/ICON-sc/blob/main/development/REGISTRY.md)
  — work-unit register, trunk decisions, human sign-offs;
  [`development/references/lock.toml`](https://github.com/grAItools/ICON-sc/blob/main/development/references/lock.toml)
  — the append-only, SHA-pinned provenance ledger for every borrowed constant and tolerance
  (itself worth stealing as a process artifact).
- Its [README](https://github.com/grAItools/ICON-sc/#readme) records the merged vertical
  slice's validation claims: L2 parity at upstream tolerances, 9-day bitwise-zero equivalence
  against the icon4py standalone driver, and T0 ≡ T1 bitwise through the dycore.

**Its model-state design — the fifth alternative in §1.** State crosses the public boundary
as `dict[str, DataArray]` under sympl property contracts (each component declares
`input_properties`/`output_properties` with dims and canonical units). At **bind time** a
compiler dissolves the composition tree into a frozen execution plan: names are resolved once,
contracts are checked once, and what survives into the time loop is a slotted,
**index-addressed** `StateVault` that no component can reach — a test proves **zero name
lookups per step** with an instrumented dict, and forbids `xarray`/`pint`/contract frames
inside `run_step`. Mutation stays legal without a freeze via three invalidation domains
(`epoch`: a field's identity changed ⇒ stale wiring raises; `generation`: a time-level swap ⇒
only cached views drop; `schema_hash`: the slot set changed), plus a debug-build
renegotiate-and-diff. Buffer *adoption* is the primary ingress path (`from_state` never
allocates), units are validated as identity and never converted, and fields without a CF name
must carry the `icon:` prefix (measured split: 18 CF / 72 `icon:`).

**Calibration.** Zero GPU execution ever (its GPU workflow asserts GPU tests *skip*), zero
MPI, 2 of ~11 NWP schemes, no real-data ingestion; several of its most-quoted ideas — the
halo validator above all — are **unbuilt** in its own tree; the validation claims above are
self-reported, backed by genuinely strong internal review discipline (it caught a tolerance
loosening with fabricated provenance) but not by production contact.

**Lessons learned**, in decreasing order of weight:

1. **It confirms the central thesis of §4.** Its architecture doc states it independently —
   *"nothing about the interfaces changes during execution … every lookup performed in the
   loop is recomputing an invariant"* — and it demonstrated the bitwise old≡new acceptance
   criterion this document adopts (§7) over 288 composed steps / 1440 dycore substeps.
2. **It corrects three claims of this document's earlier drafts** (all folded into §4): a
   container-created object *may* survive into the loop — something must hold buffers across
   a swap and carry the staleness counters, and the right test is component-unreachability,
   not non-existence; the performance stake is ~6.8 %, not orders of magnitude; and a static
   dataclass cannot be the public state type without conditional allocation (M11 — which
   ICON-sc itself entirely lacks).
3. **The dict is what costs.** The ~1730-line compiler exists chiefly to *erase* a
   `dict[str, DataArray]` that its own interpreted tier introduced — the compiler is 8.5× the
   size of the container it feeds, and icon4py never has to introduce that dict. This is the
   strongest single argument for emitting typed dataclasses directly.
4. **It does not solve C2.** ICON-sc is the driver and owns allocation (one buffer per
   contracted name — its answer to G1), so its two hosted granules copy ~17 full fields per
   Δt (~100 MB) in and out. Any icon4py-native design must *adopt* buffers instead.
5. **Its transferable residue is small and already absorbed into §5**: M6-structural (the two
   counters), M12's arity check (closing its own hole — it never checks *publisher* count,
   while ICON sums multiple publishers into `ddt_*`), M14 (parameters separate from state),
   units-as-identity, the `icon:` invariant, `origin`/K-domain as first-class metadata (its
   omission cost ICON-sc two work units of misdiagnosis), and the `lock.toml` provenance
   process. Estimated transferable code ≈300 LOC out of ~3700 LOC of compiler + tests.
6. **Do not adopt its unbuilt or unused parts**: the coupling algebra (7 combinators, 2
   used — a hand-written closure is bitwise-equivalent to the federation it replaces); the
   F-tier/JAX lowering (a *second* physics implementation, 763 hand-ported lines, and
   `functional_state()` abolishes component privacy); the halo story (`HaloState.DIRTY` never
   assigned, `HaloPolicy` without a consumer); ping-pong SSA time levels (its own dycore
   opted out, keeping `nnow`/`nnew` component-private).

**Steal** (beyond the mechanisms already in §5 and the ICON-sc items above): units as
identity-validation with the conversion path quarantined (sympl's per-call conversion is its
own documented performance regret; ICON's `post_op` converts only at the file boundary);
capability-vs-request separation (`vert_interp` says *how* a field could be interpolated, the
namelist says *whether*); revision counters over content hashes for any invalidation (hashing
is O(field bytes) and its payoff never fires in floating-point dynamics).

**Avoid**: a run-time bucket reachable from compute code; silent lookup failure or
auto-creation of unknown names; dual declaration kept in sync by hand; a general derivation
planner *and* the opposite extreme of forbidding shared derivation; per-call unit conversion;
assuming CF names cover model-internal fields (~80 % have none); adopting the unbuilt parts of
any prototype.

## 11. Relation to the other proposals *(updated 2026-08-10)*

- **[[personal/msimberg/revive-components/revive-components|msimberg's revive-components]]**:
  the original conflict analysis targeted the **v2** spec (`run(state, dtime)`,
  `convert_state`, `setflags(write=False)` read-only enforcement — the cupy objection applied
  to its AC14 and is moot for v3, which already downgrades read-only to best-effort). **v3
  supersedes all of that** and moves the design to a graph-composition layer above
  `Component`. Two readings of v3 were argued in the two parallel consolidations of this
  document, and both are partly right, so state the synthesis precisely. *On the declaration
  side they compose*: v3 owns control flow (chain/loop/when, schedules), this proposal owns
  allocation/wiring/metadata, and `reg.build(...)` emits exactly the caller-allocated
  containers v3's `CarrySpec(..., initial=…)` expects. *On the execution side v3's D1/D2 is
  a run-time, name-addressed store*: every step reads and writes a shared mutable `Carry`,
  the component adapters rebuild `InputT` from carry slots **per call**, and `sampler` keeps
  a name-keyed recycle cache — and v3 concedes the consequence itself (*"read-only is a
  debugging aid … not a hard guarantee on a shared mutable carry"*). Components never touch
  the carry directly (the adapters do), so this is not MPAS pools — but the reachability and
  emission tests of §4 apply to its executor, and the resolution is the bind-once treatment
  ICON-sc applied: resolve carry-slot → dataclass-field bindings **once at setup** and the
  per-step repacking disappears, dissolving the conflict. Three further points stand: v3
  says nothing about who allocates, so **the E1 class survives it intact**; its `FlowKind`
  conflates `role` (prognostic/tendency/diagnostic) with `intent` (in-place) with arity
  (parameter) — the `intent`/`role` split this document recommends dissolves its open
  question Q1; and its whole-graph `validate()` and M13 are the same idea approached from
  two directions — build it once.
- **[[personal/OngChia/physics-driver-and-components|OngChia's design]]** is the only one
  requiring a run-time container. Two specific problems: "each component derives its own
  inputs" is the rule that produced E3 (CCPP ran the same experiment and got 66 % interstitial
  glue); and `is_fresh` answers "was this written this timestep", not "is this consistent" — a
  hole the design documents itself (derived fields are not invalidated when their inputs
  change). Its per-component call frequency and Jacobi/Gauss-Seidel selection are genuinely
  covered nowhere else and should be kept — as driver/orchestration features, which is also
  where msimberg-v3's `sampler` overlaps them.
- **[[personal/egparedes/layered-architecture-refactor|egparedes' layered-architecture
  refactor]]** independently reaches the same duplication findings and proposes merging
  `PrepAdvection` into a shared `ModelState`. Its `-> None` in-place contract is the most
  GPU-honest of the four. The conflict is real but narrower than "bucket" *(revised, §4)*: a
  typed `ModelState` passed whole violates C3 (call sites stop naming their inputs), not the
  string-lookup prohibition. Its Phase 6 explicitly depends on the protocol question this
  document leaves to its owner.
- **[[personal/msimberg/checkpoint-restart/checkpoint-restart|Checkpoint/restart]]** is a
  consumer, not a competitor — see §9. One conversation (`restart:` metadata) should precede
  its 2-week execution.
- **What no other proposal covers**: allocation, scope/lifetime, conditional allocation,
  labels, halo intent, time-level rates, the vocabulary — and all of them assume CF standard
  names work, which they do not.

On the protocol question itself, the Working Principles are blunt: conceptual integrity comes
from one empowered designer, not committee negotiation — four drafts merged by consensus will
not produce a coherent protocol. The productive question is *who decides*, not *whose design
is best*. And events have partially decided it: PR 1301's merge made the dict-based protocol
the incumbent on `main`. If the team wants a different protocol, that is now a migration, not
a green-field choice.

## 12. Open questions

1. **Is the Fortran-embedded path permanent?** (C2). Currently held as a hard requirement; it
   shapes the entire adopt-don't-own allocation design. Re-validate explicitly — if it falls,
   the design simplifies materially.
2. **Which temperature is *the* model temperature?** When IO and physics disagree (E3), which
   one is written to output is a science decision nobody has signed off — today the published
   one is dry.
3. **Has standalone-driver tracer advection ever produced validated results?** While E1 was
   live it ran on identically-zero mass fluxes; PR 1404 fixed the wiring, but who signs off
   that post-fix results are scientifically valid?
4. **Who owns the component protocol?** Four signatures were open; PR 1301's merge made the
   dict protocol the incumbent while the typed alternatives remain drafts. Someone with design
   authority must either ratify or supersede it — merging the drafts by negotiation will not
   converge.
5. **What per-timestep Python overhead is acceptable, as a number?** Still open; with the
   datapoint that the entire stake measured ~6.8 % on a real model, whatever is built should
   not be justified on this axis.
6. **Do we commit to a controlled name vocabulary, and which domain scientist owns it?** The
   shape is settled (CF or `icon:`-prefixed, two-way invariant, enforced at registration); the
   ownership is not, M4 is gated on it — and it is CCPP's documented #1 regret.
7. **Exact or scientific restart?** The highest-leverage question in the list: it forces a
   per-field decision on every field in the model (G5), and the restart work's 2-week appetite
   means its answer will be set de facto very soon (§9).
8. ~~Bitwise reproducibility across the refactor?~~ **Answered**: yes, and it is achievable
   (ICON-sc, 288 steps); adopt as a release blocker. It rules out lazy derivation, not
   setup-time derivation.
9. ~~A hard declare→bind→freeze→run lifecycle?~~ **Answered**: no — a staleness guard beats a
   freeze (M6-structural); mutation stays legal and stale wiring raises.
10. ~~Is `mass_flx_ic` on half or full levels?~~ **Answered by PR 1404 as science**: half
    levels (`nlev+1`), both branches of the fix now allocate accordingly — but the answer
    lives in an allocation call and a comment, not in any declaration; the type still cannot
    express it (§8), so the knowledge remains one refactor away from being lost.

## Appendix: unrelated icon4py defects found along the way

Found while ICON-sc hosted icon4py granules; none is about state containers, all are
actionable independently, and **none has been filed upstream**.

| ID | Finding | Status |
|---|---|---|
| U1 | Graupel cold-glaciation water-budget leak: supercooled qc at T ≲ 233 K near the moist-domain top gains total water, +1.59e-4 kg/m² per Δt=30 s, suppressed by any coexisting ice-phase seed | has a runnable, wrapper-free reproducer on public APIs |
| U9 | `is_surface` index bug in the graupel scan: `k_lev` is a carry relative to `kstart_moist`, compared against an absolute `ground_level`, so the surface clamps only fire when `kstart_moist == 0` | verified independently; one line |
| U2 | `wgtfacq_c`/`wgtfacq_e` emitted on shifted K-domain `[nlev−3, nlev)`, visible only in the factory registration | cost ICON-sc ~2 work units; same class as E8 |
| U3–U5 | Grid-factory: `mean_cell_area` off 4e-5 relative; RBF pentagon divide warnings; `keep_skip_values=False` + `_replace_skip_values` makes the RBF matrix exactly singular for file-sourced grids | latent trap for grid-from-file |
| U6 | `SPECIFIC_HEAT_CAPACITY_ICE = 2108.0` vs ICON's `2106.0_wp`; live only in a non-default branch | latent, covered by no verification data |
| U7 | satad: ICON silently caps at `maxiter`; icon4py raises `ConvergenceError` | bites the first non-default configuration |
| U8 | The multi-substep dycore test is MCH-only (`# why is this not run for APE?`) | test-coverage gap |
| U11 | `total_precipitation_flux` computed only under `do_latent_heat_nudging=True`, else exact zeros | would mislead as a diagnostic |
| U12 | Every `solve_nonhydro`/diffusion integration test xfails on `embedded`; the diffusion granule cannot be constructed there | rules out "embedded as reference tier" for a wiring-equivalence harness |

U1 and U9 are filable today with evidence attached; U3–U5 file as one issue; U6/U7/U11 are
one-liners; U8 is a test-coverage PR.

---

Related: [[personal/msimberg/revive-components/revive-components|Revive components]],
[[personal/OngChia/physics-driver-and-components|Physics driver and component design]],
[[personal/msimberg/checkpoint-restart/checkpoint-restart|Checkpoint/restart]],
[[personal/egparedes/layered-architecture-refactor|Layered architecture refactor]],
[[knowledge/software-engineering/principles|Working Principles]].
