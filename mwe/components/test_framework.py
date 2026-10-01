import dataclasses
from collections.abc import Iterator

import numpy as np
import pytest
from icon4py.model.common import dimension as dims

from model_proposed.common import framework as fw

SIZES = {dims.CellDim: 3, dims.KDim: 2}


@pytest.fixture(autouse=True)
def _fresh_registries() -> Iterator[None]:
    saved = dict(fw.DERIVATIONS), dict(fw.RELOCATIONS)
    fw.DERIVATIONS.clear()
    fw.RELOCATIONS.clear()
    yield
    fw.DERIVATIONS.clear()
    fw.DERIVATIONS.update(saved[0])
    fw.RELOCATIONS.clear()
    fw.RELOCATIONS.update(saved[1])


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


def test_recipe_is_a_component_that_owns_its_result() -> None:
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
    class Wrong(fw.State):
        salt: Salt.Cell = fw.derived_by(DensityFromPressure)

    class Other(fw.Component):
        Input = Wrong
        Output = fw.Empty

    with pytest.raises(fw.InconsistentDerivation, match="does not produce Salt"):
        fw.resolve([Other], SIZES)

    class Twice(fw.Recipe):
        Input = Halve.Input
        Output = SaltFromDensity.Output

    class Second(fw.Component):
        Input = fw.state_type("Input", {"salt": Salt.Cell}, {"salt": fw.derived_by(Twice)})
        Output = fw.Empty

    with pytest.raises(fw.InconsistentDerivation, match="Salt: SaltFromDensity vs Twice"):
        fw.resolve([Consumer, Second], SIZES)


class SaltFromPressureHook(fw.Component):
    class Input(fw.State):
        pressure: Pressure.CellK

    class Output(fw.State):
        salt: Salt.Cell

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        np.asarray(out.salt.data.ndarray)[...] = np.asarray(input.pressure.data.ndarray).sum(axis=1)
        return out


class Heater(fw.Process):
    class Input(fw.State):
        pressure: Pressure.CellK

    class Output(fw.State):
        tend_pressure: fw.Tendency[Pressure, fw.CellK]

    class Update(fw.State):
        pressure: Pressure.CellK = fw.from_tendency()
        salt: Salt.Cell = fw.after_increments(SaltFromPressureHook)

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        np.asarray(out.tend_pressure.data.ndarray)[...] = 1.0
        return out


class SaltTendencyFromPressureTendency(fw.Recipe):
    class Input(fw.State):
        tend_pressure: fw.Tendency[Pressure, fw.CellK]

    class Output(fw.State):
        tend_salt: fw.Tendency[Salt, fw.Cell]

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        np.asarray(out.tend_salt.data.ndarray)[...] = np.asarray(input.tend_pressure.data.ndarray).sum(axis=1)
        return out


class Salter(fw.Process):
    Input = Heater.Input
    Output = Heater.Output

    class Update(fw.State):
        salt: Salt.Cell = fw.from_tendency(SaltTendencyFromPressureTendency)

    def run(self, input: Heater.Input, out: Heater.Output | None = None) -> Heater.Output:
        out = self.buffers(out)
        np.asarray(out.tend_pressure.data.ndarray)[...] = 1.0
        return out


class Box(fw.State):
    pressure: Pressure.CellK
    salt: Salt.Cell


def test_updates_reads_the_processes_update_blocks() -> None:
    heater, salter = Heater(SIZES), Salter(SIZES)
    u = fw.updates([heater, salter], SIZES, input=Box, output=Box)
    assert [(d.name, d.quantity, d.dims) for d in u.tendencies.declarations()] == [
        ("Pressure__CellK", fw.tendency_of(Pressure), fw.CellK),
        ("Salt__Cell", fw.tendency_of(Salt), fw.Cell),
    ]
    assert u.tendency_recipes[heater] == () and [type(r) for r in u.tendency_recipes[salter]] == [
        SaltTendencyFromPressureTendency
    ]
    assert [type(h) for h in u.hooks] == [SaltFromPressureHook] and u.hook_written == {(Salt, fw.Cell)}


def test_accumulate_then_update_applies_dt_once_and_runs_the_hooks_once() -> None:
    heater = Heater(SIZES)
    u = fw.updates([heater], SIZES, input=Box, output=Box)
    box, out = fw.allocate(Box, SIZES, fill=lambda name, shape: 3.0), fw.allocate(Box, SIZES)
    u.begin()
    output = heater.run(fw.collect(heater.Input, box))
    heater.accumulate(u.tendencies, output)
    heater.accumulate(u.tendencies, output)
    assert np.all(np.asarray(u.tendencies.leaves().__next__()[1].data.ndarray) == 2.0)
    u.update(box, out, 2.0)
    assert np.all(np.asarray(out.pressure.data.ndarray) == 7.0)
    assert np.all(np.asarray(out.salt.data.ndarray) == 14.0)
    assert np.all(np.asarray(box.pressure.data.ndarray) == 3.0)


