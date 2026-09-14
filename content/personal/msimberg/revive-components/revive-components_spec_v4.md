---
title: Revive components - spec v4
author: msimberg
tags: [components, model-state, protocol, interface, design, spec, field-registry, inputs-outputs, states]
created: 2026-09-02
updated: 2026-09-02
status: draft
---

# SPEC: The component, its inputs, and its outputs (v4)

## The design in one page

A central registry holds the global facts of every quantity (name, units,
dimensions). A type alias binds a quantity to a concrete field type, so the
`Annotated[...]` syntax appears exactly once, in the alias line. A component
is a typed box: it declares an input and an output dataclass whose fields use
those aliases, plus one method, `run`. States are collections of such fields;
inputs and outputs are views over states owned elsewhere. The composition
owns the states, allocates the buffers, collects the input views, and routes
the outputs. One compact pass through the four layers:

```python
# 1. registry + alias (quantities.py, abridged)
TEMPERATURE: Final[Quantity] = register(
    "air_temperature", units="K", dims=(dims.CellDim, dims.KDim),
    cf_key="temperature",
)
type TemperatureField = Annotated[fa.CellKField[ta.wpfloat], TEMPERATURE]
TENDENCY_TEMPERATURE: Final[Quantity] = register_tendency(
    "ddt_temp", of=TEMPERATURE,
)
type TemperatureTendencyField = Annotated[fa.CellKField[ta.wpfloat], TENDENCY_TEMPERATURE]

# 2. the component: nested interface + run, nothing else
class Muphys(Component):
    class Input:
        temperature: TemperatureField = decl(intent=Intent.READ)
        tracers: TracersView = decl(intent=Intent.READ)  # nested view: qv..qg
        ...

    class Output:
        ddt_temperature: TemperatureTendencyField
        precip_large_scale: PrecipLargeScaleField        # buffer bound by the caller
        ...

    def run(self, input: Input) -> Output: ...

# 3. the composition: owner-states, views, one step
input  = muphys.gather(entry_state, metric)   # generic: resolve by quantity
output = muphys.run(input)
apply(output, entry_state)                    # generic: accumulate tendencies

# 4. many components, one outer driver, all the same protocol
DerivedQuantities.run_on_state(model_state)   # intermediate producer
physics.run_on_state(model_state)             # physics driver: a component too
io.run_on_state(model_state)                  # IO: a sink component
```

Everything else in this spec details these lines: Part 1 covers the registry,
the aliases, and the per-occurrence declarations; Part 2 covers the
component, the states, the two generic verbs, ownership, and allocation. The
"Examples" section shows each shape with real names from the codebase.

## Scope

The parent proposal ([[personal/msimberg/revive-components/revive-components-synthesis|Components and model state]]) defines four parts:

1. **Part 1: every field declares itself once.** A central registry holds the
   global facts of each quantity (name, units, dimensions); field
   declarations reference the registry instead of restating them.
2. **Part 2: every component is a typed box.** A `Component` declares typed
   inputs and outputs and one method, `run`; the composition wires state to
   components and routes results.
3. **Part 3: introspection.** Deriving the composition tree and dataflow graph
   from the declarations (`driver.show()`, graphviz export).
4. **Part 4: epoch and generation staleness counters.** Registry counters that
   detect stale field references across buffer changes and time-level swaps.

This spec covers **parts 1 and 2 only**: the component and the fields it
declares.

- **In scope:** the quantity registry and the field declaration surface
  (part 1); the `Component` protocol, `Input`/`Output` slots as view-states, the
  state concept, input view construction and output routing, ownership and
  allocation rules, and coupling-mode requirements (part 2).
- **Out of scope, explicitly:** part 3 (introspection) and part 4 (the
  staleness counters, which this design deletes outright). Automatic edge
  assembly, the component verifier, IO cadence, and the sequential-coupling
  buffer machinery are composition-layer concerns, deferred; see "What moves
  to the composition layer". The Step / combinator layer and the D0-D3
  layering of v3 are unchanged; v3 remains their reference. MPI and halo
  exchange stay driver-level.

**Governing principle:** declare what you know about yourself; keep
everything else explicit. A component declares its interface. The composition
manages allocation and routing, as visible code, not hidden machinery. When
something can be an explicit component instead of machinery inside another
component, it is.

**Regularity goal:** as few special cases as possible. The design is
successful if the physics driver is expressible as a component, its subparts
as components, each physics process as a component, and IO as a component,
all through the same protocol. PR #1436 and its companion document (see
"Relationship to other documents") are the precedents that define what must
be expressible; they inform the constraints, not the software-engineering
detail decisions.

## States: the one concept

A **state** is a collection of fields that follow the declaration
conventions: every field is typed by an alias that references a registered
quantity, so every field carries its quantity's identity and metadata. This
definition is deliberately soft: a shared base class or protocol may emerge,
but the concept, not the inheritance, is what the design needs.

States can exist at every layer, and every layer is free to create them:

- The **model state** (prognostic fields, tracers, diagnostics): owned by the
  model/driver.
- **Intermediate owner-states**: buffers a composition or component creates
  for computed values.
- **Component inputs and outputs**: also states, but **views**: they collect
  fields from places where the allocation actually happened. A view never
  allocates.

One distinction matters: **owner vs view**. Whoever creates a state owns its
allocation; views reference buffers allocated elsewhere. All the machinery
below (input construction, output routing, allocation) is generic over
states; nothing in it knows which "kind" of state it touches.

This replaces the as-built's named special cases (`EntryState` facade,
`ComponentState` adapters); see "What this design supersedes from the
precedents".

## Part 1: every field declares itself once

### The Quantity registry

