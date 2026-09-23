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
    recipe: type[Component[Any, Any]]


def derived_by(recipe: type[Component[Any, Any]]) -> Any:
    return Derived(recipe)


@dataclasses.dataclass(frozen=True)
class Decl:
    name: str
    quantity: Quantity
    intent: Intent | None
    tag: Tag | None
    level: Level | None
    field_type: Any
    recipe: type[Component[Any, Any]] | None


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
    recipe = default.recipe if isinstance(default, Derived) else None
    return Decl(name, q, intent, tag, level, base, recipe)


_DECLARATIONS: dict[type, tuple[Decl, ...]] = {}


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
        for d, value in self.leaves():
            if isinstance(value, Derived):
                raise UnresolvedInput(f"{type(self).__name__}.{d.name}")

    @classmethod
    def declarations(cls) -> tuple[Decl, ...]:
        return declarations(cls)

    def leaves(self) -> Iterator[tuple[Decl, Any]]:
        for d in self.declarations():
            yield d, getattr(self, d.name)


class Empty(State):
    pass


def state_type(name: str, leaves: dict[str, tuple[Any, Derived | None]]) -> type[State]:
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


class InconsistentDerivation(ValueError):
    pass


class MissingWriteBack(ValueError):
    pass


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
    write_back: ClassVar[type[Component[Any, Any]] | None] = None
    invertible: ClassVar[bool] = False

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

    def accumulate(self, into: State, dt: float) -> None:
        targets = {d.quantity: value for d, value in into.leaves()}
        for d, value in self.output.leaves():
            if d.tag is Tag.TENDENCY and d.quantity.of is not None:
                np.asarray(targets[increment_of(d.quantity.of)].ndarray)[...] += dt * np.asarray(value.ndarray)

    def apply(self, increments: State, *targets: State) -> None:
        leaves = {d.quantity: value for target in targets for d, value in target.leaves()}
        for d, value in increments.leaves():
            if d.tag is not Tag.INCREMENT:
                continue
            if d.quantity.of not in leaves:
                raise UnappliedIncrement(d.quantity.name)
            np.asarray(leaves[d.quantity.of].ndarray)[...] += np.asarray(value.ndarray)


@dataclasses.dataclass(frozen=True)
class Resolution:
    providers: tuple[Component[Any, Any], ...]
    increments: State
    write_backs: tuple[Component[Any, Any], ...]
    reusable: frozenset[type[Component[Any, Any]]]

    def run_providers(self, *supplied: State | TimeStepPair[Any]) -> tuple[State, ...]:
        available = _available(supplied)
        produced: list[State] = []
        for provider in self.providers:
            if all((d.quantity, None) in available for d in provider.Output.declarations()):
                continue
            provider.run(provider.collect_inputs(*supplied, *produced))
            produced.append(provider.output)
        return tuple(produced)

    def reusable_outputs(self, produced: Iterable[State]) -> tuple[State, ...]:
        recipe_of = {id(provider.output): type(provider) for provider in self.providers}
        return tuple(state for state in produced if recipe_of[id(state)] in self.reusable)


def resolve(
    children: Iterable[Component[Any, Any]], sizes: dict[gtx.Dimension, int], *, targets: type[State]
) -> Resolution:
    children = tuple(children)
    recipes: dict[tuple[Quantity, Level | None], type[Component[Any, Any]]] = {}
    order: list[type[Component[Any, Any]]] = []

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

    tendencies: dict[str, tuple[Any, Derived | None]] = {}
    for child in children:
        for d in child.Output.declarations():
            if d.tag is Tag.TENDENCY and d.quantity.of is not None:
                tendencies[d.quantity.of.name] = (Annotated[d.field_type, d.quantity.of, Tag.INCREMENT], None)
    increments = allocate(state_type("Increments", tendencies), sizes)

    provided = {d.quantity: recipe for recipe in order for d in recipe.Output.declarations()}
    target_quantities = {d.quantity for d in targets.declarations()}
    incremented: set[type[Component[Any, Any]]] = set()
    write_backs: list[type[Component[Any, Any]]] = []
    for d in increments.declarations():
        parent = d.quantity.of
        if parent is None or parent in target_quantities:
            continue
        if parent not in provided:
            raise UnappliedIncrement(d.quantity.name)
        recipe = provided[parent]
        if recipe.write_back is None:
            raise MissingWriteBack(recipe.__name__)
        incremented.add(recipe)
        if recipe.write_back not in write_backs:
            write_backs.append(recipe.write_back)

    return Resolution(
        providers=tuple(recipe(allocate(recipe.Output, sizes)) for recipe in order),
        increments=increments,
        write_backs=tuple(write_back(Empty()) for write_back in write_backs),
        reusable=frozenset(recipe for recipe in order if recipe not in incremented or recipe.invertible),
    )


def dataflow(*components: Component[Any, Any]) -> str:
    def names(decls: tuple[Decl, ...], intent: Intent | None = None) -> str:
        picked = [
            d.quantity.name + (f"@{d.level.value}" if d.level else "") + (f" <- {d.recipe.__name__}" if d.recipe else "")
            for d in decls
            if intent is None or d.intent is intent
        ]
        return ", ".join(picked) or "-"

    return "\n".join(
        f"{type(c).__name__:<26} reads: {names(c.Input.declarations(), Intent.READ)}"
        f" | writes: {names(c.Input.declarations(), Intent.READWRITE)}"
        f" | produces: {names(c.Output.declarations())}"
        for c in components
    )
