import dataclasses
import functools
import types
import typing
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any, ClassVar, dataclass_transform

import gt4py.next as gtx
import numpy as np
from icon4py.model.common import dimension, type_alias as ta


# ------------------------------------------------------------------------------
# Quantity and Dims: type-level tags, never instantiated
# ------------------------------------------------------------------------------
# A place on the grid: the gt4py dimensions of a field there.
class Dims:
    dims: ClassVar[tuple[gtx.Dimension, ...]]

    def __init_subclass__(cls, *, dims: tuple[gtx.Dimension, ...]) -> None:
        super().__init_subclass__()
        cls.dims = dims

    def __new__(cls, *args: Any, **kwargs: Any) -> Any:
        raise TypeError(f"{cls.__name__} is a type-level tag, not a value")


class Cell(Dims, dims=(dimension.CellDim,)): ...
class CellK(Dims, dims=(dimension.CellDim, dimension.KDim)): ...
class CellKHalf(Dims, dims=(dimension.CellDim, dimension.KHalfDim)): ...
class Edge(Dims, dims=(dimension.EdgeDim,)): ...
class EdgeK(Dims, dims=(dimension.EdgeDim, dimension.KDim)): ...
class EdgeKHalf(Dims, dims=(dimension.EdgeDim, dimension.KHalfDim)): ...


# One subclass per quantity; the CF metadata sits on the class and the places
# on the grid it lives at are nested aliases, `ThetaV.CellK`,
# `ThetaV.CellKHalf`. A keyword not given is inherited from the base (a marker
# base like `Tendency` gives none).
class Quantity:
    standard_name: ClassVar[str | None] = None
    units: ClassVar[str]
    long_name: ClassVar[str | None] = None
    _places: ClassVar[tuple[type[Dims], ...]]

    def __init_subclass__(
        cls, *, standard_name: str | None = None, units: str | None = None, long_name: str | None = None
    ) -> None:
        super().__init_subclass__()
        for name, value in (("standard_name", standard_name), ("units", units), ("long_name", long_name)):
            if value is not None:
                setattr(cls, name, value)
        if REGISTRY.setdefault(cls.__name__, cls) is not cls:
            raise DuplicateQuantity(cls.__name__)
        if cls.standard_name and any(q.standard_name == cls.standard_name for q in REGISTRY.values() if q is not cls):
            raise DuplicateQuantity(f"{cls.__name__}: standard_name {cls.standard_name} is taken")

    def __new__(cls, *args: Any, **kwargs: Any) -> Any:
        raise TypeError(f"{cls.__name__} is a type-level tag, not a value")

    # the places this quantity declares, read from its nested aliases (a
    # derived quantity has its parent's)
    @classmethod
    def places(cls) -> tuple[type[Dims], ...]:
        if "_places" in vars(cls):
            return cls._places
        return tuple(
            typing.get_args(alias.__value__)[1]
            for alias in vars(cls).values()
            if isinstance(alias, typing.TypeAliasType)
        )


# A gt4py field tagged by its quantity and its place. Both tags are phantom
# type parameters: `Field[ThetaV, CellK]` and `Field[ThetaV, CellKHalf]` are
# different types to mypy and pyright (gt4py's own `CellKField` and
# `CellKHalfField` are not: dims are runtime objects to the checkers), the same
# array to gt4py. Stencils get `.data`. Invariant in both parameters.
class Field[Q: Quantity, D: Dims]:
    __slots__ = ("quantity", "dims", "data")

    def __init__(self, quantity: type[Q], dims: type[D], data: gtx.Field[Any, Any]) -> None:
        self.quantity = quantity
        self.dims = dims
        self.data = data

    def __repr__(self) -> str:
        return f"Field({self.quantity.__name__}, {self.dims.__name__}, {self.data.ndarray.shape})"


def zeros[Q: Quantity, D: Dims](
    quantity: type[Q], dims: type[D], sizes: Mapping[gtx.Dimension, int]
) -> Field[Q, D]:
    return Field(quantity, dims, gtx.zeros({dim: sizes[dim] for dim in dims.dims}, dtype=ta.wpfloat))


class DuplicateQuantity(ValueError):
    pass


