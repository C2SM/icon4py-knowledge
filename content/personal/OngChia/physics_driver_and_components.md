---
title: Physics driver and component design
author: Ong Chia Rui
tags: [components, physics driver, protocol, design]
created: 2026-07-20
status: draft
---


# Physics Driver Design Document

## Introduction

An atmospheric model is a discrete mathematical representation of the physical and chemical processes in the atmosphere, including the dynamics of air motion. The physical laws governing that motion follow the Navier-Stokes equations. In practice, the atmosphere is discretized onto a mesh of grid cells, and the Navier-Stokes equations are solved numerically on that mesh. A fundamental consequence of this discretization is that physical and chemical processes with spatial scales smaller than the grid spacing cannot be explicitly resolved by the model. For instance, microphysics — which governs the growth of and interactions among hydrometeors such as cloud droplets, ice crystals, rain, snow, and graupel — operates on spatial scales of μm–cm with sub-second timescales. Similarly, radiative transfer, which involves the absorption, scattering, and refraction of electromagnetic radiation by aerosols and hydrometeors, is inherently a continuous process that cannot be captured at typical model resolutions. It is computationally infeasible for a global or regional atmospheric model to achieve such fine resolution. Therefore, we rely on physics parameterizations — a concept well recognized in the atmospheric modeling community — to represent the collective effect of these unresolved processes on the resolved-scale state. To date, the vast majority of physics parameterizations are column-based (or cell-based), meaning each grid column is treated independently without lateral communication with neighboring columns. There are usually many different ways to parameterize the same physical or chemical process, depending on the underlying assumptions and the degree of complexity used to represent the unresolved physics. Crucially, there is no guarantee that these parameterizations converge as resolution increases. What constitutes a "good" parameterization often involves subjective judgment and depends heavily on the application and target resolution.

Beyond traditional physics parameterizations, real-world simulations often require additional specialized treatments that modify the model state: user-defined large-scale forcing (e.g., prescribed temperature or moisture tendencies used in idealized column experiments), synoptic-scale nudging toward analysis data, and custom boundary condition updates. The variety of such needs calls for a flexible, extensible framework.

In icon4py, the goal is to enable users to implement and integrate their own physics parameterizations with minimal friction. We use the term **component** for any self-contained module that consumes the current model state and produces tendencies or state updates during the simulation. In a broad sense, a component is not limited to traditional physics parameterizations — it encompasses user-defined large-scale or synoptic-scale forcings, boundary condition updates, and any other specialized treatment that modifies prognostic states or tendencies at runtime. This design deliberately separates components from static inputs: initial conditions and topography are treated differently, as they do not evolve during the simulation and will be handled by a dedicated reader/converter infrastructure that transforms data into the formats icon4py expects.

The **physics driver** is the central orchestrator that manages the sequence of calls to all active components within the model time loop. Since components often require inputs beyond the five dycore prognostic variables — `vn`, `theta_v`, `exner`, `rho`, and `w` (as defined in `solve_nonhydro.py`) — the physics driver is responsible for deriving the necessary diagnostic quantities (e.g., pressure, temperature, horizontal wind components at cell centers) from the current prognostic state immediately before each component is invoked. All components are required to produce and return tendencies, which the physics driver then applies to the prognostic state. To maximize flexibility, users can choose the order in which components run within a timestep and control the call frequency of each component independently. They can also choose whether a component receives the state as it was at the start of the timestep (Jacobi-style, all components see the same base state) or the most recently updated state (Gauss-Seidel-style, each component sees modifications made by previously called components). Users can create their own components by implementing a prescribed `PhysicsComponent` Protocol, and the physics driver will automatically recognize and execute any conforming component in the simulation.

---

## Implementation Plan

### Overview

The implementation is organized into six phases: (1) using the existing `Component` Protocol and defining `ComponentCallConfig` in `model/common`; (2) defining a unified model state dictionary and the responsibility boundary for diagnostic derivation; (3) implementing consistency checks; (4) implementing the `PhysicsDriver` orchestrator in `model/driver`; (5) integrating the physics driver into the existing `TimeLoop`; and (6) providing reader/converter infrastructure for static inputs. No new top-level packages are required — all new code is placed within the existing package boundaries enforced by `tach.toml`.

---

### Phase 1: Component Interface and Call Configuration

#### 1.1 Reuse the existing `Component` Protocol

