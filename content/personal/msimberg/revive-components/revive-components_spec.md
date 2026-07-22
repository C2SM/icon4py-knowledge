---
title: Revive components — spec reference
author: msimberg
tags: [components, model-state, protocol, interface, design, spec]
created: 2026-07-16
updated: 2026-07-22
status: draft
---

> **Status: v2 REFINEMENT — NOT FROZEN.** This document records a proposed
> evolution of the v1 specification. It adopts typed per-component *output*
> dataclasses, removes the shared `ComponentOutputs | None` return type, and
> introduces a `convert_state` helper. The v1 decisions that are superseded are
> listed in the appendix. The open questions at the end must be resolved before
> this spec can be frozen.

## Changelog: v1 → v2

| Topic | v1 | v2 |
|---|---|---|
| Return type | `ComponentOutputs(tendencies=dict, diagnostics=dict) \| None` | Per-component output dataclass, always returned |
| Component generic params | `Component[InputT]` | `Component[InputT, OutputT]` |
| Output access | `outputs.tendencies["tend_temperature"]` (stringly dict) | `outputs.tend_temperature` (typed member) |
| In-place branch | `None` sentinel | Output dataclass with mutated fields marked `kind="in_place"` |
| `kind` metadata location | `outputs_properties` dict | Dataclass field metadata |
| Read-only inputs | All-or-nothing per component | Per-field: input fields not present in output type are protected |
| State plumbing | Manual field packing in adapters | `convert_state([sources...], TargetState)` helper |
| Orchestrator dispatch | Structural split on `ComponentOutputs.tendencies`/`.diagnostics` | Introspection of output dataclass field metadata |

## Goal

Make the stub `Component` interface in
`model/common/src/icon4py/model/common/components/` real, general, and
long-lived. Validate the design by making `MuphysComponent`,
`SaturationAdjustment`, and `Advection` conform. Touch the physics orchestrator
only as needed for internal consistency.

## Confirmed scope (from user, unchanged)

| Axis | Decision |
|---|---|
| Conformance targets | `MuphysComponent` (primary) + `SaturationAdjustment` (second) + `Advection` (third, de-overfits toward majority in-place idiom) |
| Generality | General, physics-agnostic `Component`; physics concerns layer on top |
| Refactor boundary | `Component` interface + physics orchestrator; no bindings/ Granule migration |
| Conformance mechanism | Designer's choice — a component protocol that defines *some* shape for "a thing doing a computation" |
| Orchestrator naming | Defer to design (keep physics-specific names if the seam stays physics-specific) |

## v2 design overview

A component is still "a thing doing a computation." In v2 it has:

- a **typed input dataclass** declaring the fields it reads;
- a **typed output dataclass** declaring the fields it produces or mutates;
- a single `run(state: InputT, dtime: dt.timedelta) -> OutputT` method.

The orchestrator drives components generically by inspecting the output
dataclass fields. Field metadata carries `kind`: `"tendency"`, `"diagnostic"`, or
`"in_place"`. Tendencies are applied (when `ForcingMode.APPLY`), diagnostics are
stored, and in-place fields are trusted to have been mutated by the component.

A `convert_state` helper lets adapters and scientists build one state dataclass
from several source state objects by matching field names.

## v2 design decisions

### V2-D1. `Component` is `Protocol[InputT, OutputT]`

The protocol is generic over both the input and output dataclass types.

```python
class Component(Protocol[InputT, OutputT]):
    inputs_properties: ClassVar[dict[str, model.FieldMetaData]]
    outputs_properties: ClassVar[dict[str, model.FieldMetaData]]

    def run(self, state: InputT, dtime: dt.timedelta) -> OutputT: ...
```

This makes the input/output contract explicit at the type level and removes
the need for a shared return container.

### V2-D2. Inputs and outputs are per-component frozen dataclasses

Both sides use `@dataclasses.dataclass(frozen=True)`.

```python
@dataclasses.dataclass(frozen=True)
class MuphysInput:
    dz: fa.CellKField[ta.wpfloat] = dataclasses.field(metadata={"units": "m"})
    rho: fa.CellKField[ta.wpfloat] = dataclasses.field(metadata={"units": "kg m-3"})
    ...

@dataclasses.dataclass(frozen=True)
class MuphysOutput:
    tend_temperature: fa.CellKField[ta.wpfloat] = dataclasses.field(
        metadata={"units": "K s-1", "kind": "tendency"}
    )
    pflx: fa.CellKField[ta.wpfloat] = dataclasses.field(
        metadata={"units": "kg m-2 s-1", "kind": "diagnostic"}
    )
```

Dot notation is available on both sides: `state.rho` in, `out.pflx` out.

### V2-D3. Metadata lives on dataclass fields

