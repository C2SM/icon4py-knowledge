# ICON-Land (JSBACH) → gt4py Port — Handoff

**Status:** investigation / design phase complete; no port code written yet.
**Prepared:** by Christoph Müller's Claude Code session, for handoff to another team/instance.
**Scope of this doc:** a self-contained consolidation of the analysis, the core thesis, quantified
facts about the codebase, the agreed strategy, the oracle/validation design, the first-slice spec,
open risks, and concrete next steps. Everything here was derived from the jsbach source tree
(`externals/jsbach`) — **verify file:line citations and counts against current code before quoting**,
as they are point-in-time.

> The bundle also contains `field_catalog.csv` (1152 model variables, machine-readable requirements
> spec) and `extract_catalog.py` (regenerates it from source). Re-run the script after code changes.

---

## 0. TL;DR — the one-paragraph pitch

A land-surface model *looks* like a nightmare for a stencil DSL: 127k SLOC of heavily
object-oriented Fortran, a runtime tree of fractional "tiles," dynamic dispatch everywhere. But the
dynamic behavior is a **Fortran idiom, not a requirement**: the dispatch is coarse-grained (never in
the cell loop), closed-world (finite process set known at compile time), and frozen at init. It can
be resolved to a **static, flattened pipeline** at configuration time — which is exactly the shape
that lowers to `gt4py.next`/icon4py, *and* exactly the property NVIDIA already exploited to ship CUDA
graphs for JSBACH (production proof the pipeline is static). The numerical kernels (~30–40k SLOC) are
already written as flat array procedures and are portable; the framework (~80k SLOC) mostly
*evaporates* rather than being reimplemented. The dominant cost is not translation — it's
**scientific revalidation**, because the reordering that buys performance portability also breaks
bit-reproducibility.

---

## 1. What ICON-Land / JSBACH is

Land-surface & soil component of the ICON/ECHAM climate models (MPI-M & MPI-BGC), Fortran, ~207
`.f90` files. Checked out as a git submodule of `icon-nwp` at `externals/jsbach`.
Docs: https://jsbach.gitlab-pages.dkrz.de/jsbach

**Framework** (`src/base/`): a hierarchical **tile** tree (`mo_jsb_tile*`, `mo_hsm_class`), pluggable
**processes** (`mo_jsb_process_*`, a factory), **tasks** scheduled per timestep (`mo_jsb_task_class`),
and pointer-based **memory/var/pool** management (`mo_jsb_var_class`, `mo_lnd_bgcm_*`). Model setups
are "usecases" (`mo_jsb_model_usecases`).

**Processes** (`src/`): physical (`hydrology`, `soil_snow_energy`, `srf_energy_bal`, `turbulence`,
`radiation`, `atmland`), classic biogeochem (`carbon`, `phenology`, `assimilation`, `disturbance`,
`forest_age`), land-cover change (`anthropogenic_lcc`, `natural_lcc`, `pre_and_post_lcc`), and the
newer **QUINCY** biogeochem (`q_*` dirs). `hd/` is hydrological discharge (river routing).

**dsl4jsb** (`scripts/dsl4jsb/dsl4jsb.py`): a preprocessor — see §6.

---

## 2. Core thesis — dynamic dispatch is unnecessary

1. **Dispatch is coarse-grained.** The polymorphic call is `CALL this%Integrate(tile, options)`
   (`src/base/mo_jsb_task_class.f90:146`), taking a *whole tile*; vectorization over cells (`nproma`)
   happens *inside* the kernel. Dispatch happens per **task × tile × process × timestep**, never in
   the inner loop → the vtable indirection costs ~nothing. Removing it is **not** about speed.
2. **The polymorphism is closed-world + fixed-per-run.** The set of process *types* is finite and
   known at compile time (it is literally the `src/` tree — no runtime plugins). *Which* processes run
   on *which* tiles, and the tree shape, are config-driven but **frozen at initialization**. Dynamic
   *shape* (N PFT tiles) ≠ dynamic *type*.
