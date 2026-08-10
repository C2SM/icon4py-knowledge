---
title: Model state — evidence
author: jcanton
tags: [state, model-state, duplication, allocation, evidence, gt4py, bindings]
created: 2026-07-29
status: draft
---

> Appendix to [[personal/jcanton/model-state/model-state|Model state]].
> Defects found in `main` at `4ae9fba50`; **re-verified against `origin/main` at `4c858a6a`
> (2026-08-06)**, superseding the earlier `f94d2d44e` (2026-07-30) pass. Paths relative to the
> icon4py repo root.
>
> **This document is the single authoritative source for counts and file:line evidence** in the
> model-state doc set. The main document cross-references it rather than restating numbers.
> Line numbers drift; each entry states the revision it was last checked at.
>
> **E1 and E2 were fixed on 2026-07-30** by [PR 1404](https://github.com/C2SM/icon4py/pull/1404)
> (`3c8c69342`), which aliases the dycore's buffers into `AdvectionPrepAdvState` instead of
> allocating fresh ones, and adds an identity test. They are kept below as the record of what the
> container shape cost, and because the *fix* — a permanent hand-written aliasing function — is
> the argument for M1. `#1407` separately removed the deep-atmosphere advection metrics.

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
`extend={dims.KDim: 1}` (nlev+1). `driver_states.py:294` allocated `mass_flx_ic` as plain
`zero_field(grid, CellDim, KDim)` (nlev). Even adding a copy would not have been
shape-compatible. The annotation `fa.CellKField[float]` cannot express the difference.

Only `mass_flx_ic` disagreed — `vn_traj` and `mass_flx_me` were allocated identically on both
sides. Resolved by PR 1404's aliasing, which sidesteps the shape question entirely; the
type-system gap that let two containers claim different extents for one quantity remains.

### E3 — `T`/`Tv` derived from divergent inputs; the IO path is fully dry *(science)*

*Re-verified at `4c858a6a`. The earlier framing — "different hydrometeor inputs" — understated
this: `qv` is zero on the IO path too.*

- `driver_io.py:182` — `diagnose_virtual_temperature_and_temperature` called with
  `qv, qc, qi, qr, qs, qg` that are **all permanently zero**. `driver_io.py:146-147` allocates
  the six once, with the comment *"dry air: all hydrometeors stay zero (never written, so
  allocated once)"*, and no other line in the file assigns to them (`grep -n "_qv"` returns
  exactly `:147` and `:182`).
- muphys `state.py:87-88`, `:168` — same stencil, **real tracers**.
- `initial_condition/analytical/utils.py:287` — a third path, carrying its own comment
  *"hydrometeors are zero here, so only qv enters (see diagnose_temperature)"*.
- `jablonowski_williamson.py:300` — pressure via
  `pressure_diagnostics.diagnose_pressure_surface_to_top_ndarray`.

Consequences: on the output path `virtual_temperature ≡ temperature` identically, and the
temperature icon4py publishes is a **dry-air** temperature that no physics component uses.
Domains also differ (`horizontal_start=0` in `driver_io` vs the derivation in `driver_states`).

### E4 — `vn → u,v` computed twice, into two buffers, one of them not halo-exchanged

*Corrected at `4c858a6a`: there are **two** production call sites, not three, and they do **not**
differ in domain bounds.*

`driver_states.py:290` and `driver_io.py:199` both call `edge_2_cell_vector_rbf_interpolation`
(a third call site exists only in `test_diagnostic_calculations.py:187`):

| | `driver_states.py:290` | `driver_io.py:199` | material? |
|---|---|---|---|
| `horizontal_start` | `end_cell_lateral_boundary_level_2` | `self._cell_lateral_boundary_level_2` | **no** — same bound, computed twice |
| `horizontal_end` | `end_cell_end` | `end_cell_end` | no |
| `offset_provider` | `grid.connectivities` | `{"C2E2C2E": ...}` | **no** — the stencil only uses `C2E2C2E` |
| output | `diagnostic_state.u/.v` | private `self._u/._v` | **yes** — two buffers for one quantity |
| halo exchange after | **yes** (`:302`) | **no** | **yes** |

