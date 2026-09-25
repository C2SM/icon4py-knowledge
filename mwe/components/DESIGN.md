# Components MWE: design

Minimal working example comparing today's component and state shape in icon4py
(`model_current`) with the proposed `State`/`Component` design (`model_proposed`).

## Goal

Show the proposed design in action next to the current one, without distraction:

- same quantities, same scalars, same arithmetic, same loop, same output;
- the only thing that differs is how components declare, receive and return data;
- `model_current` is a faithful trimmed copy of icon4py: real module paths, real
  class, method, attribute, argument and dict-key names, so the group can map every
  line to code they work on daily;
- both models read the same two-line `example.yaml`; `run.py` asserts equality
  over a four-config matrix, prints the proposed model's declared dataflow and
  counts how often each side computes `temperature` and `u`;
- both models pass `mypy --strict`.

Explicitly out of scope: real physics, real grids, halo exchange, restart, IO
cadence beyond "every step", introspection beyond one `dataflow()` print,
sequential update beyond the `PhysicsDriver(update=...)` stub, py2fgen.

## Scope

### Quantities (11)

| quantity      | dims    | role                                                              |
|---------------|---------|-------------------------------------------------------------------|
| `vn`          | Edge, K | prognostic, now/next pair, swapped per dynamics substep           |
| `w`           | Cell, K | prognostic, same pair (full levels here, half levels in icon4py)  |
| `rho`         | Cell, K | prognostic, same pair                                             |
| `exner`       | Cell, K | prognostic, same pair                                             |
| `theta_v`     | Cell, K | prognostic, same pair                                             |
| `qv`          | Cell, K | tracer, now/next pair, swapped once per time step                 |
| `mass_flx_me` | Edge, K | dycore output handed to tracer advection, never accumulated       |
| `temperature` | Cell, K | derived by a recipe when a process or IO asks; incremented and pushed into exner/theta_v as the processes' `Update` declares |
| `u`           | Cell, K | derived by a recipe; read by tmx, whose `Update` turns `tend_u` into a vn increment |
| `pflx`        | Cell    | muphys precipitation diagnostic                                   |
| `ddt_vn_apc`  | Edge, K | vn advective tendency, predictor/corrector pair inside the dycore |

Tendencies and increments are derived quantities (`tendency_of`, `increment_of`),
never declared by hand: `tend_temperature` (muphys, tmx), `tend_qv` (muphys),
`tend_u` (tmx), `ddt_vn_apc` (dycore, `Tendency[VnField]`, so no new registry
entry), and one increment per parent quantity that some configured process
emits a tendency for; the `Increments` state is assembled by `resolve`, never
written by hand.

### Scalars (7)

`dtime`, `substep_dtime`, `ndyn_substeps`, `step_index`, `simulation_time`
(datetime), `at_first_substep`, `at_last_substep`. Process cadences come from
the config (`example.yaml`: muphys every step, tmx every 2).

### Grid and data

4 cells, 6 edges, 3 levels. Fields are gt4py fields (`gtx.zeros`) so the type
aliases, mypy and gt4py's type translation are the real thing. All arithmetic is
in place on `.ndarray`. Edge/cell transfers are slices:
`to_cells(e) = 0.5 * (e[:4] + e[2:])`, `to_edges(c) = concatenate(c, c[:2])`.
Initial data is deterministic (`np.arange`-based, distinct per quantity) so
ordering mistakes change the numbers.

### Fake operations (`ops.py`, shared by both models)

One function per "stencil", one to three lines each, in place on numpy arrays,
named after the icon4py program it stands in for where one exists:

| function                                                   | stands in for                            |
|------------------------------------------------------------|------------------------------------------|
| `dycore_step(*_now, *_new, mass_flx_me, predictor_..., corrector_..., dtime, ...)` | predictor + corrector, one substep; reads the predictor tendency, writes the corrector |
| `compute_advection_in_horizontal_momentum(vn, ddt_vn_apc)` | the velocity-advection program of the same name |
| `diffuse(vn, theta_v, dtime, vn_new, theta_v_new)`         | diffusion; in place when the composer aliases |
| `advect(p_tracer_now, p_tracer_new, mass_flx_me, dtime)`   | tracer advection                         |
| `compute_temperature(theta_v, exner, temperature)`         | `compute_virtual_temperature_and_temperature` |
| `edge_2_cell_vector_rbf_interpolation(vn, u)`              | the RBF program of the same name         |
| `muphys(te, qv, tend_temperature, tend_qv, pflx)`          | the muphys granule + tendency diff       |
| `tmx(temperature, u, ddt_temperature, ddt_u)`              | the tmx granule (`ddt_*` ports)          |
| `update_exner_and_theta_v(temperature, exner, theta_v, exner_new, theta_v_new)` | the program of the same name; in place when aliased |
| `compute_vn_from_uv(u, vn)`                                | the stencil of the same name             |