class UnknownQuantity(KeyError):
    pass


# every quantity tag by class name, class names and CF standard_names both
# unique; the output config names a quantity by either
REGISTRY: dict[str, type[Quantity]] = {}


# a quantity that lives somewhere (a marker base or a generic like TendencyOf
# is not one)
def lookup(key: str) -> type[Quantity]:
    for quantity in REGISTRY.values():
        if key in (quantity.standard_name, quantity.__name__) and quantity.places():
            return quantity
    raise UnknownQuantity(key)


# A tendency is a quantity derived from its parent. `TendencyOf[Temperature]`
# names it in a type and `tendency_of(Temperature)` is the one class behind it
# at runtime: the parent's places, its units per second, the CF `tendency_of_`
# name, and `parent`, the link that says where the tendency lands.
class TendencyOf[Q: Quantity](Quantity):
    parent: ClassVar[type[Quantity]]


type Tendency[Q: Quantity, D: Dims] = Field[TendencyOf[Q], D]


_DERIVED: dict[tuple[type[Quantity], type[Quantity]], type[Quantity]] = {}


def _derive(base: type[Quantity], quantity: type[Quantity], units: str, standard_name: str | None) -> Any:
    if (base, quantity) not in _DERIVED:
        name = f"{base.__name__}{quantity.__name__}"
        cls: Any = types.new_class(name, (base,), {"units": units, "standard_name": standard_name})
        cls.parent = quantity
        cls._places = quantity.places()
        _DERIVED[base, quantity] = cls
    return _DERIVED[base, quantity]


def tendency_of(quantity: type[Quantity]) -> type[TendencyOf[Any]]:
    units = "s-1" if quantity.units == "1" else f"{quantity.units} s-1"
    standard_name = f"tendency_of_{quantity.standard_name}" if quantity.standard_name else None
    return typing.cast(type[TendencyOf[Any]], _derive(TendencyOf, quantity, units, standard_name))



# ------------------------------------------------------------------------------
# State: a frozen dataclass of typed leaves
# ------------------------------------------------------------------------------
# where a leaf's value comes from when the composer does not supply it; the
# state band only carries one on the Decl, the component band defines them
class Source:
    pass


class UnresolvedInput(ValueError):
    pass


# one Field leaf read back from a State class: its name, quantity, place and
# source
@dataclasses.dataclass(frozen=True)
class Decl:
    name: str
    quantity: type[Quantity]
    dims: type[Dims]
    source: Source | None

    @property
    def key(self) -> tuple[type[Quantity], type[Dims]]:
        return (self.quantity, self.dims)

    # the quantity, and the place when the quantity lives at more than one
    @property
    def label(self) -> str:
        located = len(self.quantity.places()) > 1
        return self.quantity.__name__ + (f"@{self.dims.__name__}" if located else "")


class InvalidDims(TypeError):
    pass


@dataclass_transform(frozen_default=True, kw_only_default=True, eq_default=False)
class State:
    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        dataclasses.dataclass(frozen=True, eq=False, kw_only=True)(cls)
        cls.declarations()  # read now: an undeclared place is refused where the class is defined

    # a hand-built State cannot smuggle a source through: every leaf is a value
    def __post_init__(self) -> None:
        for d, value in self.leaves():
            if isinstance(value, Source):
                raise UnresolvedInput(f"{type(self).__qualname__}.{d.name}")

    # the Field leaves, in declaration order; plain leaves (floats, ints,
    # datetimes) are ordinary dataclass fields and not listed
    @classmethod
    def declarations(cls) -> tuple[Decl, ...]:
        return _declarations(cls)

    def leaves(self) -> Iterator[tuple[Decl, Field[Any, Any]]]:
        for d in self.declarations():
            yield d, getattr(self, d.name)


_DECLARATIONS: dict[type[State], tuple[Decl, ...]] = {}


# walks `type` aliases, plain (`ThetaV.CellK`) and generic
# (`Tendency[Temperature, CellK]`), down to the Field
def _unwrap(hint: Any) -> Any:
    while True:
        if isinstance(hint, typing.TypeAliasType):
            hint = hint.__value__
        elif isinstance(hint, types.GenericAlias) and isinstance(hint.__origin__, typing.TypeAliasType):
            hint = hint.__origin__.__value__[hint.__args__]
        else:
            return hint


