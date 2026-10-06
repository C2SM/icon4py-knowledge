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
# `ThetaV.CellKHalf`. A keyword not given is inherited from the base.
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
        if cls.__name__ in REGISTRY:
            raise DuplicateQuantity(cls.__name__)
        if cls.standard_name and any(q.standard_name == cls.standard_name for q in REGISTRY.values()):
            raise DuplicateQuantity(f"{cls.__name__}: standard_name {cls.standard_name} is taken")
        REGISTRY[cls.__name__] = cls

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


# a quantity that lives somewhere (a generic like TendencyOf is not one)
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
# where a leaf's value comes from when the composer does not put it in the
# pool: a recipe. Decl carries it; the Component section defines the kinds
class Source:
    pass


class UnresolvedInput(ValueError):
    pass


# one Field leaf read back from a State class: its name, quantity, place and
# source
# qty.ThetaV.CellK lives in annotations. mypy/pyright read it, Python at
# runtime does not, unless someone inspects hints. Decl is that inspection,
# done once, so every generic operation over "a state" asks the class instead
# of hard-coding leaf names.
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

    # declarations() is class-level. Needs no values. So `resolve` (and the
    # plan and dataflow report of later layers) can reason about a component
    # before anything is allocated.
    @classmethod
    def declarations(cls) -> tuple[Decl, ...]:
        return _declarations(cls)

    # leaves() is instance-level. Decl plus the actual Field. For things that
    # move data.
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
# style. Either way `run` returns the output. Whether the view may alias the
# input is the component's business (diffusion and the physics update tolerate
# it, the dycore needs distinct now/next); nothing checks it in this layer.
class Component:
    Input: type[State]
    Output: type[State]

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
# rather than writing a stencil call and a buffer of its own. No Output leaf
# of a recipe is among its Input leaves, quantity and place (a relocation
# reads a quantity at one place and writes it at another); a component that
# writes back what it reads is an update, not a recipe. The empty subclass is
# the name `derived_by` and `resolve` read; the composer decides when to run it.
class Recipe(Component):
    pass


class InconsistentDerivation(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class Derived(Source):
    recipe: type[Recipe]


# leaf default: `temperature: Temperature.CellK = derived_by(TemperatureFromThetaExner)`
# says which recipe provides the leaf
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
    def update(self, input: State, output: State, dt: float, *produced: State) -> None:
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
            hook.run(collect(hook.Input, output, *produced), out=collect(hook.Output, output, *produced))


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
