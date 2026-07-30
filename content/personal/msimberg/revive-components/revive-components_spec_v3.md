---
title: Revive components - spec v3
author: msimberg
tags: [components, model-state, protocol, interface, design, spec, composition]
created: 2026-07-29
updated: 2026-07-29
status: draft
---

# SPEC: Component composition layer (v3)

> Status: v3 PROPOSAL - NOT FROZEN. This document supersedes the v2 spec
> (the full v2 text is preserved in this knowledge repo's
> [[personal/msimberg/revive-components/revive-components_spec|v2 spec]]).
> v1 and v2 are summarized in Appendix A. The open questions at the end must be
> resolved before this design can be frozen. No implementation code has been
> changed yet; this is a design exploration recorded for review.

## Introduction

icon4py implements the ICON atmospheric model in Python using GT4Py stencil
operators. It already declares a `Component` Protocol in
`model/common/src/icon4py/model/common/components/`, but the protocol is a
stub: the abstract methods are unimplemented, the open TODOs are unresolved,
and no concrete component in the codebase adopts it. As a result the model
driver is hand-coded and the per-package component signatures (dycore,
diffusion, advection, physics) have drifted apart.

v3 proposes a **composition layer above `Component`**. The high level is
chaining, looping, branching, and composing components into a directed graph.
I/O is a component that only takes inputs. Type conversions are separate
components, inserted automatically by a bounded registry. The physics
specific machinery that earlier revisions kept inside a shared orchestrator
(tendency application, `ForcingMode`, the recycle cache) moves *up* into named,
inspectable graph nodes, so the component interface itself stays
physics-agnostic.

Goal and scope: make the stub `Component` interface real, general, and
long-lived, and validate the design by making `MuphysComponent`,
`SaturationAdjustment`, and `Advection` conform. Touch the physics orchestrator
only as needed for internal consistency. For this design pass YAGNI, "minimal
change", and scope are explicitly suspended: the target is the globally best,
simplest interface, and every existing decision may be reconsidered. A real
(non-Python) DSL was considered and rejected; the authoring surface is a
plain-Python embedded DSL that builds a graph.

The rest of this document defines four design points (D0 today, D1, D2, D3) in
the next section, then treats each in detail. The central finding is that the
**primitives are defined once and are stable across D1 through D3**: D3 is a
non-breaking addition on top of D2, not a fork. D2 and D3 are compared
precisely in "The D2-D3 relationship" near the end.

## The design space: D0 to D3

The design is explored as four points on a spectrum, from the hand-coded
driver today to a fully serializable graph IR. Each point is defined by what
the framework *does* with the same component declarations.

- **D0, today.** The driver is a hand-coded method. There is no enforced
  component protocol at runtime; dycore, diffusion, advection, and physics are
  called directly with bespoke signatures. State is a double-buffered
  `TimeStepPair[PrognosticState]` swapped once per step.
- **D1, no-IR embedded DSL.** The substrate (the `Component` contract,
  `FlowKind`, `CarrySpec`, and the combinators `chain`/`loop`/`when`/`fanout`/
  `sampler`) is introduced with a single live executor. A graph is a transient
  in-process object you call directly. Lambdas and closures are first-class.
  Components mutate a shared `Carry` in place.
- **D2, introspectable steps.** The live steps carry structure (a chain is a
  `list[Step]`, each exposing `inputs()`/`outputs()`), so the whole graph can
  be validated, shown, and exported. The export is opt-in and lossy: it fails
  loud on lambdas.
- **D3, serializable IR.** A projection maps each live `Step` to a
  serializable `Node`/`Edge` IR (callables as `module:qualname` handles). A
  second, deferred-instantiation interpreter validates the serialized graph
  before any component is constructed, then runs it. A config file lowers to
  the same IR.

D1, D2, and D3 share one substrate and one authoring surface. D2 keeps D1's
live executor and adds structure on the live steps; D3 adds a projection and a
second interpreter. **A D3 graph is a special case of a D2 graph**: one that
uses only named callables, so it round-trips through `export()` and
`from_serializable()`. You author the same `Step` graph at D1/D2 and add D3 as
an opt-in layer when a graph should be frozen to a config file or
checkpointed. The one thing that cannot move from D2 to D3 is a lambda, and
that is a projection constraint (raised loud), not a primitive
incompatibility. So "full IR" is not synonymous with "abstract primitives":
`Component`, `CarrySpec`, the combinators, `FlowKind`, and the conversion
registry are identical at D2 and D3.

The sections that follow treat D0 (the concrete baseline), the stable
substrate, then D1, D2, and D3 in detail.

## The driver today (D0)

The current driver is hand-coded and heterogeneous. There is no enforced
component protocol that the runtime uses: `MuphysComponent` is near the
`Component` stub (dict `__call__`), but `SolveNonHydro`, `Diffusion`,
`Advection`, and `SaturationAdjustment` all have bespoke signatures and are
called directly. State is a double-buffered `TimeStepPair[PrognosticState]`
swapped once per step; diagnostic and prep states pass separately; physics
hides its own `PhysicsState` adapter and `ForcingMode`/recycle machinery.

### Example E1: standalone driver outermost loop

`Icon4pyDriver.time_integration(self, ds: DriverStates, do_prep_adv: bool) -> None`
(`standalone_driver.py:139`). It loops over `n_time_steps` and each iteration
calls `_integrate_one_time_step(...)`, which runs the dycore substep loop,
`Diffusion.run(...)`, the per-tracer `tracer_advection.run(...)` loop,
`physics.run(...)`, then `prognostic_states.swap()`. State comes from
`DriverStates` (`driver_states.py:66`): `prognostics: TimeStepPair[PrognosticState]`,
plus `prep_advection_prognostic`,
`solve_nonhydro_diagnostic`, `diffusion_diagnostic`,
`tracer_advection_diagnostic`, `prep_tracer_advection_prognostic`, and
`diagnostic`. Time bookkeeping is `ModelTimeVariables` (`driver_states.py:89`):
`dtime`, `ndyn_substeps_var`, `is_first_step_in_simulation`, `cfl_watch_mode`,
`n_time_steps`, `simulation_current_datetime`.

