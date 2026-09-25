from __future__ import annotations

import dataclasses
import enum
import types
import typing
from collections.abc import Callable, Iterable, Iterator
from typing import Annotated, Any, ClassVar, dataclass_transform

import gt4py.next as gtx
import numpy as np
from icon4py.model.common import field_type_aliases as fa, type_alias as ta


class DuplicateQuantity(ValueError):
    pass


# a type-level tag, never instantiated: subclasses carry the CF metadata as
# class attributes and name the locations (framework aliases below) the
# quantity may live at; None means unrestricted. The same classes are meant to
# become the phantom type argument of the field once gt4py can carry one.
class Quantity:
    name: ClassVar[str]
    units: ClassVar[str]
    cf_key: ClassVar[str | None]
    parent: ClassVar[type[Quantity] | None]
    locations: ClassVar[tuple[Any, ...] | None]

    def __init_subclass__(
        cls,
        *,
        name: str,
        units: str,
        cf_key: str | None = None,
        parent: type[Quantity] | None = None,
        locations: tuple[Any, ...] | None = None,
    ) -> None:
        super().__init_subclass__()
        cls.name, cls.units, cls.cf_key, cls.parent, cls.locations = name, units, cf_key, parent, locations
        if REGISTRY.setdefault(name, cls) is not cls:
            raise DuplicateQuantity(name)

    def __new__(cls, *args: Any, **kwargs: Any) -> Any:
        raise TypeError(f"{cls.__name__} is a type-level tag, not a value")


REGISTRY: dict[str, type[Quantity]] = {}


def _derived(prefix: str, q: type[Quantity], units: str) -> type[Quantity]:
    name = f"{prefix}_{q.name}"
    if name not in REGISTRY:
        types.new_class(name, (Quantity,), {"name": name, "units": units, "parent": q, "locations": q.locations})
    return REGISTRY[name]


def tendency_of(q: type[Quantity]) -> type[Quantity]:
    return _derived("tendency_of", q, f"{q.units} s-1")


def increment_of(q: type[Quantity]) -> type[Quantity]:
    return _derived("increment_of", q, q.units)


# locations: generic aliases that put a quantity tag on a field type; the alias
# object is the location in every key
type Cell[Q] = Annotated[fa.CellField[ta.wpfloat], Q]
type CellK[Q] = Annotated[fa.CellKField[ta.wpfloat], Q]
type CellKHalf[Q] = Annotated[fa.CellKHalfField[ta.wpfloat], Q]
type Edge[Q] = Annotated[fa.EdgeField[ta.wpfloat], Q]
type EdgeK[Q] = Annotated[fa.EdgeKField[ta.wpfloat], Q]
type EdgeKHalf[Q] = Annotated[fa.EdgeKHalfField[ta.wpfloat], Q]
type Scalar[T, Q] = Annotated[T, Q]


class Tag(enum.Enum):
    TENDENCY = "tendency"
    INCREMENT = "increment"


type Tendency[F] = Annotated[F, Tag.TENDENCY]
type Increment[F] = Annotated[F, Tag.INCREMENT]


@dataclasses.dataclass(frozen=True)
class Derived:
    recipe: type[Recipe]


@dataclasses.dataclass(frozen=True)
class FromTendency:
    pass


@dataclasses.dataclass(frozen=True)
class AfterIncrements:
    recipe: type[Component]


_MARKERS = (Derived, FromTendency, AfterIncrements)


def derived_by(recipe: type[Recipe]) -> Any:
    return Derived(recipe)


def from_tendency() -> Any:
    return FromTendency()


def after_increments(hook: type[Component]) -> Any:
    return AfterIncrements(hook)


def location_name(location: Any) -> str:
    return str(getattr(location, "__name__", location))


# one declaration read back from a leaf: name, quantity, tag, location, field
# type, marker; (quantity, location) is the key everything resolves on
@dataclasses.dataclass(frozen=True)
class Decl:
    name: str
    quantity: type[Quantity]
    tag: Tag | None
    location: Any
    field_type: Any
    marker: Derived | FromTendency | AfterIncrements | None

    @property
    def key(self) -> tuple[type[Quantity], Any]:
        return (self.quantity, self.location)

    @property
    def recipe(self) -> type[Recipe] | None:
        return self.marker.recipe if isinstance(self.marker, Derived) else None

    @property
    def label(self) -> str:
        located = self.quantity.locations is not None and len(self.quantity.locations) > 1
        return self.quantity.name + (f"@{location_name(self.location)}" if located else "")


