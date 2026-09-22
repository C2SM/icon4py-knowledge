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
- `run.py` asserts equality and prints the proposed model's declared dataflow;
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
| `temperature` | Cell, K | diagnosed at physics entry, and again from the new state for IO   |
| `u`           | Cell, K | diagnosed cell-centre wind; read by tmx; its tendency goes to vn  |
| `pflx`        | Cell    | muphys precipitation diagnostic                                   |
| `ddt_vn_apc`  | Edge, K | vn advective tendency, predictor/corrector pair inside the dycore |

Tendencies and increments are derived quantities (`tendency_of`, `increment_of`),
never declared by hand: `tend_temperature` (muphys, tmx), `tend_qv` (muphys),
`tend_u` (tmx), `ddt_vn_apc` (dycore, `Tendency[VnField]`, so no new registry
entry), and one increment per accumulated parent (`temperature`, `qv`, `u`).

### Scalars (8)

`dtime`, `substep_dtime`, `ndyn_substeps`, `step_index`, `simulation_time`
(datetime), `at_first_substep`, `at_last_substep`, `tmx_interval` (= 2 steps).

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
4. Physics on `prognostic_states.next` / `tracers.next`: diagnose `temperature`
   and `u`; muphys every step; tmx every `tmx_interval` steps, its last output
   reused on the other steps; sum tendencies; apply once:
   `qv += dt * tend_qv`; `new_te = temperature + dt * tend_temperature` then
   `update_exner_and_theta_v`; `vn += dt * compute_vn_from_uv(tend_u)`.
5. Swap the prognostic pair and the tracer pair.
6. Output from `prognostic_states.current`: the five prognostics plus
   `temperature` and `u` recomputed from that state (7 records per step).

Run 4 steps with 2 substeps. Equality: `np.array_equal` on the 5 prognostics,
`qv`, `mass_flx_me`, `pflx`, both sides of `ddt_vn_apc`, and on every
`(time, name, array)` output record.

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
`temperature`/`u` diagnosed twice per step (`EntryState.diagnose_from` and
`DiagnosticsComputer.compute`), and the driver swapping the dycore's
predictor/corrector pair (`_update_time_levels_for_velocity_tendencies`) while
the dycore decides, from the same flags, whether to recompute the predictor.

## `model_proposed`

### `common/framework.py` (the reusable part, 175 lines)

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
class TimeStepPair[S](Pair[S]): now; next                     # leaves tagged NOW / NEXT when gathered
class PredictorCorrectorPair[S](Pair[S]): predictor; corrector  # component-internal, never gathered
# One Pair would do; the two subclasses only add icon4py's names (6 lines each) and let
# gather tag time levels for TimeStepPair alone.
def allocate(cls: type[S], sizes: dict[Dimension, int]) -> S  # gtx.zeros per alias dims, scalars zero

class Component[InputT, OutputT]:
    Input: type[InputT]; Output: type[OutputT]
    def __init__(self, output: OutputT)                       # composition allocates, binds here
    def run(self, input: InputT) -> OutputT                   # abstract
    def gather(self, *states) -> InputT                       # default; overridable
    def accumulate(self, into: State, dt: float) -> None      # Tendency leaf of self.output -> Increment leaf: += dt * t
    def apply(self, increments: State, *targets: State) -> None  # Increment leaf -> parent leaf in targets: +=
def dataflow(*components) -> str                              # declared reads / writes / produces
```

Rules the framework enforces:

- Every field of a `State` subclass is typed by an alias whose `Annotated`
  metadata carries a `Quantity`; `Read`/`ReadWrite`/`Tendency`/`Increment`/
  `Now`/`Next` are generic aliases that erase to the field type for mypy and
  gt4py. Reading the declaration means unwrapping `TypeAliasType`, generic
  aliases of `TypeAliasType`, and nested `Annotated`.
- `gather` flattens the given states into `{(quantity, level): value}`. A state
  given as a `TimeStepPair` contributes its `now` leaves with level `NOW` and its
  `next` leaves with `NEXT`; any other state contributes level `None`. A declaration
  resolves only against its own level. Two different buffers for one key raise
  `AmbiguousSource`; an unresolved declaration raises `MissingInput`. The same
  buffer twice is fine. Scalars resolve exactly like fields.
- `accumulate` walks `self.output`'s `Tendency` leaves and adds `dt * value`
  into the `Increment` leaf of the same parent quantity in `into`; a missing
  increment leaf is an error.
- `apply` walks `increments`' `Increment` leaves and adds each into the leaf of
  the parent quantity found in the given targets. An increment whose parent is
  not among the targets is left for another consumer (here `ExnerThetaUpdate`
  and `WindProjection`), mirroring `ApplyToPrognostic`, which applies only the
  tendencies that exist. `dt` never appears in `apply`.
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
and `Advection` do. `gather` keys on `(quantity, level)`: a `Pair` argument
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
   That is driver-owned addressing, which the `(quantity, level)` key at gather
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

### Usage

Module and class names follow `model_current` so the two trees read side by side.

```
common/quantities.py  10 field aliases + 7 scalar aliases, one line each; names are the CF standard names of data.py
common/states.py      PrognosticState, TracerState, PrepAdvection, DiagnosticState, Increments, StepInfo
solve_nonhydro.py     SolveNonhydro: Input Now[...] x5 READ, Next[...] x5 READWRITE, substep scalars; Output PrepAdvection
                      owns PredictorCorrectorPair(AdvectiveTendencies) and swaps it in run
