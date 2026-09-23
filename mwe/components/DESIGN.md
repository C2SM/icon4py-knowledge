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
sequential coupling, py2fgen.

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
| `temperature` | Cell, K | derived by a recipe when a process or IO asks; incremented, written back through the EOS; IO reuses it |
| `u`           | Cell, K | derived by a recipe; read by tmx; its increment is projected onto vn; IO recomputes it |
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
| `diffuse(vn, theta_v, dtime)`                              | diffusion, in place                      |
| `advect(p_tracer_now, p_tracer_new, mass_flx_me, dtime)`   | tracer advection                         |
| `compute_temperature(theta_v, exner, temperature)`         | `compute_virtual_temperature_and_temperature` |
| `edge_2_cell_vector_rbf_interpolation(vn, u)`              | the RBF program of the same name         |
| `muphys(te, qv, tend_temperature, tend_qv, pflx)`          | the muphys granule + tendency diff       |
| `tmx(temperature, u, ddt_temperature, ddt_u)`              | the tmx granule (`ddt_*` ports)          |
| `update_exner_and_theta_v(temperature, exner, theta_v)`    | the program of the same name             |
| `compute_vn_from_uv(u, vn)`                                | the stencil of the same name             |

`dycore_step` reads the `now` fields, writes the `new` fields and `mass_flx_me`;
it applies `0.5 * (predictor + corrector)` of the vn advective tendency.

### Time loop (identical in both models)

Per time step:

1. `ndyn_substeps` times: on the first substep compute the predictor vn advective
   tendency from `vn@now`, otherwise swap the predictor/corrector pair so the last
   corrector becomes this predictor (ICON `itime_scheme=4`); `dycore_step(now,
   next, ...)`; swap the prognostic pair unless last substep.
2. `diffuse` in place on `prognostic_states.next`.
3. `advect` each active tracer from `tracers.current` into `tracers.next`.
4. Physics on `prognostic_states.next` / `tracers.next`: derive `temperature`
   and `u` (once each, for whichever configured processes declare them); each
   process at its cadence, its last output reused on the other steps; sum
   tendencies into increments; add every increment to its parent
   (`qv += dt * tend_qv`, `temperature += dt * tend_temperature`,
   `u += dt * tend_u`); write derived parents back: `update_exner_and_theta_v`
   from the updated `temperature`, `vn += compute_vn_from_uv(u increment)`.
5. Swap the prognostic pair and the tracer pair.
6. Output the configured variables from `prognostic_states.current`. In
   `model_current` `temperature` and `u` are recomputed from that state. In
   `model_proposed` `temperature` is reused from the physics provider output,
   `u` is recomputed (see the derived-quantities section for why).

Run 4 steps with 2 substeps, for four configs (`example.yaml`; tmx only; no
physics; no output). Equality: `np.array_equal` on the 5 prognostics, `qv`,
`mass_flx_me`, `pflx` (when muphys runs), both sides of `ddt_vn_apc`, and on
every `(time, name, array)` output record, except that `temperature` records
compare with `np.allclose(rtol=1e-12)`: the reused value went through the EOS
once less than the recomputed one (`(T/exner)*exner != T` in the last bit).

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

### `common/framework.py` (the reusable part, 271 lines)

