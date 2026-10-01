# Components MWE: design, one section per layer

Minimal working example comparing today's component and state shape in icon4py
(`model_current`) with the `State`/`Component` design (`model_proposed`). The
design is built as a stack: each layer is one branch and one PR on top of the
previous one, each section below is that PR's body. Every layer keeps both
models bit-exact on the config matrix of `run.py`.

## Goal

- same quantities, same scalars, same arithmetic, same loop, same output; the
  only thing that differs is how components declare, receive and return data;
- `model_current` is a faithful trimmed copy of icon4py: real module paths, real
  class, method, attribute, argument and dict-key names;
- both models read `example.yaml`; `run.py` asserts equality over a config
  matrix and counts how often each side computes `temperature`, `u` and
  `theta_v` on half levels;
- both models pass `mypy --strict` and pyright.

Out of scope: real physics, real grids, halo exchange, restart, IO cadence
beyond "every step", sequential physics coupling, py2fgen, pint units, the
Fortran name table.

## Scope

### Quantities

| quantity      | dims        | role                                                      |
|---------------|-------------|-----------------------------------------------------------|
| `vn`          | Edge, K     | prognostic, now/next pair, swapped per dynamics substep   |
| `w`           | Cell, K     | prognostic, same pair                                     |
| `rho`         | Cell, K     | prognostic, same pair                                     |
| `exner`       | Cell, K     | prognostic, same pair                                     |
| `theta_v`     | Cell, K     | prognostic, same pair                                     |
| `theta_v_ic`  | Cell, KHalf | `theta_v` on half levels, read by the dycore (`theta_v_at_cells_on_half_levels` in icon4py) |
| `qv`          | Cell, K     | tracer, now/next pair, swapped once per time step         |
| `mass_flx_me` | Edge, K     | summed over the substeps by the dycore, read by tracer advection |
| `temperature` | Cell, K     | derived from `theta_v`, `exner`; read by physics and IO   |
| `u`           | Cell, K     | derived from `vn`; read by tmx and IO                     |
| `pflx`        | Cell        | muphys precipitation diagnostic                           |
| `ddt_vn_apc`  | Edge, K     | vn advective tendency, predictor/corrector pair in the dycore |

Tendencies: `tend_temperature` (muphys, tmx), `tend_qv` (muphys), `tend_u`
(tmx). Scalars: `dtime`, `substep_dtime`, `ndyn_substeps`, `step_index`,
`simulation_time`, `at_first_substep`. Process cadences come from the config
(`example.yaml`: muphys every step, tmx every 2).

### Grid, data, operations

4 cells, 6 edges, 3 levels (4 half levels). Fields are gt4py fields
(`gtx.zeros`), arithmetic in place on `.ndarray`, edge/cell transfers are
slices. Initial data is deterministic and distinct per quantity, so ordering
mistakes change the numbers. `ops.py` has one short function per "stencil",
named after the icon4py program it stands in for (`dycore_step`,
`interpolate_to_half_levels`, `compute_advection_in_horizontal_momentum`,
`diffuse`, `advect`, `compute_temperature`,
`edge_2_cell_vector_rbf_interpolation`, `muphys`, `tmx`,
`update_exner_and_theta_v`, `compute_vn_from_uv`), shared by both models, with a
call counter.

### Time loop (identical in both models)

Per time step: `ndyn_substeps` dycore substeps (predictor tendency on the first,
pair swap on the others; `theta_v` to half levels; `dycore_step(now, next)`;
swap the prognostic pair unless last), diffusion in place on `next`, tracer
advection `now` to `next`, physics on `next` (derive `temperature` and `u`;
each process at its cadence, its last output reused in between; summed
tendencies applied once: `qv += dt tend_qv`, `temperature += dt
tend_temperature` then `update_exner_and_theta_v`, `vn += dt
compute_vn_from_uv(tend_u)`), swap both pairs, output the configured variables
from `now` with `temperature` and `u` recomputed. 4 steps, 2 substeps, five
configs: `example.yaml`; tmx only; no physics; no output; two prognostics out,
one of them without a CF name.

## `model_current`

A trimmed copy of icon4py, not a paraphrase: `main` for driver, states, dycore,
diffusion, tracer advection, IO; PR C2SM/icon4py#1436 (`physics_driver_tmx`) for
the physics driver, `EntryState`, `TendencyAccumulators`, `ApplyToPrognostic`,
`DiagnosticsStore`, the muphys and tmx components with their
`inputs_properties`/`outputs_properties` metadata dicts and the per-process
`as_component_input` adapters. 674 non-blank lines in 28 modules.

## 01 Typed states and components

