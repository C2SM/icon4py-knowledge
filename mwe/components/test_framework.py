import dataclasses

import numpy as np
import pytest
from icon4py.model.common import dimension as dims

from model_proposed.common import framework as fw

SIZES = {dims.CellDim: 3, dims.KDim: 2}


class Pressure(fw.Quantity, dims=(dims.CellDim, dims.KDim), standard_name="air_pressure", units="Pa"): ...


class Salt(fw.Quantity, dims=(dims.CellDim,), units="1"): ...


class Column(fw.State):
    pressure: fw.Field[Pressure]
    salt: fw.Field[Salt]
    dtime: float


class Halve(fw.Component):
    class Input(fw.State):
        pressure: fw.Field[Pressure]

    class Output(fw.State):
        pressure: fw.Field[Pressure]

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        np.asarray(out.pressure.data.ndarray)[...] = 0.5 * np.asarray(input.pressure.data.ndarray)
        return out


def test_quantity_is_a_tag_with_metadata() -> None:
    assert Pressure.dims == (dims.CellDim, dims.KDim)
    assert Pressure.standard_name == "air_pressure"
    assert Pressure.units == "Pa"
    assert Salt.standard_name is None
    with pytest.raises(TypeError):
        Pressure()


def test_field_keeps_its_quantity() -> None:
    p = fw.zeros(Pressure, SIZES)
    assert p.quantity is Pressure
    assert p.data.ndarray.shape == (3, 2)


def test_state_declarations_list_the_field_leaves_only() -> None:
    assert [(d.name, d.quantity) for d in Column.declarations()] == [("pressure", Pressure), ("salt", Salt)]
    column = Column(pressure=fw.zeros(Pressure, SIZES), salt=fw.zeros(Salt, SIZES), dtime=1.0)
    assert [d.name for d, _ in column.leaves()] == ["pressure", "salt"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        column.dtime = 2.0  # type: ignore[misc]


def test_allocate_follows_the_declared_dims() -> None:
    class Fields(fw.State):
        pressure: fw.Field[Pressure]
        salt: fw.Field[Salt]

    fields = fw.allocate(Fields, SIZES, fill=lambda name, shape: float(len(name)))
    assert fields.pressure.data.ndarray.shape == (3, 2)
    assert fields.salt.data.ndarray.shape == (3,)
    assert np.all(np.asarray(fields.salt.data.ndarray) == 4.0)


def test_component_writes_its_own_buffers_or_the_callers() -> None:
    halve = Halve(SIZES)
    pressure = fw.zeros(Pressure, SIZES)
    np.asarray(pressure.data.ndarray)[...] = 8.0
    own = halve.run(Halve.Input(pressure=pressure))
    assert own is halve.output and own is halve.run(Halve.Input(pressure=pressure))
    assert np.all(np.asarray(own.pressure.data.ndarray) == 4.0)
    given = Halve.Output(pressure=pressure)
    assert halve.run(Halve.Input(pressure=pressure), out=given) is given
    assert np.all(np.asarray(pressure.data.ndarray) == 4.0)


def test_pairs_swap() -> None:
    a, b = fw.allocate(Halve.Output, SIZES), fw.allocate(Halve.Output, SIZES)
    pair = fw.TimeStepPair(a, b)
    pair.swap()
    assert pair.now is b and pair.next is a


def test_collect_picks_leaves_by_quantity() -> None:
    class Fields(fw.State):
        pressure: fw.Field[Pressure]
        salt: fw.Field[Salt]

    class View(fw.State):
        salt: fw.Field[Salt]
        dtime: float

    fields = fw.allocate(Fields, SIZES)
    view = fw.collect(View, fields, dtime=2.0)
    assert view.salt is fields.salt and view.dtime == 2.0
    same_buffers_twice = Column(pressure=fields.pressure, salt=fields.salt, dtime=0.0)
    assert fw.collect(View, fields, same_buffers_twice, dtime=2.0).salt is fields.salt
    other = fw.zeros(Salt, SIZES)
    assert fw.collect(View, fields, salt=other, dtime=2.0).salt is other
    with pytest.raises(fw.MissingInput, match="View.salt: Salt"):
        fw.collect(View, Halve.Output(pressure=fields.pressure), dtime=2.0)
    with pytest.raises(fw.AmbiguousSource, match="Pressure"):
        fw.collect(View, fields, fw.allocate(Halve.Input, SIZES), dtime=2.0)


# what mypy and pyright check: a quantity mismatch is a type error. Each
# ignore below is required (strict mode reports an unused one), so the suite
# type-checking is the test.
def static_checks(pressure: fw.Field[Pressure], salt: fw.Field[Salt]) -> None:
    wrong: fw.Field[Pressure] = salt  # type: ignore[assignment]
    Halve.Input(pressure=salt)  # type: ignore[arg-type]
    Halve.Input(pressure=pressure)
    del wrong