3. **Therefore it resolves to a static pipeline.** Read the namelist once at init → resolve the entire
   tile×process×task traversal into a flat, ordered schedule of `(kernel, field-views, tile-group)` →
   run that schedule every step. This is monomorphization-at-config-time. No per-timestep polymorphism.
4. **"Add a new tile type" does not need dynamic dispatch.** A PhD student adding tile type N+1 is
   *closed-world extension resolved at model-build time* (you recompile/re-stage; you never load an
   unknown type at runtime). A tagged-union/registry gives identical expressive power; you lose only
   the ability to add a type without touching a central registry (the expression problem), which is a
   non-cost when adding a tile type is already a deliberate compile-the-model act.

**Consequence for the port:** kernels → `gt4py.next` field operators; framework → a *static* host-side
Python orchestration layer (schedule resolved at init). The framework stays host-side, but it can be
static, not dynamic.

---

## 3. Quantified facts (grounding for estimates)

### SLOC (~127k total; `find src -name '*.f90' | xargs wc -l`)
- `base/` framework ≈ 19.8k; process modules ≈ 107k.
- By file role: `interface` 25.0k (dispatch glue **+** real science), `memory_class` 18.0k (field
  declarations + metadata), `process` 14.0k (pure kernels), `init` 11.6k, `config` 4.8k,
  `constants` 2.5k. Big kernel files: `q_soil_biogeochemistry/mo_q_sb_ssm_main` 3.6k,
  `hydrology/mo_hydro_process` 3.5k, `q_vegetation/mo_q_veg_growth` 3.4k.
- **~80k = framework/declarations/config/orchestration → collapses to ~10–20k Python.**
  **~30–40k = genuine numerics → must be faithfully re-expressed.**
- 145/207 files use `CLASS(...)`; 140 use `POINTER` — heavily OO, *not* stencil-shaped.

### The kernels are already portable-shaped
Leaf kernels (`calc_*` in `*_process.f90`) take **flat scalar/array args, not the polymorphic tile** —
e.g. `calc_surface_hydrology_land` at `src/hydrology/mo_hydro_process.f90:56` takes
`REAL(wp) :: steepness(:), t_soil_sl1(:), ...`. The tile→array unpacking lives in the `interface`
layer. **So the test seam already exists**: feed arrays, capture arrays, diff.

### Tiles (`src/base/mo_jsb_lct_class.f90:55`, `src/base/mo_jsb_model_usecases.f90`)
- Land-cover-type *kinds*: LAND, VEG, BARE(unused), GLACIER, LAKE — 5 defined, ~4 used
  (`max_no_of_lct=10`). **PFTs are not distinct types — they are many instances of `VEG_TYPE`.**
- Tiles are a **tree with nested fractions** (leaf absolute fraction = product down the path).
- Leaf (fractional) tiles per cell: `jsbach_lite` a handful; `jsbach_pfts` npft=11/12; `quincy_13_pfts`
  13; `jsbach_forest_age_classes` = forest PFTs × `nacs` (default 11) → **several tens**.
- Frozen at init → **this leaf count is the size of the dense "tile" axis** to flatten over
  (`[cells × n_leaf_tiles × levels]`). "Process all grass, then all sand" = grouping over this axis.
- *Why tiling exists:* surface fluxes are nonlinear in surface state (Jensen), so avg(flux)≠flux(avg);
  forest age classes exist because young stands are C sinks, old stands ~C-neutral (needed for
  land-use-change carbon accounting). The complexity is real physics, but it lives in the
  **bookkeeping/relocation/conservation**, not the per-tile flops.

### Field catalog (see `field_catalog.csv`; from all 1152 `Add_var` calls, 25 `*_memory_class.f90`)
- **State surface is ~⅓:** 363 prognostic + 68 conditional vs **721 diagnostic (63%, recomputed each
  step)**. gt4py state need only carry ~360–430 fields.