**File:** `model/common/src/icon4py/model/common/components/components.py` (already exists)

Physics components do **not** require a new protocol. The existing `Component[Ins, Outs]` Protocol defined in `components.py` is sufficient. Any class that implements `inputs_properties`, `outputs_properties`, and `__call__` is automatically a valid physics component — no inheritance is required. Concretely:

```python
# Existing protocol — physics components implement this directly.
class Component(Protocol[Ins, Outs]):
    @property
    def inputs_properties(self) -> dict[Ins, model.FieldMetaData]: ...

    @property
    def outputs_properties(self) -> dict[Outs, model.FieldMetaData]: ...

    def __call__(
        self, state: dict[Ins, model.DataField], time_step: datetime.datetime
    ) -> dict[Outs, model.DataField]: ...
```

A physics component declares:
- `inputs_properties`: every field it needs, keyed by CF standard name (e.g. `"air_density"`, `"air_temperature"`), with the expected units and dimensions in the associated `FieldMetaData`.
- `outputs_properties`: every tendency or updated field it returns, keyed by CF standard name (e.g. `"tendency_of_air_temperature_due_to_saturation_adjustment"`).
- `__call__`: takes the assembled `state` dict and the current simulation time; returns the output dict.

The `time_step` argument (a `datetime.datetime`) replaces the plain `float dtime` used in the existing diffusion and dycore granules, giving components access to the full simulation timestamp.

#### 1.2 Input derivation responsibility is inside the component

Each component is responsible for determining whether its required inputs are directly available in the passed `state` dict or must be derived from other fields that are present. This logic lives inside `__call__`, **not** in the driver. For example, a microphysics component that needs `"air_temperature"` can compute it internally from `"air_virtual_potential_temperature"` (`theta_v`) and `"dimensionless_exner_function"` (`exner`) if `"air_temperature"` itself is absent, provided those base fields are declared in `inputs_properties`. This makes each component self-contained and testable in isolation.

However, a subtler problem arises in Gauss-Seidel execution: a derived field (e.g., `"air_temperature"`) may already be present in the state dict but be **stale** — it was derived at the start of the timestep from the original prognostic values, but a preceding component has since modified those prognostic values. Naively reusing the stale derived field would silently propagate an inconsistency.

To address this, the `StateProvider` (Phase 2) tracks **field freshness**: every field written into the state via `StateProvider.update()` is marked as *fresh*, while all fields that come from the base prognostic/diagnostic state at the start of the timestep are considered *base* (potentially stale with respect to fields updated by other components). The driver passes a `StateView` to each component — a dict-like wrapper that exposes an `is_fresh(key: str) -> bool` query alongside the regular field values.

```python
class StateView(Mapping[str, model.DataField]):
    """Read-only view of the model state, with per-field freshness metadata."""

    def is_fresh(self, key: str) -> bool:
        """Return True if the field has been written by a component in this timestep.

        A field is fresh if it was produced by a preceding component's __call__
        and written back via StateProvider.update().
        A field is stale (not fresh) if it comes from the base prognostic/diagnostic
        state at the start of the timestep and has not been updated since.
        """
        ...
```

A component's `_derive_inputs` uses `is_fresh` to decide whether to reuse a cached derived field or recompute it:

```python
def _derive_inputs(self, state: StateView) -> dict[str, model.DataField]:
    """Derive any secondary input fields that are absent or stale in state."""
    derived = {}
    if "air_temperature" not in state or not state.is_fresh("air_temperature"):
        # Re-derive from the current (possibly updated) base prognostics.
        derived["air_temperature"] = _compute_temperature(
            state["air_virtual_potential_temperature"],
            state["dimensionless_exner_function"],
        )
    return derived
```

called at the top of `__call__` before the main computation. The component merges `derived` with `state` to form its effective working state.

**Freshness rules:**
- At the start of each physics timestep, `StateProvider` resets all freshness flags: every field sourced from `PrognosticState` or `DiagnosticState` is *not fresh*.
- Each call to `StateProvider.update(output)` marks every key in `output` as *fresh*.
- When a base prognostic field (e.g., `"air_virtual_potential_temperature"`) is updated by a component, any derived field (e.g., `"air_temperature"`) that was computed from the old value is **not** automatically marked stale — the component that computed that derived field is responsible for re-deriving it if needed, guided by checking `is_fresh` on the base fields it depends on.
- For Jacobi-style components (`use_updated_state=False`), the driver passes a snapshot `StateView` with no fresh fields; the component always derives from the base state.

