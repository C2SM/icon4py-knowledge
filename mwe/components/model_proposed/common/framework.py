from __future__ import annotations

import dataclasses
import enum
import types
import typing
from collections.abc import Callable, Iterable, Iterator
from typing import Annotated, Any, dataclass_transform

import gt4py.next as gtx
import numpy as np


@dataclasses.dataclass(frozen=True)
class Quantity:
    name: str
    units: str
    cf_key: str | None = None
    of: Quantity | None = None


REGISTRY: dict[str, Quantity] = {}


def quantity(name: str, *, units: str, cf_key: str | None = None) -> Quantity:
    return REGISTRY.setdefault(name, Quantity(name, units, cf_key))


def tendency_of(q: Quantity) -> Quantity:
    name = f"tendency_of_{q.name}"
    return REGISTRY.setdefault(name, Quantity(name, f"{q.units} s-1", of=q))


def increment_of(q: Quantity) -> Quantity:
    name = f"increment_of_{q.name}"
    return REGISTRY.setdefault(name, Quantity(name, q.units, of=q))


class Intent(enum.Enum):
    READ = "read"
    READWRITE = "readwrite"


class Tag(enum.Enum):
    TENDENCY = "tendency"
    INCREMENT = "increment"


class Level(enum.Enum):
    NOW = "now"
    NEXT = "next"


type Read[F] = Annotated[F, Intent.READ]
type ReadWrite[F] = Annotated[F, Intent.READWRITE]
type Tendency[F] = Annotated[F, Tag.TENDENCY]
type Increment[F] = Annotated[F, Tag.INCREMENT]
type Now[F] = Annotated[F, Level.NOW]
type Next[F] = Annotated[F, Level.NEXT]


@dataclasses.dataclass(frozen=True)
class Derived:
    recipe: type[Recipe[Any, Any]]


@dataclasses.dataclass(frozen=True)
class FromTendency:
    pass


@dataclasses.dataclass(frozen=True)
class AfterApply:
    recipe: type[Component[Any, Any]]


_MARKERS = (Derived, FromTendency, AfterApply)


def derived_by(recipe: type[Recipe[Any, Any]]) -> Any:
    return Derived(recipe)


def from_tendency() -> Any:
    return FromTendency()


def after_apply(recipe: type[Component[Any, Any]]) -> Any:
    return AfterApply(recipe)


# one declaration read back from a leaf: name, quantity, intent, tag, level,
# field type, marker
@dataclasses.dataclass(frozen=True)
class Decl:
    name: str
    quantity: Quantity
    intent: Intent | None
    tag: Tag | None
    level: Level | None
    field_type: Any
    marker: Derived | FromTendency | AfterApply | None

    @property
    def recipe(self) -> type[Recipe[Any, Any]] | None:
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
    intent = next((m for m in meta if isinstance(m, Intent)), None)
    level = next((m for m in meta if isinstance(m, Level)), None)
    marker = default if isinstance(default, _MARKERS) else None
    return Decl(name, q, intent, tag, level, base, marker)


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


class UnappliedIncrement(KeyError):
    pass


class UnappliedTendency(ValueError):
    pass


class InconsistentDerivation(ValueError):
    pass


class InconsistentUpdate(ValueError):
    pass


# flattens to {(quantity, level): value}, tagging pair sides, AmbiguousSource on two objects for one key
def _available(states: Iterable[State | TimeStepPair[Any]]) -> dict[tuple[Quantity, Level | None], Any]:
    available: dict[tuple[Quantity, Level | None], Any] = {}
    for state in states:
        sides = (
            ((state.now, Level.NOW), (state.next, Level.NEXT)) if isinstance(state, TimeStepPair) else ((state, None),)
        )
        for side, level in sides:
            for d, value in side.leaves():
                if available.setdefault((d.quantity, level), value) is not value:
                    raise AmbiguousSource(d.quantity.name)
    return available