# refuses a place the quantity does not declare
def _declarations(cls: type[State]) -> tuple[Decl, ...]:
    if cls not in _DECLARATIONS:
        hints = typing.get_type_hints(cls)
        found = []
        for field in dataclasses.fields(cls):  # type: ignore[arg-type]
            hint = _unwrap(hints[field.name])
            if typing.get_origin(hint) is Field:
                quantity, dims = typing.get_args(hint)
                if typing.get_origin(quantity) is TendencyOf:
                    quantity = tendency_of(typing.get_args(quantity)[0])
                if dims not in quantity.places():
                    raise InvalidDims(f"{cls.__qualname__}.{field.name}: {quantity.__name__} at {dims.__name__}")
                source = field.default if isinstance(field.default, Source) else None
                found.append(Decl(field.name, quantity, dims, source))
        _DECLARATIONS[cls] = tuple(found)
    return _DECLARATIONS[cls]


class Empty(State):
    pass


# builds a State class at runtime, one leaf per (name, type), with a source
# where given; for a view whose leaves come from the config, like IO's
def state_type(name: str, leaves: Mapping[str, Any], sources: Mapping[str, Source] = {}) -> type[State]:
    def body(namespace: dict[str, Any]) -> None:
        namespace["__annotations__"] = dict(leaves)
        namespace.update(sources)

    return typing.cast(type[State], types.new_class(name, (State,), exec_body=body))


def allocate[S: State](
    cls: type[S],
    sizes: Mapping[gtx.Dimension, int],
    fill: Callable[[str, tuple[int, ...]], Any] | None = None,
) -> S:
    values = {}
    for d in cls.declarations():
        f = zeros(d.quantity, d.dims, sizes)
        if fill is not None:
            np.asarray(f.data.ndarray)[...] = fill(d.name, f.data.ndarray.shape)
        values[d.name] = f
    return cls(**values)


# Driver-owned time levels: the driver passes `.now` as a component's input and
# `.next` as its output, so no component ever sees a TimeStepPair. A component
# may own a PredictorCorrectorPair of its own scratch, as the dycore does.
class Pair[S: State]:
    def __init__(self, first: S, second: S) -> None:
        self.first, self.second = first, second

    def swap(self) -> None:
        self.first, self.second = self.second, self.first


class TimeStepPair[S: State](Pair[S]):
    @property
    def now(self) -> S:
        return self.first

    @property
    def next(self) -> S:
        return self.second


class PredictorCorrectorPair[S: State](Pair[S]):
    @property
    def predictor(self) -> S:
        return self.first

    @property
    def corrector(self) -> S:
        return self.second


# ------------------------------------------------------------------------------
# Collecting a view from states
# ------------------------------------------------------------------------------
class MissingInput(KeyError):
    pass


class AmbiguousSource(ValueError):
    pass


# flattens states to {(quantity, dims): field}; two different buffers for one
# key is AmbiguousSource, the same buffer twice is fine
def _available(states: Iterable[State]) -> dict[tuple[type[Quantity], type[Dims]], Field[Any, Any]]:
    available: dict[tuple[type[Quantity], type[Dims]], Field[Any, Any]] = {}
    for state in states:
        for d, value in state.leaves():
            if available.setdefault(d.key, value) is not value:
                raise AmbiguousSource(d.label)
    return available


# one leaf per Field declaration of cls, picked from the given states by
# (quantity, dims); plain leaves by keyword, and a Field leaf given by keyword
# wins over the pool. Pointer selection only, never computes.
def collect[S: State](cls: type[S], *states: State, **plain: Any) -> S:
    available = _available(states)
    values: dict[str, Any] = dict(plain)
    for d in cls.declarations():
        if d.name in plain:
            continue
        if d.key not in available:
            raise MissingInput(f"{cls.__qualname__}.{d.name}: {d.label}")
        values[d.name] = available[d.key]
    return cls(**values)


