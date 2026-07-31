---
title: Model state — prior art
author: jcanton
tags: [state, model-state, prior-art, icon-sc, icon, mpas, ccpp, sympl, ndsl, lfric, registry, labels, ecs]
created: 2026-07-29
status: draft
---

> Appendix to [[personal/jcanton/model-state/model-state|Model state]].
> What other codes do about field containers and components declaring their inputs.
> Line numbers for ICON, LFRic and gt4py come from local checkouts; the rest are
> paraphrase-grade — spot-check before citing externally.

## The one-line verdict per system

| System | Container | Components declare inputs? | Resolution | Verdict for icon4py |
|---|---|---|---|---|
| **ICON-sc** | `dict[str, DataArray]` at the boundary → slotted `StateVault` at run time | **yes**, sympl property contracts | **bind time**, emits a frozen execution plan | the closest test of this document's thesis: **confirms it, and refutes three of its claims**. Take the small pieces, leave the compiler |
| **ICON** (Fortran) | typed derived types **+** parallel `var_list` registry | no | run time, I/O only | steal the *metadata-at-definition-site* + *labels*; do not pay the dual declaration |
| **MPAS** | `mpas_pool_type`, dynamic hash tables | no | run time, string-keyed | **avoid** — its successor dropped it |
| **CCPP** | host model's, unchanged | **yes**, `.meta` files | **build time**, generates the glue | closest to the goal; the framework is not in the executable |
| **sympl / climt** | `dict[str, DataArray]` | yes, `input_properties` etc. | run time, per call | icon4py's `Component` is derived from it; maintainers abstracted the container *away* for performance |
| **NDSL / Pace** | rigid dataclasses + field `metadata` | metadata only | setup | **closest technical analogue** — the other GT4Py model, and it stayed rigid |
| **ClimaAtmos** | prognostic `Y` + cache `p` | no | one explicit barrier | migrating *back* to explicit structs |
| **LFRic** | field collections + a global keyed store | **yes**, PSyclone kernel metadata | **compile time**, generates halo exchanges | steal the declared-access→derived-halo idea; its own retrospective rejects the global store |
| **CAM** `pbuf` | runtime-addressable buffer | index requested at init | init-time index, run-time access | two-phase lookup is the right shape |
| **WRF** | `Registry` text table → generated derived types | no | build time | codegen for state + IO + nesting + halos from one table |
| **NUOPC** | `ESMF_State` / `FieldBundle` | **yes**, advertise→realize | init-time negotiation | unconnected exports cost zero memory |

## ICON-sc — the only system built against our exact problem

egparedes' prototype: a sympl+Tasmania composition layer over a zero-copy device-field boundary,
**hosting** icon4py granules rather than forking them. Unlike everything else in this document it
was built to solve *our* problem on *our* codebase, so it carries the most weight — and needs the
most calibration.

**Calibration.** Six days, agent-driven (work units S01–S14, 2026-07-08→13); **nothing pushed to
any remote**; 7 human sign-offs still `pending`. **Zero GPU execution, ever** (`test-gpu.yml`
runs on `ubuntu-latest` and asserts GPU tests *skip*). **Zero MPI** (`test-mpi.yml`'s `mpirun -n 4`
is a shell comment). 2 of ~11 NWP schemes; no real data; tiers T2/T3 are 5-line roadmap stubs.
Its architecture doc is a **design proposal** — much of what it describes most confidently is
unbuilt. Its internal review discipline is genuinely strong (it caught a tolerance loosening
across six fields with fabricated provenance); that is not the same as production contact.

**What it confirms.** `plan/bind.py` is **1732 lines**; `state/vault.py` is **203** — the compiler
is 8.5× the container. A test proves **zero name lookups per step** with an instrumented dict, and
forbids `xarray`/`pint`/contract frames inside `run_step`. No component can reach the container.
Buffer *adoption* is the primary path: `from_state` never allocates, adopts `.data`, *"never
`.values`: no duck-array coercion"*. Its architecture doc states our thesis independently:
*"nothing about the interfaces changes during execution … every lookup performed in the loop is
recomputing an invariant."*

