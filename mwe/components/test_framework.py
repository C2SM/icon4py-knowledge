import numpy as np
import pytest

import ops
from model_proposed.common import framework as fw


class Pressure(fw.Quantity, locations=(fw.CellK,), standard_name="air_pressure", units="Pa"): ...
class Salt(fw.Quantity, locations=(fw.CellK, fw.CellKHalf), units="1"): ...
class Density(fw.Quantity, units="kg m-3"): ...


type TField = fw.CellK[Pressure]
type SField = fw.CellK[Salt]
type SHalfField = fw.CellKHalf[Salt]
type DField = fw.CellK[Density]


@pytest.fixture(autouse=True)
def _fresh_derivations() -> None:
    fw.DERIVATIONS.clear()


class Owner(fw.State):
    temperature: TField
    salt: SField


class Producer(fw.Process):
    class Input(fw.State):
        temperature: TField
        salt: SField

    class Output(fw.State):
        ddt_temperature: fw.Tendency[TField]

    class Update(fw.State):
        temperature: fw.Increment[TField] = fw.from_tendency()

    def run(self, input: Input, output: Output) -> None:
        ops.arr(output.ddt_temperature)[...] = 2.0


class Forgetful(fw.Component):
    class Input(fw.State):
        pass

    class Output(fw.State):
        ddt_temperature: fw.Tendency[TField]


class ForgetfulProcess(fw.Process):
    Input = Forgetful.Input
    Output = Forgetful.Output


class DensityFromSalt(fw.Recipe):
    class Input(fw.State):
        salt: SField

    class Output(fw.State):
        density: DField

    def run(self, input: Input, output: Output) -> None:
        ops.arr(output.density)[...] = 2.0 * ops.arr(input.salt)


class DensityFromNothing(fw.Recipe):
    class Input(fw.State):
        pass

    class Output(fw.State):
        density: DField

    def run(self, input: Input, output: Output) -> None:
        pass


class SaltFromDensity(fw.Component):
    class Input(fw.State):
        density: DField

    class Output(fw.State):
        salt: SField

    def run(self, input: Input, output: Output) -> None:
        ops.arr(output.salt)[...] = 0.5 * ops.arr(input.density)


class SaltIncrementFromDensityTendency(fw.Recipe):
    class Input(fw.State):
        ddt_density: fw.Tendency[DField]

    class Output(fw.State):
        salt: fw.Increment[SField]

    def run(self, input: Input, output: Output) -> None:
        ops.arr(output.salt)[...] = 5.0 * ops.arr(input.ddt_density)


class Consumer(fw.Process):
    class Input(fw.State):
        density: DField = fw.derived_by(DensityFromSalt)
        salt: SField

    class Output(fw.State):
        ddt_density: fw.Tendency[DField]

    class Update(fw.State):
        density: fw.Increment[DField] = fw.from_tendency()
        salt: SField = fw.after_increments(SaltFromDensity)

    def run(self, input: Input, output: Output) -> None:
        ops.arr(output.ddt_density)[...] = ops.arr(input.density)


class IncrementConsumer(fw.Process):
    class Input(fw.State):
        salt: SField

    class Output(fw.State):
        ddt_density: fw.Tendency[DField]

    class Update(fw.State):
        salt: fw.Increment[SField] = fw.derived_by(SaltIncrementFromDensityTendency)

    def run(self, input: Input, output: Output) -> None:
        ops.arr(output.ddt_density)[...] = 3.0 * ops.arr(input.salt)


class OtherConsumer(fw.Component):
    class Input(fw.State):
        density: DField = fw.derived_by(DensityFromNothing)

    Output = fw.Empty


class WrongHook(fw.Process):
    class Input(fw.State):
        density: DField = fw.derived_by(DensityFromSalt)

    Output = fw.Empty

    class Update(fw.State):
        density: DField = fw.after_increments(SaltFromDensity)


class WrongTendency(fw.Process):
    class Input(fw.State):
        pass

    Output = fw.Empty

    class Update(fw.State):
        salt: fw.Increment[SField] = fw.from_tendency()


class Doubler(fw.Component):
    class Input(fw.State):
        salt: SField

    class Output(fw.State):
        salt: SField

    in_place = frozenset({"salt"})

    def run(self, input: Input, output: Output) -> None:
        ops.arr(output.salt)[...] = 2.0 * ops.arr(input.salt)