**Problem.** A component in icon4py today receives `dict[str, DataField]` and
returns one. Which keys it needs and produces is in a side table of
`FieldMetaData`, and nothing checks that the driver's `as_component_input`
agrees with it. A field is a `gtx.Field` to mypy: passing `theta_v` where `vn`
is expected is not a type error.

**Adds.** `model_proposed/common/framework.py`, 139 lines, four things and a
pair:

- `Quantity`: a type-level tag, one subclass per quantity, never instantiated.
  `dims`, `units`, CF `standard_name` where the CF table has one, optional
  `long_name`, all on the class. One tag per quantity at one place on the
  grid, the way icon4py names `theta_v_at_cells_on_half_levels` today:
  `ThetaVOnCellK`, `ThetaVOnCellKHalf`. Tendencies are tags of their own under
  a `Tendency` marker base (icon4py's `FieldKind.TENDENCY`), units written by
  hand.
- `Field[Q]`: a two-slot wrapper, the tag and the gt4py field. The tag is a
  phantom type parameter: `Field[VnOnEdgeK]` and `Field[ThetaVOnCellK]` are
  different types to mypy and pyright, the same array to gt4py. Invariant, so
  `(Field[Q], Field[Q])` means the same quantity twice. Stencils get `.data`.
- `State`: a frozen, keyword-only dataclass of typed leaves;
  `declarations()` reads the `Field` leaves back (name, quantity). Plain leaves
  (`dtime: float`) are ordinary fields. `allocate(State, sizes)` makes the
  buffers from the declarations.
- `Component`: `Input`, `Output`, and `run(input, out=None) -> Output`, the
  only method a component implements. `out = c.run(input)` writes into the
  component's own buffers, allocated once on first use; `c.run(input,
  out=view)` writes where the caller says, numpy `out=` style. Either way
  `run` returns the output. Whether `out` may alias the input is the
  component's business (diffusion and the physics update tolerate it, the
  dycore needs distinct now/next); nothing checks it in this layer.
- `TimeStepPair` / `PredictorCorrectorPair`: icon4py's pairs typed
  (`common_utils.PredictorCorrectorPair[...].predictor` is `Any` to mypy),
  `current` renamed `now`.

The composers are hand-written, one-to-one with `model_current` in structure.
`PhysicsDriver.run` is icon4py's five steps as private methods of the one
class, where icon4py has them on `EntryState`, `TendencyAccumulators` and
`ApplyToPrognostic`: `_diagnose` derives `temperature` and `u` with two `ops`
calls into a driver-owned `Diagnostics` state and returns an `EntryState` over
them and the prognostics; `_zero_accumulators`; `_accumulate` sums every
`Tendency` leaf of a process's output by output name into driver-owned
accumulators; `_apply` is `ApplyToPrognostic` writing `out` views. Each
process picks its `Input` from the `EntryState` with a hand-written
`collect_input`, the typed `as_component_input`; `bind` ties a component's
`run` to its `collect_input` in one expression, so pairing tmx's with muphys's
is a type error. The later layers take these methods apart: 02 rewrites the
body of `_diagnose`, 04 rekeys `_accumulate` and `_apply` by quantity, 06
drops the `EntryState`, 08 removes `_diagnose`, 09 the other three.
`Icon4pyDriver` constructs every `Input` and `Output` view by keyword and
passes `now` in and `next` out. IO declares everything it can write and the
config selects by CF `standard_name`, or by class name where there is none
(`VnOnEdgeK`). No collection by identity, no registry, no derived-quantity
recipes, no tendency links, no checks beyond what mypy does.

Where this layer departs from `model_current`: process cadence counts steps
instead of datetimes; `pflx` is owned by muphys, there is no
`DiagnosticsStore`; muphys's input `te` is `temperature`; the dycore owns
`theta_v_ic` and the `ddt_vn_apc` pair and swaps it in `run` from
`at_first_substep` (icon4py keeps both in the driver's
`DiagnosticStateNonHydro` and swaps in the driver, so the swap condition is
written three times: driver, dycore, test; nobody else reads them);
`mass_flx_me` is a running sum over the substeps and is declared on the
dycore's `Input` and `Output`, the driver passes one buffer on both sides.

**Costs.** Every `Input`/`Output` view is spelled out by keyword at the call
site (`driver.py` is 104 lines against 258 in `model_current/driver/`), and
every stencil call reads `.data`. Calls through the `fw.Component` base are
untyped (`run(input: Any, out: Any)`); only calls on a concrete class are
checked. `_apply` is a method, not a `Component`: which tendencies it reads
depends on the configured processes, and a `State` has no optional leaf.
`model_proposed` is 576 non-blank lines against 674 for
`model_current`, the physics driver 132 against 133. Call counts are those of
`model_current`: `temperature` and `u` computed twice per step (physics and
IO), `theta_v` on half levels once per substep, 8/8/8 in every row of
`run.py`.

**Checks.** `run.py` (five configs, bit-exact); `test_equivalence.py` (the same
matrix as pytest, with the call counts); `test_framework.py` (6 unit tests and
`static_checks`, a block of quantity mismatches under `# type: ignore` that
both checkers must flag: mypy strict reports an unused ignore, pyright with
`reportUnnecessaryTypeIgnoreComment` likewise); `mypy --strict` on 61 files;
pyright 0 errors; `ruff check`.

