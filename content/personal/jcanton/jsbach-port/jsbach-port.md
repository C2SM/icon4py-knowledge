---
title: Porting ICON-Land (JSBACH) to icon4py / GT4Py — plan & scope
author: jcanton
tags: [jsbach, icon-land, land-surface, gt4py, port, tmx, aes, validation, oracle, sse]
created: 2026-07-29
status: draft
---

> **TL;DR** Two independent Claude investigations — one by @muellch (framework /
> whole-scope, with a machine-readable field catalog and a bit-reproducibility
> oracle strategy) and one by jcanton (narrow / deep on the actual in-ICON target
> usecase, its validation experiment, and the tmx seam) — converged on the same
> thesis: **JSBACH's dynamic dispatch is a Fortran idiom, not a requirement; it
> resolves to a static, flattened pipeline that lowers cleanly to GT4Py.** This
> doc merges both, records the decisions taken (in-ICON coupling; `jsbach_lite` +
> tmx target; **SSE first**; two-tier oracle), the debates behind them, and the
> concrete next steps.
>
> cc @muellch — this builds directly on your `HANDOFF.md` bundle; please correct
> anything I've mis-stated. Open question for **Reiner Schnur** flagged in §5.

---

## 1. Context — two parallel investigations

This port was scouted twice, independently, before any code was written:

- **@muellch's investigation** (`HANDOFF.md` + `field_catalog.csv` +
  `extract_catalog.py`, in `~/projects/`). Broad, framework-level, whole-JSBACH.
  Its lasting assets: a quantified codebase map, a machine-readable requirements
  spec (1152 variables), and a bit-reproducibility / oracle strategy.
- **jcanton's investigation** (prior Claude session; superseded plan drafts).
  Narrow and deep on the *actual* minimal in-ICON target: the exact usecase, the
  validation experiment, the tmx coupling seam, and the serialization gap.

They are complementary, not contradictory. This doc is the merge.

### What @muellch established (framework + tooling)

- **Quantified codebase.** ~127k SLOC Fortran, ~207 `.f90`. ~80k =
  framework / declarations / config / orchestration → *collapses* to ~10–20k
  Python. ~30–40k = genuine numerics → must be re-expressed faithfully. 145/207
  files use `CLASS(...)`, 140 use `POINTER` — heavily OO, **not** stencil-shaped
  on the surface.
- **The test seam already exists.** Leaf kernels (`calc_*` in `*_process.f90`)
  take **flat scalar/array args, not the polymorphic tile** — e.g.
  `calc_surface_hydrology_land` (`src/hydrology/mo_hydro_process.f90:56`) takes
  `REAL(wp) :: steepness(:), t_soil_sl1(:), …`. Tile→array unpacking lives in the
  `interface` layer. So: feed arrays, capture arrays, diff.
- **`field_catalog.csv`** — every `Add_var` from 25 `*_memory_class.f90` files,
  1152 rows (process / name / dim / vgrid / state / output / units / long-name),
  regenerable via `extract_catalog.py`. Headline findings:
  - **State is ~⅓:** 363 prognostic + 68 conditional vs 721 diagnostic (63%,
    recomputed each step). GT4Py state need carry only ~360–430 fields.
  - **72% have no vertical axis** (831 2D / 321 3D). Vertical axes are a small
    fixed set: soil-water layers, soil-energy layers, snow, canopy, PFT.
  - **One aggregation operator:** all 494 `Aggregate_onChunk` calls use
    `weighted_by_fract` (area-weighted). The "operator zoo" is one animal.
  - ⚠️ **Caveat:** the prognostic/diagnostic flag is inferred from `lrestart`
    and is ~90% accurate — e.g. `t_soil_sl` is labelled diagnostic but is *the*
    prognostic soil temperature. **A human must confirm the true state set.**
