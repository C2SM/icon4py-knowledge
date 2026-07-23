---
title: Specialize GT4Py programs with runtime-varying domain bounds via the variants parameter
author: iomaganaris
tags: [advection, setup_program, gt4py, performance, specialization]
created: 2026-07-23
status: draft
---

> **TL;DR** Several GT4Py programs in the advection package are configured via `setup_program` without `horizontal_start`/`horizontal_end`/`vertical_start`/`vertical_end` because those bounds change at runtime (even vs. odd timestep); using the existing `variants` parameter would let us specialize them at compile time instead of leaving the bounds dynamic.

## Problem / motivation

`setup_program` (in `model/common/src/icon4py/model/common/model_options.py:118`) specializes programs at compile time by passing `horizontal_sizes` and `vertical_sizes` to `gtx.Program.compile(...)`. Values supplied there become static and enable constant folding, loop bound specialization, and other optimizations in the generated code. Values that are **not** supplied remain ordinary runtime parameters, so the generated code must handle arbitrary loop bounds and forgoes those optimizations.

A survey of all `setup_program` calls in the advection, dycore, and diffusion packages shows that **14 advection programs** are currently configured with one or more domain bounds missing, solely because the bounds take a small number of distinct values at runtime (typically two, keyed on `even_timestep`). The `variants` parameter — which exists precisely to compile one program per combination of runtime values — is **never used** in the advection package. This means the generated code is less specialized than it could be for programs that run on every timestep.

### Programs affected

**Group A — missing `horizontal_start` only (1 program)**

| Program | Call site |
|---------|-----------|
| `apply_density_increment` | `advection/advection.py:260` |

`horizontal_end` and both vertical bounds are specialized; `horizontal_start` is not, because it is `self._start_cell_lateral_boundary_level_2` on even steps and `self._start_cell_lateral_boundary_level_3` on odd steps (`advection.py:328-332`).

**Group B — missing both horizontal bounds, vertical bounds specialized (13 programs)**

| Program | Call site |
|---------|-----------|
| `copy_cell_kdim_field` | `advection/advection_vertical.py:200, 433, 821` |
| `copy_cell_kdim_field_koff_minus1` | `advection/advection_vertical.py:831` |
| `limit_vertical_slope_semi_monotonically` | `advection/advection_vertical.py:281` |
| `compute_vertical_parabola_limiter_condition` | `advection/advection_vertical.py:294` |
| `limit_vertical_parabola_semi_monotonically` | `advection/advection_vertical.py:303` |
| `integrate_tracer_vertically` | `advection/advection_vertical.py:600, 876` |
| `init_constant_cell_kdim_field` | `advection/advection_vertical.py:760` |
| `compute_ppm4gpu_courant_number` | `advection/advection_vertical.py:773` |
| `compute_ppm_slope` | `advection/advection_vertical.py:788` |
| `compute_ppm_quartic_face_values` | `advection/advection_vertical.py:809` |
| `compute_ppm4gpu_parabola_coefficients` | `advection/advection_vertical.py:841` |
| `compute_ppm4gpu_fractional_flux` | `advection/advection_vertical.py:850` |
| `compute_ppm4gpu_integer_flux` | `advection/advection_vertical.py:863` |

Both horizontal bounds vary with `even_timestep` via `_get_horizontal_start_end` (`advection_vertical.py:445, 619, 895`).

**Group C — missing all four domain bounds (1 program)**

| Program | Call site |
|---------|-----------|
| `compute_ppm_quadratic_face_values` | `advection/advection_vertical.py:801` |

The horizontal bounds vary with `even_timestep`, and the vertical bounds change between consecutive calls (`advection_vertical.py:964-983`: one call with `vertical_start=1, vertical_end=2`, another with `vertical_start=num_levels-1, vertical_end=num_levels`).

### Programs not configured via `setup_program` (out of scope here)

The remaining 32 programs from the original list (e.g. `compute_arc_distance_of_far_edges_in_diamond`, `compute_coriolis_parameter_on_edges`, `compute_ddqz_z_half`, `cell_2_edge_interpolation`, `compute_weighted_cell_neighbor_sum`, etc.) live in `model/common` and are invoked through `factory.ProgramFieldProvider` (`model/common/src/icon4py/model/common/states/factory.py:492`) or directly via `.with_backend(backend)(...)`. Their domain bounds are computed at call time from grid zones by `ProgramFieldProvider._domain_args` (`factory.py:576-598`). Since these are typically one-time initialization computations, specialization is less performance-critical and is not addressed by this proposal.

## Proposal

Use the existing `variants` parameter of `setup_program` to specialize programs whose domain bounds take a small, known set of runtime values.

### Group A (1 program)

`horizontal_start` has two values. Pass it via `variants`:

```python
self._apply_density_increment = setup_program(
    backend=self._backend,
    program=apply_density_increment,
    constant_args={
        "deepatmo_divzl": self._metric_state.deepatmo_divzl,
        "deepatmo_divzu": self._metric_state.deepatmo_divzu,
    },
    horizontal_sizes={
        "horizontal_end": self._end_cell_end,
    },
    variants={
        "horizontal_start": [
            self._start_cell_lateral_boundary_level_2,  # even timestep
            self._start_cell_lateral_boundary_level_3,  # odd timestep
        ],
    },
    vertical_sizes={
        "vertical_start": gtx.int32(0),
        "vertical_end": gtx.int32(self._grid.num_levels),
    },
    offset_provider=self._grid.connectivities,
)
```

This compiles two specialized versions. At call time, GT4Py selects the correct one based on the `horizontal_start` value passed.

### Group B (13 programs)

Both `horizontal_start` and `horizontal_end` have two values each (even/odd). Pass both via `variants`:

```python
self._copy_cell_kdim_field = model_options.setup_program(
    backend=backend,
    program=copy_cell_kdim_field,
    variants={
        "horizontal_start": [
            self._start_cell_lateral_boundary_level_2,  # even
            self._start_cell_nudging,                   # odd
        ],
        "horizontal_end": [
            self._end_cell_end,    # even
            self._end_cell_local,  # odd
        ],
    },
    vertical_sizes={
        "vertical_start": gtx.int32(0),
        "vertical_end": gtx.int32(self._grid.num_levels),
    },
    offset_provider=self._grid.connectivities,
)
```

This compiles 2 × 2 = 4 specialized versions per program. The same pattern applies to all 13 programs in this group.

### Group C (1 program)

`compute_ppm_quadratic_face_values` has two horizontal pairs and two vertical pairs, requiring 4 × 4 = 16 compiled combinations. This is likely impractical and may be left as-is, or handled by splitting into two separate `setup_program` instances (one per vertical pair), reducing the count to 4 × 1 = 4 per instance.

## Alternatives considered

1. **Keep the current approach (no `variants`).** The bounds remain dynamic runtime parameters. This is the status quo and avoids any compile-time or binary-size increase, but forgoes specialization for hot-loop stencils.

2. **Convert the 32 common-package programs to use `setup_program`.** The `ProgramFieldProvider._domain_args` method already computes the bounds from grid zones. Passing them to `setup_program` instead would specialize them, but these are typically one-time initialization computations, so the payoff is small. Deferred.

3. **Restructure the even/odd timestep logic.** Instead of two runtime values, always use the wider (even) domain and mask the interior. This would remove the `variants` need entirely but changes the numerics and requires more extensive validation.

## Open questions / conflicts

- **Compile time and binary size.** Group B alone adds 13 × 4 = 52 specialized program variants. Combined with existing variants (e.g. `is_iau_active`, `skip_compute_predictor_vertical_advection`), some programs could accumulate many combinations. How does `GT4PY_BUILD_JOBS` interact with this, and what is the binary-size impact on GPU builds?
- **Group C practicality.** Is 16 combinations for `compute_ppm_quadratic_face_values` acceptable, or should it be split into two `setup_program` instances (4 combinations each)?
- **Interaction with dace optimization hooks.** `get_dace_options` in `model_options.py` already enables `scan_loop_unrolling` for vertically implicit solvers. Does specializing the horizontal bounds interact with these passes?
- **Validation.** No existing tests cover the `variants` path for domain bounds (the only `variants` usage is in dycore for boolean flags). A stencil test or datatest should verify that the specialized variants produce identical results to the current dynamic-bounds code.

## Appendices

### How `setup_program` handles `variants` vs `horizontal_sizes`/`vertical_sizes`

From `model/common/src/icon4py/model/common/model_options.py:118`:

- `horizontal_sizes` and `vertical_sizes` are passed to `.compile()` as single values (via `dict_values_to_list`), becoming static at compile time.
- `variants` is passed to `.compile()` as lists of values. GT4Py generates one compiled binary per combination and selects the correct one at call time based on the runtime argument value.
- `constant_args` are bound via `functools.partial` after compilation; scalar values in `constant_args` are also inlined at compile time.

### How `ProgramFieldProvider` handles domain bounds (common package)

From `model/common/src/icon4py/model/common/states/factory.py:576-638`:

- `_domain_args` iterates over the provider's `compute_domain` (a dict of `Dimension -> (start_zone, end_zone)`).
- For horizontal dimensions, it emits `horizontal_start`/`horizontal_end` from `grid.start_index(zone)` / `grid.end_index(zone)`.
- For vertical dimensions, it emits `vertical_start`/`vertical_end` from `vertical_grid.index(zone)`.
- These are passed at call time to `func.with_backend(backend)(**deps, offset_provider=...)`, not specialized at compile time.