class NotInPlaceDoubler(Doubler):
    in_place = frozenset()


class HalfOwner(fw.State):
    salt_ic: SHalfField


@fw.relocation
class SaltToHalfLevels(fw.Recipe):
    class Input(fw.State):
        salt: SField

    class Output(fw.State):
        salt_ic: SHalfField

    def run(self, input: Input, output: Output) -> None:
        ops.interpolate_to_half_levels(input.salt, output.salt_ic)


class HalfConsumer(fw.Component):
    class Input(fw.State):
        salt_ic: SHalfField = fw.derived_by(SaltToHalfLevels)

    Output = fw.Empty

    def run(self, input: Input, output: fw.Empty) -> None:
        pass


def test_declarations_carry_quantity_tag_and_marker() -> None:
    by_name = {d.name: d for d in Producer.Input.declarations()}
    assert (by_name["temperature"].quantity.__name__, by_name["temperature"].tag) == ("Pressure", None)
    (out,) = Producer.Output.declarations()
    assert out.tag is fw.Tag.TENDENCY and out.quantity.parent is not None
    assert (out.quantity.__name__, out.quantity.parent.__name__, out.quantity.units) == (
        "TendencyOfPressure",
        "Pressure",
        "Pa s-1",
    )
    assert {d.name: d.source for d in Consumer.Input.declarations()} == {"density": fw.Derived(DensityFromSalt), "salt": None}
    assert [type(d.source) for d in Consumer.Update.declarations()] == [fw.FromTendency, fw.AfterIncrements]


def test_collect_picks_leaves_by_quantity_from_several_states() -> None:
    owner = fw.allocate(Owner, ops.SIZES)
    other = fw.allocate(Producer.Output, ops.SIZES)
    got = fw.collect(Producer.Input, owner, other)
    assert got.temperature is owner.temperature and got.salt is owner.salt
    assert fw.collect(Producer.Output, other).ddt_temperature is other.ddt_temperature
    view = fw.collect(Owner, owner)
    assert view is not owner and view.salt is owner.salt


def test_collect_errors() -> None:
    with pytest.raises(fw.MissingInput):
        fw.collect(Producer.Input, fw.allocate(Producer.Output, ops.SIZES))
    with pytest.raises(fw.AmbiguousSource):
        fw.collect(Producer.Input, fw.allocate(Owner, ops.SIZES), fw.allocate(Owner, ops.SIZES))
    with pytest.raises(fw.UnresolvedInput):
        Consumer.Input(salt=fw.allocate(Owner, ops.SIZES).salt)


def test_call_refuses_undeclared_aliasing() -> None:
    owner = fw.allocate(Owner, ops.SIZES)
    ops.arr(owner.salt)[...] = 1.0
    doubler, strict = Doubler(), NotInPlaceDoubler()
    plan = fw.composition([doubler, strict], ops.SIZES, input=Owner, output=Owner).begin()
    plan.run(doubler, inputs=(owner,), outputs=(owner,))
    assert np.array_equal(ops.arr(owner.salt), np.full((4, 3), 2.0))
    with pytest.raises(fw.AliasedOutput, match="NotInPlaceDoubler.salt"):
        plan.run(strict, inputs=(owner,), outputs=(owner,))
    other = fw.allocate(Owner, ops.SIZES)
    plan.run(strict, inputs=(owner,), outputs=(other,))
    assert np.array_equal(ops.arr(other.salt), np.full((4, 3), 4.0))


def test_accumulate_then_update_adds_dt_times_tendency_to_parent() -> None:
    owner = fw.allocate(Owner, ops.SIZES)
    p = Producer()
    output = fw.allocate(Producer.Output, ops.SIZES)
    composition = fw.composition([p], ops.SIZES, input=Owner, output=Owner)
    plan = composition.begin()
    plan.run(p, inputs=(owner,), outputs=(output,))
    plan.accumulate(p, output, 0.5)
    plan.update(owner, owner)
    with pytest.raises(fw.UnappliedIncrement):
        plan.update(fw.Empty(), fw.Empty())
    assert np.array_equal(ops.arr(owner.temperature), np.full((4, 3), 1.0))
    composition.begin()
    assert not any(ops.arr(value).any() for _, value in composition.increments.leaves())