- **The `dsl4jsb` preprocessor evaporates.** It's a 20KB context-free regex macro
  expander (no namelist, no state). ~0% of its macro surface needs to be ported —
  the concerns it encodes (OO downcasts, nproma slicing, pool plumbing) are
  Fortran-memory-management artifacts the Python object model + GT4Py field model
  handle natively. Bonus: its rank/scope tags are *free layout metadata* for
  translation.
- **External validation of the static-pipeline thesis:** NVIDIA (Dmitry Alexeev)
  shipped **CUDA graphs for JSBACH** (commit `ad55a4bc4`, merged 2025-05-15). CUDA
  graphs *require* per-step launch-sequence stability, invalidated only on
  workflow change (`is_newday/newmonth/newyear/restart`,
  `src/interfaces/mo_jsb_interface.f90:680`). The Fortran had to *retrofit* that
  onto dynamic dispatch; a static-schedule port gets it **by construction**.

### What jcanton established (the concrete in-ICON target)

- **Minimal usecase:** `jsbach_lite` + TMX = `init_usecase_lite_tmx`
  (`src/base/mo_jsb_model_usecases.f90`). Tile tree box → land → veg = effectively
  **one land leaf per cell** (no lakes/glaciers in the atm-only AES config) →
  single-column, masked full-field. 8 processes: **A2L, L2A, SEB, RAD, HYDRO,
  TURB, SSE, PHENO** (~4k lines of portable numerics). Everything else — CARBON,
  ASSIMI, DISTURB, all LCC, HD, the entire QUINCY branch — is **off** in
  atmosphere-only AES.
- **The validation experiment:** `run/exp.aes_bubble_land_tmx` (Torus_Triangles
  20×4 5000m, 70 lev, 30s dt, 2h, `ljsb=.TRUE.`, `use_tmx=.TRUE.`,
  `usecase='jsbach_lite'`, desert IC). **Critical:** the tmx validation dataset
  APE_AES has *zero land* — this bubble experiment is the only dataset that
  exercises JSBACH.
- **The seam already cut:** the `tmx-surface` worktree/branch prescribes exactly
  the six fields JSBACH must produce — `land_tskin`, `land_rough_m`,
  `land_qsat_star`, `land_evapotrans`, `land_sensible_hflx`, `land_q_snocpymlt`.
  JSBACH replaces those prescribed slots. Because tmx passes `t_acoef=q_acoef=0`,
  **tmx owns the implicit vertical-diffusion solve** and JSBACH only needs the
  atmospheric b-coefficients.
- **Serialization gap:** no JSBACH savepoints exist. They must be added (template =
  the tmx savepoints in `mo_icon4py_verification.f90` on the serialize branch).
- **GT4Py feasibility: yes.** No data-dependent loops. Numerics families are all
  proven in the tmx port: tridiagonal implicit via `scan_operator`, fixed-count
  unrolled loops, neighbour ops, vertical scans, masked full-field
  `where(fract>0)` tiling. No gather/scatter needed for the single-leaf lite tile
  tree.

---

## 2. The convergent thesis

> The dynamic behaviour is a **Fortran idiom, not a requirement**. Dispatch is
> coarse-grained (`CALL this%Integrate(tile, options)`, whole-tile, never in the
> cell loop), closed-world (the process set is the `src/` tree — no runtime
> plugins), and frozen at init. It resolves to a **static, flattened pipeline**:
> read the namelist once → resolve the tile×process×task traversal into a flat
> ordered schedule of `(kernel, field-views, tile-group)` → run that every step.
> Kernels → GT4Py field operators; framework → a *static* host-side Python
> orchestration layer. Same shape icon4py already uses; same property NVIDIA
> exploited for CUDA graphs.

Both investigations reached this independently. It is the foundation of the port.

---

## 3. Decisions taken