**What it refutes** — the three corrections are folded into the main document, recorded here so
the source is traceable: (1) "nothing the container created may survive into the time loop" is too
strong — its vault *is* live, because something must hold buffers across a swap and carry the
staleness counters; (2) the performance case is wrong — the whole negotiation/execution split
measured **6.7 %** on a real model (3.68 → 3.43 s/step), and its author notes dict-vs-attribute
lookup *"was never the real cost"*; (3) a static dataclass genuinely cannot be the *public* state
type, because the schema is config-dependent — which is why M11 is load-bearing rather than a
footnote. It also does **not** solve R4: it is the driver, owns allocation, and its two hosted
granules copy in and out **17 full-field memcpys per Δt (~100 MB)**.

**Steal**

| Idea | Size |
|---|---|
| **Units as identity-validation, never conversion** — one canonical unit per name, checked at class creation; Pint lazily imported and quarantined by a subprocess test proving it never enters `sys.modules` on the apply path | ~110 LOC, no deps |
| **`icon:` namespace, two-way invariant** — unprefixed ⇒ claims CF identity; no CF name ⇒ *must* be `icon:<name>`; enforced at registration. Measured split **18 CF / 72 `icon:`** — 80 % of an atmospheric model has no CF name | S |
| **`origin`/K-domain as first-class metadata** — gt4py fields carry a *domain*, not a shape. Omitting it cost them ~2 work units of misdiagnosis; publish the symptom signature (*"bitwise-unequal across identical rebuilds"* ⇒ out-of-domain reads, not physics) | S |
| **Two counters instead of a freeze** — `epoch` (identity changed ⇒ wiring stale ⇒ raise) vs `generation` (swap ⇒ only cached views drop); *"values are the user's business, identities are the plan's"*. Plus a debug `renegotiate_and_diff` | ~100 LOC |
| **Declared I/O validated at class creation** (`__init_subclass__`), cross-dict dims/units consistency, and `ContractViolation(field, component, kind, actual, target)` batched into one error | ~40 LOC |
| **Single-consumer arity check on handoffs** — 0 or ≥2 both reject. Close their hole: they never check *publisher* count, while ICON sums multiple publishers into `ddt_*` | ~90 LOC |
| **Parameters as a structure distinct from state** — tunable scheme constants never smuggled through state fields. Zero JAX needed | S/M |
| **`lock.toml`** — an append-only SHA-pinned provenance ledger for every borrowed constant and tolerance; plus the reviewer rules (re-derive every tolerance from the pinned upstream test; mutation-probe every oracle) | M |
| **T0 ≡ T1 bitwise as a release blocker, "never a tolerance to widen"** — demonstrated over 288 composed steps / 1440 dycore substeps | process |

**Avoid**

- **The plan compiler** (2090 LOC + 1603 LOC of tests). 1732 lines exist to *dissolve a
  sympl/Tasmania composition tree*; icon4py has no such algebra to dissolve. Carries 42
  `PlanCompileError` refusal sites; hosting *one* dycore required inventing a new hook quartet.
  Transferable residue ≈300 LOC.
- **`dict[str, DataArray]` as the state type.** They needed vault + compiler + swap variants +
  cadence masks + guards to recover what a typed dataclass gives free. **ICON-sc built a
  1732-line compiler whose main job is erasing a dict its own interpreted tier introduced —
  icon4py never has to introduce it.**
- **The coupling algebra** — 7 combinators, **2 used**; a hand-written closure in their own preset
  is bitwise equivalent to the federation it replaces.
- **The F-tier / JAX** — not a lowering but a *second physics implementation* (763 hand-ported
  lines); the `custom` route has zero implementations. It would *cost* design: `functional_state()`
  abolishes component privacy, and `CallingFrequency` lowers to running radiation unconditionally
  every step.
- **The halo story** — `HaloPolicy`, `halos="auto"`, the composition-time validator. **Entirely
  unbuilt**: `HaloState.DIRTY` is never assigned anywhere in `src/`, `HaloPolicy` has no consumer,
  and `communicates_internally=True` is declared by both real components and read by nothing —
  both delegate halos back into the icon4py granule. The architecture calls it "the single most
  valuable safety net"; the annotation is 8 lines and the consumer is the entire cost.