`standard_name`, `units`, `long_name`, and `kind` are attached to the field
metadata. `inputs_properties` and `outputs_properties` are derived from the
dataclasses rather than hand-maintained separately.

```python
def _properties_from(dataclass_type: type) -> dict[str, model.FieldMetaData]:
    return {
        f.name: model.FieldMetaData(
            standard_name=f.metadata.get("standard_name", f.name),
            units=f.metadata["units"],
            kind=f.metadata.get("kind"),
        )
        for f in dataclasses.fields(dataclass_type)
    }


class MuphysComponent(Component[MuphysInput, MuphysOutput]):
    inputs_properties = _properties_from(MuphysInput)
    outputs_properties = _properties_from(MuphysOutput)
```

This removes the duplication between type annotations and metadata registries.

### V2-D4. Components always return an output dataclass; `None` is removed

There is no `ComponentOutputs | None`. An in-place component returns an output
dataclass whose fields are the objects it mutated.

```python
@dataclasses.dataclass(frozen=True)
class AdvectionOutput:
    diagnostic_state: advection_states.AdvectionDiagnosticState = dataclasses.field(
        metadata={"kind": "in_place"}
    )
    p_tracer_new: fa.CellKField[ta.wpfloat] = dataclasses.field(
        metadata={"kind": "in_place"}
    )


class Advection(Component[AdvectionInput, AdvectionOutput], ABC):
    def run(self, state: AdvectionInput, dtime: dt.timedelta) -> AdvectionOutput:
        # ... mutates state.diagnostic_state and state.p_tracer_new ...
        return AdvectionOutput(
            diagnostic_state=state.diagnostic_state,
            p_tracer_new=state.p_tracer_new,
        )
```

The return value now documents what changed instead of using a sentinel.

### V2-D5. Orchestrator dispatch introspects output field metadata

The driver walks the output dataclass fields and dispatches by `kind`:

```python
def split_outputs(outputs: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    tendencies: dict[str, Any] = {}
    diagnostics: dict[str, Any] = {}
    for f in dataclasses.fields(outputs):
        kind = f.metadata.get("kind")
        value = getattr(outputs, f.name)
        if kind == "tendency":
            tendencies[f.name] = value
        elif kind == "diagnostic":
            diagnostics[f.name] = value
        # "in_place" and absent kind are ignored by the orchestrator.
    return tendencies, diagnostics
```

This replaces the structural split on `ComponentOutputs.tendencies`/`.diagnostics`.

### V2-D6. `ForcingMode.DIAGNOSTIC` behavior

- For tendency-producing components: compute the output, call
  `store_diagnostics`, do **not** call `apply_tendencies`.
- For in-place components: the output contains no tendencies/diagnostics, so
  the driver makes no further calls. If the step is active, it logs a warning
  that the in-place component produced no inspectable results under DIAGNOSTIC.

### V2-D7. Read-only inputs are per-field

An input field that is **not** also present in the component's output dataclass
is set read-only before `run`. Fields that the component mutates (because they
appear in the output dataclass) remain writable.

For `MuphysComponent`, all input fields are read-only. For `Advection`,
`prep_adv` and `p_tracer_now` are read-only; `diagnostic_state` and
`p_tracer_new` remain writable.

```python
def _set_readonly_for_run(state: Any, output_type: type) -> None:
    output_names = {f.name for f in dataclasses.fields(output_type)}
    for f in dataclasses.fields(state):
        if f.name in output_names:
            continue
        value = getattr(state, f.name)
        if hasattr(value, "ndarray"):
            value.ndarray.setflags(write=False)
```

### V2-D8. `convert_state` helper for field-name-based plumbing

A generic utility fills a target dataclass from one or more source dataclasses
by matching attribute names.

```python
def convert_state(
    sources: Sequence[Any],
    target_type: type[T],
    *,
    overrides: dict[str, Any] | None = None,
) -> T: ...
```

Usage in a state adapter:

```python
class MuphysState(PhysicsState[MuphysInput]):
    def as_component_input(self) -> MuphysInput:
        return convert_state(
            [self._prognostic, self._diagnostic, self._tracer_state, self._metric_state],
            MuphysInput,
        )
```

If two sources expose the same field name, `convert_state` raises unless the
caller resolves the ambiguity with `overrides={"rho": specific_rho_field}`.

### V2-D9. Keep physics orchestrator names

`PhysicsState`, `PhysicsDriver`, `PhysicsProcess`, `ForcingMode`, and
`ProcessTimeControl` keep their names. The phy2dyn coupling inside the muphys
state adapter's `apply_tendencies` keeps the orchestrator physics-specific in
that one seam.

## Per-target conformance deltas (v2)

### MuphysComponent