`dycore_step` reads the `now` fields, writes the `new` fields and `mass_flx_me`;
it applies `0.5 * (predictor + corrector)` of the vn advective tendency.

### Time loop (identical in both models)

Per time step:

1. `ndyn_substeps` times: on the first substep compute the predictor vn advective
   tendency from `vn@now`, otherwise swap the predictor/corrector pair so the last
   corrector becomes this predictor (ICON `itime_scheme=4`); `dycore_step(now,
   next, ...)`; swap the prognostic pair unless last substep.
2. `diffuse` from `prognostic_states.next` into `prognostic_states.next`: in place
   because the driver passes the same buffers on both sides.
3. `advect` each active tracer from `tracers.current` into `tracers.next`.
4. Physics on `prognostic_states.next` / `tracers.next`: derive `temperature`
   and `u` (once each, for whichever configured processes declare them); each
   process at its cadence, its last output reused on the other steps; each
   process's declared `Update`, summed over processes and added once:
   `qv += dt * tend_qv`, `temperature += dt * tend_temperature`,
   `vn += dt * compute_vn_from_uv(tend_u)`; then the declared hook, once:
   `update_exner_and_theta_v` from the updated `temperature`.
5. Swap the prognostic pair and the tracer pair.
6. Output the configured variables from `prognostic_states.current`;
   `temperature` and `u` are recomputed from that state on both sides.

Run 4 steps with 2 substeps, for four configs (`example.yaml`; tmx only; no
physics; no output). Equality: `np.array_equal` on the 5 prognostics, `qv`,
`mass_flx_me`, `pflx` (when muphys runs), both sides of `ddt_vn_apc`, and on
every `(time, name, array)` output record.

## `model_current`