class Component[InputT: State, OutputT: State]:
    Input: type[InputT]
    Output: type[OutputT]

    def __init__(self, output: OutputT) -> None:
        self.output = output

    def run(self, input: InputT) -> OutputT:
        raise NotImplementedError

    def collect_inputs(self, *states: State | TimeStepPair[Any]) -> InputT:
        available = _available(states)
        values = {}
        for d in self.Input.declarations():
            if (d.quantity, d.level) not in available:
                raise MissingInput(f"{type(self).__name__}.{d.name}: {d.quantity.name}")
            values[d.name] = available[(d.quantity, d.level)]
        return self.Input(**values)


class Recipe[InputT: State, OutputT: State](Component[InputT, OutputT]):
    pass


class Process[InputT: State, OutputT: State](Component[InputT, OutputT]):
    Update: type[State] = Empty

    # walk the process's Update increment leaves: from_tendency adds dt times
    # the matching Tendency output, derived_by adds the recipe output that
    # run_updates computed
    def accumulate(self, into: State, dt: float, *computed: State) -> None:
        targets = {d.quantity: value for d, value in into.leaves()}
        tendencies = {d.quantity: value for d, value in self.output.leaves()}
        available = _available(computed)
        for d in self.Update.declarations():
            if d.tag is not Tag.INCREMENT or d.quantity.of is None:
                continue
            if isinstance(d.marker, FromTendency):
                tendency = tendencies[tendency_of(d.quantity.of)]
                np.asarray(targets[d.quantity].ndarray)[...] += dt * np.asarray(tendency.ndarray)
            elif isinstance(d.marker, Derived):
                np.asarray(targets[d.quantity].ndarray)[...] += np.asarray(available[(d.quantity, None)].ndarray)


@dataclasses.dataclass(frozen=True)
class Resolution:
    providers: tuple[Recipe[Any, Any], ...]
    increments: State
    updates: dict[Process[Any, Any], tuple[Recipe[Any, Any], ...]]
    after_apply: tuple[Component[Any, Any], ...]

    # skips a provider whose whole output is already supplied
    def run_providers(self, *supplied: State | TimeStepPair[Any]) -> tuple[State, ...]:
        available = _available(supplied)
        produced: list[State] = []
        for provider in self.providers:
            if all((d.quantity, None) in available for d in provider.Output.declarations()):
                continue
            provider.run(provider.collect_inputs(*supplied, *produced))
            produced.append(provider.output)
        return tuple(produced)

    def run_updates(self, process: Process[Any, Any], *supplied: State | TimeStepPair[Any]) -> tuple[State, ...]:
        computed: list[State] = []
        for recipe in self.updates[process]:
            recipe.run(recipe.collect_inputs(process.output, *supplied))
            computed.append(recipe.output)
        return tuple(computed)

    # add each Increments leaf into the leaf of its parent quantity among the
    # targets; a parent found nowhere is UnappliedIncrement
    def apply(self, *targets: State) -> None:
        leaves = {d.quantity: value for target in targets for d, value in target.leaves()}
        for d, value in self.increments.leaves():
            if d.quantity.of not in leaves:
                raise UnappliedIncrement(d.quantity.name)
            np.asarray(leaves[d.quantity.of].ndarray)[...] += np.asarray(value.ndarray)

    def run_after_apply(self, *supplied: State | TimeStepPair[Any]) -> None:
        for hook in self.after_apply:
            hook.run(hook.collect_inputs(*supplied))