The driver's only obligation regarding inputs is to populate `StateProvider` with all directly available fields (prognostic variables + any already-computed diagnostics) and to run consistency checks (Phase 3) on the `StateView` before passing it to the component.

#### 1.3 `ComponentCallConfig`

**File:** `model/common/src/icon4py/model/common/components/components.py` (extend)

```python
@dataclasses.dataclass(frozen=True)
class ComponentCallConfig:
    """Per-component runtime call configuration."""
    #: Call this component every `call_every_n_steps` physics timesteps (default: every step).
    call_every_n_steps: int = 1
    #: If True, this component receives the state already modified by previously
    #: called components in the same timestep (Gauss-Seidel style).
    #: If False, it receives the state at the start of the timestep (Jacobi style).
    use_updated_state: bool = True
```

---

### Phase 2: Unified Model State Dictionary (`StateProvider`)

**File:** `model/common/src/icon4py/model/common/components/state_provider.py` (new)

The driver communicates with components through a `StateView` — a read-only, dict-like object keyed by CF standard names that also carries per-field freshness metadata (see Section 1.2). A `StateProvider` class wraps the current `PrognosticState`, `DiagnosticState`, and tracer fields, maintains the freshness registry, and vends `StateView` objects to the driver.

```python
class StateProvider:
    """Assembles the current model state and tracks field freshness."""

    def __init__(
        self,
        prognostic_state: PrognosticState,
        diagnostic_state: DiagnosticState,
    ) -> None:
        # _fresh_keys: set of CF-standard-name keys written by components this timestep.
        # Initially empty — every field from the base state is considered not fresh.
        self._fresh_keys: set[str] = set()
        ...

    def reset_freshness(self) -> None:
        """Clear freshness flags at the start of each physics timestep."""
        self._fresh_keys.clear()

    def as_view(self) -> StateView:
        """Return a read-only StateView of the current state with freshness metadata.

        The returned StateView is a snapshot: it captures the current field references
        and a frozen copy of the freshness flags at the time of the call.
        Components should not store the view beyond their __call__ invocation.
        """
        ...

    def snapshot(self) -> StateView:
        """Return a frozen StateView of the base state (no fresh fields).

        Used for Jacobi-style components that must see the state at the start
        of the timestep, unaffected by updates made by preceding components.
        """
        ...

    def update(self, output: dict[str, model.DataField]) -> None:
        """Write component outputs back into the underlying state objects (in-place)
        and mark all written keys as fresh."""
        self._fresh_keys.update(output.keys())
        ...
```

The `StateView` class (defined in the same file) is a `Mapping[str, model.DataField]` with one additional method:

```python
class StateView(Mapping[str, model.DataField]):
    def is_fresh(self, key: str) -> bool:
        """Return True if the field was written by a component in this timestep."""
        ...
```

After a component's `__call__` returns, the driver calls `StateProvider.update(output)` to apply the returned fields back into `PrognosticState` / `DiagnosticState` in-place and register the written keys as fresh.

The key consequence of this design is that **the driver never proactively derives diagnostic variables before calling a component**. A component that needs `"air_temperature"` when it is not yet computed (or stale) must either (a) declare the necessary base fields in `inputs_properties` and derive the derived field internally via `_derive_inputs`, or (b) be preceded by a lightweight diagnostic component that computes `"air_temperature"` and writes it into the state via `StateProvider.update`, marking it fresh. This gives users full control over the order and cost of diagnostic computations.

---

### Phase 3: Consistency Checks

**File:** `model/common/src/icon4py/model/common/components/components.py` (extend with free functions)

Before the driver calls `component.__call__(state_view, time_step)`, it invokes a set of validation functions on the `StateView`. These are also useful as standalone utilities for component authors writing unit tests.

#### 3.1 Input completeness check

```python
class IncompleteStateError(Exception):
    """Raised when a component's required input fields are missing from the state."""

def check_input_completeness(
    component: Component,
    state: StateView,
) -> None:
    """Raise IncompleteStateError if any key in inputs_properties is absent from state."""
    missing = [key for key in component.inputs_properties if key not in state]
    if missing:
        raise IncompleteStateError(
            f"Component '{component.__class__.__name__}' is missing required input fields: {missing}."
        )
```