def test_update_into_a_separate_output_copies_what_has_no_increment() -> None:
    owner = fw.allocate(Owner, ops.SIZES, ops.initial)
    target = fw.allocate(Owner, ops.SIZES)
    p = Producer()
    output = fw.allocate(Producer.Output, ops.SIZES)
    plan = fw.composition([p], ops.SIZES, input=Owner, output=Owner).begin()
    plan.run(p, inputs=(owner,), outputs=(output,))
    plan.accumulate(p, output, 1.0)
    plan.update(owner, target)
    assert np.array_equal(ops.arr(target.salt), ops.arr(owner.salt))
    assert np.array_equal(ops.arr(target.temperature), ops.arr(owner.temperature) + 2.0)


def test_composition_builds_providers_needs_increments_recipes_and_hooks() -> None:
    consumer = Consumer()
    composition = fw.composition([consumer], ops.SIZES, input=Owner, output=Owner)
    (provider,) = composition.providers
    assert type(provider) is DensityFromSalt and composition.needs[consumer] == (provider,)
    assert [d.quantity.__name__ for d in composition.increments.declarations()] == ["IncrementOfDensity"]
    assert composition.increment_recipes == {consumer: ()}
    assert [type(h) for h in composition.hooks] == [SaltFromDensity]
    assert composition.needs[composition.hooks[0]] == (provider,)

    owner = fw.allocate(Owner, ops.SIZES)
    ops.arr(owner.salt)[...] = 1.0
    output = fw.allocate(Consumer.Output, ops.SIZES)
    plan = composition.begin()
    plan.run(consumer, inputs=(owner,), outputs=(output,))
    provided = composition.providers[provider]
    density = ops.arr(getattr(provided, "density"))
    assert plan.produced == {provider: provided} and np.array_equal(density, np.full((4, 3), 2.0))
    plan.accumulate(consumer, output, 1.0, owner)
    plan.update(owner, owner)
    assert np.array_equal(density, np.full((4, 3), 4.0))
    assert np.array_equal(ops.arr(owner.salt), np.full((4, 3), 2.0))
    ops.arr(owner.salt)[...] = 3.0
    composition.begin().run(consumer, inputs=(owner, provided), outputs=(output,))
    assert np.array_equal(density, np.full((4, 3), 4.0))


def test_composition_runs_declared_increment_recipes() -> None:
    consumer = IncrementConsumer()
    composition = fw.composition([consumer], ops.SIZES, input=Owner, output=Owner)
    assert [type(r) for r, _ in composition.increment_recipes[consumer]] == [SaltIncrementFromDensityTendency]
    assert [d.quantity.__name__ for d in composition.increments.declarations()] == ["IncrementOfSalt"]

    owner = fw.allocate(Owner, ops.SIZES)
    ops.arr(owner.salt)[...] = 1.0
    output = fw.allocate(IncrementConsumer.Output, ops.SIZES)
    plan = composition.begin()
    plan.run(consumer, inputs=(owner,), outputs=(output,))
    plan.accumulate(consumer, output, 1.0, owner)
    plan.update(owner, owner)
    assert np.array_equal(ops.arr(owner.salt), np.full((4, 3), 16.0))


def test_composition_errors() -> None:
    consumer = Consumer()
    with pytest.raises(fw.InconsistentDerivation):
        fw.composition([consumer, OtherConsumer()], ops.SIZES, input=Owner, output=Owner)
    fw.DERIVATIONS.clear()
    fw.composition([consumer], ops.SIZES, input=Owner, output=Owner)
    with pytest.raises(fw.InconsistentDerivation, match="DensityFromSalt vs DensityFromNothing"):
        fw.composition([OtherConsumer()], ops.SIZES, input=fw.Empty, output=fw.Empty)
    with pytest.raises(fw.UnappliedIncrement):
        fw.composition([Producer()], ops.SIZES, input=fw.Empty, output=fw.Empty)
    with pytest.raises(fw.UnappliedTendency):
        fw.composition([Forgetful()], ops.SIZES, input=Owner, output=Owner)
    with pytest.raises(fw.UnappliedTendency):
        fw.composition([ForgetfulProcess()], ops.SIZES, input=Owner, output=Owner)
    with pytest.raises(fw.InconsistentUpdate):
        fw.composition([WrongHook()], ops.SIZES, input=Owner, output=Owner)
    with pytest.raises(fw.InconsistentUpdate):
        fw.composition([WrongTendency()], ops.SIZES, input=Owner, output=Owner)
    with pytest.raises(fw.InconsistentUpdate, match="neither an input nor incremented"):
        fw.composition([], ops.SIZES, input=fw.Empty, output=Owner)


