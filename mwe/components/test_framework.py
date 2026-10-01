import dataclasses

import numpy as np
import pytest
from icon4py.model.common import dimension as dims

from model_proposed.common import framework as fw

SIZES = {dims.CellDim: 3, dims.KDim: 2}


class Pressure(fw.Quantity, standard_name="air_pressure", units="Pa"):
    type CellK = fw.Field[Pressure, fw.CellK]
    type Cell = fw.Field[Pressure, fw.Cell]


class Salt(fw.Quantity, units="1"):
    type Cell = fw.Field[Salt, fw.Cell]


class Density(fw.Quantity, standard_name="air_density", units="kg m-3"):
    type CellK = fw.Field[Density, fw.CellK]


class Column(fw.State):
    pressure: Pressure.CellK
    salt: Salt.Cell
    dtime: float


class Halve(fw.Component):
    class Input(fw.State):
        pressure: Pressure.CellK

    class Output(fw.State):
        pressure: Pressure.CellK

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        np.asarray(out.pressure.data.ndarray)[...] = 0.5 * np.asarray(input.pressure.data.ndarray)
        return out


def test_quantity_is_a_tag_with_metadata_and_places() -> None:
    assert Pressure.standard_name == "air_pressure"
    assert Pressure.units == "Pa"
    assert Pressure.places() == (fw.CellK, fw.Cell)
    assert Salt.standard_name is None and Salt.places() == (fw.Cell,)
    assert fw.CellK.dims == (dims.CellDim, dims.KDim)
    with pytest.raises(TypeError):
        Pressure()
    with pytest.raises(TypeError):
        fw.CellK()


def test_field_keeps_its_quantity_and_place() -> None:
    p = fw.zeros(Pressure, fw.CellK, SIZES)
    assert p.quantity is Pressure and p.dims is fw.CellK
    assert p.data.ndarray.shape == (3, 2)