#### 3.2 Unit consistency check

```python
class UnitMismatchError(Exception):
    """Raised when a field's units do not match the component's declared expectation."""

def check_input_units(
    component: Component,
    state: StateView,
) -> None:
    """Raise UnitMismatchError if any input field carries units that differ from inputs_properties."""
    for key, meta in component.inputs_properties.items():
        if key not in state:
            continue  # completeness is checked separately
        actual_units = state[key].attrs.get("units")
        expected_units = meta["units"]
        if actual_units != expected_units:
            raise UnitMismatchError(
                f"Component '{component.__class__.__name__}': field '{key}' has units "
                f"'{actual_units}' but '{expected_units}' was expected."
            )
```

#### 3.3 Dimension consistency check

```python
class DimensionMismatchError(Exception):
    """Raised when a field's dimensions do not match the component's declared expectation."""

def check_input_dimensions(
    component: Component,
    state: StateView,
) -> None:
    """Raise DimensionMismatchError if any input field has unexpected GT4Py dimensions."""
    for key, meta in component.inputs_properties.items():
        expected_dims = meta.get("dims")
        if expected_dims is None or key not in state:
            continue
        field = state[key].data
        if hasattr(field, "domain"):  # GT4Py field
            actual_dims = tuple(ax.value for ax in field.domain.dims)
            expected_dim_names = tuple(d.value for d in expected_dims)
            if actual_dims != expected_dim_names:
                raise DimensionMismatchError(
                    f"Component '{component.__class__.__name__}': field '{key}' has "
                    f"dimensions {actual_dims} but {expected_dim_names} was expected."
                )
```

#### 3.4 Output completeness check

```python
def check_output_completeness(
    component: Component,
    output: dict[str, model.DataField],  # plain dict — freshness is set by the driver after this check
) -> None:
    """Raise IncompleteStateError if any key declared in outputs_properties is absent from output."""
    missing = [key for key in component.outputs_properties if key not in output]
    if missing:
        raise IncompleteStateError(
            f"Component '{component.__class__.__name__}' did not return declared output fields: {missing}."
        )
```

#### 3.5 Aggregated check helper

```python
def check_component_inputs(
    component: Component,
    state: StateView,
) -> None:
    """Run all pre-call consistency checks (completeness, units, dimensions)."""
    check_input_completeness(component, state)
    check_input_units(component, state)
    check_input_dimensions(component, state)
```

This is the single entry point called by the driver before every `__call__`. In production, dimension checks can be disabled via a runtime flag (similar to how GT4Py disables bounds checking) to avoid overhead in long runs.

---

### Phase 4: `PhysicsDriver` in `model/driver`

**File:** `model/driver/src/icon4py/model/driver/physics_driver.py`

The `PhysicsDriver` orchestrates the sequence of component calls for one physics timestep. It is constructed once before the time loop starts and reused at each timestep.

```python
@dataclasses.dataclass
class RegisteredComponent:
    component: Component        # any Component[Ins, Outs] — no special base class needed
    config: ComponentCallConfig

class PhysicsDriver:
    def __init__(
        self,
        components: list[RegisteredComponent],
        grid: IconGrid,
        vertical_grid: VerticalGrid,
        allocator: gtx_typing.Allocator,
    ) -> None: ...

    def run(
        self,
        prognostic_state: PrognosticState,
        diagnostic_state: DiagnosticState,
        solve_nonhydro_diagnostic_state: DiagnosticStateNonHydro,
        simulation_time: datetime.datetime,
        timestep_nr: int,
    ) -> None: ...
```

The `run` method implements the following logic:

1. **Wrap state in `StateProvider`**: construct a `StateProvider` from the current `prognostic_state` and `diagnostic_state`. Optionally snapshot the initial state dict for Jacobi-style components.
2. **Loop over registered components** in order:
   a. **Call frequency**: skip if `timestep_nr % config.call_every_n_steps != 0`.
   b. **Assemble input state**: call `state_provider.as_view()` to obtain a `StateView`. If `use_updated_state=False` (Jacobi), use the base snapshot `StateView` (no fresh fields) taken in step 1 instead.
   c. **Consistency checks**: call `check_component_inputs(component, state_view)` — raises on any completeness, unit, or dimension violation.
   d. **Invoke component**: call `component(state_view, simulation_time)` → `output: dict[Outs, model.DataField]`.
   e. **Output check**: call `check_output_completeness(component, output)`.
   f. **Apply outputs**: call `state_provider.update(output)` to write returned fields (tendencies or updated prognostic/diagnostic fields) back into the underlying state objects in-place.
