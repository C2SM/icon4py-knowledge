# Components MWE: design

Minimal working example comparing today's component and state shape in icon4py
(`model_current`) with the proposed `State`/`Component` design (`model_proposed`).
Both run the same fake time loop on the same fake data and must produce identical
numbers. No real stencils, no real grid, no connectivity. Readable by the group in
5-10 minutes.

## Goal

Show the proposed design in action next to the current one, without distraction:

- same quantities, same scalars, same arithmetic, same loop, same output;
- the only thing that differs is how components declare, receive and return data;
- `run.py` asserts equality and prints the proposed model's declared dataflow;
- `model_proposed` passes `mypy --strict`.

Explicitly out of scope: real physics, real grids, halo exchange, restart, IO
cadence beyond "every step", introspection beyond one `dataflow()` print,
sequential coupling, py2fgen.

## Scope

### Quantities (10)

| quantity        | dims    | role                                                        |
|-----------------|---------|-------------------------------------------------------------|
| `vn`            | Edge, K | prognostic, now/next pair, swapped per dynamics substep     |
| `w`             | Cell, K | prognostic, same pair                                       |
| `rho`           | Cell, K | prognostic, same pair                                       |
| `exner`         | Cell, K | prognostic, same pair                                       |
| `theta_v`       | Cell, K | prognostic, same pair                                       |
| `qv`            | Cell, K | tracer, now/next pair, swapped once per time step           |
| `mass_flux_e`   | Edge, K | dycore output handed to advection, never accumulated        |
| `temperature`   | Cell, K | derived once per step; read by physics and IO               |
| `u`             | Cell, K | derived cell-centre wind; read by tmx, projected back to vn |
| `precip`        | Cell    | muphys diagnostic, read by IO                               |

Tendencies and increments are derived quantities (`tendency_of`, `increment_of`),
never declared by hand: `ddt_temperature` (muphys, tmx), `ddt_qv` (muphys),
`ddt_u` (tmx), and one increment per accumulated parent (`temperature`, `qv`, `u`).

### Scalars (8)

`dtime`, `substep_dtime`, `ndyn_substeps`, `step_index`, `simulation_time`
(datetime), `at_first_substep`, `at_last_substep`, `tmx_interval` (= 2 steps).

### Grid and data

4 cells, 6 edges, 3 levels. Fields are gt4py fields (`gtx.zeros`) so the type
aliases, mypy and gt4py's type translation are the real thing. All arithmetic is
in place on `.ndarray`. Edge/cell transfers are slices:
`cells_from_edges(vn) = 0.5 * (vn[:4] + vn[2:])`, `edges_from_cells(u)` writes
`vn[:4]` and `vn[2:]` back. Initial data is deterministic (`np.arange`-based,
distinct per quantity) so ordering mistakes change the numbers.

### Fake operations (`ops.py`, shared by both models)

One function per "stencil", one to three lines each, in place on numpy arrays:

| function                                          | stands in for                     |
|---------------------------------------------------|-----------------------------------|
| `dycore_step(now, next, mass_flux_e, dt)`         | predictor + corrector, one substep|
| `diffuse(vn, theta_v, dt)`                        | diffusion, in place               |
| `advect(qv_now, qv_next, mass_flux_e, dt)`        | tracer advection                  |
| `diagnose(exner, theta_v, vn, temperature, u)`    | dyn2phy derived quantities        |
| `muphys(temperature, qv, ddt_t, ddt_qv, precip)`  | graupel microphysics              |
| `tmx(temperature, u, ddt_t, ddt_u)`               | turbulent mixing                  |
| `eos(temperature, exner, theta_v)`                | exact EOS update after physics    |
| `project(u, vn)`                                  | cells-to-edges wind projection    |

`dycore_step` reads `now`, reads and writes `next`, writes `mass_flux_e`.

### Time loop (identical in both models)

Per time step:

1. `ndyn_substeps` times: `dycore_step(pair.now, pair.next, ...)`; `pair.swap()`
   unless last substep.