```python
@dataclass(frozen=True) class Quantity: name, units, cf_key=None, of: Quantity | None = None
def quantity(name, *, units, cf_key=None) -> Quantity      # registers in REGISTRY[name]
def tendency_of(q) -> Quantity                              # memoized; of=q, units=f"{q.units} s-1"
def increment_of(q) -> Quantity                             # memoized; of=q, units=q.units

type Read[F]      = Annotated[F, Intent.READ]
type ReadWrite[F] = Annotated[F, Intent.READWRITE]
type Tendency[F]  = Annotated[F, Tag.TENDENCY]
type Increment[F] = Annotated[F, Tag.INCREMENT]
type Now[F]       = Annotated[F, Level.NOW]
type Next[F]      = Annotated[F, Level.NEXT]

@dataclass_transform(frozen_default=True)
class State:                                   # __init_subclass__ applies dataclass(frozen=True, eq=False)
    @classmethod def declarations(cls) -> tuple[Decl, ...]    # cached: name, quantity, intent, tag, level
    def leaves(self) -> Iterator[tuple[Decl, Any]]            # (declaration, value) pairs
class Pair[S]: first: S; second: S; swap()                    # 15 lines for the three classes
class TimeStepPair[S](Pair[S]): now; next                     # leaves tagged NOW / NEXT when collected
class PredictorCorrectorPair[S](Pair[S]): predictor; corrector  # component-internal, never collected
# One Pair would do; the two subclasses only add icon4py's names (6 lines each) and let
# collect_inputs tag time levels for TimeStepPair alone.
def allocate(cls: type[S], sizes: dict[Dimension, int]) -> S  # gtx.zeros per alias dims, scalars zero
def derived_by(recipe: type[Component]) -> Any                # leaf default: `te: Read[TField] = derived_by(Recipe)`
def state_type(name, leaves: {name: (hint, Derived | None)}) -> type[State]  # State class at runtime (config-driven Inputs)

class Component[InputT, OutputT]:
    Input: type[InputT]; Output: type[OutputT]
    write_back: type[Component] | None = None                 # recipe only: pushes an incremented output into its sources
    invertible: bool = False                                  # recipe only: output still valid after write_back
    def __init__(self, output: OutputT)                       # composition allocates, binds here
    def run(self, input: InputT) -> OutputT                   # abstract
    def collect_inputs(self, *states) -> InputT               # pointer selection only, never computes
    def accumulate(self, into: State, dt: float) -> None      # Tendency leaf of self.output -> Increment leaf: += dt * t
    def apply(self, increments: State, *targets: State) -> None  # Increment leaf -> parent leaf in targets: +=; else raise

def resolve(children, sizes, *, targets: type[State]) -> Resolution   # composite init: read the children's declarations
class Resolution: providers; increments; write_backs; reusable
    def run_providers(self, *supplied) -> tuple[State, ...]   # skips a provider whose output is already supplied
    def reusable_outputs(self, produced) -> tuple[State, ...] # provider outputs still valid after the write-backs
def dataflow(*components) -> str                              # declared reads / writes / produces, `<- Recipe` on derived leaves
```

Rules the framework enforces:

- Every field of a `State` subclass is typed by an alias whose `Annotated`
  metadata carries a `Quantity`; `Read`/`ReadWrite`/`Tendency`/`Increment`/
  `Now`/`Next` are generic aliases that erase to the field type for mypy and
  gt4py. Reading the declaration means unwrapping `TypeAliasType`, generic
  aliases of `TypeAliasType`, and nested `Annotated`.
- `collect_inputs` flattens the given states into `{(quantity, level): value}`. A state
  given as a `TimeStepPair` contributes its `now` leaves with level `NOW` and its
  `next` leaves with `NEXT`; any other state contributes level `None`. A declaration
  resolves only against its own level. Two different buffers for one key raise
  `AmbiguousSource`; an unresolved declaration raises `MissingInput`. The same
  buffer twice is fine. Scalars resolve exactly like fields.
- `accumulate` walks `self.output`'s `Tendency` leaves and adds `dt * value`
  into the `Increment` leaf of the same parent quantity in `into`; a missing
  increment leaf is an error.
- `apply` walks `increments`' `Increment` leaves and adds each into the leaf of
  the parent quantity found in the given targets. A parent found nowhere raises
  `UnappliedIncrement`. `dt` never appears in `apply`.