So the defect is duplicated buffers plus divergent halo treatment, not divergent domains.
`driver_io.py:115` already asks for the fix:
*"TODO(kotsaloscv): refactor once the driver groups model state — derive these diagnostic
buffers from that shared grouping instead of recomputing them here… they should be shared
rather than duplicated across IO and physics."*
The TMX branch adds a third derivation (see E10).

### E5 — structural redundancy across interpolation/metric states

*Re-verified at `4c858a6a` by AST introspection of every state module.*

- `dycore.InterpolationState`'s 16 dataclass fields are a strict superset of
  `DiffusionInterpolationState`'s 8 — the first 8, in the same order:
  `e_bln_c_s, rbf_coeff_1, rbf_coeff_2, geofac_div, geofac_n2s, geofac_grg_x, geofac_grg_y,
  nudgecoeff_e`. (At *class* level diffusion also carries two `cached_property` members —
  `geofac_n2s_c`, `geofac_n2s_nbh` — the dycore has no counterpart for, and the two annotate the
  shared fields with `float` vs `ta.wpfloat`: same runtime type, different declarations.)
  `AdvectionInterpolationState`'s 4 are a strict subset of the dycore's 16.
- `geofac_div` declared in 3 containers (4 with TMX, see E10); `ddqz_z_full` as a dataclass field
  in 4 — `MetricStateSaturationAdjustment`, `MetricStateIconGraupel`, `AdvectionMetricState`, and
  the dead `DiagnosticMetricState` — i.e. 3 live / 4 declared; `wgtfac_c` ×2.
- `MetricStateSaturationAdjustment` (`saturation_adjustment.py:39`) and `MetricStateIconGraupel`
  (`single_moment_six_class_gscp_graupel.py:113`) are byte-identical one-field dataclasses over
  `ddqz_z_full: fa.CellKField[ta.wpfloat]`.
- `theta_ref_mc` (diffusion) and `reference_theta_at_cells_on_model_levels` (dycore) are the
  same factory key under two names.

### E6 — the hand-mapping, replicated [count corrected upward]

`driver_utils.initialize_granules` spans `:221-487` on `origin/main` at `4c858a6a`, with
**89 `.get()` calls** in that range (91 in the whole file), turning factory outputs into 9
granule dataclasses.

Taking the union of every file that constructs a granule interpolation / metric /
least-squares / diagnostic container, there are **13 further sites**, not 7:

| Kind | Sites |
|---|---|
| **Production (2)** | `bindings/src/icon4py/bindings/dycore_wrapper.py`, `bindings/src/icon4py/bindings/diffusion_wrapper.py` |
| Tests (11) | `bindings/tests/bindings/{test_dycore_wrapper,test_diffusion_wrapper}.py`; `diffusion/tests/diffusion/fixtures.py`; `diffusion/tests/.../{test_benchmark_diffusion,test_diffusion,test_diffusion_states}.py`; `diffusion/tests/.../mpi_tests/test_parallel_diffusion.py`; `dycore/tests/dycore/utils.py`; `dycore/tests/.../test_benchmark_solve_nonhydro.py`; `tracer_advection/tests/.../{fixtures,utils}.py` |

Adding one field to `MetricStateNonHydro` (32 members) touches ≥3 call sites in 3 packages.

### E7 — wrong-key bugs in exactly that hand-mapping

*Three live occurrences of two kinds, all confirmed still present on `origin/main` at
`4c858a6a`. These are filable today.*

- `test_benchmark_solve_nonhydro.py:163` — `D2DEXDZ2_FAC1_MC` assigned to `d2dexdz2_fac2_mc`
  (`:162` correctly assigns `d2dexdz2_fac1_mc` from the same key).
- `test_benchmark_solve_nonhydro.py:98` and `test_benchmark_diffusion.py:105` —
  `EDGE_NORMAL_VERTEX_V` assigned to `dual_normal_vert_y`, where the tangent was meant.

The intended mapping — `EDGE_NORMAL_VERTEX_V → primal_normal_vert_y`,
`EDGE_TANGENT_VERTEX_V → dual_normal_vert_y` — is stated correctly in three independent places:
`driver_utils.py:259,261`, `test_diffusion.py:77,81`, and `test_parallel_geometry.py:64,69`.