- **Ping-pong SSA for time levels** — only n=2, no `nsav`, and **their own dycore opted out**,
  keeping `nnow/nnew` component-private.

Note on the zero-copy wrap they use (`gtx_common._field(buffer, domain=...)` aliases with
write-through; public `gtx.as_field` copies): **this is not an ICON-sc asset** — icon4py already
uses it in `bindings/icon4py_export.py:96`, `states/factory.py:93` and `solve_nonhydro.py:1030`.
What remains is the inconsistency: `DiagnosticState.surface_pressure` still uses `as_field` and
copies on every attribute read. `_field` is private API; they pin it via `lock.toml`, which is the
right way to depend on it.

## ICON — validates labels, warns about everything else

**The dual representation.** Every field is both a member of a derived type (`t_nh_diag%vt`)
and registered via `add_var` with a pointer to itself. This costs ~15k lines across
`mo_nonhydro_state.f90` (5218), `mo_nwp_phy_state.f90` (7120), `mo_nwp_lnd_state.f90` (2186)
for 2307 `add_var` + 235 `add_ref` calls. **Python has no reason to pay this** — declare once,
derive typed access.

**Variable groups — the strongest argument for the labels idea.** `groups('atmo_ml_vars', ...)`
attaches a `LOGICAL(MAX_GROUPS)` bitset to each field at its `add_var` site. 83 static groups
plus runtime-created ones for tiles. Membership is a single array index — O(1), allocation-free.

What groups buy:

| Consumer | What the group replaces |
|---|---|
| `output_nml` | thousands of hand-listed names; users write `group:dwd_fg_atm_vars` |
| init/analysis reading (`MODE_IAU_*_IN`) | a hardcoded per-init-mode list of what to read from which file |
| `mo_save_restore.f90` | the hand-maintained IAU snapshot/restore field list |
| `mo_async_latbc.f90` | which fields the LBC prefetch rank must read |
| meteogram, ComIn, LaTeX docs | one sweep each |

The namelist gets set algebra: `ml_varlist = 'group:atmo_ml_vars', '-qg', 'group:precip_vars'`.

**Crucially the label is declared at the field's definition site, by its owner.** New field +
right group string ⇒ it automatically appears in output, restart-analysis, IAU, LBC prefetch,
meteograms and plugins. No central list to edit. That is why each of those services is ~200
lines rather than ~5000.

Three scars to avoid:

1. `group_id` **auto-creates unknown groups** (`mo_var_groups.f90:193`) — a documented typo
   trap. Also `mo_name_list_output_init.f90:776`: *"typos are not detected but the corresponding
   variable is simply not removed"*. **Make unknown labels raise.**
2. Groups **never drive computation** — only 8 query sites model-wide, all I/O-ish. They never
   express placement (`cell vs edge` is `hgrid`, a scalar enum) and never gate allocation.
3. `MAX_GROUPS` was bumped 200→250 between forks. Fixed caps are a Fortran artifact.

**Other things worth stealing:** capability-vs-request separation (`vert_interp`/`hor_interp`
say *how* a field could be interpolated; the namelist says *whether*); `post_op` +
`inverse_post_op` — pointwise output-time transforms carrying their own transformed metadata,
working in both directions; explicit construction phase then a **hard freeze** (`add_var` after
the ComIn secondary constructor is fatal); `memory_used` accounting for free once allocation
goes through one funnel.

**What ICON gets wrong:** timelevel faked via `.TLn` name mangling plus global `nnow/nnew/nsav1/nsav2`
arrays, with the same 4-line filter duplicated in output, restart, save_restore and ComIn — make
timelevel a first-class key. Sentinel-zero index globals (`iqv`, `iqc`, …) for optional tracers —
presence in the container should be the test. No staleness or provenance tracking anywhere;
`lrestart_read` is the only provenance bit that exists.

## MPAS — the design being proposed, and its own team deleted it

Pools are dynamic hash-table containers: `mpas_pool_get_field/get_array/get_dimension/get_config`,
subpools, iterators, generated from `Registry.xml` with conditional allocation via `packages`.