- `MuphysInput` frozen dataclass (already in v1).
- New `MuphysOutput` frozen dataclass with typed tendency and diagnostic fields.
- `run(...) -> MuphysOutput`.
- `inputs_properties`/`outputs_properties` derived from field metadata.
- `MuphysState.apply_tendencies` and `MuphysState.store_diagnostics` unchanged in
  responsibility; they now receive plain dicts built by `split_outputs`.

### SaturationAdjustment

- New `SaturationAdjustmentInput` frozen dataclass (`rho`, `temperature`, `qv`,
  `qc`).
- New `SaturationAdjustmentOutput` frozen dataclass (`tend_temperature`,
  `tend_qv`, `tend_qc`), all `kind="tendency"`.
- `run(state: SaturationAdjustmentInput, dtime) -> SaturationAdjustmentOutput`.

### Advection

- New `AdvectionInput` frozen dataclass packing the current structured-state
  arguments.
- New `AdvectionOutput` frozen dataclass documenting the mutated fields
  (`diagnostic_state`, `p_tracer_new`) with `kind="in_place"`.
- `run(state: AdvectionInput, dtime) -> AdvectionOutput`.
- All subclasses update their `run` signature.
- Standalone driver and advection tests update call sites to the dataclass form.

## Open questions (must resolve before freeze)

### O1. Semantics of the in-place `kind` value

We used `kind="in_place"` for fields that the component mutates and the
orchestrator ignores. Alternatives:

- `kind="prognostic"` for fields that update prognostic state and
  `kind="diagnostic"` for fields that are diagnostics but component-managed.
- A single neutral marker such as `kind="opaque"` or `kind="component_managed"`.

The choice affects whether the orchestrator can ever reason about in-place
outputs, and how `FieldMetaData.kind` must be extended.

### O2. `convert_state` behavior for nested dataclasses and ambiguity

`AdvectionInput` contains nested dataclasses (`AdvectionDiagnosticState`,
`AdvectionPrepAdvState`). Options:

- Treat nested dataclasses as opaque: `convert_state` only matches top-level
  fields.
- Recurse into nested dataclasses and build them from flat source fields.
- Support an `aliases` map so that e.g. `tend_temperature` can satisfy a target
  field named `te`.

Also: should `convert_state` live in `model.common` now, or is it a follow-up
convenience?

### O3. Explicit vs derived `inputs_properties` / `outputs_properties`

If metadata lives on dataclass fields, the properties can be derived
automatically. But explicit class attributes may still be useful for:

- readability,
- allowing metadata that does not map cleanly to a single field,
- making the protocol contract visible without reading the dataclass.

Should the protocol require derived properties, explicit properties, or a
mixin that provides a default derivation with an override option?

### O4. Validation of in-place output fields

For `AdvectionOutput`, the returned `diagnostic_state` and `p_tracer_new` are
the same objects passed in on `AdvectionInput`. Should the framework verify
this, or trust the component? If it verifies, how — identity check, shape
consistency, or nothing?

### O5. Recycle cache for in-place outputs

The driver stores the output dataclass in the recycle cache. For in-place
components this is effectively a no-op on recycle (no tendencies/diagnostics to
reapply). Is storing the output dataclass the right design, or should the cache
store a lighter sentinel for in-place components?

## Acceptance criteria (v2)

- [ ] AC1: `Component` is a `@runtime_checkable` `Protocol[InputT, OutputT]` in
  `model/common/components/components.py` with `inputs_properties` and
  `outputs_properties`, and a single
  `run(self, state: InputT, dtime: dt.timedelta) -> OutputT` method.
- [ ] AC2: Per-component frozen input dataclasses exist for `MuphysInput`,
  `SaturationAdjustmentInput`, and `AdvectionInput`.
- [ ] AC3: Per-component frozen output dataclasses exist for `MuphysOutput`,
  `SaturationAdjustmentOutput`, and `AdvectionOutput`.
- [ ] AC4: `inputs_properties`/`outputs_properties` are derived from dataclass
  field metadata (or a supported explicit override).
- [ ] AC5: `isinstance(MuphysComponent(...), Component)` is `True`.
- [ ] AC6: `isinstance(SaturationAdjustment(...), Component)` is `True`.
- [ ] AC7: `isinstance(NoAdvection(...), Component)` is `True` (or another
  `Advection` subclass).
- [ ] AC8: `PhysicsState` is a `Protocol[InputT]` with
  `gather_from_prognostic`, `as_component_input() -> InputT`,
  `input_field_units() -> dict[str, str]`, `apply_tendencies(...)`, and
  `store_diagnostics(...)`. `scatter_to_prognostic` is removed.
- [ ] AC9: `PhysicsProcess` is `Generic[InputT, OutputT]` tying component and
  state adapter together.