# ------------------------------------------------------------------------------
# Component: Input, Output, run
# ------------------------------------------------------------------------------
# `run` is the only method a component implements. `out = component.run(input)`
# writes into the component's own buffers, allocated once on first use;
# `component.run(input, out=view)` writes where the caller says, numpy `out=`
# style. Either way `run` returns the output. The aliasing a component
# tolerates is declared in `in_place`; `Plan.run` refuses any other.
class Component:
    Input: type[State]
    Output: type[State]
    # the Output leaves that may share the buffer of the same-quantity Input
    # leaf (pointwise stencils); Plan.run refuses any other aliasing
    in_place: ClassVar[frozenset[str]] = frozenset()

    def __init__(self, sizes: Mapping[gtx.Dimension, int]) -> None:
        self.sizes = sizes

    @functools.cached_property
    def output(self) -> Any:
        return allocate(type(self).Output, self.sizes)

    # the caller's buffers when given, else this component's own
    def buffers[T: State](self, out: T | None) -> T:
        return self.output if out is None else out

    def run(self, input: Any, out: Any = None) -> Any:
        raise NotImplementedError


# A derivation: quantities computed from other quantities, declared like any
# component and kept in one shared module so every consumer picks a recipe
# rather than writing a stencil call and a buffer of its own. A recipe's
# Output quantities are not among its Input quantities; a component that
# writes back what it reads is an update, not a recipe. The empty subclass is
# the name, nothing reads it yet; the composer decides when to run it.
class Recipe(Component):
    pass


class InconsistentDerivation(ValueError):
    pass


class InconsistentRelocation(ValueError):
    pass


class AliasedOutput(ValueError):
    pass


type Key = tuple[type[Quantity], type[Dims]]

# one recipe per quantity at a place across the whole model, filled once a
# resolve succeeds: two composites deriving the same key by different recipes
# fail at the second init. Process-wide, so one interpreter holds one model.
DERIVATIONS: dict[Key, type[Recipe]] = {}
# the recipes that move a quantity between two of its places, (quantity,
# from, to); the table a family-level lookup could read later
RELOCATIONS: dict[tuple[type[Quantity], type[Dims], type[Dims]], type[Recipe]] = {}


# registers a recipe that moves one quantity from one of its places to
# another: one Output leaf, an Input leaf of the same quantity elsewhere
def relocation[R: type[Recipe]](recipe: R) -> R:
    outputs = recipe.Output.declarations()
    if len(outputs) != 1:
        raise InconsistentRelocation(f"{recipe.__name__}: one output leaf expected")
    (out,) = outputs
    sources = [d for d in recipe.Input.declarations() if d.quantity is out.quantity and d.dims is not out.dims]
    if len(sources) != 1:
        raise InconsistentRelocation(f"{recipe.__name__}: {out.quantity.__name__} at another place expected in Input")
    key = (out.quantity, sources[0].dims, out.dims)
    if RELOCATIONS.setdefault(key, recipe) is not recipe:
        raise InconsistentRelocation(f"{out.quantity.__name__}: {RELOCATIONS[key].__name__} vs {recipe.__name__}")
    return recipe


@dataclasses.dataclass(frozen=True)
class Derived(Source):
    recipe: type[Recipe]


# leaf default: `temperature: Temperature.CellK = derived_by(TemperatureFromThetaExner)`
# says which recipe provides the leaf when the composer does not supply it
def derived_by(recipe: type[Recipe]) -> Any:
    return Derived(recipe)


# the recipes the children's derived_by leaves name, one instance each,
# ordered so that a recipe reading another's output runs after it
@dataclasses.dataclass(frozen=True)
class Resolution:
    providers: tuple[Recipe, ...]

    # runs every provider on the supplied states and what was produced before
    # it, returns the produced states; one pass, the composer collects from both
    def provide(self, *supplied: State) -> tuple[State, ...]:
        produced: list[State] = []
        for recipe in self.providers:
            produced.append(recipe.run(collect(recipe.Input, *supplied, *produced)))
        return tuple(produced)