Both type-check, both run, neither is detectable by any current mechanism. Wide constructors of
same-typed fields make this class of bug free to write.

**They live in the *replicated* sites, not the primary one** — `driver_utils.py:259-261` is
correct. That is an argument for deleting the replication, not for distrusting `driver_utils`.
And "shipped" overstates it: these are benchmark paths, not the production driver.

### E8 — placement recorded three times, and now tested into place

Name string (`..._at_cells_on_half_levels`) / `dims=(CellDim, KHalfDim)` in `metadata.py` /
`is_on_half_levels: bool` in `states/model.py:39` (an `OptionalMetaData` key). The bool is set
in **one** entry (`data.py:38`) and read at `driver_io.py:83` and `:242`; the factory
vocabularies use `dims` instead. And the factory **rewrites `KHalfDim → KDim` at allocation**
(`factory.py:821-823`, plus `:461`, `:470`, `:540`, `:545` — *"workaround to have consistent
definitions. Remove once gt4py supports vertically staggered dimension"*), so half-levelness
survives only in a metadata tuple that nothing validates against the allocated buffer.

**[newly verified] The redundancy is now pinned by a test.**
`standalone_driver/tests/.../test_driver_io.py:74` carries the docstring *"…`dims` and
`is_on_half_levels` are stated independently of the…"*, and `:79`, `:88`, `:118` assert on it.
Removing the third representation now requires touching a test that deliberately restates it.

Note also that `states/model.py:41` already defines a `kind: Literal["tendency", "diagnostic"]`
metadata key. Any M2 vocabulary should extend that key rather than introduce a parallel one.

### E9 — vocabulary fragmentation

Five parallel namespaces per field: catalog key (`temperature`) / CF `standard_name`
(`air_temperature`) / ICON Fortran name (`temp`) / dataclass attribute / component port name
(`te`). Only key↔ICON-name is machine-readable (`icon_var_name`).

Four disjoint metadata dicts plus one orphan, counted by `standard_name=` entries at
`4c858a6a`: `states/metadata.py` (**17**, consumed by no production factory),
`states/data.py` (**25**, IO only), `geometry_attributes.py` (**51**),
`interpolation_attributes.py` (**23**), `metrics_attributes.py` (**46**).

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

CF coverage: metrics ~0/46 are real CF names (the pattern is literally
`standard_name=<raw ICON name>`), interpolation 0/23, geometry ~1/51, `data.py` ~7/25.
Empty units, counted: **interpolation 23/23 (100 %)**, **metrics 45/46**, metadata.py 14/17,
geometry **11/51** — so "`units=""` for most geometry entries" was **wrong** and is corrected
here; it holds for interpolation and metrics. Headers carry *"should be cross checked by domain
scientist"* and *"TODO: revise names with domain scientists"*.

**A live collision already exists:** `metrics_attributes.py:103-104` — the `DDQZ_Z_FULL_E` entry
declares `standard_name=DDQZ_Z_FULL`, so two distinct fields — `(CellDim, KDim)` and
`(EdgeDim, KDim)` — advertise one standard name. The IO writer resolves variable identity by
`standard_name` equality (`writers.py:245-246`, `filter_by_standard_name`), so they would
silently alias into one netCDF variable. (Metrics are not in the output whitelist today, so the
collision is latent rather than firing — which is exactly what makes M4 auto-wiring keyed on
today's vocabulary dangerous.)

### E10 — the trend

*Verified by AST introspection of `origin/physics_driver_tmx:.../tmx/tmx_states.py`
(2026-08-05). Field counts corrected upward from the earlier estimate.*

**Seven** state dataclasses and **92 declared fields** for one component:

| Container | Fields | Overlap with existing containers |
|---|---|---|
| `TmxMetricState` | 17 | `ddqz_z_full` (a 5th declaration), `inv_ddqz_z_full`, `ddqz_z_half`, `wgtfac_c`, `wgtfac_e`, `wgtfacq_c`, `wgtfacq_e` — all in `MetricStateNonHydro` |
| `TmxInterpolationState` | 9 | `c_lin_e`, `e_bln_c_s`, `geofac_div` — makes `geofac_div` a **4th** container |
| `TmxInputState` | 16 | **all six** fields of `common.DiagnosticState` (`temperature`, `virtual_temperature`, `pressure`, `pressure_ifc`, `u`, `v`), **all six** tracers (= `TracerState`), `rho`/`w` (= `PrognosticState`), plus `air_mass` (≈ advection's `airmass_now/new`) |
| `TmxSurfaceFluxState` | 5 | — |
| `TmxDiagnosticState` | 31 | `theta_v`, `vn`, `rho_ic`, `vn_ie` overlap the dycore's |
| `TmxNewState` | 7 | the same 7 quantities as… |
| `TmxTendencyState` | 7 | …`ddt_*` of them |

Its design doc names the pattern: *"Muphys pattern: new files inside the tmx package."* Its
`gather_from_prognostic` re-derives `T`/`Tv`/`p` with the same stencils muphys uses — E3, a
third time — and its `u`/`v` a third derivation of E4.

## Constraints verified first-hand

### gt4py named collections [rule corrected and extended]

`gt4py/next/named_collections.py:35-49`, `CustomDataclassNamedCollectionABC.__subclasshook__`.
The full rule is stricter than earlier revisions of this appendix stated. It requires
`dataclasses.is_dataclass(subclass)`, a module **not** starting with `gt4py.`,
`len(fields) > 0`, and — for every entry of `__dataclass_fields__` —
`init is True`, `default is MISSING`, `default_factory is MISSING`, **and
`_field_type is dataclasses._FIELD`**.

Run empirically in icon4py's own venv:

```
dict                                      : False   # never a gtx.program argument
dataclass with a ClassVar                 : False   # <-- the _field_type clause
empty dataclass                           : False   # <-- the len(fields) > 0 clause
dataclass with any defaulted field        : False
dataclass with `x: int | None`, no default: True    # <-- CORRECTS an earlier claim
dataclass with field(metadata=...) only   : True    # M2 is free, legality-wise
```

Against the tree at `4c858a6a`:

```
PrognosticState             : True     # rho, w, vn, exner, theta_v — PR 1404 removed `tracer`
TracerState                 : False    # qv…qg all carry `= None` DEFAULTS
DiagnosticStateNonHydro     : True
PrepAdvection               : True
```

Three consequences:

1. **A dict can never be a `gtx.program` argument.** The last mile is always a typed dataclass.
2. **A `ClassVar` disqualifies a container.** `__dataclass_fields__` retains ClassVar/InitVar
   pseudo-fields and the `_field_type` clause rejects them. Class-level metadata attached to a
   *state* dataclass silently loses named-collection status; attached to the *Component* (as
   both msimberg specs do) it is safe.
3. **`| None` in the annotation is irrelevant** — the hook never inspects annotations. What
   disqualifies `TracerState` is the `= None` defaults at `tracer_states.py:107-118`. A
   `TracerState` rewritten with `spec(...)` and no defaults would be *structurally* conformant
   while some of its *instances* remain unusable, moving the failure from class-definition time
   to call time. Whether a container is a wiring object or a program argument must therefore be
   declared, not discovered.

### The Fortran-embedded boundary

`bindings/src/icon4py/bindings/dycore_wrapper.py:306` — `solve_nh_run` takes **~45 raw fields
and scalars as positional args** (the function even carries
`# noqa: PLR0917 [too-many-positional-arguments]`), all under ICON Fortran names, then spends
~68 lines (`:358-426`) rebuilding `PrepAdvection` (`:370`), `DiagnosticStateNonHydro` (`:381`),
two `PrognosticState`s (`:408`, `:415`) and a `TimeStepPair` (`:422`) before calling
`granule.solve_nh.time_step` (`:427`) — **on every timestep call**. That repack is a third,
hand-maintained copy of the ICON↔icon4py name mapping:

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
  (`py2fgen/_definitions.py:63`) — there is no record descriptor. The wrapper keeps flattening.
- **Anything the container does per construction costs per-timestep time inside ICON.**
- **Absence is faked with an allocation.** Optional IAU increments and optional diffusion
  diagnostics arrive as `Field | None` and are backed by
  `wrapper_common.cached_dummy_field_factory` — `vn_incr` (`dycore_wrapper.py:358`),
  `rho_incr` (`:361`), `exner_incr` (`:366`); `hdef_ic`/`div_ic`/`dwdx`/`dwdy`
  (`diffusion_wrapper.py:292-298`). This is the concrete evidence for goal G6.
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
- **Any *production* use of the Component protocol's declared properties.** Zero classes
  *inherit* `Component`; it is not `@runtime_checkable`; `Component.__call__` has no body and no
  `...`, so a class that forgets to implement it silently returns `None`. Both TODOs in
  `components.py:52-54` (unit matching, dimension consistency) are unimplemented. The documented
  `IncompleteStateError` is raised by exactly one site, the IO monitor (`io.py:324`).
  **[corrected] One real component does declare the contract structurally:**
  `muphys/component.py:49-50` sets `inputs_properties = muphys_data.INPUTS_PROPERTIES` and
  `outputs_properties = ...` as plain class attributes. The only readers of either attribute
  anywhere are `Component.__str__` (`components.py:85-86`) and a physics-driver test mock — so
  nothing in production consults them, but M3 has a ready-made first consumer rather than a
  greenfield.
- **An IO path for tracers or physics diagnostics.** Output is a hardcoded whitelist:
  `PROGNOSTIC_VARIABLES` (`driver_io.py:54`, 5 entries) and `DIAGNOSTIC_VARIABLES` (`:94`,
  5 entries); tracers appear in neither. Physics precipitation outputs land on `State`
  attributes and are unreachable by IO; `MICROPHYSICS_PRECIP_CF_ATTRIBUTES` is defined and
  wired to nothing.

### Restart, as it actually stands

Assembled from [[personal/msimberg/checkpoint-restart/checkpoint-restart|msimberg's doc]] and
verified against the tree. Note his doc cites some pre-rename paths: `model/driver/` is now
egg-info only, and `TimeLoop.restart_mode` no longer exists (`standalone_driver` has
`is_first_step_in_simulation`, `driver_states.py:83`).

**Read path on `main`** — `read_restart_from_file` (`initial_condition/from_file.py:147`),
gated by `FromFileConfig.is_restart` (`:54`). Serialbox-based: restores prognostics, `exner_pr`
and the predictor/corrector advective tendencies from the savepoint of the step ending at
`start_of_timestepping`. Tracers raise `NotImplementedError` (`:167`) for a **naming** reason,
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

- `DiagnosticMetricState` (`states/diagnostic_state.py:52`) — **[corrected] now fully dead**:
  zero constructors anywhere at `4c858a6a`, including tests. It was previously still built in
  two test files.
- `common.states.DiagnosticState` — constructed (`diagnostic_state.py:108` initializer, plus two
  test files), half-filled (`u`/`v` only, written and halo-exchanged at
  `driver_states.py:290,302`), stored in `DriverStates.diagnostic`; `pressure`, `pressure_ifc`,
  `temperature`, `virtual_temperature` stay zero for the whole run. Meanwhile `driver_io`
  allocates its own private shadow of the same six quantities (`driver_io.py:147-160`; own
  docstring at `:109`: *"~14 scratch/output buffers"*) — which is E4 and E3 in one place.

Deleting the first is one line. Promoting the second to *the* shared diagnostic container is
the whole refactor.

## Unrelated icon4py defects found along the way

Not about state containers, and actionable independently of everything else in this proposal.
Found by ICON-sc (see [[personal/jcanton/model-state/model-state_prior-art|prior art]]) while
hosting icon4py granules. **None was ever filed** — its work unit `0023-upstream-reports/`
contains only a `plan.md`.

| ID | Finding | Status |
|---|---|---|
| **U1** | **Graupel cold-glaciation water-budget leak.** Supercooled qc at T ≲ 233 K near the moist-domain top *gains* total water — a fixed absolute amount per column, independent of qc magnitude: **+1.59e-4 kg/m² per Δt=30 s**, worst in-domain relative 4.32e-4. Suppressed entirely by any coexisting ice-phase seed | **Has a runnable, wrapper-free reproducer** on public icon4py APIs, bounded so it visibly collapses when fixed |
| **U9** | **`is_surface` index bug in the graupel scan.** `k_lev` is a scan carry starting at 0 relative to `vertical_start=kstart_moist` (`graupel_stencils.py:827`), compared at `:218` against `ground_level = num_levels-1` (absolute). The surface minimum-fall-speed clamps **only fire when `kstart_moist == 0`** | **Verified independently.** One line |
| **U2** | **`wgtfacq_c`/`wgtfacq_e` shifted-K-domain footgun** — both the metrics factory and the serialbox reader emit these on K-domain `[nlev−3, nlev)`; the convention is visible only in the factory registration | Cost ICON-sc ~2 work units. Same class as E8 |
| **U3/4/5** | One grid-factory issue: `mean_cell_area` off **4e-5 relative** deterministically → 3.6e-6 m/s on `vn` after one Δt; RBF pentagon divide warnings; `GridManager(keep_skip_values=False)` doesn't pad file-sourced vertex tables, and `_replace_skip_values` then makes the RBF matrix **exactly singular** | Latent trap for grid-from-file rather than savepoint |
| **U6** | `SPECIFIC_HEAT_CAPACITY_ICE = 2108.0` vs ICON `ci = 2106.0_wp`; live only in the temperature-dependent latent-heat branch, dead under the default | Real, latent, covered by no verification data |
| **U7** | satad: ICON silently caps at `maxiter`; **icon4py raises `ConvergenceError`** | Bites the first non-default configuration |
| **U8** | The multi-substep dycore test is **MCH-only**, with a literal `# why is this not run for APE?` at `test_solve_nonhydro.py:784` | Test-coverage gap |
| **U11** | `total_precipitation_flux` computed only under `do_latent_heat_nudging=True` (else exact zeros) | Exposing it as a diagnostic would mislead |
| **U12** | icon4py xfails every `solve_nonhydro`/diffusion integration test on `embedded`; the diffusion granule cannot be *constructed* there | Rules out "embedded as reference tier" for a wiring-equivalence harness |

U1 and U9 are filable today with evidence attached. U3/U4/U5 file as one issue. U6/U7/U11 are
one-liners. U8 is a test-coverage PR.

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
- ~~**`tach check` reports "Unused Dependencies" for every module.**~~ **Now verified — true.**
  Running `.venv/bin/tach check` at `4c858a6a` reports *"does not depend on"* for **every**
  module (`common`, all five atmosphere packages, `standalone_driver`, `testing`, `bindings`),
  i.e. it resolves zero first-party imports and the boundary check enforces nothing. This is the
  tach ≥0.27 multi-source-root namespace-package regression documented in
  [[personal/egparedes/layered-architecture-refactor|the layered-architecture refactor]]'s
  Phase 0. Any argument of the form "tach will stop a shared container landing in the wrong
  package" is false today.
- **Micro-benchmarks** quoted in the main doc (label filtering ~4 µs/300 fields; gt4py's
  codegen extractor ~4× faster than a dict comprehension; `gtx.as_field` copying at ~1 ms/12.8 MB)
  were measured on one laptop, not on target hardware.
- **Prior-art line numbers** for sympl, climt, NDSL/Pace, ClimaAtmos, MPAS and CCPP are
  paraphrase-grade; only ICON, LFRic, MAPL and gt4py were read from local checkouts.
- **`ndarray.setflags(write=False)` does not exist on cupy** (cited against msimberg's v2 AC14).
  **Not verifiable here** — cupy is not installed in this checkout. The v3 spec has since relaxed
  read-only enforcement to best-effort anyway, so this objection no longer decides anything; it
  still deserves a one-line check before being repeated.
- **PR review-load figures** (PR 1360 at +28110/−6228 with zero reviews; PR 1301 open since
  2026-06-04) are reported, not re-checked — they need network access to GitHub.
- **DaCe orchestration** was removed (`8f3d6c5b8`, *"outdated and unmaintained"*), so its
  constraint on container shape is **not** a present-day blocker — but the DaCe *backend* is
  live (`model_backends.py:105`) and a redesign still has to survive SDFG argument-descriptor
  generation. Earlier framings conflated the two.