```python
import pint

@dataclasses.dataclass(frozen=True)
class Quantity:
    name: str                       # canonical identity
    units: pint.Unit                # parsed once at registration
    dims: tuple[gtx.Dimension, ...] # ONE source (full vs half level)
    cf_key: str | None = None       # IO name, required when IO-eligible
    of: "Quantity | None" = None    # set on tendency quantities only

def register(name, *, units, dims, cf_key=None) -> Quantity
def register_tendency(name, *, of, cf_key=None) -> Quantity
    # dims = of.dims; units = of.units / s (checked at registration)
```

- **`units`**: parsed and normalized with pint at registration, which
  validates dimensionality (a tendency's units are the parent's per second).
  Units are not used in computation today; they turn the current
  stringly-typed annotations into checked data and enable later unit-aware
  checks without any declaration-site change. pint is a pure-Python
  dependency; the registry stores the parsed unit, never a raw string.
- **`cf_key`**: the IO name for emitted quantities. Kept on the Quantity
  because the IO component is model-side; it can move to a side table the
  same way as the Fortran name if base icon4py should not know it.
- **`of`**: the single tendency link. A Quantity with `of` set IS a tendency
  (of that parent); this is what the routing and IO attribution read.

Deliberately NOT on the Quantity:

- **`icon_fortran_name`**: base icon4py (`model/common`) should not know
  Fortran naming at all. A separate name table, keyed by canonical name and
  owned by the layer that needs it (bindings, serialbox test adapters), maps
  `quantity.name -> icon_fortran_name`. The uniqueness check moves with it.
- **`precision`**: out of this version. Precision is currently handled by the
  wpfloat/vpfloat choice, and the registry has no use case for it until the
  precision work lands (PR #970 restores single precision; mixed precision is
  a later task). The alias line is the single place a dtype exists. It is
  fine to reintroduce a precision field with a per-occurrence check later;
  an unused, unchecked field does not belong in this version.
- **`restart`**: dropped. Whether the checkpoint set is a configurable field
  list (like an IO stream) or a declaration is an open question; the
  component design does not depend on the answer.

### Tendencies are registered quantities

Tendencies are registered, exactly like other quantities, with `of` naming
the parent. The reason is the alias abstraction: the purpose of the named
aliases is that the `Annotated[...]` syntax appears ONCE, in the alias line,
and never again at a declaration site. Expressing a tendency inline as
`Annotated[fa.CellKField[ta.wpfloat], TendencyOf(TEMPERATURE)]` at the output
dataclass would reintroduce the raw syntax per occurrence; explicit
registration keeps the declaration surface uniform:

```python
TENDENCY_TEMPERATURE: Final[Quantity] = register_tendency(
    "ddt_temp", of=TEMPERATURE, cf_key="tnndt"   # IO attribution: ddt_temp_muphys
)
type TemperatureTendencyField = Annotated[fa.CellKField[ta.wpfloat], TENDENCY_TEMPERATURE]
```

The cost is a manual `register_tendency` line per tendency (and one alias
line, as for every quantity). A possible refinement: the registry derives
tendency quantities automatically at `seal()` (one per registered quantity
unless excluded), removing the manual step; the alias lines stay hand-written
either way. Open item; the design works identically with both.

Routing never uses the name; it uses the quantity's `of` link.

### The per-occurrence declaration

```python
@dataclasses.dataclass(frozen=True)
class Decl:
    intent: Intent   # READ | READWRITE; Input class only
```

One fact, per-occurrence by nature:

- **`intent`**: `READ` (must not change) or `READWRITE` (written in place,
  which makes the component a producer of it). There is no intent on outputs;
  producing is implicit in being an output.

Removed from the old `Decl`, with reasons:

- **`lifetime`** (`STATIC`/`PERSISTENT`/`SCRATCH`): allocation is explicitly
  controlled (see "Ownership and allocation"); it is a decision of whoever
  creates the state, not a declared property. A declared lifetime was also
  untrue in one direction: components already allocate scratch once per
  instance and reuse it every step.
- **`labels` / `internal`**: their only consumer was the dead-output check of
  the deferred edge assembly. Dropped until that layer exists.
- **`role`/`kind`**: a component cannot know its wiring.
- The metadata-shadow copies (`_register_from_metadata` and its 118 registry
  entries) are deleted; the attrs dicts keep serving their direct consumers.

### The declaration surface

```python
# quantities.py, adjacent pairs (abridged)
TEMPERATURE: Final[Quantity] = register(
    "air_temperature", units="K", dims=(dims.CellDim, dims.KDim),
    cf_key="temperature",
)
type TemperatureField = Annotated[fa.CellKField[ta.wpfloat], TEMPERATURE]

TENDENCY_TEMPERATURE: Final[Quantity] = register_tendency(
    "ddt_temp", of=TEMPERATURE, cf_key="tnndt",
)
type TemperatureTendencyField = Annotated[fa.CellKField[ta.wpfloat], TENDENCY_TEMPERATURE]

# a component (abridged)
class MuphysInput:
    air_density: AirDensityField = decl(intent=Intent.READ)
    ...
```

The named-alias axis has exactly three forms:

1. **Hand-written literal alias (default).** Mypy-valid, no tooling, dims and
   dtype authored once per quantity. The hard constraint: the alias line
   must be a literal module-level statement (`= Annotated[...]` or PEP 695
   `type Name = ...`).
2. **Runtime factory** (`VnTraj = qfield(q.ICON_VN_TRAJ)`): dead. Mypy sees a
   variable of type `Any`; `rho: VnTraj` is rejected.
3. **Generated module**: mypy-valid but needs a generator, a committed module,
   and CI sync. Opt-in fallback only.

Layout of the alias lines is a taste decision: adjacent pairs inside
`quantities.py`, or extending the existing `field_type_aliases.py`. PEP 695
vs plain `=` aliases: `type` is self-documenting and lazy, but the runtime
reader must unwrap the `TypeAliasType` (one loop); plain `=` flattens eagerly.