- The global registry `block%allFields` is used **only by I/O**; compute goes through named subpools.
- Default lookup failure is `MPAS_POOL_SILENT` + `nullify(field)` — a misspelled key prints
  nothing and returns null. That bug class shipped for a decade.
- The pool name is part of a field's address (`diag` vs `diag_physics` both holding `relhum`),
  so moving a variable between pools breaks every call site.
- **GPU verdict:** MPAS-Dev PR #496 replaced the pool-based mesh struct with plain module
  variables because *"a large user-defined type did not perform well on GPUs"*; #580 added a
  bypass pool for offload; #891 added `mpas_pool_get_array_gpu`.
- **E3SM's MPAS successor, Omega, dropped pools entirely**, exposing tracers as
  `getByIndex(TracerArray, TimeLevel, TracerIndex)` because *"the latter may be preferred for
  performance reasons"* — i.e. resolve the name once, index thereafter.

The one genuinely good idea: `Registry.xml` `packages` + `active_when` — **conditional
allocation from a config predicate**. That is mechanism M11 and it is the only surveyed
mechanism that reliably reduces peak memory.

## CCPP — "declare your inputs and magically get them", done at build time

`.meta` files declare `standard_name`, `long_name`, `units`, `dimensions`, `type`, `intent`
for every scheme argument. `ccpp_prebuild.py` matches each scheme's requirements against the
**host model's** provided variables and generates the caps. Suite Definition Files order the
schemes.

This is exactly the "component declares `inputs_properties` and gets fields injected" idea —
and **the framework is not in the executable**. Automatic unit conversion is generated into the
caps (`mm__to__m() → '1.0E-3{kind}*{var}'`).

Costs, from their own issue tracker:

- The #1 documented regret is the **vocabulary**: *"there is no easy mechanism for scheme
  developers to know which Standard Names are already in use"*. It needed a curated 1250-name
  dictionary and two dedicated tools to police metadata↔code drift.
- Local name collisions still break it (#772: two schemes each with an argument `ni` produced
  uncompilable generated code).
- Codegen slowdown at scale (#688: 12 s → 230 s resolving many suites).
- **Derived quantities were never built.** Issue #349 has wanted `theta_v, exner → T, p`
  derivation for years and scopes it *"(this is not an open-ended task!)"* — the parenthetical
  is in the original, as a warning against generalized derivation graphs.
- Forbidding shared derivation instead produced **35 of 53 schemes being interstitial glue
  (66%)** in `suite_SCM_GFS_v16.xml`. Both extremes are bad; a small closed set is the answer.

## sympl / climt — the direct ancestor, and its performance verdict

icon4py's `Component` protocol (`inputs_properties` / `outputs_properties` / `__call__`) is
recognisably sympl's `input_properties` / `output_properties` / `tendency_properties` /
`diagnostic_properties`, each entry carrying `dims` and `units`.

Genuinely good: `get_numpy_arrays_with_properties` / `restore_data_arrays_with_properties` do
automatic unit conversion, dim reordering and aliasing; wildcard dims; composites detect
conflicting outputs at construction; **unit algebra** derives a stepper's `output_properties`
from its children's `tendency_properties` by appending the time unit — pure setup-time, and it
catches tendency-vs-value confusion for free. climt's `get_default_state` allocates only the
union of the active components' declared inputs — that is conditional allocation (M11).

The warning: the maintainers' own issues (#43 *"unit conversion checking takes up a significant
amount of CliMT's runtime"*, #46 cataloguing `DataArray.transpose()` "very slow", chained
property access, `DataArray.__init__` "huge overhead") led them to **abstract the container
away** behind a `StateBackend`. The dict-of-labelled-arrays state is the part they had to
engineer around.

**Recommendation: validate units, never convert.** On GPU every conversion is an allocation plus
a full-field kernel. Convert only at the file boundary, where the cost is already paid — ICON's
`post_op` is the proven pattern.

## NDSL / Pace — the closest technical analogue, and it stayed rigid

The only other GT4Py-based atmospheric model. **It holds state in rigid dataclasses, exactly
like icon4py — but with per-field metadata and a generic allocator, so the rigidity costs
almost no boilerplate.** They deliberately did not build a dynamic registry.

