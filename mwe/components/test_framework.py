import numpy as np
import pytest

import ops
from model_proposed.common import framework as fw


class Temperature(fw.Quantity, name="test_temperature", units="K", locations=(fw.CellK,)): ...
class Salt(fw.Quantity, name="test_salt", units="1", locations=(fw.CellK, fw.CellKHalf)): ...
class Density(fw.Quantity, name="test_density", units="kg m-3"): ...


type TField = fw.CellK[Temperature]
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


def test_declarations_carry_quantity_tag_and_marker() -> None:
    by_name = {d.name: d for d in Producer.Input.declarations()}
    assert (by_name["temperature"].quantity.name, by_name["temperature"].tag) == ("test_temperature", None)
    (out,) = Producer.Output.declarations()
    assert out.tag is fw.Tag.TENDENCY and out.quantity.parent is not None
    assert (out.quantity.name, out.quantity.parent.name, out.quantity.units) == (
        "tendency_of_test_temperature",
        "test_temperature",
        "K s-1",
    )
    assert {d.name: d.recipe for d in Consumer.Input.declarations()} == {"density": DensityFromSalt, "salt": None}
    assert [type(d.marker) for d in Consumer.Update.declarations()] == [fw.FromTendency, fw.AfterIncrements]


def test_collect_picks_leaves_by_quantity_from_several_states() -> None:
    owner = fw.allocate(Owner, ops.SIZES)
    other = fw.allocate(Producer.Output, ops.SIZES)
    p = Producer()
    got = p.collect_inputs(owner, other)
    assert got.temperature is owner.temperature and got.salt is owner.salt
    assert p.collect_output(other).ddt_temperature is other.ddt_temperature
    view = fw.collect(Owner, owner)
    assert view is not owner and view.salt is owner.salt


def test_collect_errors() -> None:
    p = Producer()
    with pytest.raises(fw.MissingInput):
        p.collect_inputs(fw.allocate(Producer.Output, ops.SIZES))
    with pytest.raises(fw.AmbiguousSource):
        p.collect_inputs(fw.allocate(Owner, ops.SIZES), fw.allocate(Owner, ops.SIZES))
    with pytest.raises(fw.UnresolvedInput):
        Consumer.Input(salt=fw.allocate(Owner, ops.SIZES).salt)


def test_call_refuses_undeclared_aliasing() -> None:
    owner = fw.allocate(Owner, ops.SIZES)
    ops.arr(owner.salt)[...] = 1.0
    doubler = Doubler()
    doubler(doubler.collect_inputs(owner), doubler.collect_output(owner))
    assert np.array_equal(ops.arr(owner.salt), np.full((4, 3), 2.0))
    strict = NotInPlaceDoubler()
    with pytest.raises(fw.AliasedOutput, match="NotInPlaceDoubler.salt"):
        strict(strict.collect_inputs(owner), strict.collect_output(owner))
    other = fw.allocate(Owner, ops.SIZES)
    strict(strict.collect_inputs(owner), strict.collect_output(other))
    assert np.array_equal(ops.arr(other.salt), np.full((4, 3), 4.0))


def test_accumulate_then_update_adds_dt_times_tendency_to_parent() -> None:
    owner = fw.allocate(Owner, ops.SIZES)
    p = Producer()
    output = fw.allocate(Producer.Output, ops.SIZES)
    resolution = fw.resolve([p], ops.SIZES, input=Owner, output=Owner)
    p(p.collect_inputs(owner), output)
    p.accumulate(resolution.increments, 0.5, output)
    resolution.update(owner, owner)
    with pytest.raises(fw.UnappliedIncrement):
        resolution.update(fw.Empty(), fw.Empty())
    assert np.array_equal(ops.arr(owner.temperature), np.full((4, 3), 1.0))
    fw.zero(resolution.increments)
    assert not any(ops.arr(value).any() for _, value in resolution.increments.leaves())