- `resolve(children, sizes, targets=CompositeInput)` runs once in a composite's
  `__init__`: it collects the `derived_by` recipes from the children's Inputs
  (transitively through the recipes' own Inputs), deduplicates them, orders
  dependencies first, allocates one instance each; builds the `Increments` state
  from the union of the children's `Tendency` outputs; and for every increment
  whose parent is neither a target leaf nor a provider output raises
  `UnappliedIncrement`, for one whose parent is a provider output without a
  `write_back` raises `MissingWriteBack`, for two recipes on one
  `(quantity, level)` raises `InconsistentDerivation`. Every error is at init.
- `Resolution.run_providers(*supplied)` runs the providers whose output is not
  already among the supplied states ("supplied wins"), in order, each seeing
  the outputs before it. `Resolution.reusable_outputs(produced)` returns the
  provider outputs that are still valid after the write-backs: never
  incremented, or from an `invertible` recipe.
- A `State` built by hand with a `derived_by` marker still in place raises
  `UnresolvedInput`; `kw_only=True` on every `State` lets leaves with a
  `derived_by` default sit anywhere in the declaration order.
- Output buffers are allocated by the composition and passed to the component's
  constructor; `run` writes into `self.output` and returns it. A component that
  did not run this step still has its last output, which is what the cadence
  rule reuses.
- Intent is metadata only; nothing prevents a `READ` write at runtime.
- No `seal()`: `quantity()` runs on first read of an alias (PEP 695 aliases are
  lazy) and `REGISTRY` fills as declarations are read.

Decisions recorded: `Component` is a nominal base class, not a `Protocol`, so
that the verbs are inherited defaults a component or composite may override.
`State` is a base class because the dataclass conversion needs one. Time level
lives on the declaration and on `Pair`, never on the `Quantity`. Tendencies and
increments are derived quantities. `dt` enters in `accumulate` so that
components with different cadences can accumulate with their own `dt`; the MWE
uses the step `dt` for both to match `model_current` numerically.

### Why `Pair` wraps a `State`, not a field or a `Quantity`

`TimeStepPair[S]` holds two whole states (`now`, `next`) and one `swap()`. The
driver owns `TimeStepPair(PrognosticState, PrognosticState)` and
`TimeStepPair(TracerState, TracerState)`.
A component that cares about levels says so in its Input (`rho_now:
Read[Now[RhoField]]`, `rho_new: ReadWrite[Next[RhoField]]`); only `SolveNonhydro`
and `Advection` do. `collect_inputs` keys on `(quantity, level)`: a `Pair` argument
contributes its `now` leaves at `NOW` and its `next` leaves at `NEXT`, a plain
state contributes level `None`. `Quantity` knows nothing about time.

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
   `TimeStepPair[PrognosticState]`.
3. No registry duplication. Quantity-level `rho_now`/`rho_new` would double the
   registry, break the `tendency_of`/`increment_of` link (tendency of which
   level?) and muddy `AmbiguousSource`/`MissingInput`, which today catch two
   different buffers for one `(quantity, level)`. `Now[F]`/`Next[F]` erase to the
   same field type, so mypy and gt4py see a plain `fa.CellKField[wpfloat]`.
4. Allocation stays trivial: a pair is two `allocate(PrognosticState, sizes)`
   calls. A field-level pair would need a special field type inside the state,
   and every in-place component would pick `.next` per field.
5. Current/next are not mere helpers: within one substep the dycore reads
   `current` and reads and writes `next`, and the driver decides when to swap.
   That is driver-owned addressing, which the `(quantity, level)` key at collect
   time expresses.

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

### Derived quantities: the component declares, the composite computes

`MuphysComponent.Input` says `te: Read[TemperatureField] =
derived_by(quantity_recipes.TemperatureFromThetaExner)`. It does not compute
`te`, and `collect_inputs` does not either: it stays pointer selection. The
composite (`PhysicsDriver`, or the driver for IO) calls `resolve` once at init
and gets the providers to run, the increments to zero and the write-backs to
run. Decisions and why:

- **Not in `collect_inputs`.** An `if te in state: use it else: compute` inside
  the component gives two temperatures in one physics step when two processes
  fall back to different recipes, costs one rbf per consumer instead of one per
  step, turns the Input from a view into a mix of aliases and scratch, puts
  ICON's prognostic vocabulary (`theta_v`, `exner`) into a granule wrapper that
  should know only `T`, and makes `dataflow()` a disjunction. The declaration
  gives the discoverability without any of that.
- **Recipes are Components**, not functions plus a source list: they carry
  their own Input and Output declarations (so a multi-output recipe is one
  run), own their output buffer, appear as ordinary nodes in `dataflow()`, and
  live in one shared module (`quantity_recipes.py`) so wrappers pick a recipe
  rather than write one. Two wrappers picking different recipes for the same
  quantity is an init-time error, not two temperatures.
- **The tendency rule is universal; the write-back belongs to the recipe.**
  `x += sum(dt_i * tend_i)` is `accumulate` + `apply`, the same for prognostic
  and derived `x`. What differs per quantity is how an updated derived value
  reaches the prognostics, and that is the inverse of the derivation:
  `TemperatureFromThetaExner.write_back = ExnerThetaFromTemperature` (full
  inverse, the EOS is a pointwise bijection), `UFromVn.write_back =
  VnFromUIncrement` (incremental, `vn += P(du)`, because `rbf(P(u)) != u`). The
  processes declare nothing about application. This is `ApplyToPrognostic`
  split along its own seams.
- **Reuse across composites is by passing an Output, and only while valid.** A
  derived value is valid for one instant of its sources. `invertible = True`
  on the temperature recipe says the incremented output equals a recomputation
  from the written-back `exner`/`theta_v` to round-off, so the driver hands
  `physics.reusable` to IO and IO's own `TemperatureFromThetaExner` provider is
  skipped. `UFromVn` is not invertible: `u_entry + du != rbf(vn_new)`, a real
  difference, not round-off, so IO recomputes `u`. That asymmetry is a fact
  about the real model, encoded once, on the recipe.
- **Nothing is computed for nobody.** With `physics: {}` no provider exists;
  with `output_variables: []` IO has no Input leaves. `model_current` computes
  `temperature` and `u` twice per step in every row of the `run.py` table.
- **Errors, not skips or defaults**: `MissingInput`, `AmbiguousSource`,
  `UnappliedIncrement`, `InconsistentDerivation`, `MissingWriteBack`,
  `UnresolvedInput`; an unknown output variable is a `KeyError` into
  `io.VARIABLES`. The one rule that looks like a default, "supplied wins over
  provider", is the reuse mechanism, and a partial supply of a multi-output
  recipe surfaces as `AmbiguousSource` in the consumer.

### Usage

Module and class names follow `model_current` so the two trees read side by side.

```
common/quantities.py  10 field aliases + 7 scalar aliases, one line each; names are the CF standard names of data.py
common/states.py      PrognosticState, TracerState, PrepAdvection, StepInfo
quantity_recipes.py   TemperatureFromThetaExner (write_back ExnerThetaFromTemperature, invertible), UFromVn (write_back VnFromUIncrement)
solve_nonhydro.py     SolveNonhydro: Input Now[...] x5 READ, Next[...] x5 READWRITE, substep scalars; Output PrepAdvection
                      owns PredictorCorrectorPair(AdvectiveTendencies) and swaps it in run
diffusion.py          Diffusion: Input ReadWrite[VnField], ReadWrite[ThetaVField], Read[TimeStep]; Output Empty
tracer_advection.py   Advection: Input Now[QvField] READ, Next[QvField] READWRITE, Read[MassFluxField], Read[TimeStep]
muphys.py             MuphysComponent: Input te = derived_by(TemperatureFromThetaExner), qv; Output Tendency[T], Tendency[Qv], pflx
tmx.py                TmxComponent: Input temperature = derived_by(...), u = derived_by(UFromVn); Output Tendency[T], Tendency[U]
io.py                 VARIABLES (name -> hint, derived_by); IOMonitor(variables): Input built by state_type from the config
physics_driver.py     PhysicsDriver(process_intervals): processes from PROCESSES by config name, resolve(...) at init
                      run: run_providers -> each process (run if active) -> accumulate -> apply -> write_backs -> reusable
driver.py             Icon4pyDriver(config): owner-states, PhysicsDriver, IOMonitor and its own resolve for IO providers
```

Where each tricky case lands: now/next in `solve_nonhydro.py` and
`tracer_advection.py`; a component-internal predictor/corrector pair in
`solve_nonhydro.py`; in-place in `diffusion.py` and the two write-back recipes;
hand-off in dycore -> advection (`mass_flx_me` is an `Output` with no tendency
tag, so it is never accumulated); cadence with cached output in
`physics_driver.py` (`ProcessTimeControl(2)` for tmx from the config); derived
inputs, increments and write-backs assembled by `resolve` in
`physics_driver.py`; scalars as quantities in `StepInfo`; config-driven IO
Input in `io.py`, collecting from `prognostic_states.now`, the physics'
reusable `temperature` and IO's own `UFromVn` provider.

## Checking

- `run.py`: prints `dataflow()` of the proposed model for `example.yaml`
  (providers, processes, write-backs, IO), then for each of four configs runs
  both models for 4 steps, compares the quantities, both sides of the dycore
  pair and the output records, and prints one table row per side with the
  number of `compute_temperature` and `edge_2_cell_vector_rbf_interpolation`
  calls: `model_current` 8 and 8 in every row; `model_proposed` 4 and 8
  (`example.yaml`), 4 and 8 (tmx only), 4 and 0 (no physics, `temperature`
  output only), 4 and 4 (no output). Exit code 1 on any mismatch.
- `test_equivalence.py`: the same matrix as four pytest cases, asserting
  agreement and the call counts.
- `test_framework.py`: eight unit tests of the framework verbs, `resolve`,
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
- Size as built (non-blank lines): `model_current` 667 across 28 modules,
  `model_proposed` 585 (of which `framework.py` 271, `quantity_recipes.py` 43),
  `ops.py` 105 (with the call counter), `config.py` 10, `run.py` + tests 260.
