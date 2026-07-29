---
title: Model state — prior art
author: jcanton
tags: [state, model-state, prior-art, icon, mpas, ccpp, sympl, ndsl, lfric, registry, labels, ecs]
created: 2026-07-29
status: draft
---

> Appendix to [[personal/jcanton/model-state/model-state|Model state — requirements and design options]].
> What other codes do about field containers and components declaring their inputs.
> Line numbers for ICON, LFRic and gt4py come from local checkouts; the rest are
> paraphrase-grade — spot-check before citing externally.

## The one-line verdict per system

| System | Container | Components declare inputs? | Resolution | Verdict for icon4py |
|---|---|---|---|---|
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
7. Two-phase lifecycle: declare → bind → **hard freeze** → run (CCPP, ICON, NUOPC).
8. Resolve names once into typed handles; never look up a string in a kernel (CAM, Omega).
9. Capability vs request separation (ICON).
10. Unit *algebra* at setup; unit *conversion* only at the file boundary (sympl, ICON `post_op`).

**Avoid**

1. A run-time global bucket reachable from compute code (MPAS, LFRic's store, ClimaAtmos's cache).
2. Silent lookup failure or auto-creation on unknown names (MPAS, ICON groups).
3. Dual declaration kept in sync by hand (ICON — a Fortran artifact Python need not inherit).
4. A general derivation planner (CCPP #349) — and equally, forbidding shared derivation
   entirely (CCPP's 66% interstitial glue).
5. Per-call unit conversion (sympl's own performance issues).
6. Assuming CF standard names cover model-internal fields. They do not, and never will.