def test_update_into_a_separate_output_copies_what_has_no_increment() -> None:
    owner = fw.allocate(Owner, ops.SIZES, ops.initial)
    target = fw.allocate(Owner, ops.SIZES)
    p = Producer()
    output = fw.allocate(Producer.Output, ops.SIZES)
    resolution = fw.resolve([p], ops.SIZES, input=Owner, output=Owner)
    p(p.collect_inputs(owner), output)
    p.accumulate(resolution.increments, 1.0, output)
    resolution.update(owner, target)
    assert np.array_equal(ops.arr(target.salt), ops.arr(owner.salt))
    assert np.array_equal(ops.arr(target.temperature), ops.arr(owner.temperature) + 2.0)


def test_resolve_builds_providers_increments_recipes_and_hooks() -> None:
    consumer = Consumer()
    resolution = fw.resolve([consumer], ops.SIZES, input=Owner, output=Owner)
    assert [type(p) for p, _ in resolution.providers] == [DensityFromSalt]
    assert [d.quantity.name for d in resolution.increments.declarations()] == ["increment_of_test_density"]
    assert resolution.increment_recipes == {consumer: ()}
    assert [type(h) for h in resolution.hooks] == [SaltFromDensity]

    owner = fw.allocate(Owner, ops.SIZES)
    ops.arr(owner.salt)[...] = 1.0
    produced = resolution.run_providers(owner)
    provided = resolution.providers[0][1]
    density = ops.arr(getattr(provided, "density"))
    assert produced == (provided,) and np.array_equal(density, np.full((4, 3), 2.0))
    assert resolution.run_providers(owner, *produced) == ()
    output = fw.allocate(Consumer.Output, ops.SIZES)
    consumer(consumer.collect_inputs(owner, *produced), output)
    consumer.accumulate(resolution.increments, 1.0, output, *resolution.run_increment_recipes(consumer, output, owner))
    resolution.update(owner, owner, *produced)
    assert np.array_equal(density, np.full((4, 3), 4.0))
    assert np.array_equal(ops.arr(owner.salt), np.full((4, 3), 2.0))


def test_resolve_runs_declared_increment_recipes() -> None:
    consumer = IncrementConsumer()
    resolution = fw.resolve([consumer], ops.SIZES, input=Owner, output=Owner)
    assert [type(r) for r, _ in resolution.increment_recipes[consumer]] == [SaltIncrementFromDensityTendency]
    assert [d.quantity.name for d in resolution.increments.declarations()] == ["increment_of_test_salt"]

    owner = fw.allocate(Owner, ops.SIZES)
    ops.arr(owner.salt)[...] = 1.0
    output = fw.allocate(IncrementConsumer.Output, ops.SIZES)
    consumer(consumer.collect_inputs(owner), output)
    computed = resolution.run_increment_recipes(consumer, output, owner)
    consumer.accumulate(resolution.increments, 1.0, output, *computed)
    resolution.update(owner, owner)
    assert np.array_equal(ops.arr(owner.salt), np.full((4, 3), 16.0))


def test_resolve_errors() -> None:
    consumer = Consumer()
    with pytest.raises(fw.InconsistentDerivation):
        fw.resolve([consumer, OtherConsumer()], ops.SIZES, input=Owner, output=Owner)
    fw.DERIVATIONS.clear()
    fw.resolve([consumer], ops.SIZES, input=Owner, output=Owner)
    with pytest.raises(fw.InconsistentDerivation, match="DensityFromSalt vs DensityFromNothing"):
        fw.resolve([OtherConsumer()], ops.SIZES, input=fw.Empty, output=fw.Empty)
    with pytest.raises(fw.UnappliedIncrement):
        fw.resolve([Producer()], ops.SIZES, input=fw.Empty, output=fw.Empty)
    with pytest.raises(fw.UnappliedTendency):
        fw.resolve([Forgetful()], ops.SIZES, input=Owner, output=Owner)
    with pytest.raises(fw.UnappliedTendency):
        fw.resolve([ForgetfulProcess()], ops.SIZES, input=Owner, output=Owner)
    with pytest.raises(fw.InconsistentUpdate):
        fw.resolve([WrongHook()], ops.SIZES, input=Owner, output=Owner)
    with pytest.raises(fw.InconsistentUpdate):
        fw.resolve([WrongTendency()], ops.SIZES, input=Owner, output=Owner)
    with pytest.raises(fw.InconsistentUpdate, match="neither an input nor incremented"):
        fw.resolve([], ops.SIZES, input=fw.Empty, output=Owner)


