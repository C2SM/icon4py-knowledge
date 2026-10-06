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


class Density(fw.Quantity, standard_name="sea_water_density", units="kg m-3"):
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


def test_recipe_is_a_component_that_owns_its_result() -> None:
    pressure = fw.zeros(Pressure, fw.CellK, SIZES)
    np.asarray(pressure.data.ndarray)[...] = 3.0
    recipe = DensityFromPressure(SIZES)
    density = recipe.run(DensityFromPressure.Input(pressure=pressure)).density
    assert density is recipe.output.density and density.quantity is Density
    assert np.all(np.asarray(density.data.ndarray) == 6.0)


def test_lookup_by_standard_name_or_class_name() -> None:
    assert fw.lookup("air_pressure") is Pressure and fw.lookup("Pressure") is Pressure
    assert fw.lookup("Salt") is Salt
    with pytest.raises(fw.UnknownQuantity, match="pepper"):
        fw.lookup("pepper")
    with pytest.raises(fw.UnknownQuantity, match="TendencyOf"):
        fw.lookup("TendencyOf")
    with pytest.raises(fw.DuplicateQuantity, match="Salt"):
        type("Salt", (fw.Quantity,), {}, units="1")
    with pytest.raises(fw.DuplicateQuantity, match="air_pressure is taken"):
        type("Pressure2", (fw.Quantity,), {}, standard_name="air_pressure", units="Pa")


def test_state_type_builds_a_collectable_state() -> None:
    View = fw.state_type("View", {"air_pressure": Pressure.CellK, "when": float})
    fields = fw.allocate(Halve.Input, SIZES)
    view = fw.collect(View, fields, when=1.0)
    assert [d.label for d in View.declarations()] == ["Pressure@CellK"]
    assert getattr(view, "air_pressure") is fields.pressure and getattr(view, "when") == 1.0
    Sourced = fw.state_type("Sourced", {"density": Density.CellK}, {"density": fw.derived_by(DensityFromPressure)})
    assert Sourced.declarations()[0].source == fw.Derived(DensityFromPressure)


class DensityFromPressure(fw.Recipe):
    class Input(fw.State):
        pressure: Pressure.CellK

    class Output(fw.State):
        density: Density.CellK

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        np.asarray(out.density.data.ndarray)[...] = 2.0 * np.asarray(input.pressure.data.ndarray)
        return out


class SaltFromDensity(fw.Recipe):
    class Input(fw.State):
        density: Density.CellK = fw.derived_by(DensityFromPressure)

    class Output(fw.State):
        salt: Salt.Cell

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        np.asarray(out.salt.data.ndarray)[...] = np.asarray(input.density.data.ndarray).sum(axis=1)
        return out


class Consumer(fw.Component):
    class Input(fw.State):
        salt: Salt.Cell = fw.derived_by(SaltFromDensity)
        pressure: Pressure.CellK

    Output = fw.Empty

    def run(self, input: Input, out: fw.Empty | None = None) -> fw.Empty:
        return self.buffers(out)


def test_derived_by_is_a_source_on_the_declaration_only() -> None:
    (salt, pressure) = Consumer.Input.declarations()
    assert salt.source == fw.Derived(SaltFromDensity) and pressure.source is None
    with pytest.raises(fw.UnresolvedInput, match="Consumer.Input.salt"):
        Consumer.Input(salt=fw.derived_by(SaltFromDensity), pressure=fw.zeros(Pressure, fw.CellK, SIZES))


def test_resolve_orders_the_providers_and_provide_runs_them() -> None:
    resolution = fw.resolve([Consumer], SIZES)
    assert [type(r) for r in resolution.providers] == [DensityFromPressure, SaltFromDensity]
    fields = fw.allocate(Halve.Input, SIZES, fill=lambda name, shape: 1.0)
    produced = resolution.provide(fields)
    view = fw.collect(Consumer.Input, fields, *produced)
    assert np.all(np.asarray(view.salt.data.ndarray) == 4.0)
    assert view.salt is resolution.providers[1].output.salt
    assert fw.resolve([Halve], SIZES).providers == ()


def test_resolve_refuses_an_inconsistent_derivation() -> None:
    class Other(fw.Component):
        class Input(fw.State):
            salt: Salt.Cell = fw.derived_by(DensityFromPressure)

        Output = fw.Empty

    with pytest.raises(fw.InconsistentDerivation, match="does not produce Salt"):
        fw.resolve([Other], SIZES)

    class Twice(fw.Recipe):
        Input = Halve.Input
        Output = SaltFromDensity.Output

    class Second(fw.Component):
        class Input(fw.State):
            salt: Salt.Cell = fw.derived_by(Twice)

        Output = fw.Empty

    with pytest.raises(fw.InconsistentDerivation, match="Salt: SaltFromDensity vs Twice"):
        fw.resolve([Consumer, Second], SIZES)


def test_resolve_refuses_a_cycle() -> None:
    class A(fw.Recipe):
        class Output(fw.State):
            density: Density.CellK

    class B(fw.Recipe):
        class Input(fw.State):
            density: Density.CellK = fw.derived_by(A)

        class Output(fw.State):
            salt: Salt.Cell

    class SaltFromB(fw.State):
        salt: Salt.Cell = fw.derived_by(B)

    A.Input = SaltFromB

    class Needs(fw.Component):
        Input = SaltFromB
        Output = fw.Empty

    with pytest.raises(fw.InconsistentDerivation, match="cycle: "):
        fw.resolve([Needs], SIZES)


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