# one recipe per (quantity, dims) across the children and the recipes
# themselves; a recipe must produce the leaf it is named on
def resolve(children: Iterable[type[Component] | Component], sizes: Mapping[gtx.Dimension, int]) -> Resolution:
    by_key: dict[tuple[type[Quantity], type[Dims]], type[Recipe]] = {}
    queue: list[type[Component] | Component] = list(children)
    seen: list[type[Component] | Component] = []
    while queue:
        child = queue.pop(0)
        seen.append(child)
        for d in child.Input.declarations():
            if not isinstance(d.source, Derived):
                continue
            recipe = d.source.recipe
            if d.key not in {o.key for o in recipe.Output.declarations()}:
                raise InconsistentDerivation(f"{child.Input.__qualname__}.{d.name}: {recipe.__name__} does not produce {d.label}")
            if by_key.setdefault(d.key, recipe) is not recipe:
                raise InconsistentDerivation(f"{d.label}: {by_key[d.key].__name__} vs {recipe.__name__}")
            if recipe not in queue and recipe not in seen:
                queue.append(recipe)
    recipes = list(dict.fromkeys(by_key.values()))
    produced_by = {o.key: r for r in recipes for o in r.Output.declarations()}
    ordered: list[type[Recipe]] = []
    visiting: list[type[Recipe]] = []

    def visit(recipe: type[Recipe]) -> None:
        if recipe in ordered:
            return
        if recipe in visiting:
            raise InconsistentDerivation("cycle: " + " -> ".join(r.__name__ for r in (*visiting, recipe)))
        visiting.append(recipe)
        for d in recipe.Input.declarations():
            if d.key in produced_by and produced_by[d.key] is not recipe:
                visit(produced_by[d.key])
        visiting.pop()
        ordered.append(recipe)

    for recipe in recipes:
        visit(recipe)
    for key, recipe in by_key.items():
        if DERIVATIONS.get(key, recipe) is not recipe:
            raise InconsistentDerivation(f"{recipe.__name__}: {DERIVATIONS[key].__name__} derives the same key in another composite")
    DERIVATIONS.update(by_key)
    return Resolution(tuple(recipe(sizes) for recipe in ordered))


# ------------------------------------------------------------------------------
# Updates: what a process adds to the model, declared on the process
# ------------------------------------------------------------------------------
class InconsistentUpdate(ValueError):
    pass


class UnappliedTendency(ValueError):
    pass


class UnappliedIncrement(KeyError):
    pass


# Update leaf default on a leaf of the quantity itself: `temperature:
# Temperature.CellK = from_tendency()` says temperature gets dt times the
# process's own tendency of it; `vn: Vn.EdgeK = from_tendency(VnTendencyFromUTendency)`
# dt times the tendency a recipe derives from the process's outputs
@dataclasses.dataclass(frozen=True)
class FromTendency(Source):
    recipe: type[Recipe] | None = None


def from_tendency(recipe: type[Recipe] | None = None) -> Any:
    return FromTendency(recipe)


# Update leaf default: the component that rewrites the leaf once, after all
# tendencies are applied (`theta_v: ThetaV.CellK = after_increments(ExnerThetaFromTemperature)`)
@dataclasses.dataclass(frozen=True)
class AfterIncrements(Source):
    hook: type[Component]


def after_increments(hook: type[Component]) -> Any:
    return AfterIncrements(hook)


def _parent_key(d: Decl) -> tuple[type[Quantity], type[Dims]]:
    parent: type[Quantity] = getattr(d.quantity, "parent")
    return (parent, d.dims)


# A component that emits tendencies and says in `Update` where they land.
class Process(Component):
    Update: type[State] = Empty

    # each tendency named in Update into the matching sum in `into`: the
    # process's own (in output) or a recipe's (in computed); dt comes later,
    # once, in Updates.update
    def accumulate(self, into: State, output: State, *computed: State) -> None:
        sums = {d.key: value for d, value in into.leaves()}
        tendencies = _available((output, *computed))
        for d in self.Update.declarations():
            if isinstance(d.source, FromTendency):
                key = (tendency_of(d.quantity), d.dims)
                np.asarray(sums[key].data.ndarray)[...] += np.asarray(tendencies[key].data.ndarray)