# walks TypeAliasType, generic aliases of aliases and nested Annotated; a
# location alias (a type parameter inside the Annotated metadata) is
# substituted by hand, since Annotated cannot be, and remembered as the location
def unwrap(hint: Any) -> tuple[Any, tuple[Any, ...], Any]:
    meta: list[Any] = []
    location: Any = None
    while True:
        if isinstance(hint, typing.TypeAliasType):
            hint = hint.__value__
        elif isinstance(hint, types.GenericAlias) and isinstance(hint.__origin__, typing.TypeAliasType):
            alias, args = hint.__origin__, hint.__args__
            value: Any = alias.__value__
            if typing.get_origin(value) is Annotated and any(isinstance(m, typing.TypeVar) for m in value.__metadata__):
                bound = dict(zip(alias.__type_params__, args, strict=True))
                meta = [bound.get(m, m) for m in value.__metadata__] + meta
                location = alias
                hint = bound.get(value.__origin__, value.__origin__)
            else:
                hint = value[args]
        elif typing.get_origin(hint) is Annotated:
            meta = list(hint.__metadata__) + meta
            hint = hint.__origin__
        else:
            return hint, tuple(meta), location


class InvalidLocation(ValueError):
    pass


# turns the quantity into its tendency or increment when tagged; refuses a
# location the quantity does not declare
def _decl(name: str, hint: Any, default: Any) -> Decl:
    base, meta, location = unwrap(hint)
    q = next(m for m in meta if isinstance(m, type) and issubclass(m, Quantity))
    tag = next((m for m in meta if isinstance(m, Tag)), None)
    if tag is Tag.TENDENCY:
        q = tendency_of(q)
    if tag is Tag.INCREMENT:
        q = increment_of(q)
    if q.locations is not None and location not in q.locations:
        raise InvalidLocation(f"{name}: {q.name} at {location_name(location)}")
    marker = default if isinstance(default, _MARKERS) else None
    return Decl(name, q, tag, location, base, marker)


_DECLARATIONS: dict[type, tuple[Decl, ...]] = {}


# cached per class
def declarations(cls: type) -> tuple[Decl, ...]:
    if cls not in _DECLARATIONS:
        hints = typing.get_type_hints(cls, include_extras=True)
        fields: dict[str, Any] = getattr(cls, "__dataclass_fields__", {})
        _DECLARATIONS[cls] = tuple(
            _decl(name, hint, fields[name].default if name in fields else None) for name, hint in hints.items()
        )
    return _DECLARATIONS[cls]


class UnresolvedInput(ValueError):
    pass


@dataclass_transform(frozen_default=True, kw_only_default=True)
class State:
    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        dataclasses.dataclass(frozen=True, eq=False, kw_only=True)(cls)

    def __post_init__(self) -> None:
        # raises UnresolvedInput if a marker is still in a leaf, so a
        # hand-built State cannot smuggle a derived_by through
        for d, value in self.leaves():
            if isinstance(value, _MARKERS):
                raise UnresolvedInput(f"{type(self).__name__}.{d.name}")

    @classmethod
    def declarations(cls) -> tuple[Decl, ...]:
        return declarations(cls)

    def leaves(self) -> Iterator[tuple[Decl, Any]]:
        for d in self.declarations():
            yield d, getattr(self, d.name)


class Empty(State):
    pass


# builds a State class at runtime; IO uses it
def state_type(name: str, leaves: dict[str, tuple[Any, Any]]) -> type[State]:
    def body(namespace: dict[str, Any]) -> None:
        namespace["__annotations__"] = {leaf: hint for leaf, (hint, _) in leaves.items()}
        namespace.update({leaf: default for leaf, (_, default) in leaves.items() if default is not None})

    return typing.cast(type[State], types.new_class(name, (State,), exec_body=body))


# Naming, open (2026-09-25): TimeStepPair.now / .next follow ICON's "time level"
# (nnow / nnew), but in icon4py "level" reads as vertical level. jcanton: "step"
# covers exactly the meaning, now/next and current/new are all words for time
# steps n and n+1, and predictor/corrector are the two steps of one time step, so
# "step" does not collide with "time step". Not changed yet; to settle with the group.
# The pair is driver-owned: the composer passes `.now` as a component's input
# and `.next` as its output, so no component ever sees a pair.
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


