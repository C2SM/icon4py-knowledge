from __future__ import annotations

import dataclasses
import enum
import types
import typing
from collections.abc import Callable, Iterable, Iterator
from typing import Annotated, Any, ClassVar, dataclass_transform

import gt4py.next as gtx
import numpy as np


@dataclasses.dataclass(frozen=True)
class Quantity:
    name: str
    units: str
    cf_key: str | None = None
    parent: Quantity | None = None


REGISTRY: dict[str, Quantity] = {}


def quantity(name: str, *, units: str, cf_key: str | None = None) -> Quantity:
    return REGISTRY.setdefault(name, Quantity(name, units, cf_key))


def tendency_of(q: Quantity) -> Quantity:
    name = f"tendency_of_{q.name}"
    return REGISTRY.setdefault(name, Quantity(name, f"{q.units} s-1", parent=q))


def increment_of(q: Quantity) -> Quantity:
    name = f"increment_of_{q.name}"
    return REGISTRY.setdefault(name, Quantity(name, q.units, parent=q))


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


# one declaration read back from a leaf: name, quantity, tag, field type, marker
@dataclasses.dataclass(frozen=True)
class Decl:
    name: str
    quantity: Quantity
    tag: Tag | None
    field_type: Any
    marker: Derived | FromTendency | AfterIncrements | None

    @property
    def recipe(self) -> type[Recipe] | None:
        return self.marker.recipe if isinstance(self.marker, Derived) else None


# walks TypeAliasType, generic aliases of aliases and nested Annotated.
def unwrap(hint: Any) -> tuple[Any, tuple[Any, ...]]:
    meta: list[Any] = []
    while True:
        if isinstance(hint, typing.TypeAliasType):
            hint = hint.__value__
        elif isinstance(hint, types.GenericAlias) and isinstance(hint.__origin__, typing.TypeAliasType):
            hint = hint.__origin__.__value__[hint.__args__]
        elif typing.get_origin(hint) is Annotated:
            meta = list(hint.__metadata__) + meta
            hint = hint.__origin__
        else:
            return hint, tuple(meta)


# turns the quantity into its tendency or increment when tagged
def _decl(name: str, hint: Any, default: Any) -> Decl:
    base, meta = unwrap(hint)
    q = next(m for m in meta if isinstance(m, Quantity))
    tag = next((m for m in meta if isinstance(m, Tag)), None)
    if tag is Tag.TENDENCY:
        q = tendency_of(q)
    if tag is Tag.INCREMENT:
        q = increment_of(q)
    marker = default if isinstance(default, _MARKERS) else None
    return Decl(name, q, tag, base, marker)


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


DERIVATIONS: dict[Quantity, type[Recipe]] = {}


# flattens states to {quantity: value}, AmbiguousSource on two objects for one quantity
def _available(states: Iterable[State]) -> dict[Quantity, Any]:
    available: dict[Quantity, Any] = {}
    for state in states:
        for d, value in state.leaves():
            if available.setdefault(d.quantity, value) is not value:
                raise AmbiguousSource(d.quantity.name)
    return available


# pointer selection only, never computes: one leaf per declaration of cls,
# taken from the given states by quantity
def collect[S: State](cls: type[S], *states: State) -> S:
    available = _available(states)
    values = {}
    for d in cls.declarations():
        if d.quantity not in available:
            raise MissingInput(f"{cls.__qualname__}.{d.name}: {d.quantity.name}")
        values[d.name] = available[d.quantity]
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
        inputs = {d.quantity: value for d, value in input.leaves()}
        for d, value in output.leaves():
            if value is inputs.get(d.quantity) and d.name not in self.in_place:
                raise AliasedOutput(f"{type(self).__name__}.{d.name}")
        self.run(input, output)

    def collect_inputs(self, *states: State) -> Any:
        return collect(self.Input, *states)

    def collect_output(self, *states: State) -> Any:
        return collect(self.Output, *states)


class Recipe(Component):
    pass