def test_state_declarations_list_the_field_leaves_only() -> None:
    assert [(d.name, d.quantity, d.dims) for d in Column.declarations()] == [
        ("pressure", Pressure, fw.CellK),
        ("salt", Salt, fw.Cell),
    ]
    column = Column(pressure=fw.zeros(Pressure, fw.CellK, SIZES), salt=fw.zeros(Salt, fw.Cell, SIZES), dtime=1.0)
    assert [d.name for d, _ in column.leaves()] == ["pressure", "salt"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        column.dtime = 2.0  # type: ignore[misc]


def test_a_place_the_quantity_does_not_declare_is_refused() -> None:
    with pytest.raises(fw.InvalidDims, match="Salt at CellK"):

        class Wrong(fw.State):
            salt: fw.Field[Salt, fw.CellK]


def test_allocate_follows_the_declared_place() -> None:
    class Fields(fw.State):
        pressure: Pressure.CellK
        salt: Salt.Cell

    fields = fw.allocate(Fields, SIZES, fill=lambda name, shape: float(len(name)))
    assert fields.pressure.data.ndarray.shape == (3, 2)
    assert fields.salt.data.ndarray.shape == (3,)
    assert np.all(np.asarray(fields.salt.data.ndarray) == 4.0)


def test_component_writes_its_own_buffers_or_the_callers() -> None:
    halve = Halve(SIZES)
    pressure = fw.zeros(Pressure, fw.CellK, SIZES)
    np.asarray(pressure.data.ndarray)[...] = 8.0
    own = halve.run(Halve.Input(pressure=pressure))
    assert own is halve.output and own is halve.run(Halve.Input(pressure=pressure))
    assert np.all(np.asarray(own.pressure.data.ndarray) == 4.0)
    given = Halve.Output(pressure=pressure)
    assert halve.run(Halve.Input(pressure=pressure), out=given) is given
    assert np.all(np.asarray(pressure.data.ndarray) == 4.0)


def test_tendency_of_derives_one_class_per_parent() -> None:
    t = fw.tendency_of(Pressure)
    assert t is fw.tendency_of(Pressure) and issubclass(t, fw.TendencyOf)
    assert t.__name__ == "TendencyOfPressure" and t.parent is Pressure
    assert t.units == "Pa s-1" and t.standard_name == "tendency_of_air_pressure"
    assert t.places() == Pressure.places()
    assert fw.tendency_of(Salt).units == "s-1" and fw.tendency_of(Salt).standard_name is None


def test_a_tendency_leaf_declares_the_derived_quantity() -> None:
    class Tendencies(fw.State):
        tend_pressure: fw.Tendency[Pressure, fw.CellK]

    (d,) = Tendencies.declarations()
    assert d.quantity is fw.tendency_of(Pressure) and d.dims is fw.CellK
    assert fw.allocate(Tendencies, SIZES).tend_pressure.data.ndarray.shape == (3, 2)


def test_pairs_swap() -> None:
    a, b = fw.allocate(Halve.Output, SIZES), fw.allocate(Halve.Output, SIZES)
    pair = fw.TimeStepPair(a, b)
    pair.swap()
    assert pair.now is b and pair.next is a


def test_recipe_is_a_component_that_owns_its_result() -> None:
    class DensityFromPressure(fw.Recipe):
        class Input(fw.State):
            pressure: Pressure.CellK

        class Output(fw.State):
            density: Density.CellK

        def run(self, input: Input, out: Output | None = None) -> Output:
            out = self.buffers(out)
            np.asarray(out.density.data.ndarray)[...] = 2.0 * np.asarray(input.pressure.data.ndarray)
            return out

    pressure = fw.zeros(Pressure, fw.CellK, SIZES)
    np.asarray(pressure.data.ndarray)[...] = 3.0
    recipe = DensityFromPressure(SIZES)
    density = recipe.run(DensityFromPressure.Input(pressure=pressure)).density
    assert density is recipe.output.density and density.quantity is Density
    assert np.all(np.asarray(density.data.ndarray) == 6.0)


def test_collect_picks_leaves_by_quantity_and_place() -> None:
    class Fields(fw.State):
        pressure: Pressure.CellK
        column: Pressure.Cell

    class View(fw.State):
        column: Pressure.Cell
        salt: Salt.Cell
        dtime: float

    fields = fw.allocate(Fields, SIZES)
    salted = Column(pressure=fields.pressure, salt=fw.zeros(Salt, fw.Cell, SIZES), dtime=0.0)
    view = fw.collect(View, fields, salted, dtime=2.0)
    assert view.column is fields.column and view.salt is salted.salt and view.dtime == 2.0
    other = fw.zeros(Pressure, fw.Cell, SIZES)
    assert fw.collect(View, fields, salted, column=other, dtime=2.0).column is other
    with pytest.raises(fw.MissingInput, match="View.salt: Salt"):
        fw.collect(View, fields, dtime=2.0)
    with pytest.raises(fw.AmbiguousSource, match="Pressure@CellK"):
        fw.collect(View, fields, salted, fw.allocate(Halve.Input, SIZES), dtime=2.0)


def test_dataflow_lists_reads_and_produces_by_label() -> None:
    class Flux(fw.Component):
        class Input(fw.State):
            pressure: Pressure.CellK
            column: Pressure.Cell
            tend: fw.Tendency[Salt, fw.Cell]

        Output = fw.Empty

    assert fw.dataflow(Halve, Flux) == (
        "Halve | reads: Pressure@CellK | produces: Pressure@CellK\n"
        "Flux | reads: Pressure@CellK, Pressure@Cell, TendencyOfSalt | produces: -"
    )


# what mypy and pyright check: a quantity or a place mismatch is a type error.
# Each ignore below is required (both checkers report an unused one), so the
# suite type-checking is the test.
def static_checks(
    pressure: Pressure.CellK, column: Pressure.Cell, salt: Salt.Cell, tendency: fw.Tendency[Pressure, fw.CellK]
) -> None:
    wrong_quantity: Pressure.Cell = salt  # type: ignore[assignment]
    wrong_place: Pressure.CellK = column  # type: ignore[assignment]
    not_a_tendency: fw.Tendency[Pressure, fw.CellK] = pressure  # type: ignore[assignment]
    other_tendency: fw.Tendency[Salt, fw.CellK] = tendency  # type: ignore[assignment]
    Halve.Input(pressure=column)  # type: ignore[arg-type]
    Halve.Input(pressure=pressure)
    del wrong_quantity, wrong_place, not_a_tendency, other_tendency
