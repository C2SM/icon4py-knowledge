---
title: Revive components — spec reference
author: msimberg
tags: [components, model-state, protocol, interface, design, spec]
created: 2026-07-16
status: draft
---

> **Status: unreviewed reference material.** This document is a verbatim copy of
> This is a frozen specification produced during one exploration of a concrete
> `Component` interface in the main icon4py repository. It has **not had major
> human input or review yet**. Treat it as a starting point for discussion, not
> as an agreed plan. Additional directions, critiques, and alternatives are
> strongly encouraged.

# SPEC: Component interface (FROZEN)
> Status: **FROZEN.** After deep 4-axis brainstorm (state representation,
> checkability, units, mutability), the user suspended minimal-change
> constraints and chose amendments: per-component frozen dataclass state
> (D2), ComponentOutputs structured return (D5), read-only numpy flag (D10),
> setup-time unit validation (D11). Three independent spec-review rounds; all
> blocking findings fixed. Spec is the verifier's ground truth.
> read-only numpy flag (D10), setup-time unit validation (D11). Awaiting
> user confirmation to freeze.

## Goal

One-line summary: make the stub `Component` interface real, general, and
long-lived; validated by making `MuphysComponent` and `SaturationAdjustment`
conform; touching the physics orchestrator only as needed for internal
consistency.

## Confirmed scope (from user)

| Axis | Decision |
|---|---|
| Conformance targets | MuphysComponent (primary) + SaturationAdjustment (second) + **Advection (third, de-overfits toward majority in-place idiom)** |
| Generality | General, physics-agnostic Component; physics concerns layer on top |
| Refactor boundary | Component interface + physics orchestrator; no bindings/ Granule migration |
| Conformance mechanism | **Designer's choice.** "The only thing that matters is a component protocol that defines _some_ shape for what a component (a thing doing a computation) should do. Anything else is up to you to design." |
| Orchestrator naming | **Defer to design** (rename if the orchestrator genuinely generalizes, keep if physics-specific) |

## The central design challenge (refined)

The Component protocol must accommodate **both** idioms validated by the three
targets:

- **Pattern A — return tendencies/diagnostics** (`MuphysComponent`): dict in,
  dict out, `datetime.datetime`. Two of the microphysics outputs are
  diagnostics (never applied); seven are tendencies.
- **Pattern B — in-place mutation, `None` return** (`Advection` ABC,
  `Diffusion.run`, `SolveNonhydro.time_step`, `SaturationAdjustment.run`,
  `SingleMomentSixClassGraupel.run`): structured state objects, named kwargs,
  scalar `dtime`. This is the **majority idiom** (5 of 6 real components).

A component is "a thing doing a computation." The protocol must give that one
shape that serves both, *plus* the orchestrator consequences: today
`scatter_to_prognostic` couples apply-tendencies with store-diagnostics, which
is why `ForcingMode.DIAGNOSTIC` raises `NotImplementedError`. Making
`SaturationAdjustment` conform is especially informative because it produces
tendencies *via in-place writes* — straddling both patterns.

## Open design questions (to be resolved in Phase 3 Design)

These are the load-bearing decisions. Each will be evaluated with 2-3
alternatives and a stated rationale.

### Q1. Return shape — one dict, or typed outputs?
Current: `__call__` returns `dict[str, DataField]` mixing tendencies
(`tend_temperature`) and diagnostics (`pflx`, `pr`, ...). The ADR hints at
keeping tendencies from different components for the same field identifiable.
Options include: flat dict + metadata `kind`; a typed `ComponentOutputs` with
separate tendency/diagnostic collections; per-field named tuples.

### Q2. Input selection — whole-state dict, or named arguments?
Current: `__call__(state: dict[Ins, DataField], time_step)`. The protocol
docstring has a TODO "is it possible to improve this interface not having to
pass on the entire state". `SaturationAdjustment` instead uses explicit named
args (`rho=`, `temperature=`, ...). These two patterns must be reconciled.

### Q3. Metadata naming — `inputs_properties` vs `input_properties`?
The protocol uses `inputs_properties`/`outputs_properties` (plural).
`SaturationAdjustment` uses `input_properties`/`output_properties` (singular,
`raise NotImplementedError`). One must win; rationale recorded.

### Q4. What does the interface enforce, and how?
Current protocol declares abstract props and a documented `__call__` but
references a nonexistent `IncompleteStateError` and has TODOs on unit/dim
checks. Decide: protocol-only (structural), runtime validation helpers
(mixins/base), static checks, or a combination. (ADR 0002's `Annotated`
config pattern is a relevant prior art for declarative metadata.)

### Q5. Does the component return tendencies, mutate state, or both?
**This is the core open question now that the ADR is non-authoritative.**
ADR 0001 proposes "return tendencies only; never mutate; state updated
separately". Alternatives: direct mutation (ICON's fast-physics style), or a
hybrid. The decision interacts with the orchestrator's current
`scatter_to_prognostic` coupling and the `ForcingMode.DIAGNOSTIC`
`NotImplementedError`. Evaluation must weigh: scientific transparency,
ergonomics for the two real cases, and long-term generality (dycore/advection
may not fit a tendency-only model).

### Q6. Output categories (tendency vs diagnostic vs prognostic)
The `FieldMetaData.kind` field already exists (`"tendency"`/`"diagnostic"`).
Is that sufficient, or does the interface need explicit per-category access?
The protocol docstring has a TODO asking whether outputs should be split into
tendencies/diagnostics/prognostics.

### Q7. Where does the orchestrator's apply/store split live?
Current `PhysicsState.scatter_to_prognostic` both applies tendencies and
stores diagnostics, which is why `ForcingMode.DIAGNOSTIC` raises
`NotImplementedError`. If Q5 keeps a separate update step, the
apply-tendencies vs store-diagnostics split needs a home (on `PhysicsState`,
on the driver, on the component).

## Findings so far (pre-exploration)

### Current `Component` protocol — `model/common/src/icon4py/model/common/components/components.py`
- `Protocol[Ins, Outs]` where `Ins`/`Outs` are `TypeVar(..., bound=str)` — meant
  to be `Literal` unions of input/output names.
- Abstract properties `inputs_properties`/`outputs_properties` →
  `dict[<name>, FieldMetaData]`.
- `__call__(state: dict[Ins, DataField], time_step: datetime.datetime) ->
  dict[Outs, DataField]` is documented but **not abstract** (Protocol method
  with a body); references a nonexistent `IncompleteStateError`.
- Docstring TODOs: unit conversion hook, dim consistency, output-category
  split, "not having to pass the entire state".
- `__str__` provided.

### MuphysComponent — `.../muphys/component.py`
- Has an explicit TODO: "inherit the Component protocol once it is
  formalized (deferred to a separate PR)". **This is that PR.**