2. `diffuse` in place on `pair.next`.
3. `advect` `qv` from `tracers.now` into `tracers.next`.
4. Physics on `pair.next` / `tracers.next`: `diagnose`; muphys every step; tmx
   every `tmx_interval` steps, its last output reused on the other steps;
   accumulate tendencies into increments with `dt`; apply increments once;
   `eos`; `project`.
5. IO records `temperature`, `precip`, and muphys's `ddt_temperature`.
6. `pair.swap()`; `tracers.swap()`.

Run 4 steps with 2 substeps. Equality: `np.array_equal` on all 10 quantities and
on the IO records.

## `model_current`

Mirrors `main` (driver, dycore, diffusion, advection), PR #1436 (physics driver,
muphys) and branch `physics_driver_tmx` (tmx), each trimmed to its state and
component surface. Kept on purpose, because they are what the proposed design
removes: dict keys agreed by convention, one state adapter class per process,
`kind` string routing, `EntryState` mixing pointers with allocation, positional
granule signatures, an output cache keyed by process name, IO picking fields by
name in the driver.

```
model_current/
  common/states.py    PrognosticState, TracerState (dataclasses of fields)
                      TimeStepPair(current, next).swap()
                      INPUTS/OUTPUTS_PROPERTIES dicts with kind="tendency"|"diagnostic"
                      PhysicsState protocol: as_component_input() -> dict[str, Field]
  dycore.py           SolveNonhydro.time_step(prognostic_states, prep_adv, dtime, at_first_substep, at_last_substep)
  diffusion.py        Diffusion.run(prognostic_state, dtime)
  advection.py        Advection.run(prep_adv, p_tracer_now, p_tracer_new, dtime)
  physics_driver.py   EntryState.diagnose_from(prognostic, tracers)
                      TendencyAccumulators.zero() / .accumulate(outputs, outputs_properties)
                      ApplyToPrognostic(entry, accumulators, dt)
                      DiagnosticsStore.allocate(process_name, outputs_properties)
                      ProcessTimeControl(interval).is_active(step)
                      PhysicsProcess(name, component, state, time_control)
                      PhysicsDriver.run(prognostic, tracers, dtime, step) with recycle cache
  muphys.py           MuphysState adapter; MuphysComponent.__call__(state: dict, step) -> dict; bind_output_buffers
  tmx.py              TmxState adapter; TmxComponent.__call__(state: dict, step) -> dict
  io.py               OutputWriter.write(step, fields: dict[str, Field])
  driver.py           TimeLoop.run(n_steps)
```

## `model_proposed`

### `common/framework.py` (the reusable part, ~110 lines)

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
    @classmethod def declarations(cls) -> tuple[Decl, ...]    # cached: name, quantity, intent, level, nested
    def leaves(self) -> Iterator[tuple[Decl, Any]]            # recursive over nested states
class Pair[S]: now: S; next: S; swap()                        # leaves tagged NOW / NEXT when gathered
def allocate(cls: type[S], sizes: dict[Dimension, int]) -> S  # gtx.zeros per alias dims, scalars zero

class Component[InputT, OutputT]:
    Input: type[InputT]; Output: type[OutputT]
    def __init__(self, output: OutputT)                       # composition allocates, binds here
    def run(self, input: InputT) -> OutputT                   # abstract
    def gather(self, *states) -> InputT                       # default; overridable
    def accumulate(self, into: State, dt: float) -> None      # Tendency leaf of self.output -> Increment leaf: += dt * t
    def apply(self, increments: State, target: State) -> None # Increment leaf -> parent leaf in target: +=
