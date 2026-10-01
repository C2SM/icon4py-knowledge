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


# A tendency is a quantity derived from its parent. `TendencyOf[Temperature]`
# names it in a type and `tendency_of(Temperature)` is the one class behind it
# at runtime: the parent's places, its units per second, the CF `tendency_of_`
# name, and `parent`, the link that says where the tendency lands.
class TendencyOf[Q: Quantity](Quantity):
    parent: ClassVar[type[Quantity]]


type Tendency[Q: Quantity, D: Dims] = Field[TendencyOf[Q], D]

_TENDENCIES: dict[type[Quantity], type[TendencyOf[Any]]] = {}


def tendency_of(quantity: type[Quantity]) -> type[TendencyOf[Any]]:
    if quantity not in _TENDENCIES:
        units = "s-1" if quantity.units == "1" else f"{quantity.units} s-1"
        standard_name = f"tendency_of_{quantity.standard_name}" if quantity.standard_name else None
        cls = typing.cast(
            type[TendencyOf[Any]],
            types.new_class(
                f"TendencyOf{quantity.__name__}", (TendencyOf,), {"units": units, "standard_name": standard_name}
            ),
        )
        cls.parent = quantity
        cls._places = quantity.places()
        _TENDENCIES[quantity] = cls
    return _TENDENCIES[quantity]


# ------------------------------------------------------------------------------
# State: a frozen dataclass of typed leaves
# ------------------------------------------------------------------------------
# one Field leaf read back from a State class: its name, quantity and place
@dataclasses.dataclass(frozen=True)
class Decl:
    name: str
    quantity: type[Quantity]
    dims: type[Dims]

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
                found.append(Decl(field.name, quantity, dims))
        _DECLARATIONS[cls] = tuple(found)
    return _DECLARATIONS[cls]


class Empty(State):
    pass


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
# rather than writing a stencil call and a buffer of its own. A recipe's
# Output quantities are not among its Input quantities; a component that
# writes back what it reads is an update, not a recipe. The empty subclass is
# the name, nothing reads it yet; the composer decides when to run it.
class Recipe(Component):
    pass


# ------------------------------------------------------------------------------
# Reports
# ------------------------------------------------------------------------------
# what each component reads and produces, from its declarations alone
def dataflow(*components: type[Component]) -> str:
    def names(decls: tuple[Decl, ...]) -> str:
        return ", ".join(d.label for d in decls) or "-"

    return "\n".join(
        f"{c.__name__} | reads: {names(c.Input.declarations())} | produces: {names(c.Output.declarations())}"
        for c in components
    )