- `inputs_properties`/`outputs_properties` are **class attributes** (not
  properties) sourced from `muphys_data.{INPUTS,OUTPUTS}_PROPERTIES`.
- `__call__(state: dict[str, DataField], time_step) -> dict[str, DataField]`
  returns a dict mixing `tend_*` (tendencies) and `pflx/pr/ps/pi/pg/pre`
  (diagnostics).
- Casts `DataField` → `fa.CellKField[ta.wpfloat]` internally; owns buffers.

### SaturationAdjustment — `.../microphysics/saturation_adjustment.py`
- Uses **singular** `input_properties`/`output_properties`, both
  `raise NotImplementedError` (with a TODO to "refactor this component to
  follow the physics component protocol").
- Different call shape: `run(*, dtime, rho, temperature, qv, qc,
  temperature_tendency, qv_tendency, qc_tendency)` — named args, in-place
  tendency outputs, no dict, no `datetime.datetime`.
- This is the cheaper second validation case; its divergence is valuable for
  de-overfitting.

### Physics orchestrator — `.../physics_interface/`
- `PhysicsState` protocol (common): `gather_from_prognostic`,
  `as_component_input`, `scatter_to_prognostic`.
- `PhysicsProcess` dataclass: `{name, component: Component, state: PhysicsState,
  time_control: ProcessTimeControl, forcing_mode: ForcingMode}`.
- `PhysicsDriver.run(...)`: per process — gather, check time control, compute or
  recycle cached outputs, then `scatter_to_prognostic`. **Raises
  `NotImplementedError` for `ForcingMode.DIAGNOSTIC`** because
  `scatter_to_prognostic` couples apply-tendencies with store-diagnostics.
- `ForcingMode {DIAGNOSTIC=0, APPLY=1}` — per-process AES `fc_xxx` analogue.
- `ProcessTimeControl` — frozen dataclass with interval/window/enable and
  `is_active`/`is_in_window` (exact-multiple firing).

### State & metadata machinery (reuse candidates)
- `states/model.py`: `FieldMetaData` (TypedDict: required `standard_name`,
  `units`; optional `long_name`, `icon_var_name`, `icon_var_list_index`,
  `dims`, `dtype`, `is_on_half_levels`, `kind: Literal["tendency","diagnostic"]`),
  `DataField` Protocol, `ModelField` dataclass.
- `states/data.py`: `PROGNOSTIC_CF_ATTRIBUTES`, `COMMON_TRACER_CF_ATTRIBUTES`,
  `DIAGNOSTIC_CF_ATTRIBUTES`, `MICROPHYSICS_PRECIP_CF_ATTRIBUTES`,
  `tendency_of(base)` helper, `TENDENCY_CF_ATTRIBUTES`.
- `PrognosticState` (`rho, w, vn, exner, theta_v, tracer`), `TracerState`
  (per-species optional `CellKField`), `TracerConfig`.

### Tests
- `physics_interface/tests/.../test_physics_driver.py` — uses `RecordingComponent`
  /`RecordingPhysicsState` stubs, exercises driver semantics (ordering,
  recycle, window, forcing-mode-not-implemented). **Must keep passing or be
  updated intentionally.**
- `muphys/tests/.../test_component_datatest.py` — datatest: granule output
  matches direct muphys via `old + tendency*dt`.
- `common/tests/common/components/unit_tests/` — **empty** (only `__init__.py`).

### ADR 0001 — now non-authoritative
- Proposes: return tendencies only; never mutate; separate update step;
  per-component tendency identity. Considered-and-rejected alternatives
  (direct mutation, hybrid) are now **back on the table** as candidates.
- ADR 0002 (`Annotated[Type, ConfigOption(...)]`) is relevant prior art if the
  interface adopts declarative metadata validation.

### Phase 2 exploration (build-explorer) — critical findings
- **Overfit risk is concentrated, not diffuse.** Both targets (Muphys,
  SaturationAdjustment) are tendency-flavored (return/dict). Five real
  components — `Diffusion.run`, `Advection.run` (ABC), `SolveNonhydro.time_step`,
  `SingleMomentSixClassGraupel.run`, `SaturationAdjustment.run` — use the
  opposite Pattern B (structured state, in-place mutation, `None` return,
  scalar `dtime`). A `Component` frozen against only the two physics targets
  would not serve them without an adapter. SaturationAdjustment only de-overfits
  the *call signature*; it reinforces the *return-tendencies* choice.
- **`kind` is dead metadata today.** The orchestrator splits outputs by
  hardcoded name (`state.py:58,222,266`), never by `FieldMetaData.kind`. No
  `"prognostic"` value exists anywhere. Making `kind` load-bearing is a real
  change, not a reuse.
- **`IncompleteStateError` exists** (`common/exceptions.py:18-21`) but
  `Component.__call__` never raises it; only `io/io.py:326` does, for a
  different purpose. The protocol docstring is wrong about this.
- **`Component` has zero subclasses, is not `@runtime_checkable`.** Conformance
  is purely structural today; `MuphysComponent` does not import it.
- **`Monitor` (side-effect-only, live in `io/`) coexists** as a second
  intentionally-different component abstraction in `common/components/`. A
  return-nothing/store-only component would duplicate it.
- **`Advection` ABC** (`advection.py:129`) is the closest non-physics precedent
  for an abstract `run` component — named kwargs, in-place, `None` return.
- **`PhysicsState`/`PhysicsDriver`/`ForcingMode` are physics-named** but live in
  `common`/`physics_interface` and depend only on `common` (tach-clean). The
  naming constrains perceived generality.
- **datatest pins tendency contract tightly** (`test_component_datatest.py:96`,
  `te0 + tend*dt`, non-bit-exact atol=1e-15). Changing muphys's return shape
  must change this test by intent.

## Phase 3: Design — direction LOCKED (user)

**Decision: Approach C — hybrid, both idioms admitted.** Chosen over A (pure
tendencies-only) despite A being free for the three targets: C admits both the
return-tendency idiom (MuphysComponent) and the in-place-mutation majority
(Advection, SaturationAdjustment, and later the dycore) as **first-class
Components without wrappers**. The accepted costs are (1) one typed branch in
the orchestrator and (2) making `FieldMetaData.kind` load-bearing (replacing
today's hardcoded name split in `state.py:58,222,266`). A's purity was
rejected in exchange for not forcing the dycore's predictor-corrector (where a
single tendency is semantically awkward) through a wrapper.

### Locked sub-decisions (from prior pass, partially superseded by amended D1-D11)
- **`kind` is demoted to a consistency check** (amended D5), NOT the single
  apply-vs-store discriminator. The dispatch is structural via
  `ComponentOutputs.tendencies`/`.diagnostics`. The prior prose saying `kind`
  is "the single discriminator" is superseded.
- **muphys phy2dyn coupling stays on the `State` adapter** as a per-adapter
  finalize inside `apply_tendencies` (APPLY mode only; never run in
  DIAGNOSTIC). YAGNI: no `"prognostic"` kind / assign semantics until a real
  component needs them. The orchestrator therefore stays physics-specific in
  that one seam; physics names are defensible.

### Architect to detail (within approved direction)
- Exact `Component` protocol shape: `inputs_properties`/`outputs_properties`
  (plural wins; rename SaturationAdjustment's singular), the single entry point
  (`run` vs `__call__` — recommend with rationale), and `-> dict[str,
  DataField] | None` semantics.
- Conformance mechanism: explicit inheritance vs structural duck-typing vs
  optional base; whether to make the Protocol `@runtime_checkable`. (User gave
  full latitude: "a component protocol that defines _some_ shape.")
- The orchestrator split: replace `PhysicsState.scatter_to_prognostic` with
  `apply_tendencies` + `store_diagnostics`; how `PhysicsDriver` gates on
  `ForcingMode`; `ForcingMode.DIAGNOSTIC` semantics for the `None` branch
  (lean: "do not run, serve cached output" mirroring the existing recycle
  cache, with a loud failure if no cache exists).
- Per-target conformance deltas: MuphysComponent, SaturationAdjustment,
  Advection (entry point rename, metadata wiring, `None`-return for the two
  in-place targets).
- Naming: whether any orchestrator type renames are warranted given the
  physics-specific seam is retained (lean: keep physics names).
- Acceptance criteria and test impact (`test_physics_driver.py`,
  `test_component_datatest.py`).

## Phase 3: Design — approaches (brainstormer, superseded by lock above)

The central question: one protocol shape serving (A) return-tendency dict
(MuphysComponent) and (B) in-place mutation / `None` (Advection, Diffusion,
SolveNonhydro, SaturationAdjustment, Graupel — the majority).

### Approach A — tendencies only (ADR 0001's proposal)
Every component returns `dict[str, DataField]`, never mutates. State updated
separately. **Reject:** forces the 5 in-place majority (incl. dycore's
multi-step predictor-corrector, where a single tendency is ill-defined and
back-computing it doubles memory + adds kernels) into a representation they
don't fit. High rework, HPC-negative, contradicts "do not overfit."

### Approach B — in-place only (majority idiom)
Single `run(...) -> None`, structured state, in-place. **Reject:** loses
MuphysComponent's modular tendency boundary (the whole point of converting
muphys's updated-state into tendencies the orchestrator decides how to apply),
makes `ForcingMode.DIAGNOSTIC` effectively unimplementable (mutation has
already happened by return time), reintroduces the opacity ADR 0001 objected
to.

### Approach C — hybrid, both idioms admitted (RECOMMENDED)
Single `run(...) -> dict[str, DataField] | None`. `None` = in-place mutation
done. `dict` = each output declares `FieldMetaData.kind` ("tendency" /
"diagnostic", already populated in `data.py`). Orchestrator branches on the
return: dict -> apply `kind=="tendency"`, store `kind=="diagnostic"`; None ->
component already updated state, orchestrator does nothing further.
- Serves both idioms without rewriting either (conformance = rename + metadata).
- Most reversible; reuses `FieldMetaData`/`kind`/`tendency_of` (makes `kind`
  load-bearing instead of today's hardcoded name split in `state.py:58,222,266`).
- Keeps transparency where it matters (physics, dict branch) and avoids dycore
  cost where it doesn't (None branch).
- Cost: one typed branch in the orchestrator; `ForcingMode.DIAGNOSTIC` now
  implementable (run + `store_diagnostics` only, skip apply).

### Orchestrator consequence (where apply/store lives)
Today `State.scatter_to_prognostic` does (1) apply moisture tendencies
`field += tend*dt`, (2) muphys-specific exner/theta_v recomputation via exact
EOS, (3) store precip diagnostics by hardcoded name. Step 2 is physics-specific;
1+3 generic. Under C: split into `apply_tendencies(prognostic, outputs, dtime)`
(1 + the muphys EOS finalize) and `store_diagnostics(outputs)` (3, now
`kind`-driven). `PhysicsState` protocol gains these two, loses
`scatter_to_prognostic`. `PhysicsDriver` chooses on `ForcingMode`. The physics
names stay defensible because the EOS seam keeps the orchestrator
physics-specific in that one place.

### Open sub-decisions (Coordinator to resolve in architect phase, unless noted)
1. muphys phy2dyn coupling: stay on adapter as finalize hook (simplest, lowest
   coupling; orchestrator stays physics-specific in that seam) vs move into
   component (fully generic apply, needs a `"prognostic"` kind + assign
   semantics). **Lean: stay on adapter** (YAGNI; avoid `"prognostic"` until a
   real component needs assign semantics).
2. Entry point name: `run` (majority idiom; one rename in MuphysComponent + test
   stubs) vs `__call__` (current protocol; callable ergonomics). **Architect to
   recommend.**
3. Make `kind` load-bearing now: yes (enables the clean split + DIAGNOSTIC; this
   is the key reuse). Changes `scatter_to_prognostic` + its test by intent.
4. SolveNonhydro/Diffusion conforming: **No** (user's three targets are
   muphys/saturation-adjustment/advection; these are the in-place majority
   represented by Advection).
5. DIAGNOSTIC for `None`-returning components: "do not run, serve cached output"
   (mirrors the existing recycle cache) vs fail loud. **Architect to
   recommend.**

## Progress

- [x] Phase 0: Init / branch context
- [x] Phase 1: Elicitation (scope confirmed; ADR reframed as non-authoritative)
- [x] Phase 2: Exploration (build-explorer)
- [x] Phase 3: Design (brainstormer 2-round deep pass on 4 axes; direction locked C then amended; architect decisions D1-D11)
- [x] Phase 4: Spec Frozen (three independent review rounds; all blocking findings fixed; user confirmed)

### Reviewer notes folded in by-design (non-blocking)
- R6: the "every output must have `kind`" rule (AC9) is enforced only inside
  `PhysicsDriver.run`. Components called directly (e.g. standalone driver
  calls to `Advection.run`) are not gated by the orchestrator; the protocol
  docstring recommends `kind` for all outputs so the rule holds wherever the
  orchestrator drives the component.
- R9: `MuphysComponent.run` uses `self._dt_seconds` (set at construction) for
  `_to_tendency`, while the protocol passes per-call `dtime`. If the physics
  step ever varies, this is an implementation-correctness concern flagged for
  the implementor, not a protocol decision.
- R10: `run` is a Protocol method with a docstring body (no `@abstractmethod`),
  matching the existing `components.py` style and `@runtime_checkable` (which
  needs real bodies, not `...`). mypy is the signature gate.
- [ ] Phase 5: Implementation
- [ ] Phase 6: Local Verification
- [ ] Phase 7: Human Review


## Phase 3: Design — concrete decisions (amended architect pass)

> Status: **ready for spec freeze.** This section supersedes the prior D1-D9
> (kept above for history as "approaches (brainstormer, superseded by lock
> above)"). The user suspended minimal-change/scope/YAGNI constraints and,
> after a deep 4-axis brainstorm (state representation, checkability, units,
> mutability), chose amendments that make the interface globally best rather
> than least-breaking. Each decision carries rationale and alternatives
> considered and rejected.

### Design constraints

- The `Component` protocol lives in `model/common` and must stay tach-clean
  (depends on nothing outside `model.common`). The physics orchestrator
  (`physics_interface`) depends on `model.common` only; muphys depends on
  `model.common` only.
- Pre-1.0 codebase (version 0.2.0). API evolution is acceptable where it
  improves the design; backward compatibility is not a constraint.
- `FieldMetaData.kind` (`Literal["tendency", "diagnostic"]`) and
  `FieldMetaData.units` (required `str`) already exist in `states/model.py`.
  Making them load-bearing for validation is a reuse, not a new field.
- `IncompleteStateError` exists in `common/exceptions.py:18` but is never
  raised by `Component`. The protocol docstring's reference to it is wrong and
  removed.
- `Monitor` protocol (`common/components/monitor.py`) coexists as a separate
  side-effect-only abstraction. This design does not merge or duplicate it.
- GT4Py fields' underlying ndarrays support `setflags(write=False)` (empirically
  verified on `gtx.zeros(...)` roundtrip fields). Compiled backends (gtfn_cpu,
  gtfn_gpu) may reject read-only inputs at the C++ level — the read-only
  enforcement is gated accordingly (see D5).

### Task boundaries

- **In scope:** the `Component` protocol in `model/common/components/components.py`;
  `ComponentOutputs` (new, same file or a sibling); the `PhysicsState` protocol
  in `model/common/components/physics_state.py`; the `PhysicsDriver`/
  `PhysicsProcess`/`ForcingMode`/`ProcessTimeControl` in `physics_interface/`;
  the three conformance targets (`MuphysComponent`, `SaturationAdjustment`,
  the `Advection` ABC); the muphys `State` adapter (`muphys/state.py`); the two
  test files named below; standalone-driver call sites for the three targets.
- **Out of scope:** `Diffusion.run`, `SolveNonhydro.time_step`,
  `SingleMomentSixClassGraupel.run` (represented by `Advection` as the in-place
  majority; user confirmed three targets only). `bindings/` Granule wrappers.
  Performance optimization of muphys itself. New physics schemes.
- **Recommendations (not in this change):** (1) once a dycore component
  conforms, revisit whether `ForcingMode` needs a third value for "compute
  and discard". (2) If a component ever needs to assign prognostic fields
  directly (not via tendencies), add `kind="prognostic"` and assign semantics
  then. (3) A unit-conversion hook (the stub's own TODO) can be added as a
  registered converter at setup; error-only is the starting point (D4).

### Design decisions

| ID | Decision | Status |
|---|---|---|
| D1 | Entry point is `run`, not `__call__` | Locked (unchanged) |
| D2 | State is a per-component frozen dataclass with typed named fields; Protocol gains `InputT` TypeVar | Locked (amends old D2 input side) |
| D3 | `inputs_properties`/`outputs_properties` are annotated Protocol attributes (plural) | Locked (unchanged) |
| D4 | `Component` is `@runtime_checkable` Protocol; layered checking (static + setup + per-call) | Locked (amends old D4) |
| D5 | `ComponentOutputs` structured return replaces flat dict; `kind` demoted to consistency check | Locked (amends old D2 output side + old D5) |
| D6 | `PhysicsState[InputT]` gains `apply_tendencies` + `store_diagnostics`, loses `scatter_to_prognostic` | Locked (amends old D6) |
| D7 | `ForcingMode.DIAGNOSTIC` resolution (unchanged from prior lock) | Locked |
| D8 | SaturationAdjustment returns `ComponentOutputs` (Pattern A) | Locked (amends old D8) |
| D9 | Keep physics names for orchestrator types | Locked (unchanged) |
| D10 | Read-only numpy flag on inputs of `ComponentOutputs`-returning components | Locked (new) |
| D11 | Setup-time unit validation (error on mismatch) | Locked (new) |

#### D1: Entry point is `run` (unchanged)

The protocol names the single entry point `run(self, ...)` (an explicit
method), not `__call__`. Five of six real components already use `run`; only
`MuphysComponent.__call__` renames. `run` reads naturally to scientists
("run the saturation adjustment") and is discoverable as a documented
method rather than an implicit dunder.

Rejected: `__call__` (current stub; callable ergonomics are a minor
convenience; renaming the majority has a far larger blast radius than
renaming the one outlier).

#### D2: Per-component frozen dataclass state (amends old D2 input side)

Each component declares its input as a **frozen dataclass** with typed,
named fields. Scientists access `state.dz`, `state.rho`, `state.te` — dot
notation that reads like physics, not framework plumbing. The Protocol
gains an `InputT` TypeVar (the per-component input state type).

@dataclasses.dataclass(frozen=True)
class MuphysInput:
    dz: fa.CellKField[ta.wpfloat]
    rho: fa.CellKField[ta.wpfloat]
    te: fa.CellKField[ta.wpfloat]
    p: fa.CellKField[ta.wpfloat]
    qv: fa.CellKField[ta.wpfloat]
    qc: fa.CellKField[ta.wpfloat]
    qr: fa.CellKField[ta.wpfloat]
    qs: fa.CellKField[ta.wpfloat]
    qi: fa.CellKField[ta.wpfloat]
    qg: fa.CellKField[ta.wpfloat]
```

The orchestrator erases to `Any` at the boundary (same as today's
`dict[str, Any]`). Inside the component, `state.dz` is mypy-checked as
`CellKField[wpfloat]`; `state.typo` is a mypy error. This resolves the
prior incoherence: "mypy is the real signature gate" is now **true**
because the state IS typed per-key, per-field, per-dimension.

The `inputs_properties`/`outputs_properties` metadata is retained. It does
not duplicate the dataclass: the dataclass carries types (dimension,
dtype), while the metadata carries CF attributes (`standard_name`,
`units`, `long_name`, `icon_var_name`). They serve different purposes.

Alternatives considered and rejected:
- **`dict[str, DataField]` (old locked design).** No per-key, per-field, or
  dimension type safety. mypy cannot check `state["typo"]`. The prior
  Coordinator claim "mypy is the real signature gate" was incoherent with a
  string-keyed dict. Every component casts internally today
  (`cast("dict[str, fa.CellKField[ta.wpfloat]]", state)`), and these casts
  are unsafe and unverified. **Rejected because the state representation is
  the biggest gap; keeping it was the easy choice, not the best one.**
- **Per-component `TypedDict` (brainstormer alt 1A).** Gives `state["dz"]`
  access with per-key typing after a cast. TypedDicts are dicts at runtime,
  so the orchestrator's `as_component_input() -> dict[str, Any]` is
  compatible without modification. **Rejected in favor of dataclass**
  because (a) the user prioritized scientist ergonomics and explicitly
  suspended minimal-change, (b) `state.dz` reads like physics while
  `state["dz"]` reads like a registry lookup, (c) five of six real
  components already use structured state objects with named fields
  (`PrognosticState`, `AdvectionDiagnosticState`, `AdvectionPrepAdvState`,
  `MetricStateSaturationAdjustment`), (d) no cast needed — the state
  adapter constructs the dataclass directly.
- **Generic `State[Literal[...]]` field bag (brainstormer alt 1C).**
  Key-existence checking only; value type still `DataField`. Weakest type
  safety of the three. **Rejected** — marginal improvement over raw dict
  without enough benefit to justify the indirection.

#### D3: Metadata as annotated Protocol attributes, plural (unchanged)

`inputs_properties` and `outputs_properties` are declared as annotated
attributes in the Protocol (not `@property @abstractmethod`), letting
conformers use either class attributes (`MuphysComponent` today) or
properties (`SaturationAdjustment`, `Advection`). `@runtime_checkable`
checks `hasattr(cls, name)` for both.

Rejected: `@property @abstractmethod` (forces every conformer to use
properties; mypy may reject class-attribute override of a Protocol
property). Rejected: singular names (only `SaturationAdjustment` uses
singular; renaming it is cheaper than renaming the protocol).

#### D4: `@runtime_checkable` Protocol + layered checking (amends old D4)

Three checking layers, each catching different error classes:

1. **Static (mypy):** with the per-component frozen dataclass state (D2),
   mypy is a real per-key, per-field, per-dimension gate inside the
   component. This resolves the prior incoherence. Each component source
   file is opted into the mypy path (mirroring `pyproject.toml:165-167`
   opt-in pattern for `microphysics/src/.../saturation_adjustment.py`).
2. **Setup-time (always on, at `PhysicsProcess` creation):** validate that
   `outputs_properties` is well-formed (all outputs have `kind`),
   `inputs_properties` is well-formed (all inputs have `units`), and input
   field units match the state adapter's field units (D11).
3. **Per-call (always on, cheap):** validate that all declared input keys
   are present in the state. O(n_inputs) attribute lookups, negligible
   compared to stencil execution.

`@runtime_checkable` is retained for quick structural conformance in tests
(`isinstance(component, Component)`).

Rejected: pure static (only covers mypy-gated code; standalone drivers and
  test scripts get zero checking). Rejected: pure runtime (stronger but
  does not catch type errors at development time). Rejected:
  `@runtime_checkable` only (checks attribute presence, not signatures or
  key types — the weakest option).

#### D5: `ComponentOutputs` structured return (amends old D2 output side + old D5)

The return type replaces `dict[str, DataField] | None` with
`ComponentOutputs | None`, where `ComponentOutputs` is a **shared** frozen
dataclass:

```python
@dataclasses.dataclass(frozen=True)
class ComponentOutputs:
    tendencies: dict[str, model.DataField]
    diagnostics: dict[str, model.DataField]
```

The component **pre-splits** its outputs at return time. The orchestrator
dispatches structurally (`result.tendencies` -> `apply_tendencies`,
`result.diagnostics` -> `store_diagnostics`), **not** by reading
`FieldMetaData.kind`.

This demotes `kind` from "the single output discriminator" (old D5) to "a
consistency check and documentation aid". The setup-time validator (D4)
verifies that keys in `tendencies` have `kind="tendency"` in
`outputs_properties`, and keys in `diagnostics` have `kind="diagnostic"`.
This catches mis-splits without making `kind` the load-bearing runtime
dispatch key.

Why this is better than the old flat-dict + `kind` dispatch:
- The orchestrator's dispatch no longer depends on metadata being correct
  at runtime. The component's intent is explicit in the return value
  (structural, not metadata-driven).
- `kind` is still useful for IO, CF conventions, and validation. It is not
  removed, just no longer the dispatch mechanism.
- The old SPEC rejected `ComponentOutputs` (old D2) on two incorrect
  premises: (a) "adds a type per component" — `ComponentOutputs` is shared,
  not per-component; (b) "no gain over dict + kind metadata" — the gain is
  structural dispatch, reduced coupling, and self-documenting return.

Rejected: flat `dict[str, DataField]` with `kind`-driven dispatch (old D5).
  The orchestrator split was metadata-driven, coupling it to `kind` being
  correct at runtime. **Rejected because it was the easy choice, not the
  best one — the structural split is cleaner, more decoupled, and
  self-documenting.**

Rejected: per-component `ComponentOutputs` subclasses. YAGNI — the shared
  `tendencies`/`diagnostics` split is sufficient for all targets. No
  per-component output types are needed.

#### D6: `PhysicsState[InputT]` + `apply_tendencies`/`store_diagnostics` (amends old D6)

`PhysicsState` gains a TypeVar and two methods, loses
`scatter_to_prognostic`:

```python
class PhysicsState(Protocol[InputT]):
    def gather_from_prognostic(
        self, prognostic: prognostic_state.PrognosticState,
        tracers: tracer_state.TracerState,
    ) -> None: ...
    def as_component_input(self) -> InputT: ...
    def input_field_units(self) -> dict[str, str]: ...
    def apply_tendencies(
        self, prognostic: prognostic_state.PrognosticState,
        tendencies: dict[str, DataField], dtime: datetime.timedelta,
    ) -> None: ...
    def store_diagnostics(
        self, diagnostics: dict[str, DataField],
    ) -> None: ...
``n
`PhysicsProcess` becomes `PhysicsProcess[InputT]` (Generic), tying component
and state adapter together by `InputT`. mypy verifies that
`state.as_component_input()` produces what `component.run(state, ...)`
consumes. The `PhysicsDriver` holds `list[PhysicsProcess[Any]]` (erased).

The orchestrator pre-splits `ComponentOutputs` into `tendencies` and
`diagnostics` (structural, D5), then dispatches:
- `result.tendencies` -> `state.apply_tendencies(prognostic, tendencies, dtime)`,
  called only when `ForcingMode.APPLY`.
- `result.diagnostics` -> `state.store_diagnostics(diagnostics)`,
  called whenever the component returned `ComponentOutputs` (both APPLY and
  DIAGNOSTIC).

The muphys `State.apply_tendencies` contains the phy2dyn coupling
(recompute `exner`/`theta_v` from the temperature tendency via the exact
EOS, mirroring `mo_interface_iconam_aes.f90`). This is the one
physics-specific seam the design retains. It runs in APPLY mode only.

`input_field_units()` (new) returns the units of each field the state
adapter produces, from the existing metadata registries. Used by the
setup-time unit validation (D11).

Rejected: keep `scatter_to_prognostic` and add a `diagnostic_only` flag.
  Couples apply and store, which is exactly the problem that makes
  `ForcingMode.DIAGNOSTIC` raise `NotImplementedError` today.

#### D7: `ForcingMode.DIAGNOSTIC` resolution (unchanged from prior lock)

**`ComponentOutputs` branch (component returns `ComponentOutputs`):**
- Run the component (compute outputs).
- Call `store_diagnostics(result.diagnostics)`.
- Do NOT call `apply_tendencies(...)`. The `result.tendencies` are computed
  but not applied; they remain available in the returned `ComponentOutputs`
  for inspection or output.
- The recycle cache stores the `ComponentOutputs` (same as today), so
  subsequent in-window non-active steps serve cached diagnostics without
  recomputing.

**None branch (component returns `None`):**

In-place computation cannot be separated from application (running IS
applying), and a `None`-returning component produces no `ComponentOutputs`
to inspect. `ForcingMode.DIAGNOSTIC` therefore degenerates to "do not run;
freeze the prognostic state." The cache's existence is irrelevant — an
in-place component has no diagnostic outputs to serve regardless of prior
runs.

| sub-case | condition | behavior |
|---|---|---|
| (c) | active (would fire under APPLY) | do NOT run; no `apply_tendencies`, no `store_diagnostics`; log a clear warning that the in-place component produced no diagnostic outputs under DIAGNOSTIC (so the operator is not confused into expecting inspectable results) |
| (d) | non-active in-window (recycle path) | do NOT run; silent (it was not going to run anyway); prognostic unchanged |

Rejected: run the component and undo the mutation afterward (save/restore
  prognostic). HPC-negative, fragile. Rejected: allow None-returning
  components to optionally return `ComponentOutputs` in DIAGNOSTIC mode.
  Breaks the clean `ComponentOutputs | None` contract.

Note (R8, acknowledged tradeoff): the `None` branch accepts *bounded*
output opacity — the orchestrator trusts the component updated prognostic
state and makes no further apply/store call. This is the opacity ADR 0001
objected to, reintroduced in exchange for admitting the in-place majority
as direct Components without a wrapper. The bound is that the orchestrator
*knows* the component ran and chose to apply itself; it is not opaque about
*whether* state advanced, only about the *form* of the advance. This
tradeoff was accepted by the user's selection of Approach C.

#### D8: SaturationAdjustment returns `ComponentOutputs` (amends old D8)

Verified by the Coordinator (`saturation_adjustment.py:294-305`): `run`
writes *tendencies* (`temperature_tendency`, `qv_tendency`, `qc_tendency`)
into caller-provided buffers and returns `None`; it does NOT mutate
prognostic state. Under the hybrid contract `None` = "state already
updated, orchestrator does nothing," which would discard these tendencies.

**Decision: SaturationAdjustment returns `ComponentOutputs`** (Pattern A),
allocating internal tendency buffers and returning
`ComponentOutputs(tendencies={"tend_temperature": ..., "tend_qv": ...,
"tend_qc": ...}, diagnostics={})` with `kind="tendency"`. The orchestrator
applies them via `apply_tendencies`. This preserves its scientific
semantics (it computes tendencies) and reuses the single apply path.

Final classification: **two `ComponentOutputs`-returning targets**
(`MuphysComponent`, `SaturationAdjustment`) and **one None-returning target**
(`Advection`, the in-place de-overfitting validator).

#### D9: Keep physics names for orchestrator types (unchanged)

Keep `PhysicsState`, `PhysicsDriver`, `PhysicsProcess`, `ForcingMode`,
`ProcessTimeControl`. The physics-specific seam (phy2dyn coupling in
`apply_tendencies`) means the orchestrator is genuinely physics-specific in
one place. Generic names would obscure this and imply a generality that
does not exist yet.

#### D10: Read-only numpy flag on inputs (new)

For `ComponentOutputs`-returning components, set
`field.ndarray.setflags(write=False)` on each input field before `run`, and
restore `write=True` after. This catches accidental mutations at the
ndarray level (where mutations actually happen) with negligible overhead
(O(n_input_fields), no copy). Empirically verified on GT4Py roundtrip
fields.

NOT applied to `None`-returning components (they mutate the prognostic
state by design — the distinction is explicit in the return type).

**Backend gating:** The read-only flag is **always-on by default**. If a
component uses a compiled backend (gtfn_cpu, gtfn_gpu) that rejects
read-only inputs at the C++ level, the component opts out via a
`read_only_inputs: bool = True` attribute (or the `PhysicsProcess` carries
the flag). The standalone driver sets this based on the backend. This
avoids any production risk with compiled backends while catching
accidental mutations for the roundtrip backend (the default).

Alternatives considered and rejected:
In-place computation cannot be separated from application (running IS
applying), and a `None`-returning component produces no `ComponentOutputs`
to inspect. This includes diagnostics: a `None`-returning component may
write diagnostic fields through its input dataclass by reference (e.g.
`Advection` mutates `diagnostic_state`), and the orchestrator does NOT call
`store_diagnostics` — the component handles all application and diagnostic
storage itself. `ForcingMode.DIAGNOSTIC` therefore degenerates to "do not
run; freeze the prognostic state." The cache's existence is irrelevant —
an in-place component has no `ComponentOutputs.diagnostics` to serve
regardless of prior runs.
  through `ndarray`, not `__setitem__`. The numpy flag (4A) is more
  effective.

#### D11: Setup-time unit validation (new)

When a `PhysicsProcess` is created, validate that each input field's units
(from `component.inputs_properties[field]["units"]`) match the state
adapter's field units (from `state.input_field_units()[field]`). Simple
string comparison, no new dependencies. **Error on mismatch** (user's
choice — no automatic conversion; a conversion hook is a later extension).

```python
# In PhysicsProcess.__post_init__ or a validate() method
for field_name, meta in self.component.inputs_properties.items():
    state_units = self.state.input_field_units().get(field_name)
    if state_units is not None and state_units != meta["units"]:
        raise ValueError(
            f"Unit mismatch for input '{field_name}': "
            f"component expects '{meta['units']}', "
            f"state adapter produces '{state_units}'."
        )
```

The muphys `State.input_field_units()` returns units from the same metadata
registries (`PROGNOSTIC_CF_ATTRIBUTES`, `DIAGNOSTIC_CF_ATTRIBUTES`,
`COMMON_TRACER_CF_ATTRIBUTES`) that `muphys_data.INPUTS_PROPERTIES` is built
from, so the check passes trivially for muphys. The real value is for
future components where the state adapter produces different units than the
component expects.

Alternatives considered and rejected:
- **Per-call unit checking.** Same check but on every `run` call. Unnecessary
  if the state shape is fixed (which it typically is). Setup-time is
  sufficient for the common case.
- **Pint / unit-aware quantities.** Heavyweight dependency, HPC-incompatible
  (Pint's `Quantity` wrapper adds overhead to every field operation; GT4Py
  stencils expect raw fields). Overkill for a small, fixed set of units.
- **Inert (current).** Unit mismatch bugs are silent and hard to debug. The
  metadata exists but is wasted.

### Open questions (resolved)

**O1 (RESOLVED): SaturationAdjustment return type.** Verified: `run` writes
*tendencies* into caller buffers, NOT prognostic state. `None` would lose
them. **Decision (D8): returns `ComponentOutputs`.**

**O2 (RESOLVED): `store_diagnostics` prognostic parameter.** No — current
diagnostic storage does not use `prognostic`. A future state adapter can
widen the protocol then (pre-1.0, YAGNI).

### Component vs Monitor (clarifying the None branch)

A `None`-returning `Component` (e.g. `Advection`) mutates prognostic state
in place and advances the model. `Monitor` (`monitor.py`) stores/freezes
state for later usage **without modifying it or producing new state**. The
distinction is intent, not return shape: Components *advance the model*;
Monitors *observe it*. The hybrid `None` branch is NOT a duplicate of
`Monitor` — a None-returning Component is part of the prognostic advance
(the orchestrator knows it ran and made no further apply/store call because
the component handled application itself), whereas a Monitor is invoked for
side effects on storage/IO and never participates in the advance.

### Per-target conformance deltas

**MuphysComponent (`ComponentOutputs` branch, smallest delta):**
- Declare a `MuphysInput` frozen dataclass with typed named fields (`dz`,
  `rho`, `te`, `p`, `qv`, `qc`, `qr`, `qs`, `qi`, `qg`), each
  `fa.CellKField[ta.wpfloat]`.
- Inherit `Component[MuphysInput]` (recommended for `isinstance` and
  `__str__`).
- Rename `__call__` to `run`. Signature: `run(self, state: MuphysInput,
  dtime: datetime.timedelta) -> ComponentOutputs`.
- `MuphysComponent` should use the per-call `dtime` for `_to_tendency`
  instead of `self._dt_seconds` (a correctness improvement if the physics
  step ever varies). Note: the muphys program (`self._step`) is compiled
  with `dt=self._dt_seconds`; if dtime varies per step, this is a separate
  implementation concern flagged for the implementor.
- `inputs_properties`/`outputs_properties`: already class attributes,
  already plural, already populated with `kind`. No change.
- The returned `dict` is wrapped in `ComponentOutputs(tendencies={...},
  diagnostics={...})` at return time. The tendencies are `tend_temperature`,
  `tend_qv`, `tend_qc`, `tend_qr`, `tend_qs`, `tend_qi`, `tend_qg`; the
  diagnostics are `pflx`, `pr`, `ps`, `pi`, `pg`, `pre`. The split replaces
  the muphys `State`'s hardcoded `_PRECIP_DIAGNOSTICS` tuple.
- The muphys `State.as_component_input()` changes return type from
  `dict[str, fa.CellKField[ta.wpfloat]]` to `MuphysInput(...)`.
- The muphys `State` implements `input_field_units()` (from the same
  registries), `apply_tendencies` (moisture tendencies + phy2dyn EOS
  finalize, APPLY mode only), and `store_diagnostics` (precip diagnostics).
  The hardcoded `_PRECIP_DIAGNOSTICS` tuple in `muphys/state.py` is removed.

**SaturationAdjustment (`ComponentOutputs` branch, medium delta):**
- Declare a `SaturationAdjustmentInput` frozen dataclass with typed named
  fields (`rho`, `temperature`, `qv`, `qc`), each
  `fa.CellKField[ta.wpfloat]`.
- Rename `input_properties`/`output_properties` (singular, NotImplemented
  methods) to `inputs_properties`/`outputs_properties` (plural) with real
  `FieldMetaData`. Output keys are LOCKED: `tend_temperature`, `tend_qv`,
  `tend_qc` (matching `MuphysComponent`'s `tend_<base>` convention), each
  with `kind="tendency"` plus the saturation-specific `standard_name`/
  `long_name` (e.g. `tendency_of_air_temperature_due_to_saturation_adjustment`).
- Add `model/atmosphere/subgrid_scale_physics/microphysics/src/icon4py/model/atmosphere/subgrid_scale_physics/microphysics/saturation_adjustment.py`
  to the `[tool.mypy].files` list in `pyproject.toml` (mirroring the opt-in
  pattern at lines 165-167).
- Change `run` from named kwargs to the protocol shape: `run(self, state:
  SaturationAdjustmentInput, dtime: datetime.timedelta) -> ComponentOutputs`.
**Advection (None branch, largest delta):**
- Declare an `AdvectionInput` frozen dataclass with typed named fields
  packing the current structured-state inputs: `diagnostic_state:
  AdvectionDiagnosticState`, `prep_adv: AdvectionPrepAdvState`,
  `p_tracer_now: fa.CellKField[ta.wpfloat]`, `p_tracer_new:
  fa.CellKField[ta.wpfloat]`.
- **`outputs_properties` is NOT empty.** `Advection.run` mutates fields in
  `diagnostic_state` (`airmass_now`, `airmass_new`, `grf_tend_tracer`,
  `hfl_tracer`, `vfl_tracer`) and `p_tracer_new` through the input dataclass
  by reference. These are in-place diagnostic and prognostic outputs. The
  `outputs_properties` documents them (with `kind="diagnostic"` for the
  diagnostic fields) for setup-time validation and documentation, EVEN
  THOUGH the orchestrator does not dispatch on them for `None`-returning
  components. This is the "bounded opacity" of the `None` branch: the
  component handles all application and diagnostic storage itself; the
  orchestrator trusts it and does nothing further.
- Add `inputs_properties` (plural) on the `Advection` ABC.
- Change `run` from structured-state named kwargs to the protocol shape:
  `run(self, state: AdvectionInput, dtime: datetime.timedelta) -> None`.
  Internally: unpack the dataclass (`state.diagnostic_state`,
  `state.prep_adv`, `state.p_tracer_now`, `state.p_tracer_new`), call the
  existing advection logic (which mutates `diagnostic_state` and
  `p_tracer_new` in place), return `None`.
- The `dtime` type changes from scalar `wpfloat` to `datetime.timedelta`;
  the component converts internally.
- All `Advection` subclasses (`NoAdvection`, `GodunovSplittingAdvection`,
  horizontal/vertical advection classes) update their `run` signature.
- The standalone driver call site (`standalone_driver.py:268`) and advection
  integration tests (`test_advection.py`, `test_parallel_advection.py`)
  update to the dataclass-in signature. This is the largest call-site blast
  radius and is flagged for the implementor.
  radius and is flagged for the implementor.

### Naming

Keep all orchestrator type names (`PhysicsState`, `PhysicsDriver`,
`PhysicsProcess`, `ForcingMode`, `ProcessTimeControl`). The physics-specific
seam (phy2dyn coupling in `apply_tendencies`) means the orchestrator is
genuinely physics-specific in one place.

The one rename that IS warranted is method-level: `scatter_to_prognostic` ->
`apply_tendencies` + `store_diagnostics` (D6).

### Acceptance criteria

- [ ] AC1: `Component` is a `@runtime_checkable` `Protocol[InputT]` in
  `model/common/components/components.py` with `inputs_properties` and
  `outputs_properties` (annotated attributes, not `@property`), and a single
  `run(self, state: InputT, dtime: datetime.timedelta) -> ComponentOutputs
  | None` method. No `@abstractmethod`. No reference to
  `IncompleteStateError` in the docstring.
- [ ] AC2: `ComponentOutputs` is a frozen dataclass with `tendencies:
  dict[str, DataField]` and `diagnostics: dict[str, DataField]`, defined in
  `model/common/components/`.
- [ ] AC3: `isinstance(MuphysComponent(...), Component)` is `True`.
- [ ] AC4: `isinstance(SaturationAdjustment(...), Component)` is `True`.
- [ ] AC5: `isinstance(NoAdvection(...), Component)` is `True` (or an
  `Advection` subclass instance).
- [ ] AC6: `PhysicsState` is a `Protocol[InputT]` with
  `gather_from_prognostic`, `as_component_input() -> InputT`,
  `input_field_units() -> dict[str, str]`,
  `apply_tendencies(prognostic, tendencies, dtime)`,
  `store_diagnostics(diagnostics)`. `scatter_to_prognostic` is removed.
- [ ] AC7: `PhysicsProcess` is `Generic[InputT]` with `component:
  Component[InputT]` and `state: PhysicsState[InputT]`. mypy verifies they
  agree on `InputT`.
- [ ] AC8: `PhysicsDriver.run` dispatches structurally: for a
  `ComponentOutputs`-returning component, `result.tendencies` ->
  `apply_tendencies` (only when `ForcingMode.APPLY`), `result.diagnostics`
- [ ] AC9: `PhysicsDriver.run` applies recycled `ComponentOutputs`
  (tendencies and diagnostics from the cache) for `ComponentOutputs`-returning
  components on non-active in-window steps, preserving ICON constant forcing.
  For `None`-returning components, the recycle cache holds `None`; the
  orchestrator does nothing (the prognostic state reflects the last in-place
  run).
- [ ] AC10: `ForcingMode.DIAGNOSTIC` no longer raises `NotImplementedError`.
  `ComponentOutputs` branch: `store_diagnostics` only, no `apply_tendencies`.
  `None` branch: do not run; log warning if active; silent if non-active.
- [ ] AC11: At `PhysicsProcess` creation, setup-time validation checks:
  (a) all `outputs_properties` have `kind`; (b) all `inputs_properties` have
  `units`; (c) input field units match `state.input_field_units()`. Error on
  mismatch.
- [ ] AC12: Per-call validation checks all declared input keys are present
  in the state. Error if any are missing.
- [ ] AC13: For `ComponentOutputs`-returning components, input fields have
  `ndarray.setflags(write=False)` applied before `run` and restored after,
  unless the component opts out (compiled backend).
- [ ] AC14: The muphys `State` implements `input_field_units`,
  `apply_tendencies` (moisture tendencies + phy2dyn EOS finalize, APPLY mode
  only), and `store_diagnostics` (precip diagnostics). The hardcoded
  `_PRECIP_DIAGNOSTICS` tuple is removed.
- [ ] AC15: `MuphysComponent.outputs_properties` and
  `SaturationAdjustment.outputs_properties` both carry `kind` for every
  output. The setup-time validator verifies consistency: keys in
  `ComponentOutputs.tendencies` have `kind="tendency"`, keys in
  `ComponentOutputs.diagnostics` have `kind="diagnostic"`.
- [ ] AC16: ruff, mypy (on the configured paths, including the newly-added
  `saturation_adjustment.py`), and tach are clean after the change.
- [ ] AC17: `uv run --group test --frozen pytest` on
  `model/common/tests/common/components/unit_tests/`,
  `model/atmosphere/subgrid_scale_physics/physics_interface/tests/`, and
  `model/atmosphere/subgrid_scale_physics/muphys/tests/muphys/unit_tests/`
  passes (no datatests required for these).

### Test impact

**`physics_interface/tests/.../test_physics_driver.py` (unit tests,
substantial update):**
- `RecordingComponent.__call__` -> `RecordingComponent.run(self, state,
  dtime)` returning `ComponentOutputs(tendencies=..., diagnostics=...)` or
  `None`.
- `RecordingPhysicsState.scatter_to_prognostic` -> `apply_tendencies` +
  `store_diagnostics` (two recording methods) + `input_field_units()`.
- The existing semantics tests (ordering, recycle, window, disabled,
  first-in-window-no-keyerror) are re-expressed against the new surface.
  The behaviors they test are unchanged; only the recording surface changes.
- The `NotImplementedError` block is removed. New tests cover DIAGNOSTIC:
  (a) `ComponentOutputs` branch: `store_diagnostics` called,
  `apply_tendencies` not called; (b) `None` branch: component not run,
  warning logged if active.
- New: setup-time validation tests (unit mismatch, missing `kind`, missing
  `units`).
- New: per-call key-presence test (missing input key -> error).
- New: read-only flag test (mutation attempt -> `ValueError`).

**`muphys/tests/.../test_component_datatest.py` (datatest, signature
update):**
- `granule(state, _T0)` -> `granule.run(MuphysInput(...),
  datetime.timedelta(seconds=experiment.dt))`.
- The assertion (`te0 + out.tendencies["tend_temperature"].asnumpy() * dt`,
  atol=1e-15) is unchanged in spirit; the output is now accessed via
  `ComponentOutputs.tendencies`.

**`model/common/tests/common/components/unit_tests/` (currently empty):**
- New conformance tests (fast, no data):
  `isinstance(MuphysComponent(...), Component)`,
  `isinstance(SaturationAdjustment(...), Component)`,
  `isinstance(NoAdvection(...), Component)`.
- These verify AC3, AC4, AC5.

**Advection tests and standalone driver (call-site updates, part of the
Advection conformance delta):**
- `standalone_driver.py:268` updates to the dataclass-in signature.
- `test_advection.py` and `test_parallel_advection.py` (integration tests)
  update call sites.
- These are flagged as the largest blast radius and are required for AC5.

## Log line
Architect (amended): 11 decisions (D1-D11), superseding prior D1-D9. Key changes: per-component frozen dataclass state (D2), ComponentOutputs structured return (D5), layered checking (D4), read-only numpy flag (D10), setup-time unit validation (D11). All prior open questions resolved.