## 02 Recipes

**Problem.** A derived quantity is computed wherever someone needs it:
`temperature` and `u` in `EntryState.diagnose_from` for physics and again in
`DiagnosticsComputer` for output, `theta_v_ic` inside the dycore, `ddt_vn` from
`tend_u` inside `ApplyToPrognostic`. Each site allocates its own buffer and
names the stencil; what is derived from what is in the argument order of an
`ops` call. A new consumer of `u` has to know the stencil's name and allocate.

**Adds.** `Recipe`, an empty subclass of `Component`: a derivation declared
like any component, `Input`, `Output`, `run`, owning its result. `recipes.py`
(56 lines): `TemperatureFromThetaExner`, `UFromVn`, `ThetaVToHalfLevels`,
`VnTendencyFromUTendency`, and `ExnerThetaFromTemperature`, a plain
`Component`: its outputs are among its inputs, it updates rather than derives.
`Recipe` is a name only, nothing reads it until a later layer. One module for
the whole model: a consumer picks a recipe and reads `.temperature` off the
result instead of writing a stencil call and a buffer. The drivers still
decide when. `PhysicsDriver._diagnose` runs the two diagnostics recipes and
the driver's `Diagnostics` state is gone, the recipes own the buffers;
`Icon4pyDriver` runs `ThetaVToHalfLevels` before each dycore substep and the
two diagnostics before each output; the dycore's `Input` names `theta_v_ic`
instead of computing it.

**Costs.** `model_proposed` 643 (+67: `recipes.py` 56, the `Recipe` base 8,
a recipe call is longer than the `ops` call it replaces, the `Diagnostics`
state and its allocation gone). `temperature`
is still computed twice per step, since physics reads it before its update
and output after; counts unchanged, 8/8/8. Nothing checks that two consumers
derive a quantity the same way; later layer.

**Checks.** As 01, plus `test_recipe_is_a_component_that_owns_its_result`.

## 03 Dims

**Problem.** With one tag per quantity and place, `ThetaVOnCellK` and
`ThetaVOnCellKHalf` are two unrelated quantities: a CF name is written twice
or left off one, a tendency would exist per place, the config names the place
in the name (`VnOnEdgeK`), and the place is checked nowhere: gt4py's
`CellKField` and `CellKHalfField` are one type to mypy and pyright, because
dims are runtime objects.

**Adds.** `Dims`, a second kind of tag: a place on the grid with its gt4py
dimensions, six of them (`Cell`, `CellK`, `CellKHalf`, `Edge`, `EdgeK`,
`EdgeKHalf`). `Field[Q, D]` takes both tags. A quantity declares the places
it lives at as nested aliases,

```python
class ThetaV(fw.Quantity, units="K"):
    type CellK = fw.Field[ThetaV, fw.CellK]
    type CellKHalf = fw.Field[ThetaV, fw.CellKHalf]
```

and a component writes `theta_v: qty.ThetaV.CellK`. `Decl` carries `dims`.
A place the quantity does not declare is refused where the `State` class is
defined (`InvalidDims`; to the checkers `fw.Field[ThetaV, fw.EdgeK]` is a
valid type). `zeros(quantity, dims, sizes)`. A place mismatch between two
declared places is a type error (`static_checks`), which gt4py cannot give
today. The config says `Vn`, not `VnOnEdgeK`.

**Costs.** Framework 175 lines (+28). `model_proposed` 681 (+38). `quantities.py` 38 (+9): a tag is two
lines, the alias line per place is its declaration of where it lives.
`Field` takes three arguments. Counts unchanged, 8/8/8. `places()` reads the
class body; nothing else is automated.

**Checks.** As 02, plus `test_quantity_is_a_tag_with_metadata_and_places`,
`test_a_place_the_quantity_does_not_declare_is_refused`, and the place
mismatch line in `static_checks`.

## 04 Tendencies