- **72% have no vertical axis:** 831 2D / 321 3D. Vertical axes are a small fixed set: soil-water
  layers (`vgrid_soil_w`), soil-energy layers (`soil_e`), snow (`snow_e`), canopy, PFT, + singletons.
- **One aggregation operator:** all 494 `Aggregate_onChunk` calls use `weighted_by_fract`
  (area-weighted), despite an *abstract* `t_jsb_aggregator` hierarchy with a single concrete impl.
  The "operator zoo" is one animal.
- ⚠️ **Caveat:** the prognostic/diagnostic flag is inferred from `lrestart` (default FALSE) and is
  ~90% accurate — e.g. `t_soil_sl` is labeled diagnostic but is physically *the* prognostic soil
  temperature. **A human must confirm the true state set** (see §9, task 1).

### Transcendental density (drives the bit-rep routing, §5)
High (need tolerance): `q_vegetation` 68, `assimilation` 50, `srf_energy_bal` 40, `hydrology` 33,
`q_soil_biogeochemistry` 24. Low/arithmetic (bit-rep achievable): `soil_snow_energy` 18,
`radiation` 14, `turbulence` 10, `carbon` 3, `q_phenology` 1.

---

## 4. The dsl4jsb "DSL" — what it is (and isn't)

`scripts/dsl4jsb/dsl4jsb.py` is a single 20KB script, ~60 macros, no dependencies. It is a
**context-free, line-by-line regex macro expander** (C-preprocessor-like) — **NOT** config-driven
codegen. There are **no inputs but the source text**: no namelist, no conditionals, no state; same
line → same output. (A post-pass lowercases `UPPER_` tokens — harmless because Fortran is
case-insensitive; plus md5 caching and `#line` directives.)

The ~60 macros collapse to **5 concerns**, all pure layout/dispatch boilerplate:
(1) polymorphic memory/config access (`SELECT TYPE` downcasts); (2) field access + nproma-block
slicing `%ptr(ics:ice,iblk)`; (3) tile aggregation; (4) bgc-material pool store accessors;
(5) lctlib parameter lookup.

**Port impact: capture ~0% of the macro surface, none as a preprocessor.** Concerns (1), (2)-slicing,
and (4)-store-plumbing **evaporate** (they are Fortran-OO/memory-management artifacts the Python
object model + gt4py field model handle natively). What survives becomes ordinary constructs: 2D/3D →
field dimensions declared once; aggregation → the static tile-axis reduction; lctlib → a parameter
table by tile type. **Bonus:** the DSL tags are *free layout metadata* — each access is tagged with
its rank (2D/3D) and scope (chunk/domain), which hands you the gt4py field signature for translation.

---

## 5. Oracle / bit-reproducibility strategy

To make autonomous kernel porting safe, build a **deterministic oracle** and route each kernel to the
right gate.

- **Flags (both sides):** nvhpc Fortran `-Kieee -Mnofma` (IEEE-strict, no FMA, no flush-to-zero);
  gt4py backend compiled no-fast-math + `-ffp-contract=off` (CPU) / nvcc `--fmad=false` (GPU).
  Compare **CPU gt4py backend vs CPU Fortran** — GPU libdevice diverges more (separate, looser
  revalidation).
- **What is bit-identical:** `+ - * / sqrt` (correctly rounded). **What is not, ever:** transcendentals
  (`exp/log/pow/tanh`, and `**` = `exp(y·log(x))`) go through libm and differ ~1–few ULP regardless of
  flags — the math libraries differ Fortran-side vs backend-side. **Unfixable.**
- **Route by transcendental density (predictable up front):** arithmetic kernels → **bit-exact (or
  few-ULP) gate**; transcendental kernels → **relative tolerance** (never absolute; the original
  target was rel `1e-10` for that bucket — note this is ~1e6 ULP, a loose backstop; keep arithmetic
  kernels much tighter). Refinement: **measure & display the actual rel err per transcendental kernel**
  rather than assume a threshold — let the distribution show where the gate belongs.