A trimmed copy of icon4py, not a paraphrase. Sources: `main` (driver, states,
dycore, diffusion, tracer advection, IO), PR C2SM/icon4py#1436
`two_layer_physics_state_refactor` (physics driver, physics state, muphys
component, `FieldMetaData`, `ComponentState`) and branch `physics_driver_tmx`
(PR #1360; tmx component, adapted to #1436's `as_component_input(state)`).

Trimming rules:

1. Drop grid, config, backend, allocator, exchange, timers, logging, the
   diagnostic/metric/interpolation states, and every argument that only carries
   them. Keep every argument that carries prognostic data or step control.
2. Each stencil or granule call becomes one `ops.*` call.
3. Keep every remaining module path (minus `src/icon4py/model/`), class, method,
   attribute, argument and dict key verbatim. All 112 names in the tree were
   checked with `git grep -w` against the three sources.
4. `w` on full levels; every field is `wpfloat` (`ta.vpfloat` is a runtime
   variable that mypy rejects as a type); xarray `DataArray`s are plain fields;
   the netCDF dataset is a list of `(time, name, array)`.
5. The only `type: ignore` pragmas in the tree (three in `solve_nonhydro.py`, two
   in `run.py`) cover icon4py's `PredictorCorrectorPair`: its descriptor-based
   accessors type `.predictor`/`.corrector` as `Callable[..., Any]` under mypy
   strict. The proposed 15-line `Pair` family keeps `predictor -> S`.
6. Configuration is `example.yaml` read by `config.py` (shared with
   `model_proposed`; YAML because icon4py's `config_io` reads YAML), consumed
   where the real code takes its config objects: `initialize_granules` builds
   the process list from `physics`, `IOMonitor(variables=...)` takes
   `output_variables`. `DEFAULT_OUTPUT_VARIABLES` is gone: an empty list means
   no output, not the default set.

```
model_current/
  common/
    states/model.py                FieldKind, FieldMetaData (#1436 dataclass form)
    states/data.py                 *_CF_ATTRIBUTES registries, tendency_of
    states/prognostic_state.py     PrognosticState, initialize_prognostic_state
    states/tracer_states.py        TracerField, TracerState.active_fields/.copy
    states/tracer_prep_adv_states.py  TracerPrepAdvState (mass_flx_me)
    states/diagnostic_state.py     DiagnosticState (temperature, u)
    states/nonhydro_states.py      DiagnosticStateNonHydro (normal_wind_advective_tendency: PredictorCorrectorPair)
    components/components.py       Component protocol (inputs/outputs_properties, __call__)
    components/component_state.py  ComponentState protocol (as_component_input)
    io/io.py                       IOMonitor.store(state, model_time)
  atmosphere/
    dycore/dycore_states.py        PrepAdvection (mass_flx_me)
    dycore/solve_nonhydro.py       SolveNonhydro.time_step(*, diagnostic_state_nh, prognostic_states, prep_adv, dtime, ...)
    diffusion/diffusion.py         Diffusion.run(prognostic_state, dtime)
    tracer_advection/tracer_advection.py  Advection.run(*, prep_adv, p_tracer_now, p_tracer_new, dtime)
    subgrid_scale_physics/physics_driver/
      physics_driver.py            PhysicsComponent, PhysicsProcess, PhysicsDriver.run with _recycle_cache
      physics_state.py             EntryState, TendencyAccumulators, ApplyToPrognostic, DiagnosticsStore
      process_time_control.py      ProcessTimeControl(interval, start_date).is_active
    subgrid_scale_physics/muphys/  component.py MuphysComponent, state.py State, data.py *_PROPERTIES
    subgrid_scale_physics/tmx/     component.py TmxComponent, state.py, data.py, tmx_states.py
  driver/
    driver.py                      Icon4pyDriver.time_integration/_integrate_one_time_step/_do_dyn_substepping/_store_output
                                   _update_time_levels_for_velocity_tendencies, initialize_driver, run_driver
    driver_states.py               DriverStates, ModelTimeVariables, link_tracer_prep_adv_to_dycore, assemble_driver_states
    driver_utils.py                Granules, initialize_granules
    driver_io.py                   *_VARIABLES, prognostic_state_to_dataarrays, DiagnosticsComputer
```

`TimeStepPair` and `PredictorCorrectorPair` are imported from
`icon4py.model.common.utils`, as the real code does. What the copy keeps on
purpose, because it is what the proposed design removes: dict keys agreed by
convention (`"te"`, `"tend_temperature"`, `"pflx"`),
one `State` adapter class per process, `FieldKind` routing, `EntryState` mixing
pointers with allocation, `ddt_*` granule ports mapped to `tend_*` component keys,
an output cache keyed by process name, IO picking fields by name from a dict,
`temperature`/`u` diagnosed twice per step whatever the config
(`EntryState.diagnose_from` runs with zero processes, `DiagnosticsComputer.compute`
runs with zero output variables: 8 + 8 calls in every row of the `run.py`
table), and the driver swapping the dycore's
predictor/corrector pair (`_update_time_levels_for_velocity_tendencies`) while
the dycore decides, from the same flags, whether to recompute the predictor.

## `model_proposed`

### `common/framework.py` (the reusable part, 379 lines)

```python
@dataclass(frozen=True) class Quantity: name, units, cf_key=None, parent: Quantity | None = None
def quantity(name, *, units, cf_key=None) -> Quantity      # registers in REGISTRY[name]
def tendency_of(q) -> Quantity                              # memoized; parent=q, units=f"{q.units} s-1"
def increment_of(q) -> Quantity                             # memoized; parent=q, units=q.units

type Tendency[F]  = Annotated[F, Tag.TENDENCY]
type Increment[F] = Annotated[F, Tag.INCREMENT]

@dataclass_transform(frozen_default=True)
class State:                                   # __init_subclass__ applies dataclass(frozen=True, eq=False, kw_only=True)
    @classmethod def declarations(cls) -> tuple[Decl, ...]    # cached: name, quantity, tag, field type, marker
    def leaves(self) -> Iterator[tuple[Decl, Any]]            # (declaration, value) pairs
class Pair[S]: first: S; second: S; swap()                    # 15 lines for the three classes
class TimeStepPair[S](Pair[S]): now; next                     # driver-owned: `.now` goes in as input, `.next` as output
class PredictorCorrectorPair[S](Pair[S]): predictor; corrector  # component-internal, never collected
def allocate(cls: type[S], sizes: dict[Dimension, int]) -> S  # gtx.zeros per alias dims, scalars zero
def collect(cls: type[S], *states) -> S                       # one leaf per declaration of cls, picked from states by quantity
def derived_by(recipe: type[Recipe]) -> Any    # leaf default: `temperature: TField = derived_by(Recipe)`; on an Update Increment leaf too
def from_tendency() -> Any                     # Update leaf default: `x: Increment[XField] = from_tendency()`, += dt * own Tendency[X]
def after_increments(hook: type[Component]) -> Any  # Update leaf default: `y: YField = after_increments(Hook)`, run once after the increments
def state_type(name, leaves: {name: (hint, marker | None)}) -> type[State]  # State class at runtime (config-driven Inputs)

class Component:                                              # not generic, see the decisions below
    Input: type[State]; Output: type[State]                   # a leaf in Input is read, a leaf in Output is written
    in_place: ClassVar[frozenset[str]] = frozenset()          # Output leaves that may share the buffer of the same-quantity Input leaf
    def run(self, input: Input, output: Output) -> None       # abstract; the composer hands both views per call
    def __call__(self, input, output) -> None                 # refuses an undeclared alias (AliasedOutput), then run
    def collect_inputs(self, *states) -> Any                  # collect(self.Input, *states)
    def collect_output(self, *states) -> Any                  # collect(self.Output, *states)
class Recipe(Component)                                       # a derivation; derived_by accepts nothing else
class Process(Component):                                     # emits tendencies and declares where they land
    Update: type[State] = Empty                               # Increment leaves (from_tendency / derived_by), plain leaves (after_increments)
    def accumulate(self, into: State, dt, output, *computed) -> None  # emitter's hook: each Update increment -> Increment leaf of into: +=

def resolve(children, sizes, *, input: type[State], output: type[State]) -> Resolution  # composite init: read the children's declarations
class Resolution: providers; increments; increment_recipes; hooks   # providers and increment recipes carry their output buffers
    def run_providers(self, *supplied) -> tuple[State, ...]   # skips a provider whose output is already supplied
    def run_increment_recipes(self, process, output, *supplied) -> tuple[State, ...]  # runs the process's increment recipes on its output
    def update(self, input, output, *produced) -> None        # output = input + increments, leaf by leaf; then the deduplicated hooks, once
def dataflow(*components) -> str                              # declared reads / produces (in place) / updates, `<- Recipe` on derived leaves
```

Rules the framework enforces:

- Every field of a `State` subclass is typed by an alias whose `Annotated`
  metadata carries a `Quantity`; `Tendency`/`Increment` are generic aliases that
  erase to the field type for mypy and gt4py. Reading the declaration means
  unwrapping `TypeAliasType`, generic aliases of `TypeAliasType`, and nested
  `Annotated`.
- `collect(cls, *states)` flattens the given states into `{quantity: value}`
  and picks one value per declaration of `cls`. Two different buffers for one
  quantity raise `AmbiguousSource`; an unresolved declaration raises
  `MissingInput`. The same buffer twice is fine. Scalars resolve exactly like
  fields. No component ever sees a `TimeStepPair`: the composer passes `.now`
  as input and `.next` as output.
- A component is called as `component(input, output)`. `__call__` refuses an
  Output leaf that is the same buffer as the Input leaf of its quantity unless
  the leaf's name is in `in_place` (`AliasedOutput`), then calls `run`. In-place
  update is the composer's choice, declared safe by the component.
- `accumulate` (on `Process`) walks the `Update` leaves tagged `Increment`:
  `from_tendency()` adds `dt * value` of the process's own `Tendency` output of
  the same parent into the `Increment` leaf of `into`; `derived_by(recipe)`
  adds the recipe's output increment, computed by
  `Resolution.run_increment_recipes` from the process output and the composite
  input. A missing increment leaf is an error.
- `Resolution.update(input, output, *produced)` makes `output` the updated
  state: an output leaf with no increment is copied from `input` unless it is
  the same buffer; each `Increments` leaf is added onto its parent as
  `out = in + inc`, the parent found in `output` or in a provider's buffer; a
  parent found nowhere raises `UnappliedIncrement`; then the hooks run once,
  reading from `output` and the provider buffers and writing into `output`.
  `dt` never appears in `update`.
- `resolve(children, sizes, input=CompositeInput, output=CompositeOutput)`
  runs once in a composite's `__init__`. Inputs: it collects the `derived_by`
  recipes from the children's Inputs (transitively through the recipes' own
  Inputs), deduplicates them, orders dependencies first, allocates one instance
  and one output buffer each; two recipes on one quantity raise
  `InconsistentDerivation`, within one composite or across composites:
  `resolve` records every derivation in the process-wide `DERIVATIONS`
  registry, so physics deriving `temperature` by one recipe and IO by another
  fails at the second `resolve` (tests clear the registry). Updates: for every
  `Process` it reads `Update`; the `Increment` leaves build the `Increments`
  state and, for `derived_by`, one recipe instance per process; the leaves with
  `after_increments` collect the hooks, deduplicated. Errors, all at init: an
  increment whose parent is neither a composite output nor a provider output,
  `UnappliedIncrement`; a `Tendency` output that no `Update` leaf consumes, or
  any `Tendency` output of a non-`Process`, `UnappliedTendency`;
  `from_tendency()` without the matching tendency, a `derived_by` recipe that
  does not produce the leaf's increment, an `after_increments` hook that does
  not produce the leaf's quantity or a leaf that is not a composite output, two
  processes naming different hooks for one quantity, a leaf with no marker, or
  a composite output that is neither an input nor incremented,
  `InconsistentUpdate`; a recipe or hook input that no process output,
  composite output or provider supplies, `MissingInput`.
- `Resolution.run_providers(*supplied)` runs the providers whose output is not
  already among the supplied states ("supplied wins"), in order, each seeing
  the outputs before it, each into its own buffer.
- A `State` built by hand with a marker still in place raises
  `UnresolvedInput`; `kw_only=True` on every `State` lets leaves with a
  `derived_by` default sit anywhere in the declaration order.
- Every buffer is owned by the composition: owner states, process outputs
  (`PhysicsDriver.outputs`, kept across steps, so a process that did not run
  this step still has its last output, which is what the cadence rule reuses),
  provider and increment-recipe outputs (in the `Resolution`). A component
  owns scratch only (`VnIncrementFromUTendency._ddt_vn`, the dycore's
  predictor/corrector pair).
- No `seal()`: `quantity()` runs on first read of an alias (PEP 695 aliases are
  lazy) and `REGISTRY` fills as declarations are read.

Decisions recorded: **the contract is pure.** A leaf in `Input` is read, a
leaf in `Output` is written; there is no read-write intent and no level
marker. The composer hands both views to every call, `component(input,
output)`, and decides whether an output buffer is also the input buffer: the
driver passes `prognostic_states.next` as diffusion's input and output, and as
the physics driver's, so the memory footprint is today's; a composer that
passes distinct buffers gets a copy instead. Whether that aliasing is safe is a
stencil property (pointwise updates are, neighbour stencils are not, and gt4py
does not check), so the component declares it, `in_place = {"vn",
"theta_v"}`, and `__call__` refuses anything else. `Component` is a nominal
base class, not a `Protocol`, so that a verb can be an inherited default a
component may override. Only one is: `accumulate`, the emitter's hook, on
`Process` (a process that wants `2 * dt * tend` or a clipped tendency
overrides it there, before the sum). `update` is `out = in + sum(increments)`
then the hooks, with nothing per component to override (a composite that
wants clipping declares an `after_increments` hook), so it lives on
`Resolution`, which owns the increments, next to `run_providers` and
`run_increment_recipes`; the composite's `run` is the schedule that calls
them. `Component` is the initial spec: `Input`, `Output`, `run`,
`collect_inputs`. It is not generic in them: pyright (Pylance) reports `class
C(Component["C.Input", "C.Output"])` as a class that depends on itself and
types everything inside it as Unknown, and a nested `Input` cannot be named in
the base list any other way; `run(self, input: Input, output: Output)` in the
subclass is typed by its own annotations, `collect_inputs` and
`collect_output` return `Any`, which is what the composites' call sites accept
anyway. Two subclasses: `Recipe`, an empty marker for what `derived_by` accepts
(mypy rejects `derived_by(MuphysComponent)`), and `Process`, a `Component`
with an `Update` block and `accumulate`. `IOMonitor`, the dycore, diffusion,
advection, recipes and hooks are plain `Component`s. `State` is a base class
because the dataclass conversion needs one. Tendencies and increments are
derived quantities. `dt` enters in `accumulate` so that components with
different cadences can accumulate with their own `dt`; the MWE uses the step
`dt` for both to match `model_current` numerically.

### Why the driver owns the pairs and no component sees one

`TimeStepPair[S]` holds two whole states (`now`, `next`) and one `swap()`. The
driver owns `TimeStepPair(PrognosticState, PrognosticState)` and
`TimeStepPair(TracerState, TracerState)` and addresses them itself: the dycore
is called with `collect_inputs(prognostic_states.now, substep)` and
`collect_output(prognostic_states.next, prep_advection)`, advection with
`tracers.now` in and `tracers.next` out, diffusion and physics with `next` on
both sides. A component declares level-free quantities and gets whichever
buffers the driver hands over. `Quantity` knows nothing about time.

1. Double buffering is a driver decision, not a property of the quantity.
   `air_density` is one quantity; whether two buffers of it exist depends on the
   owner and the scheme. The same quantity is single-level in the physics Input,
   in `DiagnosticsComputer`, in IO, in a checkpoint. A level on the global
   `Quantity` would be false for most of its uses and would leak the driver's
   buffering into every consumer.
2. Cadence differs per state group and swap is atomic within the group.
   Prognostics swap after every dynamics substep except the last, then once per
   step; tracers swap once per step (ICON `nnow/nnew` vs `nnow_rcf/nnew_rcf`).
   One `swap()` on the state moves all five prognostic fields together, so the
   invariant is structural. Field-level pairs would be five swaps kept in
   lockstep by convention. icon4py already does it this way with
   `TimeStepPair[PrognosticState]`. This is also the only reason
   `PrognosticState` and `TracerState` are still two classes: nothing else in
   the design knows the word "prognostic", a composite's Input lists its
   quantities flat.
3. No registry duplication. Quantity-level `rho_now`/`rho_new` would double the
   registry, break the `tendency_of`/`increment_of` link (tendency of which
   level?) and muddy `AmbiguousSource`/`MissingInput`.
4. Allocation stays trivial: a pair is two `allocate(PrognosticState, sizes)`
   calls.
5. Current/next are not mere helpers: within one substep the dycore reads
   `now` and writes `next` (and reads its own output in the corrector), and the
   driver decides when to swap. Input and output views make that addressing
   explicit at the call site. An earlier version of this MWE had level tags on
   the declaration instead (`Now[F]`/`Next[F]`, keyed by `collect_inputs`); the
   pure contract made them redundant.

icon4py also has field-level pairs: `PredictorCorrectorPair` for the advective
tendencies in `DiagnosticStateNonHydro`, swapped by the driver in
`_update_time_levels_for_velocity_tendencies`. That is a component-internal
buffer trick of the `MOST_EFFICIENT` time stepping scheme (reuse last substep's
corrector as this substep's predictor), not a driver-owned time level. Nobody
outside the dycore reads those pairs, yet the swap condition is written three
times: in the driver, in `SolveNonhydro.run_predictor_step` (as the decision to
skip the recomputation) and in the dycore integration test. The MWE shows both:
`model_current` keeps the driver-side swap verbatim; `model_proposed` owns the
pair inside `SolveNonhydro` (`PredictorCorrectorPair` of the one-field state
`AdvectiveTendencies`) and swaps it in `run` from `at_first_substep`, which it
already receives, so the condition exists once. Either way the `Quantity` stays
level-free: the tendency is `Tendency[VnField]`.

### Derived quantities and updates: the component declares, the composite computes

`MuphysComponent.Input` says `temperature: TemperatureField =
derived_by(recipes.TemperatureFromThetaExner)`. It does not compute
`temperature`, and `collect_inputs` does not either: it stays pointer selection.
`MuphysComponent.Update` says where its tendencies land: `temperature: Increment =
from_tendency()`, `qv: Increment = from_tendency()`, `theta_v =
after_increments(recipes.ExnerThetaFromTemperature)`, `exner` likewise. The composite
(`PhysicsDriver`, or the driver for IO) calls `resolve` once at init and gets
the providers to run, the increments to zero, the increment recipes to run per
process and the hooks to run after the increments. Decisions and why:

- **Not in `collect_inputs`.** An `if temperature in state: use it else: compute`
  inside the component gives two temperatures in one physics step when two
  processes fall back to different recipes, costs one rbf per consumer instead
  of one per step, turns the Input from a view into a mix of aliases and
  scratch, and makes `dataflow()` a disjunction. The declaration gives the
  discoverability without any of that.
- **Recipes are Components** (`Recipe` is an empty marker subclass, so
  `derived_by(MuphysComponent)` is a mypy error), not functions plus a source
  list: they carry their own Input and Output declarations (so a multi-output
  recipe is one run), own their output buffer, appear as ordinary nodes in
  `dataflow()`, and live in one shared module (`recipes.py`) so wrappers pick
  a recipe rather than write one. Two wrappers picking different recipes for
  the same quantity is an init-time error, not two temperatures.
- **Every landing is declared on the process, in `Update`.** A `Tendency[X]`
  output says nothing about the host state by itself. `Update` says it:
  `x: Increment[XField] = from_tendency()` is `x += dt * tend_x`; `vn:
  Increment[VnField] = derived_by(recipes.VnIncrementFromUTendency)` is `vn +=
  dt * P(tend_u)`, the increment route, because `rbf(P(u)) != u` and so there is
  no `VnFromU`; `theta_v`, `exner = after_increments(ExnerThetaFromTemperature)`
  is the EOS on the incremented `temperature`. Reading a process tells you
  everything it touches; the granule wrapper is the layer that knows the host
  conventions. icon4py's `ApplyToPrognostic` says the same by tendency name,
  once, in the composer, whatever the config. An earlier version of this MWE
  attached the write-back to the recipe (`inverse`, `exact_inverse`): declared
  once instead of per process, but the vn update sat two hops away from tmx.
  Rejected for that; the numerics were identical.
- **Parallel update is the composer's schedule, not the process's.** The
  composite sums the declared increments over processes, applies them once,
  then runs the deduplicated hooks once: `theta_v, exner <- EOS(T_entry + dt *
  sum(tend_T))`, as `ApplyToPrognostic` does (the EOS is nonlinear, so per-process
  application would differ by a real `ab` term, not round-off). Sequential
  update would apply and hook per process and re-derive the providers between
  processes: same declarations, different schedule. `PhysicsDriver(update=
  "parallel")` is the only mode built; `"sequential"` raises `NotImplementedError`.
- **IO reuses only declared Outputs, so IO recomputes.** The post-hook
  `temperature` buffer is the provider's, mutated by `update`; nobody declares it
  valid, so IO derives its own from the prognostics, exactly as `model_current`
  does, and every output record is bit-identical. The flag that marked it
  reusable went with the inverse; it can return as a declaration if the
  recompute ever matters.
- **Nothing is computed for nobody.** With `physics: {}` no provider exists;
  with `output_variables: []` IO has no Input leaves. `model_current` computes
  `temperature` and `u` twice per step in every row of the `run.py` table.
- **Errors, not skips or defaults**: `MissingInput`, `AmbiguousSource`, `AliasedOutput`,
  `UnappliedIncrement`, `UnappliedTendency`, `InconsistentDerivation`,
  `InconsistentUpdate`, `UnresolvedInput`; an unknown output variable is a
  `KeyError` into `io.VARIABLES`. The one rule that looks like a default,
  "supplied wins over provider", is the reuse mechanism, and a partial supply
  of a multi-output recipe surfaces as `AmbiguousSource` in the consumer.

### Usage

Module and class names follow `model_current` so the two trees read side by side.

```
common/quantities.py  10 field aliases + 7 scalar aliases, one line each; names are the CF standard names of data.py
common/states.py      PrognosticState, TracerState, PrepAdvection, StepInfo
recipes.py            Recipes TemperatureFromThetaExner, UFromVn, VnIncrementFromUTendency (Tendency[U] + dt -> Increment[Vn]); hook ExnerThetaFromTemperature, in_place exner, theta_v
solve_nonhydro.py     SolveNonhydro: Input the five prognostics (the driver passes `now`), substep scalars; Output the five prognostics (`next`) + mass_flx_me
                      owns PredictorCorrectorPair(AdvectiveTendencies) and swaps it in run
diffusion.py          Diffusion: Input vn, theta_v, dtime; Output vn, theta_v; in_place both (the driver passes `next` on both sides)
tracer_advection.py   Advection: Input qv (tracers.now), mass_flx_me (the driver's prep_advection), dtime; Output qv (tracers.next)
muphys.py             MuphysComponent(Process): Input temperature = derived_by(TemperatureFromThetaExner), qv; Output Tendency[T], Tendency[Qv], pflx
                      Update temperature, qv = from_tendency(); theta_v, exner = after_increments(ExnerThetaFromTemperature)
tmx.py                TmxComponent(Process): Input temperature = derived_by(...), u = derived_by(UFromVn); Output Tendency[T], Tendency[U]
                      Update temperature = from_tendency(); vn = derived_by(VnIncrementFromUTendency); theta_v, exner = after_increments(...)
io.py                 VARIABLES (name -> hint, derived_by); IOMonitor(variables): Input built by state_type from the config
physics_driver.py     PhysicsDriver(process_intervals, update="parallel"): processes and their output buffers from PROCESSES by config name, resolve(...) at init
                      Input the prognostics, qv, dtime, step_index; Output vn, exner, theta_v, qv, in_place all four
                      run: run_providers -> each process (call if active, then run_increment_recipes, accumulate) -> resolution.update(input, output, *produced)
driver.py             Icon4pyDriver(config): owner states and pairs, prep_advection, PhysicsDriver, IOMonitor and its own resolve;
                      every call is component(collect_inputs(...), collect_output(...))
```

Where each tricky case lands: now/next in `driver.py` (`.now` in, `.next` out
for the dycore and advection); a component-internal predictor/corrector pair in
`solve_nonhydro.py`; in-place by declared aliasing in `diffusion.py`, the after-increments hook and
`physics_driver.py`;
hand-off in dycore -> advection (`mass_flx_me` lands in the driver's
`prep_advection`, an `Output` leaf with no tendency tag, never accumulated); cadence with the composer-held output in
`physics_driver.py` (`ProcessTimeControl(2)` for tmx from the config); derived
inputs, increments, increment recipes and hooks assembled by `resolve` in
`physics_driver.py`; scalars as quantities in `StepInfo`; config-driven IO
Input in `io.py`, collecting from `prognostic_states.now` and IO's own
providers.

## Checking

- `run.py`: prints `dataflow()` of the proposed model for `example.yaml`
  (providers, processes, increment recipes, hooks, IO), then for each of four configs runs
  both models for 4 steps, compares the quantities, both sides of the dycore
  pair and the output records, and prints one table row per side with the
  number of `compute_temperature` and `edge_2_cell_vector_rbf_interpolation`
  calls: `model_current` 8 and 8 in every row; `model_proposed` 8 and 8
  (`example.yaml`), 8 and 8 (tmx only), 4 and 0 (no physics, `temperature`
  output only), 4 and 4 (no output). Exit code 1 on any mismatch.
- `test_equivalence.py`: the same matrix as four pytest cases, asserting
  agreement and the call counts.
- `test_framework.py`: fifteen unit tests of the framework verbs, `resolve`,
  its errors and `state_type`.
- `mypy.ini`: `strict = True`; `implicit_reexport = True` for `model_current.*`
  only, as icon4py's own `pyproject.toml` sets it. Command:
  `<icon4py>/.venv/bin/python -m mypy model_current model_proposed run.py test_framework.py test_equivalence.py config.py ops.py`.
- Python 3.12, the icon4py virtualenv; imports from icon4py limited to
  `dimension`, `field_type_aliases`, `type_alias`, `utils.TimeStepPair`,
  `utils.PredictorCorrectorPair`; `pyyaml` for `config.py`.

## Housekeeping

- Location `mwe/components/` in this repository, outside `content/` so Quartz
  ignores it. Branch `components-mwe`, one PR.
- `README.md` in the folder: purpose, the three commands.
- One line added to the layout block of `AGENTS.md` naming `mwe/`.
- Code is comment-free by request; names carry the meaning.
- Size as built (non-blank lines): `model_current` 668 across 28 modules,
  `model_proposed` 717 (of which `framework.py` 379, `recipes.py` 40),
  `ops.py` 107 (with the call counter), `config.py` 10, `run.py` + tests 352.