def allocate[S: State](
    cls: type[S], sizes: dict[gtx.Dimension, int], fill: Callable[[str, tuple[int, ...]], Any] | None = None
) -> S:
    values = {}
    for d in cls.declarations():
        dims, dtype = typing.get_args(d.field_type)
        f = gtx.zeros({dim: sizes[dim] for dim in typing.get_args(dims)}, dtype=dtype)
        if fill is not None:
            np.asarray(f.ndarray)[...] = fill(d.name, f.ndarray.shape)
        values[d.name] = f
    return cls(**values)


def zero(state: State) -> None:
    for _, value in state.leaves():
        np.asarray(value.ndarray)[...] = 0.0


class MissingInput(KeyError):
    pass


class AmbiguousSource(ValueError):
    pass


class AliasedOutput(ValueError):
    pass


class UnappliedIncrement(KeyError):
    pass


class UnappliedTendency(ValueError):
    pass


class InconsistentDerivation(ValueError):
    pass


class InconsistentUpdate(ValueError):
    pass


class InconsistentRelocation(ValueError):
    pass


type Key = tuple[type[Quantity], Any]

DERIVATIONS: dict[Key, type[Recipe]] = {}
RELOCATIONS: dict[tuple[type[Quantity], Any, Any], type[Recipe]] = {}


# registers a recipe that moves one quantity from one of its locations to
# another, one recipe per (quantity, from, to); the table is what a
# family-level lookup would read (see quantities.py)
def relocation[R: type[Recipe]](recipe: R) -> R:
    outputs = recipe.Output.declarations()
    if len(outputs) != 1:
        raise InconsistentRelocation(f"{recipe.__name__}: one output leaf expected")
    (out,) = outputs
    sources = [d for d in recipe.Input.declarations() if d.quantity is out.quantity and d.location is not out.location]
    if len(sources) != 1:
        raise InconsistentRelocation(f"{recipe.__name__}: {out.quantity.name} at another location expected in Input")
    key = (out.quantity, sources[0].location, out.location)
    if RELOCATIONS.setdefault(key, recipe) is not recipe:
        raise InconsistentRelocation(f"{out.quantity.name}: {RELOCATIONS[key].__name__} vs {recipe.__name__}")
    return recipe


# flattens states to {(quantity, location): value}, AmbiguousSource on two objects for one key
def _available(states: Iterable[State]) -> dict[Key, Any]:
    available: dict[Key, Any] = {}
    for state in states:
        for d, value in state.leaves():
            if available.setdefault(d.key, value) is not value:
                raise AmbiguousSource(d.label)
    return available


# pointer selection only, never computes: one leaf per declaration of cls,
# taken from the given states by (quantity, location)
def collect[S: State](cls: type[S], *states: State) -> S:
    available = _available(states)
    values = {}
    for d in cls.declarations():
        if d.key not in available:
            raise MissingInput(f"{cls.__qualname__}.{d.name}: {d.label}")
        values[d.name] = available[d.key]
    return cls(**values)


class Component:
    Input: type[State]
    Output: type[State]
    in_place: ClassVar[frozenset[str]] = frozenset()

    def run(self, input: Any, output: Any) -> None:
        raise NotImplementedError

    # the composer's entry: refuses an output buffer that is also the input
    # buffer of the same quantity unless the leaf is declared in_place, then runs
    def __call__(self, input: State, output: State) -> None:
        inputs = {d.key: value for d, value in input.leaves()}
        for d, value in output.leaves():
            if value is inputs.get(d.key) and d.name not in self.in_place:
                raise AliasedOutput(f"{type(self).__name__}.{d.name}")
        self.run(input, output)

    def collect_inputs(self, *states: State) -> Any:
        return collect(self.Input, *states)

    def collect_output(self, *states: State) -> Any:
        return collect(self.Output, *states)


class Recipe(Component):
    pass


def _parent_key(d: Decl) -> Key:
    assert d.quantity.parent is not None
    return (d.quantity.parent, d.location)