```python
@dataclass()
class DycoreState:
    u: Quantity = field(metadata={"name": "x_wind", "dims": [X_DIM, Y_INTERFACE_DIM, Z_DIM],
                                  "units": "m/s", "intent": "inout"})
    def __post_init__(self):        # validates declared metadata against the actual Quantity
        ...
```

Three transferable pieces:

1. **`State._init(quantity_factory)`** walks `dataclasses.fields`, recurses into nested
   dataclasses, and allocates each field from its declared `dims`/`units`/`dtype`. Adding a
   field to a state means adding *one line*. This is mechanism M4 in ~40 lines, with no registry.
2. **`QuantityFactory` + `GridSizer`** own the `dims → (origin, extent, shape)` map. A field
   only ever declares symbolic dims. This is the piece icon4py most obviously needs — a
   `(CellDim, KHalfDim)` tuple resolved to a concrete allocation by one sizer object, which
   would also fix the `KHalfDim → KDim` erasure.
3. **`Local`** — a `Quantity` subclass for granule-private scratch that (a) poisons the buffer
   at init (`data[:] = 123456789`) so accidental reads blow up, (b) sets DaCe `transient=True`
   so the compiler can elide the allocation entirely, (c) raises if read from outside the
   object that allocated it. **This is the single most transferable idea in NDSL** and it
   attacks the memory problem without any global registry.

Also note: `"intent": "inout"` is declared and used by nothing — the same latent hook icon4py
has. And their `# TODO: move a-grid winds to temporary internal storage` on `ua`/`va` is
icon4py's `u`/`v` problem verbatim; they noted it and did nothing for years.

**No staleness tracking, no lazy derivation, no labels, no unit conversion anywhere in NDSL.**
Units are asserted, never converted.

## ClimaAtmos — the cautionary tale, plus one good idea

Splits prognostic `Y` (in the ODE state vector, forced by the solver) from a cache `p` of
precomputed quantities, refreshed at **one explicit barrier**, `set_precomputed_quantities!` —
not lazily. They document the real `ᶜK ↔ ᶜT ↔ ᶜp` cycle and break it with a physical
approximation, not a solver. icon4py has the same cycle (`theta_v, exner → T, p` and back).

Their issue #2217, *"Replace cache namedtuple with explicit struct"*: *"over 60 fields
accumulated through splatting, unpacking, and merging operations"* — inconsistent structure,
mixed responsibilities, fragile construction, discoverability collapse. **They are migrating
back to explicit named structs.**

The good idea: `ClimaDiagnostics.jl` is a genuine lazy diagnostic registry — variables keyed by
`short_name` with `compute!` functions, on the **output path only**. Same shape as ICON's
`pp_scheduler`, which also does automatic chaining (`vn → vn@plev → u,v@plev`) but likewise
never for compute.

## LFRic / PSyclone — declared access is where the real win is

PSyclone kernel metadata declares, per argument,
`arg_type(GH_FIELD, GH_REAL, GH_INC, W1)` — access mode × function space × stencil. From that
it **statically derives** whether a halo exchange is needed and to what depth, whether OpenMP
needs colouring or atomics, and where to emit `set_dirty()` / `set_clean()`. The generated code
contains `if (field_proxy%is_dirty(depth)) call field_proxy%halo_exchange(depth)`.

That is the biggest structural prize in the whole survey, and it needs **`intent`, not a
container**. Neither existing icon4py spec records it.

LFRic's staleness tracking is also the only real precedent worth copying: **one bit per field
per halo depth**, and the `set_dirty`/`is_dirty` calls are *generated*, never hand-maintained.

LFRic also built the global keyed store icon4py is considering. Its own retrospective
(`components/inventory/future.rst`): *"We have an ever expanding pool of global scope data
encapsulated in an ever expanding source file. This is becoming unwieldy and likely to only
become more so… It doesn't meet our aspiration to adopt an object approach with tight cohesion
and loose coupling."* Their proposed fix is to push data back onto the object it is keyed by.

## Shorter notes

- **CAM `pbuf`** — a runtime-addressable field buffer with `pbuf_add_field` / `pbuf_get_field`
  and time levels. The important shape: **the index is requested once at init, and used
  thereafter** — never a string lookup in the compute path. Same as Omega's `getIndex` /
  `getByIndex`. No staleness tracking; CAM developers pay for it in debugging.