class Process(Component):
    Update: type[State] = Empty

    # walk the process's Update increment leaves: from_tendency adds dt times
    # the matching Tendency leaf of output, derived_by adds the recipe output
    # that run_increment_recipes computed
    def accumulate(self, into: State, dt: float, output: State, *computed: State) -> None:
        targets = {d.quantity: value for d, value in into.leaves()}
        tendencies = {d.quantity: value for d, value in output.leaves()}
        available = _available(computed)
        for d in self.Update.declarations():
            if d.tag is not Tag.INCREMENT or d.quantity.parent is None:
                continue
            if isinstance(d.marker, FromTendency):
                tendency = tendencies[tendency_of(d.quantity.parent)]
                np.asarray(targets[d.quantity].ndarray)[...] += dt * np.asarray(tendency.ndarray)
            elif isinstance(d.marker, Derived):
                np.asarray(targets[d.quantity].ndarray)[...] += np.asarray(available[d.quantity].ndarray)


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
            if all(d.quantity in available for d in provider.Output.declarations()):
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
        incremented = {d.quantity.parent for d in self.increments.declarations()}
        for d, value in output.leaves():
            if d.quantity not in incremented and value is not inputs[d.quantity]:
                np.asarray(value.ndarray)[...] = np.asarray(inputs[d.quantity].ndarray)
        for d, value in self.increments.leaves():
            parent = d.quantity.parent
            if parent not in outputs:
                raise UnappliedIncrement(d.quantity.name)
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
    input_quantities = {d.quantity for d in input.declarations()}
    output_quantities = {d.quantity for d in output.declarations()}
    order: list[type[Recipe]] = []

    def visit(cls: type[State]) -> None:
        for d in cls.declarations():
            if d.recipe is None:
                continue
            known_recipe = DERIVATIONS.setdefault(d.quantity, d.recipe)
            if known_recipe is not d.recipe:
                raise InconsistentDerivation(f"{d.quantity.name}: {known_recipe.__name__} vs {d.recipe.__name__}")
            if d.recipe not in order:
                visit(d.recipe.Input)
                order.append(d.recipe)

    for child in children:
        visit(child.Input)
    known = output_quantities | {d.quantity for recipe in order for d in recipe.Output.declarations()}

    increments: dict[str, tuple[Any, None]] = {}
    incremented: set[Quantity] = set()
    increment_recipes: dict[Process, tuple[tuple[Recipe, State], ...]] = {}
    hooks: dict[Quantity, type[Component]] = {}
    hook_order: list[type[Component]] = []
    for child in children:
        label = type(child).__name__
        outputs = {d.quantity for d in child.Output.declarations()}
        consumed: set[Quantity] = set()
        computed: list[tuple[Recipe, State]] = []
        for d in child.Update.declarations() if isinstance(child, Process) else ():
            parent = d.quantity.parent
            if isinstance(d.marker, AfterIncrements):
                hook = d.marker.recipe
                if d.quantity not in {h.quantity for h in hook.Output.declarations()}:
                    raise InconsistentUpdate(f"{label}.{d.name}: {hook.__name__} does not write {d.quantity.name}")
                if d.quantity not in known:
                    raise InconsistentUpdate(f"{label}.{d.name}: {d.quantity.name} is not an output of the composite")
                if hooks.setdefault(d.quantity, hook) is not hook:
                    raise InconsistentUpdate(d.quantity.name)
                if hook not in hook_order:
                    for i in hook.Input.declarations():
                        if i.quantity not in known:
                            raise MissingInput(f"{hook.__name__}.{i.name}: {i.quantity.name}")
                    hook_order.append(hook)
                continue
            if d.tag is not Tag.INCREMENT or parent is None:
                raise InconsistentUpdate(f"{label}.{d.name}")
            if isinstance(d.marker, FromTendency):
                if tendency_of(parent) not in outputs:
                    raise InconsistentUpdate(f"{label}.{d.name}: no tendency of {parent.name} in Output")
                consumed.add(tendency_of(parent))
            elif isinstance(d.marker, Derived):
                recipe = d.marker.recipe
                if d.quantity not in {o.quantity for o in recipe.Output.declarations()}:
                    raise InconsistentUpdate(f"{label}.{d.name}: {recipe.__name__} does not produce {d.quantity.name}")
                for i in recipe.Input.declarations():
                    if i.quantity not in outputs and i.quantity not in input_quantities:
                        raise MissingInput(f"{recipe.__name__}.{i.name}: {i.quantity.name}")
                    if i.tag is Tag.TENDENCY:
                        consumed.add(i.quantity)
                computed.append((recipe(), allocate(recipe.Output, sizes)))
            else:
                raise InconsistentUpdate(f"{label}.{d.name}")
            if parent not in known:
                raise UnappliedIncrement(d.quantity.name)
            increments[parent.name] = (Annotated[d.field_type, parent, Tag.INCREMENT], None)
            incremented.add(parent)
        for d in child.Output.declarations():
            if d.tag is Tag.TENDENCY and d.quantity not in consumed:
                raise UnappliedTendency(f"{label}.{d.name}")
        if isinstance(child, Process):
            increment_recipes[child] = tuple(computed)
    for d in output.declarations():
        if d.quantity not in input_quantities and d.quantity not in incremented:
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
        out = d.quantity.name
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