**Problem.** A tendency is a quantity declared by hand: four tags with their
units typed in (`TendencyOfTemperature`, `K s-1`) and nothing linking
`TendencyOfTemperature` to `Temperature`. The physics driver sums tendencies
by output name, so muphys's `tend_temperature` and tmx's `tend_temperature`
add up because both authors typed the same name, and `ApplyToPrognostic`
knows by name which prognostic each sum lands on. icon4py's `tendency_of(...)`
in `states/data.py` derives the metadata, but the link is gone once the dict
is built.

**Adds.** `TendencyOf[Q]`, a quantity derived from its parent:
`fw.Tendency[qty.Temperature, fw.CellK]` names it in a type,
`tendency_of(qty.Temperature)` is the one class behind it at runtime,
memoized, with the parent's places, its units per second, the CF
`tendency_of_` name where the parent has one, and `parent`. `declarations()`
resolves the alias to that class. `_accumulate` keys the accumulators by
`(parent, dims)` instead of output name, and `_apply` reads the sum for
`(Qv, CellK)`: two processes' temperature tendencies add up because both are
tendencies of `Temperature` at `CellK`. Still by hand: where each sum lands
is written in `_apply`.

**Costs.** Framework 212 lines (+37). `quantities.py` 25 (-13): the four
hand-written tendency tags and the marker base are gone. A tendency leaf is
`fw.Tendency[qty.U, fw.CellK]`, one subscription longer than `qty.U.CellK`.
Counts unchanged, 8/8/8.

**Checks.** As 03, plus `test_tendency_of_derives_one_class_per_parent`,
`test_a_tendency_leaf_declares_the_derived_quantity`, and two tendency lines
in `static_checks`.

## 05 Dataflow

**Problem.** What a component reads and writes is in its code. icon4py's
physics processes carry `inputs_properties`/`outputs_properties` dicts; the
dycore, diffusion, advection and IO carry nothing, and no view lists them
together.

**Adds.** `Decl.label` (the quantity, plus the place when the quantity lives
at more than one) and `dataflow(*component classes) -> str`, one line per
component from its declarations alone. `run.py` prints it for `example.yaml`
before the table:

```
ThetaVToHalfLevels | reads: ThetaV@CellK | produces: ThetaV@CellKHalf
SolveNonhydro | reads: Vn, W, Rho, Exner, ThetaV@CellK, ThetaV@CellKHalf, MassFlux | produces: Vn, W, Rho, Exner, ThetaV@CellK, MassFlux
...
MuphysComponent | reads: Temperature, Qv | produces: TendencyOfTemperature, TendencyOfQv, PrecipitationFlux
IOMonitor | reads: Rho, W, Vn, Exner, ThetaV@CellK, Temperature, U | produces: -
```

**Costs.** Framework 228 lines (+16). Nothing else changes: a report, not a
mechanism.

**Checks.** As 04, plus `test_dataflow_lists_reads_and_produces_by_label`.

## 06 Collect

**Problem.** Every view is spelled out by keyword at the call site: seven
field lines for the dycore's `Input` in the driver, a `collect_input` function per
physics process plus `bind` to pair it with the right component, and an
`EntryState` whose only job is to hold the pool the processes pick from. A
leaf renamed in a `State` means editing every call site, and the same wiring
is written once per consumer.

**Adds.** `collect(cls, *states, **plain)`: one leaf per `Field` declaration
of `cls`, picked from the given states by `(quantity, dims)`; plain leaves by
keyword, and a field given by keyword wins over the pool. Pointer selection
only, never computes. `MissingInput` names the
leaf and the quantity; `AmbiguousSource` fires when two different buffers of
one quantity at one place are in the pool (the same buffer twice is fine).
Composers now pass states, not leaves:

```python
self.solve_nonhydro.run(
    fw.collect(SolveNonhydro.Input, now, theta_v_ic, self.prep_advection, substep_dtime=..., ...),
    out=fw.collect(SolveNonhydro.Output, next, self.prep_advection),
)
```

and the physics driver runs each process on
`fw.collect(component.Input, input, *produced)`, `produced` being the two
recipe outputs `_diagnose` now returns. `EntryState`,
`collect_input` and `bind` are gone; the process/collect pairing they had to
check by hand no longer exists. This is the first mechanism that builds a
component's view by quantity identity: a quantity at a place is found
wherever it is, by what it is, not by the name of the attribute that holds it.