# First pass: visit each child's Input for derived_by, recurse into recipe
# Inputs, dedupe, order dependencies first. Second pass, per Process: hooks
# must write the leaf they hang on, and one hook per quantity; from_tendency
# needs the matching tendency in Output; derived_by increment leaves get one
# recipe instance per process, its inputs checked against the process Output
# and the composite Input; every increment parent must be a target leaf or a
# provider output; every Tendency output must be consumed by some leaf. Returns
# the Resolution.
def resolve(
    children: Iterable[Component[Any, Any]], sizes: dict[gtx.Dimension, int], *, targets: type[State]
) -> Resolution:
    children = tuple(children)
    target_quantities = {d.quantity for d in targets.declarations()}
    recipes: dict[tuple[Quantity, Level | None], type[Recipe[Any, Any]]] = {}
    order: list[type[Recipe[Any, Any]]] = []

    def visit(cls: type[State]) -> None:
        for d in cls.declarations():
            if d.recipe is None:
                continue
            if recipes.setdefault((d.quantity, d.level), d.recipe) is not d.recipe:
                raise InconsistentDerivation(d.quantity.name)
            if d.recipe not in order:
                visit(d.recipe.Input)
                order.append(d.recipe)

    for child in children:
        visit(child.Input)
    known = target_quantities | {d.quantity for recipe in order for d in recipe.Output.declarations()}

    increments: dict[str, tuple[Any, None]] = {}
    updates: dict[Process[Any, Any], tuple[Recipe[Any, Any], ...]] = {}
    hooks: dict[Quantity, type[Component[Any, Any]]] = {}
    hook_order: list[type[Component[Any, Any]]] = []
    for child in children:
        label = type(child).__name__
        outputs = {d.quantity for d in child.Output.declarations()}
        consumed: set[Quantity] = set()
        computed: list[Recipe[Any, Any]] = []
        for d in child.Update.declarations() if isinstance(child, Process) else ():
            parent = d.quantity.of
            if isinstance(d.marker, AfterApply) and d.intent is Intent.READWRITE:
                hook = d.marker.recipe
                if not any(h.quantity == d.quantity and h.intent is Intent.READWRITE for h in hook.Input.declarations()):
                    raise InconsistentUpdate(f"{label}.{d.name}: {hook.__name__} does not write {d.quantity.name}")
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
                    if i.quantity not in outputs and i.quantity not in target_quantities:
                        raise MissingInput(f"{recipe.__name__}.{i.name}: {i.quantity.name}")
                    if i.tag is Tag.TENDENCY:
                        consumed.add(i.quantity)
                computed.append(recipe(allocate(recipe.Output, sizes)))
            else:
                raise InconsistentUpdate(f"{label}.{d.name}")
            if parent not in known:
                raise UnappliedIncrement(d.quantity.name)
            increments[parent.name] = (Annotated[d.field_type, parent, Tag.INCREMENT], None)
        for d in child.Output.declarations():
            if d.tag is Tag.TENDENCY and d.quantity not in consumed:
                raise UnappliedTendency(f"{label}.{d.name}")
        if isinstance(child, Process):
            updates[child] = tuple(computed)

    return Resolution(
        providers=tuple(recipe(allocate(recipe.Output, sizes)) for recipe in order),
        increments=allocate(state_type("Increments", increments), sizes),
        updates=updates,
        after_apply=tuple(hook(Empty()) for hook in hook_order),
    )


# Helper: one line per component, reads, writes, produces, updates, with <-
# Recipe on derived leaves
def dataflow(*components: Component[Any, Any]) -> str:
    def text(d: Decl) -> str:
        out = d.quantity.name + (f"@{d.level.value}" if d.level else "")
        if isinstance(d.marker, Derived):
            out += f" <- {d.marker.recipe.__name__}"
        elif isinstance(d.marker, FromTendency):
            out += " <- tendency"
        elif isinstance(d.marker, AfterApply):
            out += f" <- after apply {d.marker.recipe.__name__}"
        return out

    def names(decls: tuple[Decl, ...], intent: Intent | None = None) -> str:
        return ", ".join(text(d) for d in decls if intent is None or d.intent is intent) or "-"

    return "\n".join(
        f"{type(c).__name__:<26} reads: {names(c.Input.declarations(), Intent.READ)}"
        f" | writes: {names(c.Input.declarations(), Intent.READWRITE)}"
        f" | produces: {names(c.Output.declarations())}"
        f" | updates: {names(c.Update.declarations()) if isinstance(c, Process) else '-'}"
        for c in components
    )