class Process(Component):
    Update: type[State] = Empty

    # walk the process's Update increment leaves: from_tendency adds dt times
    # the matching Tendency leaf of output, derived_by adds the recipe output
    # that run_increment_recipes computed
    def accumulate(self, into: State, dt: float, output: State, *computed: State) -> None:
        targets = {d.key: value for d, value in into.leaves()}
        tendencies = {d.key: value for d, value in output.leaves()}
        available = _available(computed)
        for d in self.Update.declarations():
            if d.tag is not Tag.INCREMENT or d.quantity.parent is None:
                continue
            if isinstance(d.marker, FromTendency):
                tendency = tendencies[(tendency_of(d.quantity.parent), d.location)]
                np.asarray(targets[d.key].ndarray)[...] += dt * np.asarray(tendency.ndarray)
            elif isinstance(d.marker, Derived):
                np.asarray(targets[d.key].ndarray)[...] += np.asarray(available[d.key].ndarray)


@dataclasses.dataclass(frozen=True)
class Resolution:
    providers: tuple[tuple[Recipe, State], ...]
    increments: State
    increment_recipes: dict[Process, tuple[tuple[Recipe, State], ...]]
    hooks: tuple[Component, ...]

    # skips a provider whose whole output is already supplied
    def run_providers(self, *supplied: State) -> tuple[State, ...]:
        available = _available(supplied)
        produced: list[State] = []
        for provider, output in self.providers:
            if all(d.key in available for d in provider.Output.declarations()):
                continue
            provider(provider.collect_inputs(*supplied, *produced), output)
            produced.append(output)
        return tuple(produced)

    def run_increment_recipes(self, process: Process, output: State, *supplied: State) -> tuple[State, ...]:
        computed: list[State] = []
        for recipe, recipe_output in self.increment_recipes[process]:
            recipe(recipe.collect_inputs(output, *supplied), recipe_output)
            computed.append(recipe_output)
        return tuple(computed)

    # output = input + increments, leaf by leaf: an output leaf without an
    # increment is copied from input unless it is the same buffer; each
    # Increments leaf is added onto its parent, found in output or in produced
    # (a provider's buffer); a parent found nowhere is UnappliedIncrement; then
    # the hooks, once, reading the updated state and writing into output
    def update(self, input: State, output: State, *produced: State) -> None:
        inputs = _available((input, *produced))
        outputs = _available((output, *produced))
        incremented = {_parent_key(d) for d in self.increments.declarations()}
        for d, value in output.leaves():
            if d.key not in incremented and value is not inputs[d.key]:
                np.asarray(value.ndarray)[...] = np.asarray(inputs[d.key].ndarray)
        for d, value in self.increments.leaves():
            parent = _parent_key(d)
            if parent not in outputs:
                raise UnappliedIncrement(d.label)
            np.add(np.asarray(inputs[parent].ndarray), np.asarray(value.ndarray), out=np.asarray(outputs[parent].ndarray))
        for hook in self.hooks:
            hook(hook.collect_inputs(output, *produced), hook.collect_output(output, *produced))