def test_location_is_part_of_the_key() -> None:
    owner = fw.allocate(Owner, ops.SIZES)
    half = fw.allocate(HalfOwner, ops.SIZES)
    assert ops.arr(half.salt_ic).shape == (4, 4)
    with pytest.raises(fw.MissingInput, match="test_salt@CellKHalf"):
        fw.collect(HalfOwner, owner)
    assert fw.collect(HalfOwner, owner, half).salt_ic is half.salt_ic
    assert fw.collect(Owner, owner, half).salt is owner.salt
    labels = {d.name: d.label for d in (*Owner.declarations(), *HalfOwner.declarations())}
    assert labels == {"temperature": "test_temperature", "salt": "test_salt@CellK", "salt_ic": "test_salt@CellKHalf"}


def test_quantity_tags_are_types_with_declared_locations() -> None:
    with pytest.raises(TypeError):
        Salt()
    with pytest.raises(fw.DuplicateQuantity):

        class Again(fw.Quantity, name="test_salt", units="1"): ...

    class Misplaced(fw.State):
        temperature: fw.CellKHalf[Temperature]

    with pytest.raises(fw.InvalidLocation, match="test_temperature at CellKHalf"):
        Misplaced.declarations()
    assert fw.tendency_of(Salt).locations == Salt.locations and fw.tendency_of(Salt).parent is Salt
    assert fw.tendency_of(Salt) is fw.tendency_of(Salt) and fw.REGISTRY["tendency_of_test_salt"] is fw.tendency_of(Salt)


def test_relocation_registers_one_recipe_per_edge() -> None:
    assert fw.RELOCATIONS[(Salt, fw.CellK, fw.CellKHalf)] is SaltToHalfLevels
    with pytest.raises(fw.InconsistentRelocation, match="SaltToHalfLevels vs"):

        @fw.relocation
        class SaltToHalfLevelsAgain(SaltToHalfLevels): ...

    with pytest.raises(fw.InconsistentRelocation, match="another location expected"):
        fw.relocation(DensityFromSalt)
    consumer = HalfConsumer()
    resolution = fw.resolve([consumer], ops.SIZES, input=Owner, output=fw.Empty)
    owner = fw.allocate(Owner, ops.SIZES)
    ops.arr(owner.salt)[...] = [[1.0, 3.0, 5.0]] * 4
    (produced,) = resolution.run_providers(owner)
    assert np.array_equal(ops.arr(consumer.collect_inputs(owner, produced).salt_ic), [[1.0, 2.0, 4.0, 5.0]] * 4)
    assert "test_salt@CellKHalf <- SaltToHalfLevels" in fw.dataflow(consumer)


def test_state_type_builds_a_declared_state() -> None:
    cls = fw.state_type("Dynamic", {"salt": (SField, None), "density": (DField, fw.derived_by(DensityFromSalt))})
    assert [(d.name, d.quantity.name, d.recipe) for d in cls.declarations()] == [
        ("salt", "test_salt", None),
        ("density", "test_density", DensityFromSalt),
    ]


def test_dataflow_lists_reads_produces_updates() -> None:
    text = fw.dataflow(Producer(), Consumer(), Doubler())
    assert "reads: test_temperature, test_salt@CellK" in text
    assert "produces: tendency_of_test_temperature" in text
    assert "test_density <- DensityFromSalt" in text
    assert "updates: increment_of_test_density <- tendency, test_salt@CellK <- after increments SaltFromDensity" in text
    assert "produces: test_salt@CellK (in place)" in text