- [ ] AC10: `PhysicsDriver.run` dispatches by inspecting output dataclass field
  metadata: tendencies are applied only under `ForcingMode.APPLY`, diagnostics
  are stored, in-place fields are trusted to the component.
- [ ] AC11: `ForcingMode.DIAGNOSTIC` no longer raises `NotImplementedError`.
  Tendency components store diagnostics only. In-place components are skipped
  (with a warning if active).
- [ ] AC12: At `PhysicsProcess` creation, setup-time validation checks: all
  output fields have `kind`; all input fields have `units`; input field units
  match `state.input_field_units()`. Error on mismatch.
- [ ] AC13: Per-call validation checks that all declared input fields are
  present in the state dataclass.
- [ ] AC14: Input fields that do not also appear in the component's output
  dataclass have `ndarray.setflags(write=False)` applied before `run` and
  restored after, unless the component opts out.
- [ ] AC15: `convert_state` exists and is used by the muphys and advection state
  adapters to build component input dataclasses.
- [ ] AC16: ruff, mypy (on configured paths), and tach are clean after the
  change.
- [ ] AC17: Unit tests pass for
  `model/common/tests/common/components/unit_tests/`,
  `model/atmosphere/subgrid_scale_physics/physics_interface/tests/`, and
  `model/atmosphere/subgrid_scale_physics/muphys/tests/muphys/unit_tests/`.

## Test impact (v2)

### `physics_interface/tests/.../test_physics_driver.py`

- `RecordingComponent` now has `RecordingInput` and `RecordingOutput` dataclasses.
- `RecordingPhysicsState` implements `apply_tendencies`, `store_diagnostics`,
  and `input_field_units`.
- Existing semantics tests (ordering, recycle, window, disabled,
  first-in-window) are re-expressed against the new surface.
- New tests cover `ForcingMode.DIAGNOSTIC` for both tendency and in-place
  components.
- New tests cover setup-time validation (unit mismatch, missing `kind`,
  missing `units`).
- New tests cover per-call key-presence validation.
- New tests cover per-field read-only enforcement.

### `muphys/tests/.../test_component_datatest.py`

- `granule.run(MuphysInput(...), dt)` returns `MuphysOutput`.
- The assertion accesses `out.tend_temperature` directly.

### `model/common/tests/common/components/unit_tests/`

- New conformance tests:
  - `isinstance(MuphysComponent(...), Component)`
  - `isinstance(SaturationAdjustment(...), Component)`
  - `isinstance(NoAdvection(...), Component)`
- New `convert_state` tests for ambiguity and overrides.

### Advection tests and standalone driver

- `standalone_driver.py` updates the advection call site to
  `tracer_advection.run(AdvectionInput(...), dt)`.
- `test_advection.py` and `test_parallel_advection.py` update call sites.

## Appendix: v1 decisions (superseded)

The v1 specification is preserved below as a compact reference. The full v1
text is available in the git history of this branch and in the previous version
of the knowledge-repo copy.

| v1 ID | v1 decision | Why it changed in v2 |
|---|---|---|
| D1 | Entry point is `run` | Retained (V2-D1 still uses `run`) |
| D2 | Per-component frozen dataclass input, shared `ComponentOutputs` dict return | Output is now also a per-component typed dataclass (V2-D2) |
| D3 | `inputs_properties`/`outputs_properties` are annotated Protocol attributes | Metadata moved to dataclass fields; properties derived (V2-D3) |
| D4 | `@runtime_checkable` Protocol + layered checking | Retained, but read-only is now per-field (V2-D7) |
| D5 | `ComponentOutputs` structured return | Replaced by per-component output dataclass (V2-D2/D4) |
| D6 | `PhysicsState[InputT]` gains `apply_tendencies`/`store_diagnostics` | Retained, dispatch now uses output dataclass metadata (V2-D5) |
| D7 | `ForcingMode.DIAGNOSTIC` resolution | Retained, semantics unchanged (V2-D6) |
| D8 | `SaturationAdjustment` returns `ComponentOutputs` | Now returns `SaturationAdjustmentOutput` (V2-D2/D4) |
| D9 | Keep physics orchestrator names | Retained (V2-D9) |
| D10 | Read-only numpy flag on inputs | Evolved to per-field read-only (V2-D7) |
| D11 | Setup-time unit validation | Retained, metadata source moved to dataclass fields (V2-D3/D12) |

## Log line

Coordinator: v2 refinement recorded. Direction: per-component typed input/output
frozen dataclasses, no `ComponentOutputs | None`, metadata on dataclass fields,
orchestrator dispatch by field metadata, per-field read-only inputs,
`convert_state` helper. Open questions O1–O5 listed; spec not frozen.