def test_updates_refuses_inconsistent_declarations() -> None:
    class Silent(fw.Process):
        Input = Heater.Input
        Output = Heater.Output

    with pytest.raises(fw.UnappliedTendency, match="Silent.tend_pressure"):
        fw.updates([Silent(SIZES)], SIZES, input=Box, output=Box)

    class Elsewhere(fw.Process):
        Input = Heater.Input
        Output = Heater.Output
        Update = fw.state_type("Update", {"density": Density.CellK}, {"density": fw.from_tendency()})

    with pytest.raises(fw.InconsistentUpdate, match="no tendency of Density"):
        fw.updates([Elsewhere(SIZES)], SIZES, input=Box, output=Box)

    class Pressures(fw.State):
        pressure: Pressure.CellK

    with pytest.raises(fw.InconsistentUpdate, match="Salt is not an output"):
        fw.updates([Heater(SIZES)], SIZES, input=Pressures, output=Pressures)

    class Lost(fw.Process):
        Input = Heater.Input
        Output = Heater.Output
        Update = fw.state_type("Update", {"pressure": Pressure.CellK}, {"pressure": fw.from_tendency()})

    with pytest.raises(fw.UnappliedIncrement, match="neither an input nor provided"):
        fw.updates([Lost(SIZES)], SIZES, input=fw.Empty, output=Pressures)


class Counting(fw.Recipe):
    Input = DensityFromPressure.Input
    Output = DensityFromPressure.Output
    calls = 0

    def run(self, input: DensityFromPressure.Input, out: DensityFromPressure.Output | None = None) -> DensityFromPressure.Output:
        out = self.buffers(out)
        Counting.calls += 1
        np.asarray(out.density.data.ndarray)[...] = np.asarray(input.pressure.data.ndarray)
        return out


def test_composition_runs_a_provider_once_per_plan_and_only_when_needed() -> None:
    class Needs(fw.Component):
        class Input(fw.State):
            density: Density.CellK = fw.derived_by(Counting)

        Output = fw.Empty

        def run(self, input: Input, out: fw.Empty | None = None) -> fw.Empty:
            return self.buffers(out)

    needs, other = Needs(SIZES), Halve(SIZES)
    composition = fw.composition([needs, other], SIZES, input=fw.Empty, output=fw.Empty)
    assert [type(r) for r in composition.providers] == [Counting]
    assert composition.needs[needs] == composition.providers and composition.needs[other] == ()
    fields = fw.allocate(Halve.Input, SIZES)
    Counting.calls = 0
    plan = composition.begin()
    plan.run(other, inputs=(fields,))
    assert Counting.calls == 0
    plan.run(needs, inputs=(fields,))
    plan.run(needs, inputs=(fields,))
    assert Counting.calls == 1
    composition.begin().run(needs, inputs=(fields,))
    assert Counting.calls == 2
    supplied = fw.allocate(DensityFromPressure.Output, SIZES)
    composition.begin().run(needs, inputs=(fields, supplied))
    assert Counting.calls == 2
    plan = composition.begin()
    plan.run(needs, inputs=(fields,))
    assert plan.run(needs, inputs=(fields, supplied)).__class__ is fw.Empty and Counting.calls == 3


def test_plan_run_refuses_an_undeclared_alias() -> None:
    halve = Halve(SIZES)
    composition = fw.composition([halve], SIZES, input=fw.Empty, output=fw.Empty)
    fields = fw.allocate(Halve.Input, SIZES)
    with pytest.raises(fw.AliasedOutput, match="Halve.pressure"):
        composition.begin().run(halve, inputs=(fields,), outputs=(fields,))

    class InPlace(Halve):
        in_place = frozenset({"pressure"})

    inplace = InPlace(SIZES)
    fw.composition([inplace], SIZES, input=fw.Empty, output=fw.Empty).begin().run(inplace, inputs=(fields,), outputs=(fields,))


def test_relocation_registers_one_recipe_per_edge() -> None:
    class Flatten(fw.Recipe):
        class Input(fw.State):
            pressure: Pressure.CellK

        class Output(fw.State):
            column: Pressure.Cell

    assert fw.relocation(Flatten) is Flatten and fw.RELOCATIONS == {(Pressure, fw.CellK, fw.Cell): Flatten}

    class Again(Flatten):
        pass

    with pytest.raises(fw.InconsistentRelocation, match="Pressure: Flatten vs Again"):
        fw.relocation(Again)
    with pytest.raises(fw.InconsistentRelocation, match="another place expected"):
        fw.relocation(DensityFromPressure)


def test_derivations_are_checked_across_composites() -> None:
    fw.composition([Consumer(SIZES)], SIZES, input=fw.Empty, output=fw.Empty)

    class OtherSalt(SaltFromDensity):
        pass

    class Second(fw.Component):
        Input = fw.state_type("Input", {"salt": Salt.Cell}, {"salt": fw.derived_by(OtherSalt)})
        Output = fw.Empty

    with pytest.raises(fw.InconsistentDerivation, match="another composite"):
        fw.composition([Second(SIZES)], SIZES, input=fw.Empty, output=fw.Empty)


def test_dataflow_lists_reads_and_produces_by_label() -> None:
    class Flux(fw.Component):
        class Input(fw.State):
            pressure: Pressure.CellK
            column: Pressure.Cell
            tend: fw.Tendency[Salt, fw.Cell]

        Output = fw.Empty

    assert fw.dataflow(Halve, Flux, Consumer, Salter) == (
        "Halve | reads: Pressure@CellK | produces: Pressure@CellK\n"
        "Flux | reads: Pressure@CellK, Pressure@Cell, TendencyOfSalt | produces: -\n"
        "Consumer | reads: Salt <- SaltFromDensity, Pressure@CellK | produces: -\n"
        "Salter | reads: Pressure@CellK | produces: TendencyOfPressure@CellK | updates: Salt += SaltTendencyFromPressureTendency"
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