# The composite's view of its processes' Update blocks: one summed tendency
# per quantity at a place, the tendency recipes per process, the hooks once
# each, the leaves the hooks write.
@dataclasses.dataclass(frozen=True)
class Updates:
    tendencies: State
    tendency_recipes: dict[Process, tuple[Recipe, ...]]
    hooks: tuple[Component, ...]
    hook_written: frozenset[tuple[type[Quantity], type[Dims]]]

    def begin(self) -> None:
        for _, value in self.tendencies.leaves():
            np.asarray(value.data.ndarray)[...] = 0.0

    # output = input + dt * summed tendency, leaf by leaf (in place where the
    # composer aliased; in a provider's buffer for a quantity the composite
    # does not output), the other output leaves carried; then the hooks, once
    def update(
        self,
        input: State,
        output: State,
        dt: float,
        *produced: State,
        guard: Callable[[Component, State, State], None] | None = None,
    ) -> None:
        inputs = _available((input, *produced))
        outputs = _available((output, *produced))
        updated = {_parent_key(d) for d in self.tendencies.declarations()}
        for d, value in output.leaves():
            if d.key not in updated and d.key not in self.hook_written and value is not inputs[d.key]:
                np.asarray(value.data.ndarray)[...] = np.asarray(inputs[d.key].data.ndarray)
        for d, value in self.tendencies.leaves():
            parent = _parent_key(d)
            np.asarray(outputs[parent].data.ndarray)[...] = np.asarray(inputs[parent].data.ndarray) + dt * np.asarray(
                value.data.ndarray
            )
        for hook in self.hooks:
            hook_input, hook_out = collect(hook.Input, output, *produced), collect(hook.Output, output, *produced)
            if guard is not None:
                guard(hook, hook_input, hook_out)
            hook.run(hook_input, out=hook_out)


# Reads the processes' Update blocks once, at composite init: every tendency a
# process emits must land somewhere (UnappliedTendency); a from_tendency
# recipe must produce the tendency and read only the process's outputs, the
# composite's input or a provider's output; a hook must write the leaf it
# hangs on, one hook per leaf; a quantity a tendency lands on must come in as
# a composite input or a provider output, and when it is not a composite
# output some hook must read it, or the update is lost (UnappliedIncrement);
# every composite output is an input, updated or hook-written.
def updates(
    processes: Iterable[Process],
    sizes: Mapping[gtx.Dimension, int],
    *,
    input: type[State],
    output: type[State],
    provided: Iterable[Recipe] = (),
) -> Updates:
    input_keys = {d.key for d in input.declarations()}
    output_keys = {d.key for d in output.declarations()}
    provided_keys = {d.key for r in provided for d in r.Output.declarations()}
    known = output_keys | provided_keys
    leaves: dict[str, Any] = {}
    updated: set[tuple[type[Quantity], type[Dims]]] = set()
    written: set[tuple[type[Quantity], type[Dims]]] = set()
    tendency_recipes: dict[Process, tuple[Recipe, ...]] = {}
    hooks: dict[tuple[type[Quantity], type[Dims]], type[Component]] = {}
    hook_order: list[type[Component]] = []
    field: Any = Field
    for process in processes:
        label = type(process).__name__
        outputs = {d.key for d in process.Output.declarations()}
        consumed: set[tuple[type[Quantity], type[Dims]]] = set()
        computed: list[Recipe] = []
        for d in process.Update.declarations():
            if isinstance(d.source, AfterIncrements):
                hook = d.source.hook
                if d.key not in {h.key for h in hook.Output.declarations()}:
                    raise InconsistentUpdate(f"{label}.{d.name}: {hook.__name__} does not write {d.label}")
                if d.key not in known:
                    raise InconsistentUpdate(f"{label}.{d.name}: {d.label} is not an output of the composite")
                if hooks.setdefault(d.key, hook) is not hook:
                    raise InconsistentUpdate(f"{d.label}: {hooks[d.key].__name__} vs {hook.__name__}")
                if hook not in hook_order:
                    for i in hook.Input.declarations():
                        if i.key not in known:
                            raise MissingInput(f"{hook.__name__}.{i.name}: {i.label}")
                    hook_order.append(hook)
                written.add(d.key)
                continue
            if not isinstance(d.source, FromTendency):
                raise InconsistentUpdate(f"{label}.{d.name}")
            tendency = (tendency_of(d.quantity), d.dims)
            if d.source.recipe is None:
                if tendency not in outputs:
                    raise InconsistentUpdate(f"{label}.{d.name}: no tendency of {d.quantity.__name__} in Output")
            else:
                recipe = d.source.recipe
                if tendency not in {o.key for o in recipe.Output.declarations()}:
                    raise InconsistentUpdate(
                        f"{label}.{d.name}: {recipe.__name__} does not produce a tendency of {d.quantity.__name__}"
                    )
                for i in recipe.Input.declarations():
                    if i.key not in outputs and i.key not in input_keys and i.key not in known:
                        raise MissingInput(f"{recipe.__name__}.{i.name}: {i.label}")
                computed.append(recipe(sizes))
            consumed.add(tendency)
            consumed |= {i.key for r in computed for i in r.Input.declarations()}
            if d.key not in input_keys and d.key not in provided_keys:
                raise UnappliedIncrement(f"{label}.{d.name}: {d.label} is neither an input nor provided")
            leaves[f"{d.quantity.__name__}__{d.dims.__name__}"] = field[tendency_of(d.quantity), d.dims]
            updated.add(d.key)
        for d in process.Output.declarations():
            if issubclass(d.quantity, TendencyOf) and d.key not in consumed:
                raise UnappliedTendency(f"{label}.{d.name}")
        tendency_recipes[process] = tuple(computed)
    hook_reads = {i.key for hook in hook_order for i in hook.Input.declarations()}
    for key in updated:
        if key not in output_keys and key not in hook_reads:
            raise UnappliedIncrement(f"{key[0].__name__}: updated in a provider's buffer that no hook reads")
    for d in output.declarations():
        if d.key not in input_keys and d.key not in updated and d.key not in written:
            raise InconsistentUpdate(f"{output.__qualname__}.{d.name}: neither an input, updated nor written")
    return Updates(
        tendencies=allocate(state_type("Tendencies", leaves), sizes),
        tendency_recipes=tendency_recipes,
        hooks=tuple(hook(sizes) for hook in hook_order),
        hook_written=frozenset(written),
    )


