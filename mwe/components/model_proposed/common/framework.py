import dataclasses
import functools
import typing
from collections.abc import Callable, Iterable, Iterator, Mapping
from typing import Any, ClassVar, dataclass_transform

import gt4py.next as gtx
import numpy as np
from icon4py.model.common import type_alias as ta


# ------------------------------------------------------------------------------
# Quantity: a type-level tag, never instantiated
# ------------------------------------------------------------------------------
# One subclass per quantity; the CF metadata and the grid dimensions sit on the
# class. The class exists to be named in types: `Field[VnOnEdgeK]`. A keyword
# not given is inherited from the base (a marker base like `Tendency` gives
# none).
class Quantity:
    dims: ClassVar[tuple[gtx.Dimension, ...]]
    standard_name: ClassVar[str | None] = None
    units: ClassVar[str]
    long_name: ClassVar[str | None] = None

    def __init_subclass__(
        cls,
        *,
        dims: tuple[gtx.Dimension, ...] | None = None,
        standard_name: str | None = None,
        units: str | None = None,
        long_name: str | None = None,
    ) -> None:
        super().__init_subclass__()
        for name, value in (("dims", dims), ("standard_name", standard_name), ("units", units), ("long_name", long_name)):
            if value is not None:
                setattr(cls, name, value)

    def __new__(cls, *args: Any, **kwargs: Any) -> Any:
        raise TypeError(f"{cls.__name__} is a type-level tag, not a value")


# A gt4py field tagged by its quantity. The tag is a phantom type parameter:
# `Field[VnOnEdgeK]` and `Field[ThetaVOnCellK]` are different types to mypy and
# pyright, the same array to gt4py. Stencils get `.data`. Invariant: a
# `Field[VnOnEdgeK]` is not a `Field[Quantity]`, so a signature `(Field[Q],
# Field[Q])` means the same quantity twice.
class Field[Q: Quantity]:
    __slots__ = ("quantity", "data")

    def __init__(self, quantity: type[Q], data: gtx.Field[Any, Any]) -> None:
        self.quantity = quantity
        self.data = data

    def __repr__(self) -> str:
        return f"Field({self.quantity.__name__}, {self.data.ndarray.shape})"


def zeros[T: Quantity](quantity: type[T], sizes: Mapping[gtx.Dimension, int]) -> Field[T]:
    return Field(quantity, gtx.zeros({dim: sizes[dim] for dim in quantity.dims}, dtype=ta.wpfloat))


# ------------------------------------------------------------------------------
# State: a frozen dataclass of typed leaves
# ------------------------------------------------------------------------------
# one Field leaf read back from a State class: its name and its quantity
# fw.Field[qty.VnOnEdgeK] lives in annotations. mypy/pyright read it, Python at
# runtime does not, unless someone inspects hints. Decl is that inspection,
# done once, so every generic operation over "a state" asks the class instead
# of hard-coding leaf names.
@dataclasses.dataclass(frozen=True)
class Decl:
    name: str
    quantity: type[Quantity]


@dataclass_transform(frozen_default=True, kw_only_default=True, eq_default=False)
class State:
    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        dataclasses.dataclass(frozen=True, eq=False, kw_only=True)(cls)

    # declarations() is class-level. Needs no values. So later layers can
    # reason about a component before anything is allocated (resolve, plan,
    # dataflow report).
    @classmethod
    def declarations(cls) -> tuple[Decl, ...]:
        return _declarations(cls)

    # leaves() is instance-level. Decl plus the actual Field. For things that
    # move data.
    def leaves(self) -> Iterator[tuple[Decl, Field[Any]]]:
        for d in self.declarations():
            yield d, getattr(self, d.name)


_DECLARATIONS: dict[type[State], tuple[Decl, ...]] = {}


def _declarations(cls: type[State]) -> tuple[Decl, ...]:
    if cls not in _DECLARATIONS:
        hints = typing.get_type_hints(cls)
        found = []
        for field in dataclasses.fields(cls):  # type: ignore[arg-type]
            hint = hints[field.name]
            if typing.get_origin(hint) is Field:
                (quantity,) = typing.get_args(hint)
                found.append(Decl(field.name, quantity))
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
        f = zeros(d.quantity, sizes)
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


# flattens states to {quantity: field}; two different buffers for one quantity
# is AmbiguousSource, the same buffer twice is fine
def _available(states: Iterable[State]) -> dict[type[Quantity], Field[Any]]:
    available: dict[type[Quantity], Field[Any]] = {}
    for state in states:
        for d, value in state.leaves():
            if available.setdefault(d.quantity, value) is not value:
                raise AmbiguousSource(d.quantity.__name__)
    return available


# one leaf per Field declaration of cls, picked from the given states by
# quantity; plain leaves by keyword, and a Field leaf given by keyword wins
# over the pool. Pointer selection only, never computes.
def collect[S: State](cls: type[S], *states: State, **plain: Any) -> S:
    available = _available(states)
    values: dict[str, Any] = dict(plain)
    for d in cls.declarations():
        if d.name in plain:
            continue
        if d.quantity not in available:
            raise MissingInput(f"{cls.__qualname__}.{d.name}: {d.quantity.__name__}")
        values[d.name] = available[d.quantity]
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