- **WRF Registry** — a flat text table generating state derived types, I/O, nesting and halo
  communications. The strongest argument that one declaration can drive many cross-cutting
  services; the strongest argument against is that it is a bespoke DSL with a build step.
- **NUOPC** — components `Advertise` fields, then `Realize` the ones actually connected;
  **unconnected exports cost zero memory**. Negotiation errors on ambiguity rather than
  guessing. That failure policy is the right one (contrast MPAS's silent null).
- **ESMF `FieldBundle` / xarray `Dataset` / Iris `CubeList`** — general labelled containers;
  model codes rarely put them on hot paths, for the sympl reasons.
- **ECS (Bevy, flecs, EnTT)** — the "one bucket, dynamic labels, systems query for what they
  need" idea is literally an ECS, and the transferable part is **not** the storage but the
  scheduling: declared read/write sets let the scheduler derive parallelism and insert sync
  points automatically. Same insight as PSyclone and as Legion's privilege lattice
  (`READ_ONLY`/`READ_WRITE`/`WRITE_DISCARD`/`REDUCE`). Again: `intent`, not a container.
- **Incremental-compute systems** (Salsa, Adapton, Bazel, Nix) — for M6, the algorithm choice
  is revision counters, not content hashing: hashing costs O(field bytes) per field per step
  and its payoff (early cutoff on an identical recomputed value) essentially never fires in
  floating-point dynamics. The dependency graph here is static and tiny, so precompute the
  reverse-dependency closure at setup and make invalidation "stamp this precomputed set".

## Summary: steal / avoid

**Steal**

1. Metadata at the field's definition site, declared by its owner (ICON, NDSL).
2. `dims → allocation` resolved by one sizer object (NDSL `QuantityFactory` + `GridSizer`).
3. A `Local` type for granule-private scratch, with DaCe `transient=True` (NDSL).
4. Declared `intent`, and derive halo exchanges from it (PSyclone).
5. Labels declared at the definition site, O(1) membership, materialized at setup, **unknown
   label raises** (ICON, minus its auto-create).
6. Conditional allocation from config predicates (MPAS `packages`, climt `get_default_state`).
7. A two-phase lifecycle — declare → bind → run. CCPP, ICON and NUOPC all end it with a **hard
   freeze**; ICON-sc shows a **staleness guard is strictly better** (mutation stays legal, using
   a stale wiring raises), costs ~100 LOC, and forbids nothing.
8. Resolve names once into typed handles; never look up a string in a kernel (CAM, Omega).
9. Capability vs request separation (ICON).
10. Unit *algebra* at setup; unit *conversion* only at the file boundary (sympl, ICON `post_op`),
   with ICON-sc's sharpening: one canonical unit per name, checked at declaration, and the
   conversion path quarantined so it cannot be reached in production.
11. A namespace invariant for the ~80 % of model fields CF cannot name — no CF name ⇒ mandatory
   `icon:` prefix, enforced at registration (ICON-sc).
12. `origin`/K-domain as first-class metadata: gt4py fields carry a *domain*, not a shape
   (ICON-sc, learned the hard way).
13. Bitwise old-wiring ≡ new-wiring as a release blocker, never a tolerance to widen (ICON-sc).

**Avoid**

1. A run-time global bucket reachable from compute code (MPAS, LFRic's store, ClimaAtmos's cache).
2. Silent lookup failure or auto-creation on unknown names (MPAS, ICON groups).
3. Dual declaration kept in sync by hand (ICON — a Fortran artifact Python need not inherit).
4. A general derivation planner (CCPP #349) — and equally, forbidding shared derivation
   entirely (CCPP's 66% interstitial glue).
5. Per-call unit conversion (sympl's own performance issues).
6. Assuming CF standard names cover model-internal fields. They do not, and never will.
7. Building a compiler to erase a dict you were never forced to introduce (ICON-sc) — and,
   generally, adopting the *unbuilt* parts of a prototype: its halo validator is the most quoted
   idea in its architecture and has no consumer anywhere in its source.