# ------------------------------------------------------------------------------
# Composition and Plan: the composer's one verb
# ------------------------------------------------------------------------------
# The wiring of a composite, made once at its init by composition(): the
# providers (resolve) with what each child and hook needs of them,
# transitively, and the updates (updates). A pass over the children begins a
# Plan.
@dataclasses.dataclass(frozen=True)
class Composition:
    providers: tuple[Recipe, ...]
    needs: dict[Component, tuple[Recipe, ...]]
    updates: Updates

    def begin(self) -> "Plan":
        self.updates.begin()
        return Plan(self)


# refuses an Output leaf sharing the buffer of the same-quantity Input leaf
# unless the component declares it in_place
def _check_alias(component: Component, input: State, out: State) -> None:
    given = {d.key: value for d, value in input.leaves()}
    for d, value in out.leaves():
        if value is given.get(d.key) and d.name not in component.in_place:
            raise AliasedOutput(f"{type(component).__name__}.{d.name}: {d.label}")


# One pass over a composite's children with fixed inputs. A provider runs at
# most once per plan, at the first child that needs it, and not at all when
# the composer supplied its output or no child that needs it runs: a new plan
# per substep, step or physics call is what makes "once" mean once. A child
# that writes into a supplied state through `out=` drops the providers that
# read it from the plan's cache.
class Plan:
    def __init__(self, composition: Composition) -> None:
        self.composition = composition
        self.produced: dict[Recipe, State] = {}

    # the outputs of the providers this component needs, run if not yet in
    # this plan; a provider whose output the supplied states carry is skipped
    def _provide(self, component: Component, supplied: tuple[State, ...]) -> tuple[State, ...]:
        available = _available(supplied)
        states: list[State] = []
        for provider in self.composition.needs[component]:
            if all(d.key in available for d in provider.Output.declarations()):
                continue
            if provider not in self.produced:
                upstream = self._provide(provider, supplied)
                self.produced[provider] = provider.run(collect(provider.Input, *supplied, *upstream))
            states.append(self.produced[provider])
        return tuple(states)

    # provide, collect the child's views from the supplied and provided
    # states, refuse an undeclared alias, run; plain leaves by keyword
    def run(self, child: Component, inputs: tuple[State, ...], outputs: tuple[State, ...] = (), **plain: Any) -> State:
        provided = self._provide(child, inputs)
        input = collect(child.Input, *inputs, *provided, **plain)
        out = collect(child.Output, *outputs) if outputs else None
        if out is not None:
            _check_alias(child, input, out)
        result: State = child.run(input, out)
        if out is not None:
            written = {d.key for d in child.Output.declarations()}
            self.produced = {
                p: s for p, s in self.produced.items() if not written & {d.key for d in p.Input.declarations()}
            }
        return result

    # the process's tendency recipes on its output (their providers first),
    # then its accumulate
    def accumulate(self, process: Process, output: State, *supplied: State) -> None:
        computed = tuple(
            recipe.run(collect(recipe.Input, output, *supplied, *self._provide(recipe, supplied)))
            for recipe in self.composition.updates.tendency_recipes[process]
        )
        process.accumulate(self.composition.updates.tendencies, output, *computed)

    # the hooks' providers first, then output = input + dt * sums, then the
    # hooks, through the alias check
    def update(self, input: State, output: State, dt: float) -> None:
        for hook in self.composition.updates.hooks:
            self._provide(hook, (input,))
        self.composition.updates.update(input, output, dt, *self.produced.values(), guard=_check_alias)