### Example E2: physics driver

```python
PhysicsDriver.run(self, prognostic, tracers, dtime: timedelta,
                  simulation_current_datetime: datetime) -> None
```

(`physics_driver.py:80`). For each registered `PhysicsProcess`
(`physics_driver.py:50`: `name`, `component`, `state: PhysicsState`,
`time_control: ProcessTimeControl`, `forcing_mode: ForcingMode = APPLY`), it
checks `ProcessTimeControl.is_in_window(dt)`
(`process_time_control.py:17`, `start_date <= dt < end_date`) and
`is_active(dt)` (`elapsed % interval == 0`). If active or not yet cached, it
calls `state.as_component_input()` (a dict, `physics_state.py:20`), runs the
component, and stores the dict in `_recycle_cache: dict[str, dict[str, Any]]`
(`physics_driver.py:78`); otherwise it recycles the cached dict. Tendencies are
scattered back by `state.scatter_to_prognostic(...)` when
`forcing_mode == APPLY`. `ForcingMode {DIAGNOSTIC=0, APPLY=1}`
(`physics_driver.py:29`): DIAGNOSTIC computes but does not apply.

### Example E3: dycore sub-stepping loop

```python
SolveNonHydro.time_step(
    self, *,
    diagnostic_state_nh, prognostic_states: TimeStepPair[PrognosticState],
    prep_adv, second_order_divdamp_factor, dtime: float,
    ndyn_substeps_var: int, at_initial_timestep: bool, lprep_adv: bool,
    at_first_substep: bool, at_last_substep: bool, is_iau_active=False,
    iau_wgt=0.0,
) -> None
```

(`solve_nonhydro.py:1113`). The driver calls this `ndyn_substeps_var` times per
outer step with `substep_timestep = dtime_in_seconds / ndyn_substeps_var`.
After the substeps,
`_adjust_ndyn_substeps_var` recomputes `ndyn_substeps_var` from
`global_reductions.max(max_vertical_cfl)` for the next outer step. The count is
runtime-varying.

### Example E4: tracer advection fanout

```python
Advection.run(
    self, *,
    diagnostic_state: AdvectionDiagnosticState, prep_adv: AdvectionPrepAdvState,
    p_tracer_now: CellKField, p_tracer_new: CellKField, dtime: wpfloat,
) -> None
```

(`advection.py:140` ABC; `:200` `NoAdvection`). It
mutates `diagnostic_state` and `p_tracer_new` in place and returns `None`. The
driver loops over the active tracers calling `tracer_advection.run(...)`, a
hand-rolled fanout.

### D0 costs (the baseline this design improves)