3. **Accumulate into dycore-facing tendency fields**: after all components have run, sum the tendency contributions keyed as `"tendency_of_dimensionless_exner_function_due_to_slow_physics"` and `"tendency_of_normal_wind_due_to_slow_physics"` into `solve_nonhydro_diagnostic_state.exner_tendency_due_to_slow_physics` and `solve_nonhydro_diagnostic_state.normal_wind_tendency_due_to_slow_physics_process`, which the dycore reads at the next substep.

**Tendency accumulation helper:**

```python
def accumulate_slow_physics_tendencies(
    output_fields: list[dict[str, model.DataField]],
    solve_nonhydro_diagnostic_state: DiagnosticStateNonHydro,
) -> None:
    """Sum per-component tendency contributions into the dycore-facing fields."""
    ...
```

This function iterates over all component outputs collected during the loop and adds their exner and vn tendency fields to the existing `DiagnosticStateNonHydro` slots using GT4Py field operators (supporting the `roundtrip` and `gtfn_cpu` backends).

---

### Phase 5: Integration with `TimeLoop`

**File:** `model/driver/src/icon4py/model/driver/icon4py_driver.py`

The `TimeLoop` is extended to accept an optional `PhysicsDriver`. The physics driver is called once per full physics timestep (after the dycore substepping loop and diffusion), immediately before `prognostic_states.swap()`. This mirrors the call order used in the ICON Fortran code, where slow-physics tendencies are applied after the dynamical core.

Changes to `TimeLoop.__init__`:
```python
def __init__(
    self,
    run_config: driver_config.Icon4pyRunConfig,
    diffusion_granule: diffusion.Diffusion,
    solve_nonhydro_granule: solve_nh.SolveNonhydro,
    physics_driver: PhysicsDriver | None = None,   # NEW
):
    ...
    self.physics_driver = physics_driver
```

Changes to `_integrate_one_time_step`:
```python
def _integrate_one_time_step(self, *, ..., simulation_time: datetime.datetime, timestep_nr: int):
    self._do_dyn_substepping(...)

    if self.diffusion.config.apply_to_horizontal_wind:
        self.diffusion.run(...)

    if self.physics_driver is not None:           # NEW
        self.physics_driver.run(
            prognostic_state=prognostic_states.next,
            diagnostic_state=diagnostic_state,
            solve_nonhydro_diagnostic_state=solve_nonhydro_diagnostic_state,
            simulation_time=simulation_time,
            timestep_nr=timestep_nr,
        )

    prognostic_states.swap()
```

`simulation_time` and `timestep_nr` are threaded from `time_integration` through `_integrate_one_time_step`. `simulation_time` is the `datetime.datetime` already tracked as `self._simulation_date` in `TimeLoop`, so no new state is needed.

---

### Phase 6: Static Input Infrastructure (Initial Conditions and Topography)

**File:** `model/common/src/icon4py/model/common/io/field_reader.py` (new)

Initial conditions and topography are static during a simulation and are conceptually distinct from components. A lightweight `FieldReader` Protocol abstracts over different file formats (NetCDF, GRIB2, Serialbox):

```python
class FieldReader(Protocol):
    def read(self, var_name: str) -> xr.DataArray: ...
    def close(self) -> None: ...
```

A converter utility will transform the returned `xr.DataArray` objects into GT4Py fields on the appropriate grid dimensions, reusing the `data_allocation` helpers in `model/common`. This infrastructure is intentionally minimal at this stage (following the YAGNI principle) and can be extended when concrete file format support is required.

---

### Phase 7: Testing Strategy

All new code must be covered by tests following the existing convention in `model/testing`.

#### 7.1 Unit tests for `Component` protocol and consistency checks (`unit_tests/`)