diffusion.py          Diffusion: Input ReadWrite[VnField], ReadWrite[ThetaVField], Read[TimeStep]; Output Empty
tracer_advection.py   Advection: Input Now[QvField] READ, Next[QvField] READWRITE, Read[MassFluxField], Read[TimeStep]
diagnostics.py        DiagnosticsComputer: Input theta_v, exner, vn READ; Output DiagnosticState (temperature, u)
muphys.py             MuphysComponent: Input te, qv READ; Output Tendency[T], Tendency[Qv], pflx
tmx.py                TmxComponent: Input temperature, u READ; Output Tendency[T], Tendency[U]
eos.py                ExnerThetaUpdate: Input Read[T], Read[Increment[T]], ReadWrite[exner], ReadWrite[theta_v]
projection.py         WindProjection: Input Read[Increment[U]], ReadWrite[VnField]
io.py                 IOMonitor: Input the 7 output variables + Read[SimulationTime]; appends (time, name, array)
physics_driver.py     PhysicsDriver(Component): processes with ProcessTimeControl(interval) cadence, Increments owner-state
                      run: entry diagnostics -> each process (run if active) -> accumulate -> apply -> eos -> projection
driver.py             Icon4pyDriver: same method names as model_current; owner-states allocated in __init__
```

Where each tricky case lands: now/next in `solve_nonhydro.py` and
`tracer_advection.py`; a component-internal predictor/corrector pair in
`solve_nonhydro.py`; in-place in `diffusion.py`, `eos.py`, `projection.py`;
hand-off in dycore -> advection (`mass_flx_me` is an `Output` with no tendency
tag, so it is never accumulated); cadence with cached output in
`physics_driver.py` (`ProcessTimeControl(2)` for tmx); the accumulate/apply split
in `physics_driver.py`, with one consumer per increment (`apply` for `qv`,
`ExnerThetaUpdate` for `temperature`, `WindProjection` for `u`); scalars as
quantities in `StepInfo`; IO gathering from two states (`prognostic_states.now`
and a second `DiagnosticsComputer` output), as the current driver does.

## Checking

- `run.py`: runs both models for 4 steps, prints `dataflow()` of the proposed
  model, compares the 8 quantities, both sides of the dycore pair and the output
  records, prints `OK` or the mismatches, exit code accordingly.
- `test_equivalence.py`: pytest wrapper around `run.py`, one assert.
- `test_framework.py`: five unit tests of the framework verbs.
- `mypy.ini`: `strict = True`; `implicit_reexport = True` for `model_current.*`
  only, as icon4py's own `pyproject.toml` sets it. Command:
  `<icon4py>/.venv/bin/python -m mypy model_current model_proposed run.py test_framework.py test_equivalence.py`.
- Python 3.12, the icon4py virtualenv; imports from icon4py limited to
  `dimension`, `field_type_aliases`, `type_alias`, `utils.TimeStepPair`,
  `utils.PredictorCorrectorPair`.

## Housekeeping

- Location `mwe/components/` in this repository, outside `content/` so Quartz
  ignores it. Branch `components-mwe`, one PR.
- `README.md` in the folder: purpose, the three commands.
- One line added to the layout block of `AGENTS.md` naming `mwe/`.
- Code is comment-free by request; names carry the meaning.
- Size as built (non-blank lines): `model_current` 668 across 28 modules,
  `model_proposed` 566 (of which `framework.py` 175), `ops.py` 85,
  `run.py` + tests 135.
