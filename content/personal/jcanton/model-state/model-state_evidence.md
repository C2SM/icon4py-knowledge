---
title: Model state — evidence
author: jcanton
tags: [state, model-state, duplication, allocation, evidence, gt4py, bindings]
created: 2026-07-29
status: draft
---

> Appendix to [[personal/jcanton/model-state/model-state|Model state — requirements and design options]].
> Defects found in `main` at `4ae9fba50`. Paths relative to the icon4py repo root.

## Verified defects

### E1 — `PrepAdvection` / `AdvectionPrepAdvState`: duplicated *and* disconnected

Two containers hold the same three quantities:

| ICON name | `PrepAdvection` (`dycore_states.py:215`) | `AdvectionPrepAdvState` (`tracer_advection_states.py:46`) |
|---|---|---|
| `vn_traj` | `vn_traj: EdgeKField` | `vn_traj: EdgeKField` |
| `mass_flx_me` | `mass_flx_me: EdgeKField` | `mass_flx_me: EdgeKField` |
| `mass_flx_ic` | `dynamical_vertical_mass_flux_at_cells_on_half_levels` | `mass_flx_ic` |
| `vol_flx_ic` | `dynamical_vertical_volumetric_flux_at_cells_on_half_levels` | *absent* |
| mutability | mutable (dycore accumulates into it) | `frozen=True` |

`driver_states.py:283` allocates the first, `:290` allocates the second as three fresh
`zero_field`s. Grep across `model/` finds **no code that copies or aliases one into the
other**. The dycore writes `prep_adv`; the advection reads `tracer_prep_adv`
(`standalone_driver.py:256` vs `:289`). Standalone-driver tracer advection therefore runs on
identically-zero trajectory velocity and mass fluxes.

Caveat: `standalone_driver.py:277` carries `# Precondition: passing data test with ntracer > 0`,
so this is plausibly known-incomplete rather than a shipped regression. PR 1404 fixes it with
`initialize_prep_tracer_advection`, ~30 lines that alias the buffers, plus an identity test.

Note the same quantity carries two names across the boxes — the dycore took the descriptive
rename, the advection kept the Fortran name.

### E2 — the two disagree on vertical extent

`dycore_states.py:239` allocates `dynamical_vertical_mass_flux_at_cells_on_half_levels` with
`extend={dims.KDim: 1}` (nlev+1). `driver_states.py:294` allocates `mass_flx_ic` as plain
`zero_field(grid, CellDim, KDim)` (nlev). Even adding a copy would not be shape-compatible.
The annotation `fa.CellKField[float]` cannot express the difference. Unresolved in PR 1404.

### E3 — `T`/`Tv`/`p` derived ≥3× with divergent hydrometeors *(science)*

- `driver_io.py:181` — `diagnose_virtual_temperature_and_temperature` with `qv…qg` that are
  **permanently zero**: `driver_io.py:146`, comment *"dry air: all hydrometeors stay zero
  (never written, so allocated once)"*.
- muphys `state.py` — same stencil, **real tracers**.
- `jablonowski_williamson.py:299` — a third path.

Same stencil, same CF `standard_name`, different values. The temperature written to output is
not the temperature physics computed with. Domains also differ: `Zone.END` vs raw `num_cells`.

### E4 — `vn → u,v` computed 3× with divergent halo treatment

`driver_states.py:255` and `driver_io.py:199` both call `edge_2_cell_vector_rbf_interpolation`:

| | `driver_states.py:255` | `driver_io.py:199` |
|---|---|---|
| `horizontal_start` | `end_cell_lateral_boundary_level_2` | `self._cell_lateral_boundary_level_2` |
| `offset_provider` | `grid.connectivities` | `{"C2E2C2E": ...}` |
| output | `diagnostic_state.u/.v` | private `self._u/._v` |
| halo exchange after | **yes** (`:266`) | **no** |

PR 1360's TMX adds a fourth. `driver_io.py:115` already asks for the fix:
*"TODO(kotsaloscv): refactor once the driver groups model state — derive these diagnostic
buffers from that shared grouping instead of recomputing them here… they should be shared
rather than duplicated across IO and physics."*

### E5 — structural redundancy across interpolation/metric states

- `dycore.InterpolationState` ⊇ `DiffusionInterpolationState` **exactly** (all 8 fields,
  identical names and shapes); `AdvectionInterpolationState` is a strict subset.
- `geofac_div` declared in 3 containers; `ddqz_z_full` in 3 live / 4 declared; `wgtfac_c` ×2.
- `MetricStateSaturationAdjustment` and `MetricStateIconGraupel` are byte-identical one-field
  dataclasses over the same field.
- `theta_ref_mc` (diffusion) and `reference_theta_at_cells_on_model_levels` (dycore) are the
  same factory key under two names.