| # | Decision | Rationale |
|---|----------|-----------|
| D1 | **In-ICON coupling** (not offline standalone) as the *port product*. | The tmx seam already exists (`tmx-surface`); offline forcing (`mo_jsb4_forcing`, 2.7k SLOC) is throw-away harness. Target is jsbach driven by tmx b-coeffs. |
| D2 | **`jsbach_lite` + tmx** as the target usecase. | Minimal 8-process path; single land leaf; the AES atm-only config. |
| D3 | **SSE (soil-snow energy) first slice.** | Hits every hard framework primitive with minimal science: 3D field + tridiagonal vertical solve (first `scan_operator`), multi-timestep prognostic state, one weighted aggregation. Avoids biogeochem transcendental-tolerance pain. |
| D4 | **Two-tier oracle** (see §4). | Reconciles the fast-feedback appeal of offline forcing with the in-ICON product. |
| D5 | Merge @muellch's **catalog + bit-rep oracle strategy** with jcanton's **experiment + seam**. | Complementary strengths. |

Still **open** (see §7): base branch / worktree; confirming the true state set;
whether standalone can build without full ICON (§5).

---

## 4. The debate: in-ICON vs offline standalone — resolved as a two-tier oracle

This was the main tension between the two investigations. @muellch's `HANDOFF.md`
recommends an **offline forcing** first slice (SSE on land+glacier, file-driven);
jcanton's target is **in-ICON** (tmx-coupled). Both are right about different
things, and the tension dissolves once you separate *product* from *oracle*:

- **Product = in-ICON** (D1). The eventual jsbach4py is driven by tmx, validated
  against `exp.aes_bubble_land_tmx`.
- **Oracle = two tiers:**
  1. **Kernel/slice oracle = offline standalone**, single-column, file forcing.
     Cheap golden-I/O capture with no dynamical-core spin-up and MPI-trivial at
     one site. **SSE's tridiagonal solve does not care where its forcing came
     from** — a soil column with prescribed top-boundary flux is identical whether
     that flux arrived from observations or from tmx. So the offline standalone is
     a *perfectly valid, much faster* oracle for kernel-level validation. This is
     the fast feedback loop Reiner/Christoph flagged.
  2. **Coupling oracle = `exp.aes_bubble_land_tmx`**, in-ICON, the real tmx seam.
     Validates the A2L / L2A boundary (the b-coefficient handshake) that the
     offline path *cannot* exercise, because offline forcing uses a different A2L
     source (`mo_jsb4_forcing`, not `mo_atmland_interface`/tmx). Deferred to the
     integration slice.

**Net:** offline standalone is used as a *faster reference generator* for the
early SSE-first work, **not** as the product. This gives the feedback-loop win
without contradicting the in-ICON decision. It also means @muellch's SSE-offline
slice-1 and jcanton's in-ICON target are the *same plan* at different tiers.

---

## 5. Standalone JSBACH — findings and the open question for Reiner Schnur

Context (from @muellch): *"We learned from Jeff that you have a standalone jsbach
that can be compiled without ICON and some datatests for it? For an AI port this
probably would allow for a faster feedback loop that does not require a
supercomputer."*

Investigated in `~/projects/icon-nwp/externals/jsbach`:

- **The standalone driver exists.** `src/drivers/mo_jsbach_model.f90` — *"ICON
  driver for the JSBACH standalone model"* / *"Main routine for running ICON-Land
  standalone"*. `jsbach_model()` → `run_one_timestep()` → forcing via
  `mo_jsb4_forcing::get_standalone_driver`.