### Spelling of per-occurrence metadata: OPEN

Two equal candidates, both mypy-clean:

- **Option A:** `rho: Annotated[Field, q.X] = decl(intent=READ)`, where
  `decl()` returns `dataclasses.field(metadata={"decl": Decl(...)})`. Reader:
  `dataclasses.fields()[i].metadata`; validation at import. Con: the
  assignment looks like a default value; the declaration splits across two
  channels.
- **Option B:** `rho: Annotated[Field, meta(q.X, intent=READ)]`, where the
  call sits in an `Annotated` extra slot. Reader:
  `get_type_hints(include_extras=True)`; one declaration site; mypy fully
  typechecks the call including keywords. Cons: reader machinery, a rule that
  all annotation names must be runtime-importable, validation moves to seal.

Facts that do not discriminate: gt4py strips `Annotated` extras before
`from_type_hint` (`func_to_foast.py:74`), and dataclass annotations never
reach gt4py's type translation, so cache granularity does not favor either.
Non-viable forms (rejected): `q.X.type` in the type slot (mypy rejects
instance-attribute access), `Annotated[*helper(...)]` (unchecked type slot),
keyworded extras (SyntaxError).

Two runtime gotchas of the slot mechanism, recorded so nobody fixes them
into bugs later: the base classes must read `self.Input`, not
`type(self).Input` (the class-attribute lookup bypasses the per-instance
assembly), and `typing.get_type_hints(component.run)` cannot resolve nested
`Input`/`Output` names (they live in the class namespace, not module
globals; `gather`/`apply` read the slot dataclasses, not `run`'s
signature).

### Self-checks, freeze, linter

- Per-occurrence check at `declare()`/`seal()`: alias dims vs `q.dims`. No
  alias enumeration needed; the check holds both sides. (A dtype check
  becomes possible if and when the precision axis returns.)
- Units are validated at registration (via pint), including the tendency
  rule (parent units per second); Fortran names in their own table.
- The registry freezes after `seal()`: any later `register` raises. A dtype
  change after import requires a fresh process (gt4py caches compiled
  stencils).
- A migration linter flags old-style `spec(quantity=, units=, dims=, ...)`
  declarations and unregistered `Annotated` tokens, at pre-commit.
- `bump_epoch`/`bump_generation` (proposal part 4) are removed (zero
  production callers; replaced by
  `test_fresh_registry_decouples_containers`).

## Part 2: the component, its inputs, and its outputs

### The component protocol

The protocol, in full:

```python
class Component:
    Input: type = EmptyInput       # the interface slot (a state class)
    Output: type = EmptyOutput

    # -- the one abstract member: the computation --
    def run(self, input: Input) -> Output:
        raise NotImplementedError

    # -- default methods, driven by the slots; overridable --
    def gather(self, *states) -> Input:
        ...   # sketch under "Input views"; reads self.Input

    # -- output routing: a method on the component, symmetric with gather --
    def apply(self, output: Output, *states) -> None:
        ...   # sketch under "Output routing"; reads self.Output
```

Contract rules:

- **`run` is the only member a component must implement.** No
  `init(Config)`: the constructor carries grid and config.
- **`gather` and `apply` are defaults, not abstract**: every component gets
  them; most never override them. `gather` may be overridden for sources
  the default cannot resolve (one real case today, see the advection
  example). `apply` is NOT expected to be overridden: derived updates
  (EOS, wind projection) are components in the composition, not apply
  overrides; if an apply override ever seems needed, that is a signal the
  logic belongs in a component or in `run`.
- **`Input` and `Output` are slots** holding frozen dataclasses of declared
  fields: states in the view role (see "States"). The component knows its
  interface; it does not manage anyone's state.
- **`apply` is a method, not a free function.** The verb form
  (`apply(output, state)`) in the sketches and examples is the call from
  the composition's side; it maps to the component's own default method
  (or to a free function dispatching on the slots, if a codebase prefers
  that; same mechanism either way).
- `EmptyInput`/`EmptyOutput` are empty frozen state dataclasses; a component
  with no inputs or no fresh outputs simply keeps them.
- **The protocol is nominal (an inherited base class), not structural (a
  `typing.Protocol`).** Defaults are part of the contract: a class that
  matches the protocol structurally but does not inherit it lacks the
  `gather`/`apply` defaults, passes every static structural check, and
  fails at runtime. A narrow structural seam (abstract `run` only, for
  test doubles or a free-function dispatch layer) can be added later as an
  optional extra; it is not the component contract.

The slots can be filled in three ways, and all three coexist:

1. **Nested classes** (the default for hand-written components):

```python
class Muphys(Component):
    class Input:
        temperature: TemperatureField = decl(intent=Intent.READ)
        ...
    class Output:
        ddt_temperature: TemperatureTendencyField
        ...

    def run(self, input: Input) -> Output: ...
```

2. **Module-level types bound to the slots** (shared types, or a style
   preference):

```python
@dataclass(frozen=True)
class AdvectionInput: ...

class Advection(Component[AdvectionInput, AdvectionOutput]):
    Input = AdvectionInput          # the slot is the runtime truth
    Output = AdvectionOutput
    def run(self, input: AdvectionInput) -> AdvectionOutput: ...
```

3. **Assembled per instance** (composites; see "Composite components"):

```python
class PhysicsDriver(Component):
    def __init__(self, processes):
        self.Input = assemble_input(processes)
```

All three fill the same slot; `gather` and `apply` read `self.Input` /
`self.Output`, so they never care which form was used. The subscript form
(`Component[InputT, OutputT]`) is optional documentation on top of the
slots, not a separate mechanism: the generic base gives `run` a checked
signature, and the slots give `gather`/`apply` the runtime interface. (The
subscript cannot reference the class's own nested classes; a class body
cannot name itself while it executes. `Component[...]` with module-level
types, or plain nesting, are the two static forms.)