# once, at composite init, for all its children: resolve, updates, and what
# each child and hook needs of the providers (the providers whose output keys
# its Input names, and theirs, dependencies first)
def composition(
    children: Iterable[Component],
    sizes: Mapping[gtx.Dimension, int],
    *,
    input: type[State],
    output: type[State],
) -> Composition:
    children = tuple(children)
    resolution = resolve(children, sizes)
    processes = [c for c in children if isinstance(c, Process)]
    updates_ = updates(processes, sizes, input=input, output=output, provided=resolution.providers)
    by_key = {d.key: provider for provider in resolution.providers for d in provider.Output.declarations()}

    def needs_of(cls: type[State]) -> tuple[Recipe, ...]:
        found: list[Recipe] = []
        for d in cls.declarations():
            provider = by_key.get(d.key)
            if provider is not None and provider not in found:
                found.extend(n for n in needs_of(provider.Input) if n not in found)
                found.append(provider)
        return tuple(found)

    recipes = [r for rs in updates_.tendency_recipes.values() for r in rs]
    return Composition(
        providers=resolution.providers,
        needs={c: needs_of(c.Input) for c in (*children, *updates_.hooks, *resolution.providers, *recipes)},
        updates=updates_,
    )


# ------------------------------------------------------------------------------
# Reports
# ------------------------------------------------------------------------------
# what each component reads and produces, from its declarations alone, with
# `<- Recipe` on a derived leaf, and what a process updates (`+=` by its own
# tendency, `+= Recipe` by a derived one, `<- Hook` a rewritten leaf); an
# instance for a component whose Input is built per instance
def dataflow(*components: type[Component] | Component) -> str:
    def text(d: Decl) -> str:
        if isinstance(d.source, Derived):
            return f"{d.label} <- {d.source.recipe.__name__}"
        if isinstance(d.source, AfterIncrements):
            return f"{d.label} <- {d.source.hook.__name__}"
        if isinstance(d.source, FromTendency):
            return f"{d.label} +=" + (f" {d.source.recipe.__name__}" if d.source.recipe else "")
        return d.label

    def names(decls: tuple[Decl, ...]) -> str:
        return ", ".join(text(d) for d in decls) or "-"

    def name(c: type[Component] | Component) -> str:
        return c.__name__ if isinstance(c, type) else type(c).__name__

    def line(c: type[Component] | Component) -> str:
        cls = c if isinstance(c, type) else type(c)
        updates = f" | updates: {names(cls.Update.declarations())}" if issubclass(cls, Process) else ""
        return f"{name(c)} | reads: {names(c.Input.declarations())} | produces: {names(c.Output.declarations())}{updates}"

    return "\n".join(line(c) for c in components)