- **"Standalone" = land without the atmosphere dynamical core — but still built
  inside an ICON tree.** The driver `USE`s **92 ICON-infrastructure modules**
  (`mo_master_control`, `mo_load_restart`, `mo_name_list_output_init`,
  `mo_build_decomposition`, `mo_restart`, `mo_mpi`, `mo_time_management`,
  `mo_dynamics_config`, …). It is **not** a pip-installable pure-land library. So
  "compiled without ICON" most plausibly means *without the ICON atmosphere*,
  using a bundled ICON-infrastructure subset (I/O, restart, mtime, MPI, grid
  decomposition) — the **ICON-Land** product
  (<https://jsbach.gitlab-pages.dkrz.de/jsbach>).
- **Why it still helps our loop:** forcing is file-based (`force_from_observations`,
  `setup_forcing`) rather than a live atmosphere, and
  `build_sitelevel_decomposition(nsites)` supports **single-site / single-column**
  runs. That is a genuinely cheaper reference run than the full bubble experiment —
  it is exactly tier-1 of the §4 oracle.

**Open question for Reiner Schnur (cannot be resolved locally — no Fortran build
environment here):**

1. Does the ICON-Land standalone genuinely build **without the full ICON
   atmosphere**, or only without the *dynamical core* while still requiring the
   ICON infrastructure tree? What is the minimum buildable unit?
2. Do the *"some datatests"* Jeff mentioned exist as **site-level golden I/O**
   (e.g. FLUXNET-style single-column cases) we could reuse directly as the tier-1
   oracle? Where do they live and what forcing/IC files do they need?
3. Is there a supported way to **serialize kernel I/O** from a standalone run
   (savepoints), or would we add serialbox calls ourselves (as planned for the
   in-ICON path)?

Answers to these decide how cheap tier-1 really is. If the standalone needs the
full ICON infra anyway, tier-1's advantage shrinks to "no dynamical core + single
column" — still useful, but not a laptop-scale loop.

---

## 6. First slice — SSE (soil-snow energy)

Chosen (D3) to exercise every hard framework primitive with minimal, low-
transcendental science (`soil_snow_energy` has only 18 transcendentals per
@muellch's density count — a bit-exact-gate candidate).

- **Numerics:** `calc_soil_temperature` (`src/soil_snow_energy/mo_sse_process.f90:353`)
  — Richtmyer-Morton tridiagonal, sequential back-sweep (`:731`) → `scan_operator`
  (fwd + back), as in the tmx port. `calc_snow_temperature` (`:763`) — same over 5
  fixed snow layers. `nsnow=5`, `nsoil=5` (from IC file, max 20).
- **Catalog handle:** the Thomas-algorithm coefficients are exposed directly —
  `t_soil_acoef/bcoef`, `t_snow_acoef/bcoef` on `soil_e`/`snow_e` vgrids. The
  25-field `soil_snow_energy` slice of `field_catalog.csv` is the concrete
  requirements list.
- **K-axes:** `soil_e`, `snow_e`. **Aggregation:** one weighted reduction.
- **Prognostic state:** `t_soil_sl`, `snow_depth_sl` → the restart/multi-step
  state path. (Confirm `t_soil_sl` prognostic status — the catalog mislabels it;
  it is the state variable.)
- **Oracle:** tier-1 offline single-column (§4) → bit-diff each kernel before any
  tile-reordering is introduced.

Deliberately avoided for slice 1: biogeochem (transcendental tolerance + pool
relocation), LCC/QUINCY, river routing.

---

## 7. Base branch / worktree

Facts on the ground (as of 2026-07-29):

- `main` has **advanced**; the tmx work is **not** currently rebased onto it.
- `tmx-surface` (worktree + branch) is **WIP** — it holds the prescribed `land_*`
  seam JSBACH will replace, but is not finished.
- JSBACH replaces the prescribed `land_*` slots, so the port logically **depends
  on** the tmx-surface seam.

**Recommendation (to confirm):** create the `port_jsbach` worktree/branch based on
the **tmx integration tip that carries the `tmx-surface` seam**, not bare `main`
and not bare `port_turbulence` — since day-1 SSE work is decoupled (tier-1 offline
oracle, pure kernels) but the eventual integration needs the seam. Given
`tmx-surface` is WIP and `main` has moved, expect a rebase/merge before the
integration slice. **Decision deferred to Jacopo** — options:

- (a) branch off `tmx-surface` now, accept it's WIP, rebase later;
- (b) branch off `main`, develop SSE kernels + tier-1 oracle standalone (they
  don't need the seam), merge the seam when tmx-surface stabilises. ← lower
  coupling risk while tmx-surface is in flux.

Leaning **(b)** precisely because tier-1 SSE work is seam-independent.

---

## 8. Architecture — what evaporates, what ports

| Fortran layer | ~SLOC | Fate |
|---|---|---|
| `base/` framework (tile tree, HSM, task scheduler, var/pool mgr) | ~19.8k | **Evaporates** → static Python schedule + Python object model. |
| `*_memory_class.f90` (field declarations + metadata) | ~18k | **Evaporates** → GT4Py field decls (catalog is the spec). |
| `config` / `init` | ~16k | Mostly collapses → a namelist reader + build-time registry. |
| `dsl4jsb` preprocessor | 20KB | **Evaporates** (§1). |
| `*_process.f90` leaf kernels (`calc_*`) | ~14k (whole model) | **Port faithfully** → GT4Py field operators. SSE's share is small. |
| `interface` layer (tile→array unpack + real science) | ~25k | Split: unpack logic evaporates; embedded science ports. |
| Aggregation / relocation operators | — | **Port as first-class** — they encode conservation laws (C/water closure), *not* layout fluff. For lite+tmx, only `weighted_by_fract` over one leaf. |

---

## 9. Validation / oracle strategy (from @muellch, adopted)

- **Route kernels by transcendental density.** Arithmetic kernels (`+ - * / sqrt`,
  correctly rounded) → **bit-exact / few-ULP gate**. Transcendental kernels
  (`exp/log/pow/tanh`, and `**` = `exp(y·log(x))`) → **relative tolerance** — libm
  differs Fortran-side vs backend-side by ~1–few ULP, unfixable. SSE is
  low-transcendental → bit-exact candidate.
- **Compiler flags both sides:** Fortran `-Kieee -Mnofma`; GT4Py CPU backend
  no-fast-math + `-ffp-contract=off`. Compare **CPU GT4Py vs CPU Fortran**.
- **Translation discipline:** mirror Fortran operation order & parenthesisation
  literally; where the idiomatic GT4Py form reorders a sum, that kernel drops to
  the tolerance gate.
- **Measure, don't assume** the per-kernel relative error — let the distribution
  place the gate.
- **Residual risk = input coverage** (a kernel bit-identical on captured inputs
  can be wrong on an unexercised branch: frozen soil, zero-fraction, clamp/NaN).
  Backstop pure functions with **property/fuzz testing via FFI** (f2py /
  iso_c_binding).
- **The dominant hidden cost** is *scientific revalidation*: the tile-by-type
  reordering that buys performance portability changes FP summation order → breaks
  bit-reproducibility → needs multi-run energy/water/carbon-balance closure.
  Mitigation: bit-diff each kernel *before* introducing any reordering.

For icon4py specifically, note the local constraints (memory): only `embedded` and
`gtfn_cpu` backends work on this machine; `roundtrip` is gone upstream; no
`gtfn_gpu`/`dace` here. Serialbox savepoints + the c2sm testdata bucket are the
delivery mechanism for the in-ICON oracle; the 20×4 torus grid must be newly
registered in icon4py `Grids`/`Experiments`. **No local Fortran builds** — Jacopo
runs ICON + serialization on a separate machine, so any Fortran-side capture
(adding savepoints, standalone runs) needs a hand-off checklist.

---

## 10. Milestones (SSE-first, adapted from @muellch §6)

- **M0 — Confirm the true state set** for SSE (cross-check `t_soil_sl` etc.
  against the restart list). Highest-leverage, riskiest to get wrong. No build
  needed.
- **M1 — Reference / oracle.** Resolve §5 with Reiner. Stand up tier-1 (offline
  single-column golden I/O for SSE) *or*, if standalone is impractical, add SSE
  savepoints to `exp.aes_bubble_land_tmx` and capture there. **Long pole.**
- **M2 — SSE kernels in GT4Py.** `calc_soil_temperature` + `calc_snow_temperature`
  as `scan_operator`s, bit-diffed against the oracle (bit-exact gate).
- **M3 — SSE slice as an icon4py component test.** Prognostic state over multiple
  steps; one weighted aggregation.
- **M4 — Integration slice.** Wire SSE into the tmx seam (`tmx-surface`), validate
  against `exp.aes_bubble_land_tmx` (tier-2 oracle).
- **M5+ — Further processes** (TURB → SEB → RAD → HYDRO → PHENO), each: catalog
  slice → kernels → bit-diff → integrate. TURB/SEB share the Monin-Obukhov
  exchange solver likely already in the tmx domain.

---

## 11. Open questions / risks

1. **§5 standalone build + datatests** — blocks the cheapness of tier-1. → Reiner.
2. **True state set** — catalog prognostic flag ~90% accurate (M0). → human.
3. **Base branch** (§7) — pending Jacopo; leaning (b).
4. **Revalidation cost** — the dominant schedule risk once reordering starts (§9).
5. **GT4Py indexed gather/scatter** for tile-by-type batching — *not* needed for
   the single-leaf `jsbach_lite` tile tree, so **de-risked for this scope**;
   becomes relevant only if PFT tiles (`jsbach_pfts`) are added later.
6. **Coupling scope** — settled as in-ICON (D1); offline only as oracle (D4).

---

## 12. Next steps (all groundable without a build environment except M1)

1. Confirm Christoph's handle (**@muellch**) and share this doc with him + Reiner.
2. Resolve §5 with Reiner Schnur (three questions).
3. M0: confirm the SSE true state set against the restart list.
4. Extract the SSE-only slice of `field_catalog.csv` (25 rows) as the concrete
   requirements list; attach per-field aggregation call (all `weighted_by_fract`).
5. Decide base branch (§7).
6. Commit @muellch's bundle (`HANDOFF.md`, `field_catalog.csv`,
   `extract_catalog.py`) somewhere durable — currently only in `~/projects/`.

---

## References / bundle

- @muellch's handoff bundle (`~/projects/`): `HANDOFF.md`, `field_catalog.csv`
  (1152 vars, machine-readable requirements spec), `extract_catalog.py`
  (regenerator; `JSBACH_SRC=… python3 extract_catalog.py`).
- ICON-Land docs: <https://jsbach.gitlab-pages.dkrz.de/jsbach>
- Key Fortran anchors (verify file:line against current source before quoting):
  - Usecase: `src/base/mo_jsb_model_usecases.f90` (`init_usecase_lite_tmx`).
  - Interface: `src/interfaces/mo_jsb_interface.f90` (`interface_tmx`);
    graph boundary at `:680`.
  - Standalone driver: `src/drivers/mo_jsbach_model.f90`; forcing
    `src/drivers/mo_jsb4_forcing.f90`.
  - SSE: `src/soil_snow_energy/mo_sse_process.f90`
    (`calc_soil_temperature:353`, back-sweep `:731`, `calc_snow_temperature:763`).
  - tmx caller: icon-nwp `src/atm_phy_aes/tmx/mo_tmx_surface.f90`.
  - Validation experiment: `run/exp.aes_bubble_land_tmx`.
- icon4py tmx port (jcanton): `.worktrees/port_turbulence`,
  `.worktrees/tmx_surface`; tmx plan
  `~/.claude/plans/hey-we-need-to-indexed-riddle.md`.
- CUDA-graphs proof point: commit `ad55a4bc4` (2025-05-15), DKRZ MR !173.

*Attribution: framework analysis, field catalog, oracle strategy and CUDA-graphs
context are @muellch's (`HANDOFF.md`). Target usecase, validation experiment, tmx
seam, serialization gap, and the two-tier / SSE-first synthesis are jcanton's.*