def test_location_is_part_of_the_key() -> None:
    owner = fw.allocate(Owner, ops.SIZES)
    half = fw.allocate(HalfOwner, ops.SIZES)
    assert ops.arr(half.salt_ic).shape == (4, 4)
    with pytest.raises(fw.MissingInput, match="Salt@CellKHalf"):
        fw.collect(HalfOwner, owner)
    assert fw.collect(HalfOwner, owner, half).salt_ic is half.salt_ic
    assert fw.collect(Owner, owner, half).salt is owner.salt
    labels = {d.name: d.label for d in (*Owner.declarations(), *HalfOwner.declarations())}
    assert labels == {"temperature": "Pressure", "salt": "Salt@CellK", "salt_ic": "Salt@CellKHalf"}


def test_quantity_tags_are_types_with_declared_locations() -> None:
    with pytest.raises(TypeError):
        Salt()
    with pytest.raises(fw.DuplicateQuantity):
        type("Salt", (fw.Quantity,), {}, units="1")
    class Misplaced(fw.State):
        temperature: fw.CellKHalf[Pressure]

    with pytest.raises(fw.InvalidLocation, match="Pressure at CellKHalf"):
        Misplaced.declarations()
    assert fw.tendency_of(Salt).locations == Salt.locations and fw.tendency_of(Salt).parent is Salt
    assert fw.tendency_of(Salt) is fw.tendency_of(Salt) and fw.REGISTRY["TendencyOfSalt"] is fw.tendency_of(Salt)
    assert (fw.tendency_of(Pressure).standard_name, fw.tendency_of(Salt).standard_name) == ("tendency_of_air_pressure", None)
    assert fw.lookup("air_pressure") is Pressure and fw.lookup("Salt") is Salt
    with pytest.raises(fw.UnknownQuantity):
        fw.lookup("salinity")


def test_relocation_registers_one_recipe_per_edge() -> None:
    assert fw.RELOCATIONS[(Salt, fw.CellK, fw.CellKHalf)] is SaltToHalfLevels
    with pytest.raises(fw.InconsistentRelocation, match="SaltToHalfLevels vs"):

        @fw.relocation
        class SaltToHalfLevelsAgain(SaltToHalfLevels): ...

    with pytest.raises(fw.InconsistentRelocation, match="another location expected"):
        fw.relocation(DensityFromSalt)
    consumer = HalfConsumer()
    composition = fw.composition([consumer], ops.SIZES, input=Owner, output=fw.Empty)
    owner = fw.allocate(Owner, ops.SIZES)
    ops.arr(owner.salt)[...] = [[1.0, 3.0, 5.0]] * 4
    composition.begin().run(consumer, inputs=(owner,))
    (provided,) = composition.providers.values()
    assert np.array_equal(ops.arr(getattr(provided, "salt_ic")), [[1.0, 2.0, 4.0, 5.0]] * 4)
    assert "Salt@CellKHalf <- SaltToHalfLevels" in fw.dataflow(consumer)


def test_state_type_builds_a_declared_state() -> None:
    cls = fw.state_type("Dynamic", {"salt": (SField, None), "density": (DField, fw.derived_by(DensityFromSalt))})
    assert [(d.name, d.quantity.__name__, d.source) for d in cls.declarations()] == [
        ("salt", "Salt", None),
        ("density", "Density", fw.Derived(DensityFromSalt)),
    ]


def test_dataflow_lists_reads_produces_updates() -> None:
    text = fw.dataflow(Producer(), Consumer(), Doubler())
    assert "reads: Pressure, Salt@CellK" in text
    assert "produces: TendencyOfPressure" in text
    assert "Density <- DensityFromSalt" in text
    assert "updates: IncrementOfDensity <- tendency, Salt@CellK <- after increments SaltFromDensity" in text
    assert "produces: Salt@CellK (in place)" in text