### E6 — the hand-mapping, replicated

`driver_utils.py:229-439` is ~175 lines / ~90 `.get()` calls turning factory outputs into 9
granule dataclasses. Repeated in `diffusion/tests/diffusion/fixtures.py`,
`dycore/tests/dycore/utils.py`, `test_benchmark_diffusion.py`, `test_benchmark_solve_nonhydro.py`,
`tracer_advection/tests/.../utils.py`. Adding one field to `MetricStateNonHydro` (34 members)
touches ≥3 call sites in 3 packages.

### E7 — two shipped wrong-key bugs in exactly that hand-mapping

- `test_benchmark_solve_nonhydro.py:162` — `D2DEXDZ2_FAC1_MC` assigned to `d2dexdz2_fac2_mc`.
- `test_benchmark_diffusion.py:101,105` — `EDGE_NORMAL_VERTEX_V` assigned to
  `dual_normal_vert_y`, where the tangent was meant (cf. `driver_utils.py:253`, which uses
  `EDGE_TANGENT_VERTEX_V`).

Both type-check, both run, neither is detectable by any current mechanism. Wide constructors
of same-typed fields make this class of bug free to write.

### E8 — placement recorded three times

Name string (`..._at_cells_on_half_levels`) / `dims=(CellDim, KHalfDim)` in `metadata.py` /
`is_on_half_levels: bool` in `states/model.py:38`. The bool is set in **one** entry
(`data.py:38`) and read only by IO; the factory vocabularies use `dims` instead. And the
factory **rewrites `KHalfDim → KDim` at allocation** (`factory.py:544`, `:468`, `:821` —
*"workaround to have consistent definitions. Remove once gt4py supports vertically staggered
dimension"*), so half-levelness survives only in a metadata tuple that nothing validates
against the allocated buffer.

### E9 — vocabulary fragmentation

Five parallel namespaces per field: catalog key (`temperature`) / CF `standard_name`
(`air_temperature`) / ICON Fortran name (`temp`) / dataclass attribute / component port name
(`te`). Only key↔ICON-name is machine-readable (`icon_var_name`).

Four disjoint metadata dicts plus one orphan: `states/metadata.py` (17 entries, consumed by no
production factory), `states/data.py` (18, IO only), `geometry_attributes.py` (50),
`interpolation_attributes.py` (23), `metrics_attributes.py` (49).

And **six places where a field's `(name, dims, units)` is independently re-derived**, none of
which can see the others:

| Site | What it re-derives | From |
|---|---|---|
| the three factory attribute dicts | `standard_name`, `units`, `dims`, `dtype` | hand-written |
| `states/data.py` | CF attrs + `icon_var_name` | hand-written, IO only |
| `states/metadata.py` | same, orphaned | hand-written, no consumer |
| `bindings/.../dycore_wrapper.py:370` | ICON name → icon4py field, per timestep | hand-written |
| `driver_io.py:224` | output key → field | hand-written |
| `ibm_02` `io/restart.py:204` | `dims` for the restart file | read off the **live field** |

The last one is the interesting case — see "Restart, as it actually stands" below.

CF coverage: metrics ~0/49 are real CF names (the pattern is literally
`standard_name=<raw ICON name>`), interpolation 0/23, geometry ~1/50, `data.py` ~7/18.
`units=""` for most geometry/interpolation/metrics entries. Headers carry
*"should be cross checked by domain scientist"* and *"TODO: revise names with domain scientists"*.

**A live collision already exists:** `metrics_attributes.py:106` — the `DDQZ_Z_FULL_E` entry
declares `standard_name=DDQZ_Z_FULL`, so two distinct fields (cell and edge, different dims)
advertise one standard name. The IO writer resolves variable identity by `standard_name`
(`writers.py:245`), so they would silently alias into one netCDF variable.

### E10 — the trend

PR 1360 adds **seven** state dataclasses for one component: `TmxMetricState` (14 fields),
`TmxInterpolationState` (5), `TmxInputState` (16), `TmxSurfaceFluxState`, `TmxDiagnosticState`
(~30), `TmxNewState` (7), `TmxTendencyState` (7). `TmxInputState` re-declares `qv…qg`
(= `TracerState`), `rho`/`w` (= `PrognosticState`), and `air_mass` (≈ advection's
`airmass_now/new`). Its design doc names the pattern: *"Muphys pattern: new files inside the
tmx package."* Its `gather_from_prognostic` re-derives `T`/`Tv`/`p` with the same stencils
muphys uses — E3, a fourth time.

## Constraints verified first-hand

### gt4py named collections

`gt4py/next/named_collections.py:34-48`, `CustomDataclassNamedCollectionABC.__subclasshook__`
requires `dataclasses.is_dataclass(subclass)` and, per field,
`init is True and default is MISSING and default_factory is MISSING`. Run against the tree:

```
dict                        : False
PrognosticState             : False    # tracer: TracerState = field(default_factory=TracerState)
DiagnosticStateNonHydro     : True
PrepAdvection               : True
```

A dict can never be a `gtx.program` argument. `PrognosticState` is **not** a valid named
collection today; PR 1404, by removing the `tracer` field, incidentally makes it one.

### The Fortran-embedded boundary

`bindings/src/icon4py/bindings/dycore_wrapper.py:306` — `solve_nh_run` takes **37 raw fields +
10 scalars as positional args**, all under ICON Fortran names, then spends ~55 lines
(`:370-424`) rebuilding `PrepAdvection`, `DiagnosticStateNonHydro`, two `PrognosticState`s and
a `TimeStepPair` **on every timestep call**. That repack is a third, hand-maintained copy of
the ICON↔icon4py name mapping:

| Fortran | icon4py |
|---|---|
| `theta_v_ic` | `theta_v_at_cells_on_half_levels` |
| `exner_pr` | `perturbed_exner_at_cells_on_model_levels` |
| `mass_flx_ic` | `dynamical_vertical_mass_flux_at_cells_on_half_levels` |

Consequences:

- **The container cannot own allocation.** ICON owns this memory; py2fgen wraps it zero-copy
  (`tools/src/icon4py/tools/py2fgen/_conversion.py:50` `np.frombuffer(ffi.buffer(...))`,
  `:68` `cp.cuda.UnownedMemory(...)`, `order="F"`). It must *adopt* external buffers.
- **No struct can cross the ABI.** py2fgen's whole type model is
  `ParamDescriptor = ArrayParamDescriptor | ScalarParamDescriptor`
  (`py2fgen/_definitions.py:41`) — there is no record descriptor. The wrapper keeps flattening.
- **Anything the container does per construction costs per-timestep time inside ICON.**
- Optional IAU increments arrive as `Field | None` with a `dummy_field_factory` fallback
  (`:335`) — exactly the `Optional`/default pattern gt4py named collections reject.
- In the embedded path `PrepAdvection` and the advection arrays *are* the same memory, because
  Fortran hands over the same pointers. E1 is a standalone-driver-only divergence.
- `bindings/tests/bindings/test_codegen_references.py` is a **golden-file test of generated
  Fortran/C bindings** — any wrapper signature change breaks a checked-in artifact.

### What does not exist

- **A checkpoint *write* path.** `io/io.py:290` carries
  `# TODO (jcanton): take care of this when implementing restart` (output-file overwrite
  protection). A **read** path does exist — see below — and a prototype writer exists on
  `origin/ibm_02`. What is missing on `main` is the write side and any per-field restart flag.
- **Any invalidation machinery.** `grep -i "invalidat|stale|recompute|dirty|version"` over
  `states/`, `geometry.py`, `metrics_factory.py`, `interpolation_factory.py` returns **zero**
  hits. Once `provider._fields[k] is not None` the value is returned forever; there is no
  evict API and no time awareness (`get()` takes only `(field_name, type_)`).
- **Any use of the Component protocol's declared properties.** `inputs_properties` /
  `outputs_properties` are never consulted at runtime anywhere. Zero classes subclass
  `Component`; it is not `@runtime_checkable`; `Component.__call__` has no body and no `...`,
  so a class that forgets to implement it silently returns `None`. Both TODOs in
  `components.py:52-54` (unit matching, dimension consistency) are unimplemented. The
  documented `IncompleteStateError` is raised by exactly one site, the IO monitor
  (`io.py:324`).
- **An IO path for tracers or physics diagnostics.** Output is a hardcoded whitelist
  (`PROGNOSTIC_VARIABLES` / `DIAGNOSTIC_VARIABLES` in `driver_io.py`); tracers appear in
  neither. Physics precipitation outputs land on `State` attributes and are unreachable by IO;
  `MICROPHYSICS_PRECIP_CF_ATTRIBUTES` is defined and wired to nothing.

### Restart, as it actually stands

Assembled from [[personal/msimberg/checkpoint-restart/checkpoint-restart|msimberg's doc]] and
verified against the tree. Note his doc cites some pre-rename paths: `model/driver/` is now
egg-info only, and `TimeLoop.restart_mode` no longer exists (`standalone_driver` has
`is_first_step_in_simulation`, `driver_states.py:83`).

**Read path on `main`** — `read_restart_from_file` (`initial_condition/from_file.py:142`),
gated by `FromFileConfig.is_restart` (`:50`). Serialbox-based: restores prognostics, `exner_pr`
and the predictor/corrector advective tendencies from the savepoint of the step ending at
`start_of_timestepping`. Tracers raise `NotImplementedError` (`:162`) for a **naming** reason,
quoted verbatim:

> the solve-nonhydro savepoints do not carry them, they are in the advection-init savepoint of
> the same date.

**Write prototype on `origin/ibm_02`** — `io/restart.py`, `RestartManager`, pickle, alternating
`restart_0/1.pkl` with `.meta` sidecars and temp-file-then-rename. Saves prognostics for both
`.current` and `.next`, plus three hand-picked `DiagnosticStateNonHydro` members
(`perturbed_exner_at_cells_on_model_levels`, `vertical_wind_advective_tendency.predictor`,
`.corrector`). No tracers, no diffusion diagnostics, no advection prep, no real datetime, no
adaptive-substep state.

**A sixth reinvention of field metadata.** `restart.py:204-210`:

```python
def _store_field(self, state_dict, key, field):
    state_dict[key] = {
        "data": field.asnumpy(),
        "dims": [d.value for d in field.domain.dims],
    }
```

and on read (`:75-77`, `:100-106`):

```python
dims_tuple = tuple(getattr(dims, name + "Dim") for name in dim_names)
field = gtx.as_field(dims_tuple, arr, allocator=backend)
```

The string round-trip itself is sound — checked for `CellDim`/`EdgeDim`/`KDim`/`KHalfDim`, all
four survive `d.value + "Dim"`. The problem is where the dims come from: **they are read off a
live field at write time**, because there is no declaration to read them from. Consequences:

1. It cannot allocate a field that does not exist yet — which is exactly what restarting into a
   fresh process needs. `main`'s read path sidesteps this by requiring the caller to pass
   already-allocated `prognostic_state_now` and `solve_nonhydro_diagnostic_state` in.
2. Half-levelness cannot reach the file, because the factory already erased `KHalfDim → KDim` at
   allocation (E8) — so a half-level field's live domain reports `K` with length nlev+1.
3. Add `_store_field` to the list in E9: field metadata is now independently re-derived in
   `states/metadata.py`, `states/data.py`, the three factory attribute dicts, the bindings
   repack, `driver_io`'s output dict, and here.

This is the `QuantityFactory`/`GridSizer` argument (declare `dims` once, resolve to an
allocation through one object) arriving from a second, independent direction.

### Dead or near-dead containers

- `DiagnosticMetricState` — zero constructors in `src/`; still constructed in two test files.
- `common.states.DiagnosticState` — constructed, half-filled (`u`/`v` only), stored in
  `DriverStates.diagnostic`, and **never read by the time loop**; `pressure`, `temperature`,
  `virtual_temperature` stay zero for the whole run. Its only consumer is one MPI test.
  Meanwhile `driver_io` allocates its own private shadow of the same six quantities
  (`driver_io.py:150-158`; own docstring at `:109`: *"~14 scratch/output buffers"*).

Deleting the first is one line. Promoting the second to *the* shared diagnostic container is
the whole refactor.

## Claims I could not verify — treat with suspicion

- **All memory numbers.** Figures circulated during this investigation (~185 MB redundancy,
  ~270 MB `DiagnosticStateNonHydro`, ~290 MB granule scratch, ~65 MB unambiguous waste) were
  derived from an assumed grid (`C=20896, E=31558, L=65`) **not read from any file in this
  repo**, and they conflict with a per-GPU strong-scaled estimate of 23–118 MB/field. Treat all
  of them as order-of-magnitude only. The *relative* claim — granule scratch exceeds
  cross-granule duplication — is the load-bearing one and should be measured before being cited.
- **A claimed tracer double-buffering bug** tied to the parity of `ndyn_substeps_var` (mutated
  at runtime, `standalone_driver.py:441,455`). Derived by counting swaps; no test, no observed
  wrong answer. Verify by running with an even `ndyn_substeps` and asserting tracer conservation.
- **`tach check` reports "Unused Dependencies" for every module**, i.e. the boundary check
  currently enforces nothing. Load-bearing for "where can a shared container live" — verify with
  `.venv/bin/tach check` before relying on it.
- **Micro-benchmarks** quoted in the main doc (label filtering ~4 µs/300 fields; gt4py's
  codegen extractor ~4× faster than a dict comprehension; `gtx.as_field` copying at ~1 ms/12.8 MB)
  were measured on one laptop, not on target hardware.
- **Prior-art line numbers** for sympl, climt, NDSL/Pace, ClimaAtmos, MPAS and CCPP are
  paraphrase-grade; only ICON, LFRic, MAPL and gt4py were read from local checkouts.
- **DaCe orchestration** was removed (`8f3d6c5b8`, *"outdated and unmaintained"*), so its
  constraint on container shape is **not** a present-day blocker — but the DaCe *backend* is
  live (`model_backends.py:105`) and a redesign still has to survive SDFG argument-descriptor
  generation. Earlier framings conflated the two.