**`Input` = the declared read/write set.**
- `READ`: the component reads it; must not change it.
- `READWRITE`: the component writes it in place, which makes it a producer
  of it.
- `Input` fields may themselves be nested states (groups of declared leaf
  fields); see "Nested states and views" below.
- The whole model state as `Input` is the forbidden degenerate case: the
  declared set stops naming anything.

**`Output` = what `run` produces that is not already in a state it received.**
- No intent, no mirrors. Producing is implicit; content is fully defined by
  `run`. `READ` on `Output` is forbidden at seal (a pass-through is a phantom
  producer; read the original producer's buffer instead).
- In-place writes NEVER appear in `Output`. A component that only writes
  received state in place has an **empty** `Output`; `Input` `READWRITE`
  is the single witness.
- Universal rule: `Output` is non-empty if and only if `run` produces values
  that must be routed or bound (tendencies, IO-bound quantities, values for
  other components).
- No replace verb for state writes: a replace-style write is an in-place
  write through `Input` `READWRITE`. Accumulation is the definition of a
  tendency.

### Ownership and allocation

The ownership rule: **the caller manages allocation; the component
knows its input and output.** The model owns the model state and passes it
down; components never manage it. A component may provide helpers (default
factories, convenience constructors for the states it is usually given), but
helpers are offers, not obligations.

Allocation is a first-class, visible decision. It is never inferred from
component behavior:

- **Owner-states** are created by the composition (or, for private scratch,
  by the component instance for itself). Buffer counts, shapes, and lifetimes
  are visible where the state is created.
- **Input views never allocate.** Building an input view is pure binding:
  it collects references to buffers that owner-states already hold. This is
  the rule that dissolves the as-built `EntryState` mix (see "superseded"
  below): if view construction needs a buffer, that buffer belongs to an
  owner-state created earlier, or to an upstream producer component.
- **Tendency buffers**: per-component instance (allocated once at
  construction, reused every step). Cross-process accumulation sums them
  into composition-owned accumulators, zeroed per step (`TendencyAccumulators`
  in the as-built).
- **Fresh non-tendency outputs** (diagnostics, IO-bound quantities): buffers
  allocated by the composition and bound to the component at construction
  (`DiagnosticsStore` + `bind_output_buffers` in the as-built). The
  component writes into the bound buffer. When the component runs standalone
  (component datatests), it allocates its own buffers instead; the
  declaration does not change, only who allocates.
- **Component scratch**: private to the instance, allocated at construction.
  No declaration, no registry entry.

No allocation happens implicitly between input construction and output
routing; every buffer exists because an owner-state's creator made it.

### Input views (the wiring question)

Something must collect a component's `Input` from one or more owner-states.
`gather` (or `collect_inputs`; name open) takes one or more states and
returns the input view. Requirements:

- **From multiple places into one input**: an input view may collect fields
  from several states (the as-built muphys collects prognostic views, its
  own `dz` from the metric, and diagnosed fields from three places).
- **Generic by default**: collection is driven by the declarations. Each
  declared input resolves by quantity identity from the composed owner
  states; the composition fixes source choices (for example `.now` vs
  `.next`) once, when it sets up the states. Time level is NOT a Quantity
  attribute and NOT in the registry.
- **Minimal machinery**: the default is declaration-driven resolution plus
  rare, small, hand-written overrides for sources the default cannot
  resolve (the advection two-source case, see the examples). No
  customization framework is built initially; add machinery only when a
  second real case demands it (open item 3).

Because `Input` is typed, correctness of the collection is checkable:
a missing or doubly-provided quantity is an error at construction, not a
string-key mismatch discovered at runtime (see "superseded": the as-built
`as_component_input() -> dict[str, Any]` and its unvalidated key agreement).

#### The default gather (sketch)

The default has three steps: flatten the given states into a
quantity-to-buffer map, resolve each declared input by quantity identity,
construct the `Input`. The sketch shows resolution only; the arithmetic
(thresholding, stencil launches) belongs to `run`:

```python
def gather(self, *states) -> Input:
    # 1. flatten: every leaf of every given state, keyed by quantity
    available: dict[Quantity, Field] = {}
    for leaf in declared_leaves(states):            # recurses nested states
        q, buf = leaf.quantity, leaf.buffer
        if q in available and available[q] is not buf:
            raise AmbiguousSource(q)                # same buffer twice is fine
        available[q] = buf
    # 2. resolve each declared input by quantity identity
    values = {}
    for name, d in declared_fields(self.Input):
        if d.quantity not in available:
            raise MissingInput(name, d.quantity)
        values[name] = available[d.quantity]
    return self.Input(**values)                     # intent is metadata only
```

What this needs from the runtime, and where it comes from:

- **`declared_fields(Input)`**: dataclass fields plus the annotation reader
  (the Option A/B machinery of Part 1). One small function, already required
  for the seal-time checks.
- **`leaf.quantity`**: a field knows its Quantity through its alias
  annotation; the same reader. Fields in an owner-state are constructed
  through the same aliases, so the identity is present on both sides.
- **`leaf.buffer`**: a field in a state holds (a reference to) its buffer;
  that is all a view ever reads. No allocation, no copying.

The whole routine is a few dozen lines, framework-free, and shared by every
component. Components whose inputs the default cannot resolve override
`gather` (one real case today, see the advection example) and typically call
the default first, then patch the special fields.

### Composite components (user-specified children)

A composite (the physics driver with user-specified physics processes) cannot
hand-write its interface: its read/write set is the union of the children's
sets, known only at construction. The composite assembles `Input` (and
`Output`) in `__init__` from the children's typed declarations:

```python
class PhysicsDriver(Component):
    def __init__(self, processes):
        self.Input = assemble_input(processes)   # per-instance slot fill

def assemble_input(processes) -> type:
    leaves = {}                                  # quantity -> (annotation, decl)
    for p in processes:
        for name, d, q in declared_fields(p.Input):
            merge_leaf(leaves, d)                # see the merge rules below
    return make_input_dataclass(leaves)          # frozen dataclass of leaves
```

Assembly from children's declaration fields produces a genuine frozen
dataclass; the per-instance slot override serves it to the generic
`gather`/`apply`; and the construction-time checks apply (missing quantity,
double provision, intent conflicts: see the merge rules below).

- **The merge rules** (construction-time): READ + READ is one READ leaf;
  the same buffer twice is fine; READWRITE + READWRITE on one quantity is an
  error under parallel coupling (independent in-place writers racing one
  buffer); READ + READWRITE is the sequential/accumulation case, legal but
  the composition must acknowledge it. The merge step is also where
  coupling rules are enforced, in one place.
- **The mypy boundary, stated honestly**: static checking covers each leaf
  component (its `Input` was checked at its declaration site: aliases, dims,
  seal checks). The assembled interface is opaque to mypy and is
  construction-checked instead, with the same rigor as the seal-time
  checks. For composites, the `Input` slot is runtime truth; per-leaf static
  guarantees are inherited from the children. A factory function
  (`make_physics_driver(processes) -> PhysicsDriver`) can serve as the
  typing seam for callers.
- **The line that must hold**: assembly consumes only typed declarations,
  never untyped dicts. This is what keeps the `as_component_input` status
  quo (see the precedents table) from re-entering through the plugin door.
- The whole-model-state degenerate case applies recursively: an assembled
  interface is still a set of named leaves, never a blob.

### Nested states and views

A field of a state may itself be a state: a group of declared leaf fields.

```python
class TracersView:        # a nested state (a view over the tracer group)
    qv: QvField
    qc: QcField
    ...
```

- **Nesting is grouping only.** Every leaf carries its quantity identity; a
  group adds no new mechanism, only a name for a set of fields.
- **Collection and routing recurse.** The generic gather resolves every
  leaf by quantity identity; apply routes every leaf the same way. A
  component can declare a group (all moisture species, the five surface-flux
  fields of the provider seam) without listing each leaf in its interface.
- **One quantity, two occurrences**: if the same quantity appears twice in
  one input view and the two occurrences need different sources, the
  default (one source per quantity) cannot resolve it. Such an input uses
  an explicit gather override. Tracer advection is the one real case today
  (see the examples).
- **The degenerate case applies recursively**: a group must not swallow a
  whole state. Every leaf must name its quantity, so the declared set keeps
  naming everything.

Collecting from a view is the same operation as collecting from an
owner-state: the mechanism reads fields by quantity identity from whatever
states it is given. The physics driver's processes, for example, collect
their inputs from the frozen entry view plus the driver's internal
owner-states.

### Output routing

Symmetric with input views: something must route a component's `Output`
into owner-states, possibly several. Routing is a first-class, generic
mechanism, driven by the typed output declarations:

- Tendency outputs (their Quantity has `of` set): **accumulated**
  (`target += dt * output`). The caller names the destination state, never
  the per-field targets; each tendency resolves its field target by its
  `of` link, so a tendency cannot be applied to the wrong field.
- Outputs whose Quantity has no `of`: **stored** where the composition
  decides: usually the pre-bound buffer (see allocation above), which makes
  routing a no-op for them; or an explicitly configured target (the
  as-built's per-process diagnostics store). Both remain expressible; the
  routing key is the typed declaration, not a string tag.

#### The default apply (sketch)

```python
def apply(self, output: Output, *states) -> None:
    # 1. flatten the destination states: quantity -> buffer
    targets = {q: buf for q, buf in leaf_buffers(states)}
    # 2. route each output leaf
    for name, leaf in declared_leaves(self.Output):
        parent = leaf.quantity.of
        if parent is None:
            continue        # non-tendency: buffer was bound at construction
        target = targets.get(parent)
        if target is None:
            raise MissingTarget(parent)
        accumulate_stencil(target, getattr(output, name), dtime)
```

Two feasibility notes:

- The routine only RESOLVES targets; the accumulation itself is a gt4py
  stencil (or an in-place addition), not a Python loop over cells. The
  resolution work per step is a few dict lookups per output field.
- Non-tendency outputs cost nothing here: their buffers were bound at
  construction (see "Ownership and allocation"), so the component wrote
  directly into its destination and apply skips them.

```python
input  = component.gather(state)     # state: one or more owner-states
output = component.run(input)
apply(output, state)                  # or apply_tendencies; name open
```

The verb names are open (`gather` vs `collect_inputs`; `apply` vs
`apply_tendencies` vs `store`; PR #1436 uses `collect_inputs`). The
question each names is deliberately general, not tendency-specific. A
convenience helper (`run_on_state`) is shown in the examples; it is an
example, not part of the design. The uniform protocol works for any
component: empty `Output` gives an empty apply step.

### Coupling modes

Both coupling modes must be expressible with the same protocol:

- **Parallel coupling** (as-built decision): every process computes from the
  same frozen input views; tendencies accumulate across processes; one apply
  writes back. Freezing is a composition decision: the views handed to the
  processes are not rewritten until the apply step.
- **Sequential coupling** (ICON's AES default for mig/vdf): a later process
  consumes an earlier process's within-step output. This needs provisional
  advance and working buffers: the composition-layer edge machinery (deferred,
  see below). The requirement on THIS design is to not preclude it: the
  declaration surface (inputs, outputs, tendency links) already names
  everything such machinery needs.

### Derived updates are components

The as-built `ApplyToPrognostic` bundles accumulation with two derived
updates: the exact-EOS exner/theta_v recomputation and the cells-to-edges
wind projection. This design extracts them as explicit components in the
composition, which makes the apply step itself generic. See the
`ExnerAndThetaVUpdate` example below.

### Halo exchange

Halo synchronization stays hidden for now: inside components, or between
driver phases around them (today: one natural sync point after the apply
step). A future design may make halo exchanges part of the general dataflow;
the declaration surface does not prevent that. Out of scope here.

### Intermediate components and IO regularize diagnostics

"Diagnostics" and "prognostics" are not special categories. Any component
that computes values other components need is an intermediate producer
(`DerivedQuantities` is today's single example, see the examples). Physics
and IO declare its outputs as `READ` inputs; the composition allocates one
buffer per declared output, so sharing is automatic and duplication is
impossible; consumers have no verb to compute their own copy. **IO as a
component** (its input declares what it emits; it appears in the composition
like any other component) is what removes the remaining specialness: an
emitted diagnostic is just a consumed output. How much derivation machinery
the composition grows around this (registry recipes, on-demand producers) is
composition-layer design, out of scope here.

## Examples (abridged, real names)

All examples omit fields and details (`...`); the names are the real ones
from the codebase and the #1436 stack. Together they demonstrate the
regularity goal: every layer uses the same protocol.

### A physics process: muphys (graupel microphysics)

Tendency outputs (registered tendencies) plus fresh diagnostics. All
non-tendency output buffers are bound at construction; the component never
applies anything itself.

```python
class Muphys(Component):
    class Input:
        air_density: AirDensityField = decl(intent=Intent.READ)
        temperature: TemperatureField = decl(intent=Intent.READ)
        pressure: PressureField = decl(intent=Intent.READ)
        tracers: TracersView = decl(intent=Intent.READ)  # nested view: qv..qg
        height: HeightField = decl(intent=Intent.READ)   # dz: metric, static
        ...

    class Output:
        ddt_temperature: TemperatureTendencyField
        ddt_qv: QvTendencyField
        ...                                              # ddt_qc..ddt_qg
        precip_large_scale: PrecipLargeScaleField        # pflx -> bound buffer
        ...

    def run(self, input: Input) -> Output: ...
```

### A multi-source process: tmx (turbulent mixing)

Shows one input collected from several owner-states: prognostic views, its
own derived inputs (`air_mass`, `cv_air`), and the five surface-flux fields
from a provider seam.

```python
class Tmx(Component):
    class Input:
        temperature: TemperatureField = decl(intent=Intent.READ)
        pressure_ifc: PressureIfcField = decl(intent=Intent.READ)
        wind_u: WindUField = decl(intent=Intent.READ)    # edge fields
        ...
        air_mass: AirMassField = decl(intent=Intent.READ)  # tmx-derived (rho*dz)
        cv_air: CvAirField = decl(intent=Intent.READ)
        surface_flux: SurfaceFluxView = decl(intent=Intent.READ)  # 5 fields
        ...

    class Output:
        ddt_temperature: TemperatureTendencyField
        ddt_qv: QvTendencyField
        ddt_wind_u: WindUTendencyField                   # tend_u/v/w
        ...
        mixing_length: MixingLengthField                 # km, kh, ... -> bound buffers
        ...

    def run(self, input: Input) -> Output: ...
```

The surface-flux provider is itself a component (a `ZeroFluxProvider` today,
ocean bulk fluxes later) whose outputs feed the tmx input view.

### The intermediate producer: DerivedQuantities

Computes the diagnosed physics fields once per step; everyone else reads
them. This is the component whose composition-allocated buffers replace the
as-built `EntryState`'s owned fields.

```python
class DerivedQuantities(Component):
    class Input:
        exner: ExnerField = decl(intent=Intent.READ)
        rho: AirDensityField = decl(intent=Intent.READ)
        vn: WindVnField = decl(intent=Intent.READ)
        ...

    class Output:
        temperature: TemperatureField                    # ta
        virtual_temperature: VirtualTemperatureField     # tv
        pressure: PressureField
        pressure_ifc: PressureIfcField
        wind_u: WindUField                               # u, v at cell centers
        ...

    def run(self, input: Input) -> Output: ...
```

Physics processes and IO declare these outputs as `READ` inputs; the
composition allocates one buffer per output.

### A derived update in the apply path: ExnerAndThetaVUpdate

Extracted from the as-built `ApplyToPrognostic` so the apply step stays a
generic router.

```python
class ExnerAndThetaVUpdate(Component):
    class Input:
        rho:     AirDensityField = decl(intent=Intent.READ)
        theta_v: ThetaVField     = decl(intent=Intent.READWRITE)
        exner:   ExnerField      = decl(intent=Intent.READWRITE)

    def run(self, input: Input) -> None:
        ...   # exact EOS: T' = ta + dt*ddt_T -> exner, theta_v
```

The wind projection (cells-to-edges, `compute_vn_from_uv`) is the same shape:
a component with empty `Output`.

### An in-place component: diffusion

Writes state in place; empty `Output`. `READWRITE` is the only witness that
it produces anything.

```python
class Diffusion(Component):
    class Input:
        exner: ExnerField = decl(intent=Intent.READWRITE)
        virtual_temperature: VirtualTemperatureField = decl(intent=Intent.READWRITE)
        wind_vn: WindVnField = decl(intent=Intent.READWRITE)
        ...

    def run(self, input: Input) -> None: ...
```

### A sink component: IO

Its input IS the emission list; it appears in the composition like any other
component. An emitted diagnostic is just a consumed output.

```python
class IO(Component):
    class Input:
        temperature: TemperatureField = decl(intent=Intent.READ)
        pressure: PressureField = decl(intent=Intent.READ)
        precip_large_scale: PrecipLargeScaleField = decl(intent=Intent.READ)
        ddt_temperature_muphys: TemperatureTendencyField = decl(
            intent=Intent.READ)          # attribution stream
        ...

    def run(self, input: Input) -> None:
        ...   # netcdf write; interval accumulation is its own state
```

### An input the default cannot resolve: tracer advection

The declaration-driven default resolves each declared quantity from one
source. Tracer advection needs each tracer quantity twice, from two sources:
the current-step value comes from the foreach item over tracers, the
new-step value from `tracers.next`, keyed by name. One quantity, two
occurrences with different sources: no default rule can decide, so the
component overrides gather with a small explicit mapping. This is an
override case, not a framework.

```python
class TracerAdvection(Component):
    class Input:
        tracers_now: TracersView = decl(intent=Intent.READ)       # foreach item
        tracers_new: TracersView = decl(intent=Intent.READWRITE)  # tracers.next
        airmass_now: AirMassView = decl(intent=Intent.READ)
        ...

    def gather(self, *states):   # override: map the two sources explicitly
        ...

    def run(self, input: Input) -> None: ...
```

### A convenience helper: run_on_state

An example of a helper a codebase could define (on the Component protocol,
or as a free function). It is NOT part of the design.

```python
def run_on_state(component, state):
    output = component.run(component.gather(state))
    apply(output, state)
    return output

# use at the outer driver
DerivedQuantities.run_on_state(model_state)   # diagnosed fields, once
physics.run_on_state(model_state)             # the physics driver component
io.run_on_state(model_state)                  # sink, cadence by gated steps
```

Convenient for tests and simple sequential compositions. Real drivers keep
the phases explicit: halo exchanges, coupling, and view freezing happen
between the phases, which this helper hides.

### The physics driver as a component (parallel coupling)

The driver is expressible through the same protocol: its input is a view
over the model state (frozen by the caller before `run`), and `run`
composes the processes, accumulates, applies once, and runs the derived
updates. It uses only the generic verbs on its input and its internal
owner-states; it defines no new machinery.

```python
class PhysicsDriver(Component):
    def __init__(self, processes, factories, grid, backend):
        self.processes = processes
        self.Input = assemble_input(processes)     # composite; see above
        self.Output = assemble_output(processes)   # non-tendency outputs
        self.outputs = make_owner_state(...)       # internal buffers

    def run(self, input):
        # input: the frozen entry view over the model state
        for process in self.processes:
            p_in = process.gather(input, self.air_mass, self.surface_flux)
            p_out = process.run(p_in)   # parallel coupling: same frozen entry
            apply(p_out, self.outputs)  # internal owner-state: tendencies
                                        # accumulate, diagnostics store
        apply(self.outputs, input)      # the single write-back through the
                                        # entry view (dt * accumulated sums)
        for update in (self.exner_and_theta_v, self.wind_projection):
            update.run(update.gather(input))   # in-place; empty Output
        return self.Output(                    # view over the bound buffers
            precip_large_scale=self.outputs.precip_large_scale,
            mixing_length=self.outputs.mixing_length,
            ...
        )
```

With a FIXED process set the same component can hand-write nested `Input`/
`Output` classes instead of assembling; the assembly form is for
user-specified processes (see "Composite components").

`self.outputs` is the driver's internal owner-state (tendency accumulators
and diagnostics buffers, constructed in `__init__` from factories, grid,
and backend). Whether the accumulators and the diagnostics store are one
state or two is an implementation choice; both are ordinary owner-states.

Sequential coupling (ICON's mig/vdf order) composes the same way with the
processes chained instead of parallel; the buffer machinery is
composition-layer work (deferred).

## What this design supersedes from the precedents

PR #1436 and its companion document are precedents for the **shape of
composition** and the **constraints** (no copies, pointer binding, frozen
entry views, accumulate-across-processes, apply-once, per-process
diagnostics, provider seams, unchanged component datatests when standalone).
They are not normative for engineering detail, and they deliberately shipped
status-quo compromises so they could land before this design was finished.
The design must express everything they do; the following details are
consciously superseded:

| As-built detail | Status | This design |
|---|---|---|
| `as_component_input() -> dict[str, Any]` | status quo, deliberately temporary | typed `Input`; missing/doubly-provided quantities are construction-time errors, not runtime key mismatches |
| `kind == "tendency"` string tags routing outputs | status quo | registered tendency quantities with `of` links |
| `ComponentState` adapter protocol (two methods, no storage) | status quo, exists because inputs/outputs are untyped dicts | dissolves: collection is generic and declaration-driven; no separate protocol |
| `EntryState` facade (view binding + diagnosed-field allocation in one object) | status quo | decomposed: view binding is the generic input mechanism; diagnosed fields are `DerivedQuantities` outputs with composition-allocated buffers; the facade may survive as a driver convenience, not a design concept |
| `ApplyToPrognostic` bundling accumulate + EOS + wind projection | status quo | accumulation stays in the generic apply; EOS and wind projection become explicit components |
| `gather` -> `collect_inputs` rename | settled there, open here | naming is an open item of this spec |
| Parallel-only coupling | settled decision there | both parallel and sequential must be expressible here |
| Diagnostics store keyed by process | status quo | expressible; whether pre-bound buffers or post-run routing is the default is an open item |

## What moves to the composition layer

These mechanisms belong to the composition (a later part, or v3's layer),
not to parts 1 and 2:

- **Automatic edge assembly**: producer/consumer discovery, handoff
  same-buffer identity, shared-read counting, dead-output errors. The
  declaration surface provides all the facts (producers = `Output` +
  `READWRITE` occurrences; consumers = `READ` occurrences).
- **Sequential-coupling machinery**: provisional advance, working buffers,
  within-step ordering.
- **The `internal` marker**: dropped from `Decl` for now; reintroduce with
  edge assembly if the dead-output check needs it.
- **The component verifier**: not needed for the first ship; the
  declarations keep it constructible later.
- **Derived-quantity recipes** (registry-declared derivation stencils with
  on-demand producers): evolution of intermediate components.
- **Gated steps** (`when` predicates, IO cadence): Step-list policy.
- **The checkpoint/restart set**: configurable field list vs declaration is
  open; it touches only the restart component's configuration.

## Excluded paths (recorded, with reasons)

| Idea | Outcome | Reason |
|---|---|---|
| `role` / `kind=HANDOFF` field flag | Deleted | A component cannot know its wiring |
| `output` flag on outputs | Deleted; IO declares what it reads | Same layering principle |
| `intent` on outputs | Deleted; producing implicit | `Input` = consume/mutate, `Output` = produce |
| Mirror fields in outputs | Removed | Redundant; drift risk |
| Replace verb for state writes | Not taken | In-place `READWRITE` writes cover it; accumulation defines a tendency |
| Boundary-owned `store`/`emit` verb | Deleted; IO is a component that reads | The sink should own the sink; output routing is generic, not boundary-owned |
| Cached target slot | Deleted | Target selection is composition code, not per-step state |
| `lifetime` on `Decl` | Removed | Allocation belongs to whoever creates the state, not the declaration |
| `labels`/`internal` on `Decl` | Removed for now | Only consumer (edge assembly) is out of scope |
| `precision` on the Quantity | Out this version | No current use case; wpfloat/vpfloat choice suffices; may return with its check |
| `restart` on the Quantity | Removed for now | Checkpoint-set shape is an open question |
| Unregistered tendencies (inline `TendencyOf` token) | Rejected | Reintroduces raw `Annotated` syntax at declaration sites; registration keeps the alias abstraction uniform |
| Fortran name on the Quantity | Moved to a side table | Base icon4py should not know Fortran naming |
| Stringly-typed units | Replaced by pint | Strings are only good for printing |
| Code-generated alias module as default | Not taken | Hand-written aliases give the same gains without tooling |
| `Tendency[A]` generic, `NewType`, `Field` subclassing | Rejected | Mypy or gt4py cannot express them |
| Positional typed `run` | Rejected | Loses output names and source pairing |
| Whole model state as `Input` | Forbidden | The declared set stops naming anything |
| Dynamically discovered / type-keyed state | Rejected | Declaration-driven collection is the explicit bridge; the state must not know component types |
| Untyped dict component inputs | Superseded | See the precedents table |
| EOS as hidden machinery inside muphys or apply | Replaced by components | Explicit composition over hidden machinery |
| Input-customization framework (built upfront) | Not built | Declaration-driven default plus hand-written overrides; machinery only on a second real case |
| `typing.Protocol` as the component base | Rejected | Defaults are part of the contract; a structurally-valid non-inheriting class passes static checks and fails at runtime |
| Epoch/generation counters (part 4) | Deleted | Zero production callers |
| Component verifier (first ship) | Deferred | Not needed now; declarations keep it constructible |

## Open items

1. Metadata spelling (Option A `decl()` vs Option B `meta()` in `Annotated`).
2. Alias layout (adjacent in `quantities.py` vs `field_type_aliases.py`).
3. Gather verb name (`gather` vs `collect_inputs`) and how much of the
   declaration-driven default needs machinery vs convention.
4. Apply verb name and reach (`apply`, `apply_tendencies`, `store`), and
   whether pre-bound buffers or post-run routing is the default for
   non-tendency outputs.
5. Whether the registry auto-derives tendency quantities at `seal()` (one
   per registered quantity unless excluded) to remove the manual
   `register_tendency` step; alias lines stay hand-written either way.
6. Composite interface merge rules: exact behavior of READ + READWRITE
   under each coupling mode, and where the acknowledge step lives
   (composition config vs error).
7. Checkpoint/restart set: configurable field list vs declaration.
8. Whether `cf_key` moves to a side table like the Fortran name.

## Migration notes

- Ship part 1 before part 2 (the generic collection and routing read the
  declaration surface).
- Migrate producer+consumer handoff pairs (dycore and tracer advection) as
  ONE unit; non-handoff components migrate independently.
- Keep the migration linter until the old declarations are gone.
- The #1436 stack can adopt this design incrementally: its dict-based
  adapters collapse into the typed `Input` slots and the declaration-driven
  default; `DiagnosticsStore` and `TendencyAccumulators` are already the
  explicit-allocation story; `EntryState` decomposes when `DerivedQuantities`
  covers the diagnosed fields.

## Python version assumptions

- The examples use PEP 695 syntax (`type X = ...` aliases and the
  `Component[InputT, OutputT]` subscript), which needs Python 3.12; icon4py
  supports 3.11+.
- Everything in this design is expressible on 3.11: plain
  `X = Annotated[...]` aliases and a `class Component(Generic[InputT,
  OutputT])` base. The PEP 695 forms are preferred for readability only.
- No 3.13+ features are assumed.

## Relationship to other documents

- Main note: [[personal/msimberg/revive-components/revive-components|Revive
  components]].
- v3 spec ([[personal/msimberg/revive-components/revive-components_spec_v3|composition
  layer]]): NOT superseded by this document; the Step / combinator layer and
  the D0-D3 progression remain its subject. This v4 supersedes v3's
  Component contract and field-metadata sections.
- `GOAL.md` and `SPEC.md` in the repository: implementation plan and locked
  decisions; the v4-direction section in `SPEC.md` records the supersessions
  (D10, D13, D14).
- PR #1436 (`refactor(physics_driver): two layer physics state`) and its
  companion document
  [[personal/Yilu/physics-interface-current-design|Physics interface -
  current design (as built)]]: precedents for the shape of composition and
  the constraints; the "superseded" table above separates what must be
  expressible from what is deliberately temporary as-built detail.
  The related [[personal/OngChia/physics-driver-and-components|Physics
  driver and component design]] proposal overlaps in protocol shape; the
  superseded table covers the overlap.
- PR #970 (restore single precision): the precondition for possibly
  reintroducing the registry precision axis.