- Inflexibility: every experiment edits `_integrate_one_time_step`.
- Hidden dataflow: the orchestrator cannot see what each component reads or
  writes (the v1 review's R3); diagnostics mutated by reference bypass the
  output contract.
- No enforced contract: the five call sites have five different signatures.
- No validation before the first eager stencil compile (D3 notes why this
  matters).

## The stable substrate (Layer 0): primitives that work across D1-D3

Everything in this part is defined once and does not change when you move from
D1 to D2 to D3. D2 and D3 only add new *consumers* of these declarations.

### The Component contract (v3; supersedes the dict stub and v2)

The current stub (`components.py:21-106`) is:

```python
__call__(self, state: dict[Ins, model.DataField], time_step: datetime) -> dict[Outs, model.DataField]
```

with dict-valued `inputs_properties` / `outputs_properties`. v3 supersedes it:

```python
class Component(Protocol[InputT, OutputT]):
    inputs_properties:  ClassVar[dict[str, model.FieldMetaData]]  # derived from InputT
    outputs_properties: ClassVar[dict[str, model.FieldMetaData]]  # derived from OutputT

    def run(self, state: InputT) -> OutputT: ...   # NO dtime positional arg
```

- `InputT` and `OutputT` are `@dataclasses.dataclass(frozen=True)`. Each field
  carries metadata `{standard_name, units, kind, dims}`. The dataclass is
  frozen (you cannot reassign a field) but the underlying GT4Py field object
  keeps a mutable `.ndarray` buffer, so in-place components can mutate the
  buffer they were handed.
- `dtime` is a field of `InputT` with `kind="parameter"` for components that
  need it (EulerStep, dycore). Most components do not declare it. This replaces
  both the stub's `time_step` positional arg and v2's `run(state, dtime)`.
- `outputs_properties` is derived from `OutputT` field metadata at the class
  level (no instance needed), so a validator can read it before any component
  is constructed.

### FlowKind and field metadata

```python
class FlowKind(enum.Enum):
    PROGNOSTIC = "prognostic"  # threaded across steps (the current generation)
    TENDENCY   = "tendency"    # a rate consumed by an explicit apply (EulerStep)
    DIAGNOSTIC = "diagnostic"  # output-only, never applied
    IN_PLACE   = "in_place"    # buffer the component mutates; output declares it
    PARAMETER  = "parameter"  # scalar provided each step (dtime, datetime, flags)
```

`FlowKind` is a per-field contract marker used by validation and
auto-conversion. It is **not** the execution substrate at any level: at D1/D2
the shared `Carry` is the substrate; at D3 the carry is represented as
`delay=1` feedback edges in the IR, still not by `FlowKind` alone. A mislabeled
`kind` changes what `validate` reports, not what runs.

### CarrySpec and the Carry

```python
@dataclasses.dataclass(frozen=True)
class CarrySpec:
    name: str
    kind: FlowKind               # PROGNOSTIC (double-buffered) or IN_PLACE
    buffering: Literal["double", "in_place"] = "double"
    initial: Any = None
```

`CarrySpec` declares a threaded slot once. At D1/D2 the executor allocates a
mutable `Carry` object with `{name}_current` / `{name}_next` for a
double-buffered slot, or a single `{name}` buffer for an in-place slot, and the
`loop` owns the current-to-next promotion. At D3 the same `CarrySpec` projects
to a `delay=1` feedback edge. One declaration, two interpreters.

This is a faithful lift of what the driver already threads
(`driver_states.py:66-103`): `DriverStates.prognostics: TimeStepPair[PrognosticState]`
becomes a `CarrySpec("prognostics", PROGNOSTIC, buffering="double")`; the
diagnostic/prep states become `CarrySpec(..., IN_PLACE)` slots.
`ModelTimeVariables` (dtime, ndyn_substeps_var, is_first_step_in_simulation,
cfl_watch_mode) becomes parameter fields on the carry.

### Step (provisional; see Naming)

```python
StepResult: TypeAlias = None | Mapping[str, Any]   # {field_name: value} for produced fields

class Step(Protocol):
    name: str
    def inputs(self)  -> list[Port]: ...
    def outputs(self) -> list[Port]: ...
    def __call__(self, carry: Carry) -> StepResult: ...
```

A `Component` is adapted into a `Step`: the adapter builds `InputT` from the
carry fields, calls `component.run`, and routes `OutputT` by `kind`
(tendency onto `carry.tendencies`, diagnostic onto `carry.diagnostics`, in-place
nothing because the mutation already happened on the carry buffer the component
was handed). This is the v2 `split_outputs` idea, generalized to the carry and
no longer physics-specific.

At D3 a `Step` projects to a serializable `Node` (same shape, live callables
replaced by handles). `Step` is the supertype; `Node` is a projection of it,
not a second type you migrate to.

### Combinators

All return `Step`. Signatures and semantics are identical at D1, D2, D3.

```python
def chain(*steps: Step, name: str | None = None) -> Step: ...
def fanout(*branches: Step) -> Step: ...                  # I/O side branch, does not consume
def when(pred: Callable[[Carry], bool], then: Step, else_: Step | None = None) -> Step: ...
def branch(value: Callable[[Carry], K], cases: dict[K, Step], default: Step | None = None) -> Step: ...
def loop(body: Step, schedule: Schedule, *, carry: Sequence[CarrySpec],
         dtime: Callable[[Carry], float] | None = None,
         stop_signals: Sequence[str] = (), post: Step | None = None,
         name: str | None = None) -> Step: ...
def sampler(source: Step, schedule: Schedule, *, name: str | None = None) -> Step: ...
def compose(name: str, body: Step) -> Step: ...           # name a subgraph as one reusable Step
def connect(from_: str, to: str) -> Step: ...              # explicit carry route (validation/export)
def adapt(component: Component, ...) -> Step: ...          # wrap a Component into a Step
def derive(component: Component, converter: Component, ...) -> Step: ...  # output-side conversion
```

`loop` owns the current-to-next feedback (a closure over the carry) and the
active `dtime`. `schedule.steps` is an `int` (fixed count) or a
`Callable[[Carry], int]` (runtime-varying, e.g. CFL). `sampler` owns a firing
interval and recycles the last output on non-firing steps (replaces
`PhysicsDriver._recycle_cache`).

### Auto-conversion (bounded, fail-loud)

A closed registry of converters (each a `Component` with its own input/output
ports). When a producer output and a consumer input disagree on
`(standard_name, units, dims, kind)`, the framework looks up the registry:
exactly one match inserts a converter `Step` (logged); zero or more than one
fails loud with the candidate list. Same rule at every level. At D3 the
inserted converter must be a named callable to survive `export()`; otherwise
the projection fails loud naming the converter.

### The two disciplines that make D1 forward-compatible to D3

1. **Every component declares an output dataclass *type*** (with `kind` on
   fields). The instance return is optional: at D1/D2 an in-place component may
   mutate its handed buffer and return `None`; the framework reads the output
   *type* to know what changed. At D3 the component returns the instance
   (identity-checked) for the value-on-edges projection. Because the *type* is
   always declared, going from D1 to D3 does not change the component's
   declarations; D3 just reads them differently.
2. **`dtime` is a field of `InputT`, never a positional arg.** This is the one
   rule that lets the same component run at D1 (dtime set on the carry by the
   loop) and at D3 (dtime a `PARAMETER` port in the IR). v2's `run(state, dtime)`
   is the forward-incompatible form and is superseded.

Neither discipline is the no-lambda tax. That tax appears only at `export()`
time (projection), never at authoring time.


## D1: no-IR embedded DSL (live steps, lambdas first-class, in-place carry)

D1 introduces the Layer 0 substrate and a single live `Step` executor. A
graph is a transient in-process object: `chain(...)` returns a `Step` you call
directly. Lambdas and closures are first-class (inline predicates, one-off
converters). Components mutate the shared `Carry` in place; the in-place
majority idiom is first-class.

### Example E1 in D1

```python
dycore_substeps = loop(                                    # E3, above
    body=solve_nonhydro_step,
    schedule=Schedule(steps=lambda c: c.clock.ndyn_substeps_var),
    dtime=lambda c: c.clock.dtime_in_seconds / c.clock.ndyn_substeps_var,
    carry=[CarrySpec("prognostics", FlowKind.PROGNOSTIC, initial=prog0),
           CarrySpec("solve_nh_diag", FlowKind.IN_PLACE, initial=nhdiag0),
           CarrySpec("prep_adv",      FlowKind.IN_PLACE, initial=prep0)],
    name="dycore_substeps",
)

physics_windowed = when(                                   # E2, above
    lambda c: physics_window.contains(c.clock.simulation_current_datetime),
    then=physics_apply,
    else_=physics_diagnose,
)

one_step = chain(advance_clock, dycore_substeps,
                 diffusion_step, tracer_advection_fanout,  # E4, above
                 physics_windowed, adjust_ndyn)

driver = loop(
    body=one_step,
    schedule=Schedule(steps=lambda c: c.clock.n_time_steps),
    dtime=lambda c: c.clock.dtime,
    carry=[CarrySpec("prognostics", FlowKind.PROGNOSTIC, initial=prog0),
           CarrySpec("dycore_diag",  FlowKind.IN_PLACE, initial=dydiag0),
           CarrySpec("prep_adv",     FlowKind.IN_PLACE, initial=prep0),
           CarrySpec("adv_diag",     FlowKind.IN_PLACE, initial=advdiag0)],
    post=fanout(io_snapshot),                               # I/O sink after swap
    name="icon4py_driver",
)
driver.run(initial_carry)
```

`advance_clock` maps to `ModelTimeVariables.advance_simulation_datetime()`;
`adjust_ndyn` maps to `_adjust_ndyn_substeps_var`. The `prognostics.swap()` that
today sits at the end of `_integrate_one_time_step` is now the loop's
current-to-next feedback (owned by `loop`, not a step).

### Example E2 in D1

```python
physics_compute = chain(muphys_step, satadj_step, theta_to_temperature_tendency)
physics_apply    = chain(physics_compute, euler_step)
physics_diagnose = chain(physics_compute, store_diagnostics_step)  # no apply
physics_windowed = when(lambda c: physics_window.contains(c.clock.simulation_current_datetime),
                        then=physics_apply, else_=physics_diagnose)

muphys_recycled = sampler(physics_windowed,
                          Schedule(interval=physics_interval,
                                   start=physics_window.start_date,
                                   end=physics_window.end_date),
                          name="muphys_scheduled")
```

`physics_apply` and `physics_diagnose` are two explicit chains; the diagnose
chain is `physics_compute` plus a `store_diagnostics_step` (built explicitly,
no `ForcingMode` enum, no graph transform). `sampler` owns the firing interval
and recycles the last output on non-firing steps, replacing
`PhysicsDriver._recycle_cache`. `theta_to_temperature_tendency` is the phy2dyn
converter (temperature tendency to theta_v tendency, pulling `exner`); at D1 it
can be an inline lambda or a registered component.

### Example E3 in D1

```python
solve_nonhydro_step = adapt(SolveNonhydro(), ...)        # wraps time_step

dycore_substeps = loop(
    body=solve_nonhydro_step,
    schedule=Schedule(steps=lambda c: c.clock.ndyn_substeps_var),  # runtime-varying
    dtime=lambda c: c.clock.dtime_in_seconds / c.clock.ndyn_substeps_var,
    carry=[CarrySpec("prognostics", FlowKind.PROGNOSTIC, initial=prog0),
           CarrySpec("solve_nh_diag", FlowKind.IN_PLACE, initial=nhdiag0),
           CarrySpec("prep_adv",      FlowKind.IN_PLACE, initial=prep0)],
    stop_signals=("solve_nh.cfl_safe",),                   # per-iteration early stop (optional)
    name="dycore_substeps",
)

# Fixed-interval variant (int, not callable):
dycore_fixed = loop(solve_nonhydro_step,
                    Schedule(steps=cfg.ndyn_substeps,
                             dtime=lambda c: c.clock.dtime_in_seconds / cfg.ndyn_substeps),
                    carry=[...], name="dycore_fixed")
```

`steps` as a `Callable` re-reads `ndyn_substeps_var` each outer step (the
value `_adjust_ndyn_substeps_var` mutates). `substeps` and the nested-loop form
(see Open questions, Q3) are both available.

### Example E4 in D1

```python
def _advect_one(carry, tracer_name):
    p_now = getattr(carry.prognostics.current.tracer, tracer_name)
    p_new = getattr(carry.prognostics.next.tracer,    tracer_name)
    tracer_advection.run(diagnostic_state=carry.adv_diag,
                         prep_adv=carry.prep_adv,
                         p_tracer_now=p_now, p_tracer_new=p_new,
                         dtime=carry.dtime_seconds)
    return None                                             # in-place; returns nothing

tracer_advection_fanout = fanout(
    *[adapt("advection." + t, lambda c, tn=t: _advect_one(c, tn)) for t in active_tracers]
)
```

The per-tracer hand-rolled loop becomes a `fanout` over `active_tracers`. Each
branch is an in-place component returning `None`; the output *type*
(`AdvectionOutput` with `diagnostic_state, p_tracer_new` both `kind="in_place"`)
declares what changed for validation.

### What D1 gains over D0

- A reusable composition vocabulary (chain/loop/when/fanout/sampler) so
  scientists reorder or recombine physics without editing the driver method.
- The in-place majority idiom is first-class and explicit; mutation is declared
  on the output type, addressing v1 R3 (hidden dataflow) at the declaration
  level.
- ForcingMode dissolves into two explicit chains plus a `when`, which is
  closer to the per-step `is_in_window` runtime check than v2's modal approach.
- Lambdas and closures are first-class, matching the script/notebook
  authoring reality.

### What D1 loses or carries forward

- No serialization: an inline-lambda graph cannot round-trip to a config file.
  `export()` does not exist at D1.
- No whole-graph validation: per-edge checks at composition time catch local
  mismatches, but there is no single global view, so a read-only field mutated
  at step 4 by a non-adjacent component is not caught (v1 R5 partly open).
- The framework still cannot, in general, *prove* a component did not mutate a
  field it declared read-only; read-only is a debugging aid that surfaces
  accidental writes, not a hard guarantee on a shared mutable carry.

## D2: introspectable steps (whole-graph view, opt-in export)

D2 keeps D1's live executor and adds **structure on the live steps**: a chain
is a `list[Step]`, each `Step` exposes `inputs()` / `outputs()`. Nothing about
the components or the substrate changes; the steps now carry enough structure
to support whole-graph validation, inspection, and an opt-in, lossy export.

### What D2 adds over D1 (same examples)

```python
g = compose("icon4py_driver", driver)                     # driver is the D1 loop from 3.1
g.validate(registry)                                       # whole-graph schema + flow check
print(g.show())                                            # who writes rho, what step 3 reads
physics_apply2, physics_diagnose2 = physics_apply, drop_last(physics_apply, expect="euler")
assert g.validate(registry) is clean                       # diagnose chain reuses the prefix
cfg = g.export()                                           # opt-in, lossy: fails loud on lambdas
```

`drop_last(chain, expect="euler")` builds the diagnose chain from the apply
chain by name, so the two cannot drift the way two hand-maintained chains can.
`validate(registry)` walks all steps: every declared input is sourced (or is a
parameter), every `TENDENCY` output is consumed by an apply role, no
read-declared field is mutated by a later step, converter availability is
satisfied. `export()` lowers the graph to a serializable dict but **fails loud
on any lambda or unnamed callable**, so the export is honest about what it can
reproduce.

### What D2 gains over D1

- Whole-graph validation (the v1 review's core complaint): the framework can
  answer "who writes `rho`" and "what does step 3 read," and catch a
  read-declared field mutated by a non-adjacent step.
- `show()` for debugging in a notebook, and `drop_last()` so the APPLY and
  DIAGNOSE chains share a prefix by construction.
- An opt-in `export()` that keeps the path to a config file open without
  forcing it: scientists author with lambdas daily, and name callables only
  when they want to freeze a graph.

### What D2 loses or carries forward

- The export is **lossy**: a graph built with lambdas cannot be serialized, and
  the framework does not keep provenance for auto-inserted converters (the
  registry holds live callables), so a frozen config cannot reproduce an
  inserted converter that was a lambda.
- Validation still runs after construction (stencils compile eagerly at
  `__init__` via `setup_program`, `model_options.py:156`), so a wiring error
  caught by `validate` is found after the first slow compile, not before. This
  is reconcilable later (Open questions, Q6) and the user has deferred it.

## D3: serializable IR (projection plus second interpreter plus config)

D3 adds a **projection** from live `Step` to a serializable `Node`/`Edge` IR,
and a **second interpreter** that reconstructs components from `(Type, args)`
or registry keys, validates the serialized graph before any component is
constructed, and runs it. A config file lowers to the same IR. Nothing about
Layer 0 changes; D3 is a new consumer of the same declarations.

### The projection

```python
@dataclasses.dataclass(frozen=True)
class NodeIR:
    id: str
    component_key: str | None = None        # "mypkg.muphys:MuphysComponent" (no live object)
    factory_args: dict[str, Any] = dataclasses.field(default_factory=dict)
    inputs:  tuple[PortIR, ...] = ()
    outputs: tuple[PortIR, ...] = ()

@dataclasses.dataclass(frozen=True)
class EdgeIR:
    src: PortRef; dst: PortRef
    converter_key: str | None = None
    delay: int = 0                           # 1 for carry feedback edges

@dataclasses.dataclass(frozen=True)
class GraphIR:
    nodes: tuple[NodeIR, ...]
    edges: tuple[EdgeIR, ...]
    parameters: dict[str, Any]
```

`export()` (D2's lossy version) becomes lossless for named-callable graphs: it
projects each `Step` to a `NodeIR`, replacing the live component with a
`component_key` and the `CarrySpec` slots with `delay=1` feedback `EdgeIR`s.
`from_serializable(ir, registry)` reconstructs a live graph by resolving keys,
then validates the serialized graph **before constructing any component**, then
constructs. This is the single benefit D3 adds over D2 that D2 cannot provide:
a wiring error is caught before the first eager stencil compile.

### Config file (lowers to the same IR)

```yaml
name: icon4py_driver
loop:
  steps: 2400                              # graph-level stop, literal
  carry: [prognostics, dycore_diag, prep_adv, adv_diag]
  body:
    chain:
      - { component: mypkg.driver:advance_clock }
      - loop:
          steps: ref:mypkg.driver:ndyn_substeps_from_cfl   # callable: state -> int
          dtime: ref:mypkg.driver:substep_dtime            # callable: state -> float
          body: { component: mypkg.dycore:SolveNonhydro }
      - { component: mypkg.diffusion:Diffusion }
      - fanout: [{ component: mypkg.advection:TracerAdvection, over: active_tracers }]
      - when:
          pred: ref:mypkg.physics:in_forcing_window         # callable: state -> bool
          then:  { chain: [mypkg.physics:Muphys, mypkg.physics:SaturationAdjustment,
                           mypkg.physics:ThetaToTemperatureTendency, mypkg.update:EulerStep] }
          else_:  { chain: [mypkg.physics:Muphys, mypkg.physics:SaturationAdjustment,
                            mypkg.physics:ThetaToTemperatureTendency, mypkg.update:StoreDiagnostics] }
      - { component: mypkg.driver:adjust_ndyn }
  post: { sink: { component: mypkg.io:IoSnapshot } }
```

Structure and literals are inline; anything runtime-varying or non-trivial
(CFL substep count, forcing-window predicate, converters) is a `ref:` to a
named Python callable. The parser resolves every `ref:` against the closed
registry at load and fails loud on missing or ambiguous names.

### The D2-D3 relationship

They do **not** collapse into one design. D2 has one live interpreter and
allows lambdas; D3 has a projection plus a second (deferred-instantiation)
interpreter and requires named callables for the projection to succeed. But D3
is a **non-breaking addition**: you author the same `Step` graph in both, and
a D3 graph is a D2 graph that uses only named callables. The lower-level
primitives (Component contract, CarrySpec, combinators, FlowKind, the
conversion registry) are identical. The only thing that cannot move from D2 to
D3 is a lambda, and that is a projection constraint (raised loud), not a
primitive incompatibility.

So the practical layering is: **author at D1/D2 with lambdas; add D3 as an
opt-in layer when (and only when) a graph should be frozen to a config file or
checkpointed.** No component or primitive changes to make that step.

### What D3 gains over D2

- A wiring error is caught before the first eager stencil compile
  (deferred-instantiation validation against the serialized graph). This is the
  one D3 benefit D2 cannot provide without the IR.
- A serializable graph: a config file for frozen runs, and a checkpointable
  experiment topology (`git_ref + script_path + config_hash`), with no rework
  to the authoring layer.

### What D3 loses

- The no-lambda discipline applies to any graph you want to freeze. For a
  research code authored in scripts and notebooks with inline predicates, that
  is a real tax on the throwaway majority to serve the frozen minority.
- Carrying cost: IR types, (de)serialization, `component_key` resolution, a
  build phase, identity-checked in-place returns. Much of it has no current
  user in icon4py given fixed topology per run and script-and-git authoring.

## What each design point adds (consolidated, in detail)

**D0 to D1.** Adds the Layer 0 substrate (Component contract with dtime as a
field, FlowKind, CarrySpec, the combinators, the bounded conversion registry)
and a single live `Step` executor. The driver stops being a hand-coded method
and becomes a composed graph. Gained: reusability, explicit declared mutation
(addressing v1 R3 at the declaration level), ForcingMode dissolved to two
chains plus `when`, lambdas first-class. Lost: the flat grep-able method as
single source of truth (a mild loss today; real once a second physics package
arrives). Carried forward: no serialization, no whole-graph validation,
read-only is a best-effort aid.

**D1 to D2.** Adds structure on the live steps (a chain is a `list[Step]`,
each exposing `inputs()`/`outputs()`), enabling `validate(registry)`,
`show()`, and `drop_last()`; and an opt-in, lossy `export()`. Nothing about
components or the substrate changes. Gained: whole-graph validation and
inspection (the v1 review's core complaint), and a non-drifting diagnose chain
via `drop_last`. Lost: none new; the export is lossy and validation still runs
after eager compilation.

**D2 to D3.** Adds a serializable `Node`/`Edge` projection (lossless for
named-callable graphs), a deferred-instantiation second interpreter that
validates before construction, and a config file lowering to the IR. Gained:
pre-compile wiring validation (unique, load-bearing because stencils compile
eagerly at `__init__`), and a frozen config/checkpoint surface. Lost: lambdas
are banned from any frozen graph; the largest carrying cost in the design,
much of it without a current user given fixed topology and script authoring.

## Supersessions of v2 (named, not silent)

| v2 item | v2 decision | v3 | Action |
|---|---|---|---|
| V2-D1 / AC1 | `run(self, state: InputT, dtime: dt.timedelta) -> OutputT` | `run(self, state: InputT) -> OutputT`; dtime is a `PARAMETER` field | Supersede |
| V2-D2 | Per-component frozen input/output dataclasses | Retained; output **type** required, instance return optional | Refine |
| V2-D3 | Metadata on dataclass fields; properties derived | Retained; properties derived at class level for pre-construction validation | Retain |
| V2-D4 | Components always return an output dataclass; in-place returns the mutated buffer (identity-checked) | Output **type** required; returning the instance is an optional validation aid (identity-checked at D3) | Refine (relax) |
| V2-D5 | Orchestrator dispatches by output field `kind` | Dispatch by `kind` removed; applying a tendency is an explicit `EulerStep` component | Supersede |
| V2-D6 | `ForcingMode.DIAGNOSTIC` behavior in the orchestrator | `ForcingMode` removed; APPLY/DIAGNOSE is a runtime `when` over two explicit chains | Supersede |
| V2-D7 | Per-field read-only inputs | Retained as an explicit per-field `read_only` flag on the declaration (best-effort on a shared mutable carry) | Retain |
| V2-D8 | `convert_state` helper | Becomes an explicit converter component/graph node with the same name-matching plus `overrides` semantics | Refine |
| V2-D9 | Keep physics orchestrator names | `PhysicsDriver` becomes a graph; `PhysicsState` survives as the per-process adapter seam; `ProcessTimeControl` survives as the `sampler` schedule source; `ForcingMode` removed | Partial supersede |
| AC8/AC10/AC11 | `PhysicsState.apply_tendencies`/`store_diagnostics`; `PhysicsDriver.run` dispatch | Tendency application is an `EulerStep` node; storage is an `IoSnapshot`/`StoreDiagnostics` sink; no orchestrator dispatch | Supersede (mechanism) |
| v2 O1 | `in_place` `kind` semantics | Resolved: `FlowKind = {prognostic, tendency, diagnostic, in_place, parameter}`; in-place declares mutated buffers on the output type | Resolve |
| v2 O4 | Validate in-place outputs | Resolved: identity check at D3 (instance returned); at D1/D2 the type declares mutation and read-only is best-effort | Resolve |
| v2 O5 | Recycle cache for in-place | Resolved: in-place needs no recycle; the `sampler` node owns firing-interval recycle for scheduled processes | Resolve |

## Open questions

- **Q1 (explicit vs derived properties).** Keep v2-O3 open: derived from dataclass fields by default, with an explicit override. Best guess: a mixin providing derivation with an override hook.
- **Q2 (loop-context flags).** `at_initial_timestep`, `at_first_substep`, `at_last_substep`, `lprep_adv` are parameters today (`solve_nonhydro.py:1113`). Model as individual `PARAMETER` fields or one structured `LoopContext` field provided by `loop`? Best guess: one structured `LoopContext` to avoid flag proliferation.
- **Q3 (substeps primitive vs nested loop).** Keep both `loop.substeps` (int or callable) and a nested `loop` with its own dt, per the original default-9 exploration. Best guess: keep `substeps` for the common case; require a nested `loop` only when the substep region has a distinct body.
- **Q4 (per-iteration stop semantics).** Does a `stop_signals` port stop the current loop after this iteration or an inner substep loop? Best guess: scope-bound; a signal declared on a `loop` stops that loop after the current iteration, mirroring today's CFL watch-mode leave logic.
- **Q5 (sampler vs when overlap).** `sampler` owns the firing interval plus recycle; `when` owns the structural APPLY/DIAGNOSE branch. Compose them: `when(window, then=apply, else_=diagnose)` wrapped in `sampler(...)` for the firing interval. Best guess: as stated.
- **Q6 (pre-construction validation timing).** Stencils compile eagerly at `__init__` (`model_options.py:156`), so D2's `validate` runs after the first compile. A `(Type, args)` accepting combinator would let D2 validate class-level schemas before construction, capturing D3's main benefit without the IR. The user has deferred this; it is reconcilable later and non-breaking to add.
- **Q7 (D3 trigger).** When is freezing a graph to a config file actually worth the no-lambda tax for icon4py, given fixed topology per run and script-and-git authoring? Best guess: opt-in, only for frozen production runs and checkpointable experiment topologies; not the default authoring mode.
- **Q8 (carrying cost honesty).** Most of D3 (serialization, `component_key` resolution, build phase, identity-checked in-place returns) has no current user in icon4py. Is D3 worth carrying at all, or should it remain an explicitly opt-in, possibly never-built layer? Best guess: design the substrate so D3 is *possible* (Layer 0 disciplines 1 and 2), but do not build D3 until Q7 says yes.

## Naming: the composition primitive is called Step (provisional)

Throughout this document the composition primitive (formerly called `Stage`)
is named `Step`. The rename is provisional; see Q9 at the end of this section.

### Why Stage was dropped

`Stage` collided with two names already in icon4py's audience:

- Apache Spark calls a `Stage` a physical execution unit split at a shuffle
  boundary, not a logical graph node (https://spark.apache.org/docs/latest/cluster-overview.html).
- GT4Py itself calls `Stage` a compiler phase in `ffront/stages.py`
  (https://github.com/GridTools/gt4py). GT4Py has no runtime graph-of-work
  abstraction today; a `@program` is one sequential compiled unit.

`Stage` also reads as "a pipeline phase", not a named, typed node that mutates
a shared carry in place.

### Why Step (for now)

`Step` matches the climate and weather vocabulary scientists already use (time
step, RK step, physics step, substep). Metaflow names its logical node `@step`
and threads a shared mutable `self` carry (https://docs.metaflow.org/metaflow/basics),
the closest mainstream analogue to the in-place majority idiom. Sympl names its
time-advancer `Stepper` and its logical unit `step`
(https://sympl.readthedocs.io/en/latest/computation.html). Framed as "a
schedule of steps over a shared state", the API fits the in-place majority and
the runtime-varying `dtime` better than "a dataflow graph of immutable values".

### The cost of Step (open)

`step` is already a domain term in icon4py: the outer loop runs `n_time_steps`;
the dycore takes `ndyn_substeps_var` `substeps`; `substep_timestep` is the
inner dt. Naming the primitive `Step` relies on capitalization (`Step` the type
versus `step` the time step) and context, which is fragile in prose. This is
the principal reservation and the reason `Step` is provisional.

### Alternatives considered

- `Op` or `Operator`: the most reusable name for a typed, named, composable
  graph node (Dagster, TensorFlow, Ray DAG, and GT4Py's own `field_operator`).
  Rejected for now because it implies value-passing on edges, which fights the
  in-place majority idiom.
- `Task`: generic in workflow schedulers (Airflow, Prefect, Ray). Implies a
  stateless unit that returns a value, opposite of the in-place carry.
- `Node`: accurate for the graph projection (D3 lowers a `Step` to a `NodeIR`)
  but too abstract for the primary authoring surface.
- `Sender`: matches the C++ P2300 (std::execution) model of a lazy description
  of work connected to a receiver and then started. Rejected because a sender
  implies value channels, schedulers, and typed cancellation that `Step`
  deliberately excludes; misleading for scientists.

### The underlying pattern is standard (references)

"Describe a graph of work, then execute it" is well precedented; `Step` is one
instance of it, specialized for in-place physics. A few references, with the
name each uses for the node and the describe/execute split:

- C++ P2300 `std::execution`: `sender` and `receiver`; `connect` then `start`;
  output types via `completion_signatures`. No loop primitive, no shared
  mutable state (https://www.open-std.org/jtc1/sc22/wg21/docs/papers/2024/p2300r10.html).
- Dask: a task graph (a dict) plus separate schedulers; lazy `.compute()`
  (https://docs.dask.org/en/stable/spec.html). Closest to the D3 IR projection.
- Apache Beam: `PTransform` (node) and `PCollection` (edge); `Pipeline.run()`
  with a portable Runner; composite `PTransform.expand()`
  (https://beam.apache.org/documentation/programming-guide/).
- Dagster: `op` (typed inputs and outputs) inside a `graph` or `job`; describe
  then materialize (https://docs.dagster.io/concepts/ops-jobs-graphs/ops).
- Metaflow: `@step` over a shared mutable `self`; `foreach`, branching
  (https://docs.metaflow.org/metaflow/basics). Closest to the in-place carry.
- Sympl (CliMA): `TendencyComponent`, `DiagnosticComponent`, `Stepper`,
  `TendencyStepper`, and `UpdateFrequencyWrapper` (the analogue of `sampler`)
  (https://sympl.readthedocs.io/en/latest/computation.html). Closest direct
  climate-model analogue.
- PyTorch `torch.fx`: a `Graph` of `Node` objects traced from a function,
  executed by an `Interpreter` (https://pytorch.org/docs/stable/fx.html). The
  describe/execute plus second-interpreter split mirrors D3.

### Q9 (naming)

Is `Step` the right name given its collision with `step` and `substep` (the
domain terms), or should the primitive be `Op` (reusable, value-passing
framing) or `Node` (graph-projection framing) instead? Best guess: keep `Step`
provisionally and revisit once the in-place-versus-value-passing framing (the substrate
and the majority examples) is exercised by the three conformance targets
(`MuphysComponent`, `SaturationAdjustment`, `Advection`).

## Appendix A: v2 decisions (superseded, compact)

v2 made the `Component` interface real with: per-component frozen input/output
dataclasses (D2); `Component[InputT, OutputT]` with
`run(state, dtime) -> OutputT` (D1/AC1); metadata on dataclass fields (D3);
`@runtime_checkable` (D4); a shared `ComponentOutputs`-style return replaced by
per-component output dataclasses (D2/D4); `PhysicsState` gains
`apply_tendencies`/`store_diagnostics` and the orchestrator dispatches by
output field `kind` (D5/D6/AC8/AC10/AC11); per-field read-only inputs (D7);
`convert_state` helper (D8); keep physics orchestrator names (D9). v3 keeps the
frozen dataclasses, the per-field metadata, and the per-field read-only intent,
and supersedes the `run` signature, the `kind`-based dispatch, `ForcingMode`,
and the orchestrator's apply/store machinery by moving them up into named graph
nodes. The full v2 text is preserved in this knowledge repo's
[[personal/msimberg/revive-components/revive-components_spec|v2 spec]].

## Appendix B: canonical example source locations

- Standalone driver: `model/standalone_driver/src/icon4py/model/standalone_driver/standalone_driver.py:139` (`time_integration`), `driver_states.py:66` (`DriverStates`), `:89` (`ModelTimeVariables`); `model/common/src/icon4py/model/common/utils/_common.py:236` (`TimeStepPair`).
- Physics driver: `model/atmosphere/subgrid_scale_physics/physics_interface/src/icon4py/model/atmosphere/subgrid_scale_physics/physics_interface/physics_driver.py:80` (`run`), `:78` (`_recycle_cache`), `:50` (`PhysicsProcess`), `:29` (`ForcingMode`); `physics_state.py:20` (`PhysicsState`); `process_time_control.py:17` (`ProcessTimeControl`).
- Dycore: `model/atmosphere/dycore/src/icon4py/model/atmosphere/dycore/solve_nonhydro.py:1113` (`SolveNonHydro.time_step`).
- Advection: `model/atmosphere/advection/src/icon4py/model/atmosphere/advection/advection.py:140` (`Advection.run` ABC), `:200` (`NoAdvection.run`).
- Diffusion: `model/atmosphere/diffusion/src/icon4py/model/atmosphere/diffusion/diffusion.py:805` (`Diffusion.run`).
- Saturation adjustment: `model/atmosphere/subgrid_scale_physics/microphysics/src/icon4py/model/atmosphere/subgrid_scale_physics/microphysics/saturation_adjustment.py:217` (`SaturationAdjustment.run`).
- Muphys: `model/atmosphere/subgrid_scale_physics/muphys/src/icon4py/model/atmosphere/subgrid_scale_physics/muphys/component.py:160` (`__call__`), `:197` (returned dict).
- Component stub: `model/common/src/icon4py/model/common/components/components.py:21`.
- Eager compile: `model/common/src/icon4py/model/common/model_options.py:118` (`setup_program`), `:156` (`static_args_program.compile`).

## Appendix C: v2 to v3 changelog

| Topic | v2 | v3 |
|---|---|---|
| Where the usable API lives | The `Component` interface and a shared `PhysicsDriver` orchestrator | A composition layer above `Component`; the orchestrator becomes a graph of components |
| Tendency application | Orchestrator dispatches by output `kind`, calls `apply_tendencies` | An explicit `EulerStep` component in the graph; no orchestrator dispatch by `kind` |
| `ForcingMode` | Per-process runtime mode on `PhysicsProcess`; `DIAGNOSTIC` semantics kept | Dissolved: APPLY vs DIAGNOSE is a runtime `when` over two explicit chains; no `ForcingMode` enum |
| Recycle cache | `_recycle_cache: dict[str, dict[str, Any]]` inside `PhysicsDriver` | A `sampler` node owning the firing interval and last-output recycle |
| `dtime` | A fixed second argument of `run(state, dtime)` | A field of the input dataclass (a `PARAMETER` port); not a positional arg |
| Output contract | Components return a per-component frozen output dataclass; in-place returns the mutated buffer as an output port (identity-checked) | The output dataclass **type** is required (declares what changed, with `kind` on fields); returning the instance is an optional validation aid, not load-bearing |
| State threading | `TimeStepPair[PrognosticState]` swapped inside the orchestrator | A declared `CarrySpec`; the `loop` construct owns the current-to-next feedback |
| Component protocol | `Component[InputT, OutputT]` with `run(state, dtime) -> OutputT` | `Component[InputT, OutputT]` with `run(state) -> OutputT`; `dtime` is a field of `InputT` |
| Serialization | Not addressed | A projection (`export()`) to a serializable graph IR is an opt-in layer (D3); not required at D1/D2 |