- Verify that a plain Python class implementing `inputs_properties`, `outputs_properties`, and `__call__` satisfies the `Component` Protocol at type-check time (mypy) and at runtime.
- Verify `check_input_completeness` raises `IncompleteStateError` with the correct message when a required key is absent.
- Verify `check_input_units` raises `UnitMismatchError` when units differ; passes when units match.
- Verify `check_input_dimensions` raises `DimensionMismatchError` when GT4Py field dimensions differ from declared `dims` in `FieldMetaData`; skips the check when `dims` is not declared.
- Verify `check_output_completeness` raises `IncompleteStateError` when a declared output key is missing from the returned dict.
- Verify `ComponentCallConfig` call-frequency logic: a component with `call_every_n_steps=3` is skipped for `timestep_nr` 0, 1, 2, called at 3, skipped at 4, 5, called at 6, etc.

#### 7.2 Unit tests for `StateProvider` and `StateView` (`unit_tests/`)

- Construct a `StateProvider` from known `PrognosticState` and `DiagnosticState` instances; verify `as_view()` contains the correct CF-standard-name keys.
- Verify that all fields from the base state report `is_fresh(key) == False` immediately after construction and after `reset_freshness()`.
- Call `update()` with a mock output dict; verify the underlying state objects are updated in-place and that every written key now reports `is_fresh(key) == True` in a subsequent `as_view()`.
- Verify that a key not written by any component still reports `is_fresh(key) == False` after `update()`.
- Verify that `snapshot()` returns a `StateView` with no fresh fields regardless of prior `update()` calls, and that subsequent `update()` calls do not retroactively mark snapshot fields as fresh.
- Verify that the `StateView` returned by `as_view()` is read-only (attempting to assign raises `TypeError` or is not possible).

#### 7.3 Unit tests for `PhysicsDriver` (`unit_tests/`)

Use a mock component (a simple class returning a fixed output dict with known values) and an idealized grid (from `model/testing` fixtures) to verify:
- Components are called in the registered order.
- `use_updated_state=False` components see the base-state fields (snapshot), not fields modified by earlier components.
- `use_updated_state=True` components see the already-updated fields.
- `check_component_inputs` is called before each component; an `IncompleteStateError` propagates to the caller.
- Accumulated exner and vn tendencies are correctly written into `DiagnosticStateNonHydro`.

#### 7.4 Unit tests for component input derivation (`unit_tests/`)

For any component that derives secondary fields inside `__call__` (e.g., computing `temperature` from `exner` and `theta_v`):
- Pass a state dict that omits the derived field but contains the base fields; verify the component produces the correct output.
- Pass a state dict that already contains the derived field; verify the component uses it directly without recomputing.

#### 7.5 Integration test with `TimeLoop` (`integration_tests/`)

Using the existing Jablonowski-Williamson (JW) test case infrastructure (via the fixtures in `model/testing`), register a no-op component (returns an output dict with zero tendency fields) and verify that the `TimeLoop` produces identical results to the baseline without a physics driver. This guards against inadvertent state corruption introduced by the driver infrastructure.

#### 7.6 Stencil test for `accumulate_slow_physics_tendencies` (`stencil_tests/`)

Verify the GT4Py field addition stencil used in `accumulate_slow_physics_tendencies` against a numpy reference implementation for all supported backends (`roundtrip`, `gtfn_cpu`).

---

### Summary of New and Modified Files

| File | Package | Action | Purpose |
|---|---|---|---|
| `model/common/.../components/components.py` | `model/common` | Extend | Add `ComponentCallConfig`, `IncompleteStateError`, `UnitMismatchError`, `DimensionMismatchError`, consistency check functions |
| `model/common/.../components/state_provider.py` | `model/common` | New | `StateProvider`: assembles flat CF-keyed state dict from prognostic/diagnostic state |
| `model/common/.../io/field_reader.py` | `model/common` | New | `FieldReader` Protocol for static inputs |
| `model/driver/.../physics_driver.py` | `model/driver` | New | `PhysicsDriver`, `RegisteredComponent`, `accumulate_slow_physics_tendencies` |
| `model/driver/.../icon4py_driver.py` | `model/driver` | Extend | Add optional `physics_driver` to `TimeLoop` |
| `model/driver/tests/.../unit_tests/test_physics_driver.py` | `model/driver` | New | Unit tests for `PhysicsDriver` |
| `model/driver/tests/.../unit_tests/test_state_provider.py` | `model/driver` | New | Unit tests for `StateProvider` |
| `model/driver/tests/.../integration_tests/test_physics_timeloop.py` | `model/driver` | New | Integration test with `TimeLoop` |
| `model/common/tests/.../unit_tests/test_component_checks.py` | `model/common` | New | Unit tests for consistency check functions |