- **Translation discipline:** bit-rep holds only if source-level operation order & parenthesization are
  preserved exactly. Mirror the Fortran arithmetic literally even when less idiomatic; where the
  idiomatic gt4py form reorders a sum, that kernel drops to the tolerance gate.
- **Residual risk the oracle does NOT solve = input coverage:** a kernel can be bit-identical on the
  captured inputs yet wrong on an unexercised branch (frozen soil, glacier, zero-fraction, clamp/NaN).
  Backstop with **property/fuzz testing via FFI** (f2py / iso_c_binding): generate physically-plausible
  random inputs, run both sides, compare. Pure functions are exactly where this is cheap and safe.

> **The big-picture cost:** the tile-by-type reordering that buys performance portability changes
> floating-point summation order in aggregation → you lose bit-reproducibility against the reference →
> you need **scientific revalidation** (multi-year runs, energy/water/carbon balance closure), not just
> bit-diffing. This is usually the *largest* hidden cost of a climate-model port. Mitigation: port
> kernels incrementally and bit-diff each one *before* introducing the reordering.

---

## 6. Phased plan (agreed) + refinements

**Phases:** (A) human-led **design** — abstract the real memory-layout & dispatch requirements away
from Fortran fluff; establish static dispatch suffices. (B) Python **skeleton**. (C) unit-test +
shortest-possible **validation harness**. (D) port **pure functions** first, validate vs Fortran
oracle — agent-autonomous. (E) first **vertical slice** with real state change on a small subset,
verified as component/integration test — human-assisted. (F) more slices — agent more independent.

**Cadence:** design = human; pure-functions = autonomous *with per-batch checkpoints* (not unattended
weeks); slice-1 = assisted; later slices = independent. Whoever runs it should **own the oracle**.

**Refinements (important):**
1. **Aggregation/relocation operators encode conservation laws** (C/water closure) — they *look* like
   layout fluff but are not. Enumerate them as first-class requirements; don't abstract them away.
2. **The requirements are half-written already** in `*_memory_class.f90` `Add_var` metadata (name,
   dims, restart/prognostic flag, output flag) — extract, don't invent (`field_catalog.csv` is a start).
3. **Don't waterfall the design.** Design the *framework abstractions* fully (tile, field, schedule,
   aggregation operator, parameter table, build-time registry); design only the *first slice's* science
   in depth; sketch the rest. **Expect to revise the paper design after slice 1** — that's the point of
   a vertical slice.
4. **The harness (C) is the critical-path long pole**, and a hard prerequisite to the agent marathon
   (D): offline reference build + golden-I/O capture + a minimal forcing/IO path (`mo_jsb4_forcing`
   alone is 2.7k SLOC). **One offline reference run yields three things at once**: golden kernel I/O,
   initial conditions for slices, and integration-test reference trajectories.
5. **Define "pure"**: referentially transparent given explicit array inputs, no global mutable state.
   Triage `calc_*` first — some have `intent(inout)` accumulation or reach into module state; `USE`ing
   a constants module is fine, mutating a shared buffer is not.

---

## 7. First vertical slice spec (recommended)

**`jsbach_lite` + SSE (soil-snow energy)** on land+glacier tiles, offline forcing. Chosen to hit every
hard framework primitive with minimal science:
- **3D field + tridiagonal vertical solve** → your first `scan_operator` (the catalog exposes the
  Thomas-algorithm coefficients directly: `t_soil_acoef/bcoef`, `t_snow_acoef/bcoef` on `soil_e`/`snow_e`).
- **2-tile aggregation** (land+glacier) → the conservation/weighted-reduction path.
- **multi-timestep prognostic state** (`snow_depth_sl`, `t_soil_sl`) → restart/state path.
- K-axes needed: `soil_e`, `snow_e`. Aggregation: one weighted reduction.

Avoid starting with biogeochem (transcendental tolerance issues + pool relocation too early).
The 25-field SSE slice of `field_catalog.csv` is the concrete requirements list.

---

## 8. Top risks / open questions