**Costs.** Framework 260 lines (+32). `model_proposed` 698 (-27): `driver.py`
78 (was 112), `physics_driver.py` 113 (was 120), `physics_state.py` gone. A
pool with two buffers of one quantity at one place cannot be collected from,
by design: the driver keeps `now` and `next` in separate calls, and a view
over a bare field is still built by keyword, the incremented temperature and
the `tend_u` sum in `_apply`. Wiring errors at a composer call site move from
mypy to runtime (`MissingInput`, the dataclass's `TypeError` for a plain
leaf). Scalars stay plain leaves, passed by keyword, rather than tagged
quantities; the aliasing guard once planned for this layer comes with the
composer verb in 10. Counts unchanged, 8/8/8.

**Checks.** As 05, plus `test_collect_picks_leaves_by_quantity_and_place`
(pick from two states, `MissingInput`, `AmbiguousSource`).

## 07 IO from the config

**Problem.** IO declares a fixed `Input` of everything it could write and the
config filters it: adding an output variable means editing IO's `Input`, and
IO reads seven leaves to write two. The config vocabulary (CF names, class
names) is resolved by scanning that `Input`.

**Adds.** `REGISTRY`: every quantity tag registers when defined; a repeated
class name or a repeated CF `standard_name` is `DuplicateQuantity`.
`lookup(key)` by either name, among the quantities that live somewhere
(`UnknownQuantity` at init for a typo in the config). `state_type(name,
leaves)` builds a `State` class at runtime. IO's `Input` is built per instance
from the config, one leaf per requested variable at the quantity's first
declared place, plus the time: `IOMonitor | reads: Temperature, U` for
`example.yaml`. The driver collects it like any other view; `dataflow`
accepts an instance for it, so `run.py` builds the driver to print the line.

**Costs.** Framework 287 lines (+27). `io.py` 28 (was 30). A per-instance
`Input` is opaque to mypy: the driver passes `self.io_monitor.Input` and IO
reads its leaves with `getattr`; the class-level `IOMonitor.Input` is `Empty`.
A configured variable that `lookup` knows but no state the driver passes
carries (`specific_humidity`) fails at the first output step with
`MissingInput`, as `model_current` fails late too; 06 failed at init. `temperature` and `u` are still derived at
every output step whether or not the config asks; counts unchanged, 8/8/8.

**Checks.** As 06, plus `test_lookup_by_standard_name_or_class_name` (with
`DuplicateQuantity`) and `test_state_type_builds_a_collectable_state`.

## 08 Derived inputs

**Problem.** The composer knows which recipes its children need and calls
them by hand: the physics driver instantiates `TemperatureFromThetaExner` and
`UFromVn` whether or not a configured process reads them, the driver does the
same for IO whether or not the config asks for `temperature` or `u`, and a
process that starts reading a new diagnostic needs a matching line in its
composer. Who needs what is written in two places.

**Adds.** `Source`, a leaf default that says where a value comes from when
the composer does not supply it, and `derived_by(Recipe)`:
`temperature: qty.Temperature.CellK = fw.derived_by(recipes.TemperatureFromThetaExner)`
on muphys and tmx, `u` on tmx, `theta_v_ic` on the dycore, IO's config leaves
through its `DERIVED` table. `Decl.source`; a hand-built `State` cannot carry
a source (`UnresolvedInput`). `resolve(children, sizes) -> Resolution`: the
recipes the children name, one instance each, dependency-ordered, one recipe
per quantity at a place (`InconsistentDerivation` for two recipes on one key,
or a recipe named on a leaf it does not produce). `Resolution.provide(*supplied)`
runs them all once, eagerly, and the composer collects its children from the
supplied and the produced states. Three resolutions: dycore, physics, IO. In
this layer a derived leaf is always derived: supplying it as well is
`AmbiguousSource`; "supplied wins" comes with the plan in 10. A cycle of
recipes is `InconsistentDerivation`. `dataflow` prints
`Temperature <- TemperatureFromThetaExner`.

**Costs.** Framework 363 lines (+76). The composers lose their recipe
instances and `PhysicsDriver` its `_diagnose` (`physics_driver.py` 106,
`driver.py` 75). Providers run once per pass whatever the children's cadence:
`u` is derived for tmx on every physics step, active or not. Counts now
depend on the config: 8/8/8 for the example
and tmx-only, 4/0/8 without physics (IO's temperature only), 4/4/8 without
output, 4/0/8 for the prognostics config; `model_current` computes 8/8/8 in
every row.

**Checks.** As 07, plus `test_derived_by_is_a_source_on_the_declaration_only`,
`test_resolve_orders_the_providers_and_provide_runs_them`,
`test_resolve_refuses_an_inconsistent_derivation`, the `<- SaltFromDensity`
line in the dataflow test, and the per-config counts in `test_equivalence.py`.