# First pass: visit each child's Input for derived_by, recurse into recipe
# Inputs, dedupe, order dependencies first. Second pass, per Process: hooks
# must write the leaf they hang on, and one hook per quantity; from_tendency
# needs the matching tendency in Output; derived_by increment leaves get one
# recipe instance per process, its inputs checked against the process Output
# and the composite Input; every increment parent and hook target must be a
# composite output or a provider output; every Tendency output must be consumed
# by some leaf; every composite output is an input or incremented. Returns the
# Resolution.
def resolve(
    children: Iterable[Component], sizes: dict[gtx.Dimension, int], *, input: type[State], output: type[State]
) -> Resolution:
    children = tuple(children)
    input_keys = {d.key for d in input.declarations()}
    output_keys = {d.key for d in output.declarations()}
    order: list[type[Recipe]] = []

    def visit(cls: type[State]) -> None:
        for d in cls.declarations():
            if d.recipe is None:
                continue
            known_recipe = DERIVATIONS.setdefault(d.key, d.recipe)
            if known_recipe is not d.recipe:
                raise InconsistentDerivation(f"{d.label}: {known_recipe.__name__} vs {d.recipe.__name__}")
            if d.recipe not in order:
                visit(d.recipe.Input)
                order.append(d.recipe)

    for child in children:
        visit(child.Input)
    known = output_keys | {d.key for recipe in order for d in recipe.Output.declarations()}

    increments: dict[str, tuple[Any, None]] = {}
    incremented: set[Key] = set()
    increment_recipes: dict[Process, tuple[tuple[Recipe, State], ...]] = {}
    hooks: dict[Key, type[Component]] = {}
    hook_order: list[type[Component]] = []
    for child in children:
        label = type(child).__name__
        outputs = {d.key for d in child.Output.declarations()}
        consumed: set[Key] = set()
        computed: list[tuple[Recipe, State]] = []
        for d in child.Update.declarations() if isinstance(child, Process) else ():
            parent = d.quantity.parent
            if isinstance(d.marker, AfterIncrements):
                hook = d.marker.recipe
                if d.key not in {h.key for h in hook.Output.declarations()}:
                    raise InconsistentUpdate(f"{label}.{d.name}: {hook.__name__} does not write {d.label}")
                if d.key not in known:
                    raise InconsistentUpdate(f"{label}.{d.name}: {d.label} is not an output of the composite")
                if hooks.setdefault(d.key, hook) is not hook:
                    raise InconsistentUpdate(d.label)
                if hook not in hook_order:
                    for i in hook.Input.declarations():
                        if i.key not in known:
                            raise MissingInput(f"{hook.__name__}.{i.name}: {i.label}")
                    hook_order.append(hook)
                continue
            if d.tag is not Tag.INCREMENT or parent is None:
                raise InconsistentUpdate(f"{label}.{d.name}")
            parent_key = (parent, d.location)
            if isinstance(d.marker, FromTendency):
                if (tendency_of(parent), d.location) not in outputs:
                    raise InconsistentUpdate(f"{label}.{d.name}: no tendency of {parent.name} in Output")
                consumed.add((tendency_of(parent), d.location))
            elif isinstance(d.marker, Derived):
                recipe = d.marker.recipe
                if d.key not in {o.key for o in recipe.Output.declarations()}:
                    raise InconsistentUpdate(f"{label}.{d.name}: {recipe.__name__} does not produce {d.label}")
                for i in recipe.Input.declarations():
                    if i.key not in outputs and i.key not in input_keys:
                        raise MissingInput(f"{recipe.__name__}.{i.name}: {i.label}")
                    if i.tag is Tag.TENDENCY:
                        consumed.add(i.key)
                computed.append((recipe(), allocate(recipe.Output, sizes)))
            else:
                raise InconsistentUpdate(f"{label}.{d.name}")
            if parent_key not in known:
                raise UnappliedIncrement(d.label)
            increment_alias: Any = Increment
            increments[f"{parent.name}__{location_name(d.location)}"] = (increment_alias[d.location[parent]], None)
            incremented.add(parent_key)
        for d in child.Output.declarations():
            if d.tag is Tag.TENDENCY and d.key not in consumed:
                raise UnappliedTendency(f"{label}.{d.name}")
        if isinstance(child, Process):
            increment_recipes[child] = tuple(computed)
    for d in output.declarations():
        if d.key not in input_keys and d.key not in incremented:
            raise InconsistentUpdate(f"{output.__qualname__}.{d.name}: neither an input nor incremented")

    return Resolution(
        providers=tuple((recipe(), allocate(recipe.Output, sizes)) for recipe in order),
        increments=allocate(state_type("Increments", increments), sizes),
        increment_recipes=increment_recipes,
        hooks=tuple(hook() for hook in hook_order),
    )


# Helper: one line per component, reads, produces (in place where declared),
# updates, with <- Recipe on derived leaves
def dataflow(*components: Component) -> str:
    def text(d: Decl) -> str:
        out = d.label
        if isinstance(d.marker, Derived):
            out += f" <- {d.marker.recipe.__name__}"
        elif isinstance(d.marker, FromTendency):
            out += " <- tendency"
        elif isinstance(d.marker, AfterIncrements):
            out += f" <- after increments {d.marker.recipe.__name__}"
        return out

    def names(decls: tuple[Decl, ...], in_place: frozenset[str] = frozenset()) -> str:
        return ", ".join(text(d) + (" (in place)" if d.name in in_place else "") for d in decls) or "-"

    return "\n".join(
        f"{type(c).__name__:<26} reads: {names(c.Input.declarations())}"
        f" | produces: {names(c.Output.declarations(), c.in_place)}"
        f" | updates: {names(c.Update.declarations()) if isinstance(c, Process) else '-'}"
        for c in components
    )