def dataflow(*components) -> str                              # declared reads / writes / produces
```

Rules the framework enforces:

- Every field of a `State` subclass is typed by an alias whose `Annotated`
  metadata carries a `Quantity`; `Read`/`ReadWrite`/`Tendency`/`Increment`/
  `Now`/`Next` are generic aliases that erase to the field type for mypy and
  gt4py. Reading the declaration means unwrapping `TypeAliasType`, generic
  aliases of `TypeAliasType`, and nested `Annotated`.
- `gather` flattens the given states into `{(quantity, level): value}`. A state
  given as a `Pair` contributes its `now` leaves with level `NOW` and its `next`
  leaves with `NEXT`; any other state contributes level `None`. A declaration
  resolves only against its own level. Two different buffers for one key raise
  `AmbiguousSource`; an unresolved declaration raises `MissingInput`. The same
  buffer twice is fine. Scalars resolve exactly like fields.
- `accumulate` walks `self.output`'s `Tendency` leaves and adds `dt * value`
  into the `Increment` leaf of the same parent quantity in `into`.
- `apply` walks `increments`' `Increment` leaves and adds each into the leaf of
  the parent quantity in `target`. `dt` never appears in `apply`.
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

### Usage

```
common/quantities.py  10 field aliases + 8 scalar aliases, one line each
common/states.py      Prognostics, Tracers, PrepAdvection, Derived, StepInfo, Increments (owner-states)
dycore.py             Input: Now[...] x5 READ, Next[...] x5 READWRITE, substep scalars; Output: mass_flux_e
diffusion.py          Input: ReadWrite[VnField], ReadWrite[ThetaVField], Read[TimeStep]; Output: Empty
advection.py          Input: Now[QvField] READ, Next[QvField] READWRITE, Read[MassFluxField], Read[TimeStep]
derived.py            Input: exner, theta_v, vn READ; Output: temperature, u
muphys.py             Input: temperature, qv READ; Output: Tendency[T], Tendency[Qv], precip
tmx.py                Input: temperature, u READ; Output: Tendency[T], Tendency[U]
eos.py                Input: Read[TemperatureField], ReadWrite[ExnerField], ReadWrite[ThetaVField]; Output: Empty
projection.py         Input: Read[UField], ReadWrite[VnField]; Output: Empty
io.py                 Input: temperature, precip, Read[Tendency[TemperatureField]]; Output: Empty
physics_driver.py     Physics(Component): processes with Every(n) cadence, increments owner-state
                      run: derived -> each process (run if due) -> accumulate -> apply -> eos -> projection
driver.py             allocate owner-states; Pair(prognostics), Pair(tracers); loop identical to model_current
```

Where each tricky case lands: now/next in dycore and advection; in-place in
diffusion, eos, projection; hand-off in dycore -> advection (`mass_flux_e` is an
`Output` with no tendency tag, so it is never accumulated); cadence with cached
output in `physics_driver.py` (`Every(2)` for tmx); the accumulate/apply split
in `physics_driver.py`; scalars as quantities in `StepInfo`; IO attribution by
source selection (the composition passes `muphys.output` to `io.gather`, so the
only `ddt_temperature` buffer in scope is muphys's).

## Checking

- `run.py`: seeds identical initial arrays into both models, runs 4 steps,
  prints `dataflow()` of the proposed model, compares all 10 quantities and the
  IO records, prints `OK` or the first mismatch, exit code accordingly.
- `test_equivalence.py`: pytest wrapper around `run.py`, one assert.
- `mypy.ini`: `strict = True`; command
  `<icon4py>/.venv/bin/python -m mypy mwe/components/model_proposed`.
  `model_current` is not type-checked.
- Python 3.12, the icon4py virtualenv; imports from icon4py limited to
  `dimension`, `field_type_aliases`, `type_alias`.

## Housekeeping

- Location `mwe/components/` in this repository, outside `content/` so Quartz
  ignores it. Branch `components-mwe`, one PR.
- `README.md` in the folder: purpose, the two commands, line counts.
- One line added to the layout block of `AGENTS.md` naming `mwe/`.
- Code is comment-free by request; names carry the meaning.
- Budget: `model_current` ~350 lines, `model_proposed` ~380 (framework ~110),
  `ops.py` ~60, `run.py` + test ~50.