1. **gt4py.next indexed gather/scatter** for the tile-by-type batching (an indexed permutation of an
   unstructured field) — is it expressible cleanly in the *current* gt4py? **Check first; it gates the
   whole batching approach.**
2. **Land-cover change / pool relocation** (`anthropogenic_lcc`, `natural_lcc`, `mo_jsb_lcc`): moving
   conserved matter between tiles = irregular gather/scatter + conservation bookkeeping. Worst fit for
   a dense-field DSL.
3. **Revalidation cost** (§5) — the dominant schedule risk.
4. **True state set** — the catalog's prognostic flag is ~90% right; must be confirmed (§9.1).
5. **Coupling scope** — jsbach is an ICON *component*. Offline standalone vs in-ICON coupled
   (Fortran↔Python boundary) is a major scope fork.

**Effort ballpark:** de-risk PoC (one column-physics slice, offline, no LCC/QUINCY) ≈ 3–6
person-months; full classic JSBACH validated ≈ 5–8 person-years; +QUINCY roughly doubles the science
surface; in-ICON coupling adds a substantial work package. (Reference: icon4py — dycore + some physics
— is a ~5+ year, multi-FTE effort.)

---

## 9. Concrete next steps (all groundable without a build environment)

1. **Resolve the true state set.** Cross-reference each "prognostic" catalog candidate against the
   actual restart-variable list and the restart-identity logic (see recent commit `IQ: Fix restart
   identity`). This is the highest-leverage, riskiest-to-get-wrong column. *(Recommended first.)*
2. **Per-variable aggregation map.** Parse `interface` files to attach each field's `Aggregate_onChunk`
   call (and rare 2D/3D/domain rank variant) to the catalog — confirms the "one operator" finding
   per-field.
3. **Pure-function triage.** Classify `calc_*` kernels into cleanly-pure vs needs-context; produces the
   worklist for the agent marathon.
4. **lctlib parameter catalog.** Extract the per-land-cover-type parameter set (`Lctlib_param` lookups)
   — the other half of the requirements (parameters vs fields).
5. **Stand up the offline reference build + golden capture** (the §6.4 long pole) — needs the build
   environment.

---

## 10. External context — the CUDA-graphs validation

NVIDIA (Dmitry Alexeev, `dalexeev@nvidia.com`) shipped **CUDA graphs for JSBACH** — commit
`ad55a4bc4`, merged 15 May 2025 (DKRZ MR !173; capture/replay machinery in ICON core, `icon-mpim!401`).
It made jsbach fully OpenACC-async + multi-stream and pushed scalars on-device so nothing host-side is
baked into a frozen graph. jsbach is **launch-overhead-bound** (task×tile×process×timestep = hundreds–
thousands of tiny kernel launches/step); graphs amortize that.

**Why it matters here:** graphs are invalidated *only on workflow change* —
`is_newday/newmonth/newyear/restart/experiment_start` (`src/interfaces/mo_jsb_interface.f90:680`);
between those boundaries the per-step launch sequence is **frozen and replayed**. That is production
proof of the §2 thesis. CUDA graphs *require* the pipeline stability we argue is *achievable*: the
Fortran had to **retrofit** it (pin the graph boundary to workflow changes) on top of dynamic dispatch;
a static-schedule port gets it **by construction**, and the graph-invalidation boundaries are exactly
the residual config-time dynamism ("which processes run" changes at day/month/year). A lowered static
pipeline (icon4py `program`) is the ideal graph-capture input — the port does not lose this win.

---

## 11. Bundle contents

- `HANDOFF.md` — this document.
- `field_catalog.csv` — 1152 model variables: process, name, dim, vgrid, state, output, units,
  long-name. The machine-readable requirements spec / SSE slice-1 source.
- `extract_catalog.py` — regenerates the catalog from `../src` (`python3 extract_catalog.py`).

*Recommended reading order for a new instance: §0 → §2 → §3 → §6 → §7, then §5 and §9 when starting to
build. §4/§8/§10 are supporting depth.*
