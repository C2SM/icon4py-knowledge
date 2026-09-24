from typing import Annotated

import numpy as np
import pytest
from icon4py.model.common import field_type_aliases as fa, type_alias as ta

import ops
from model_proposed.common import framework as fw

type TField = Annotated[fa.CellKField[ta.wpfloat], fw.quantity("test_temperature", units="K")]
type SField = Annotated[fa.CellKField[ta.wpfloat], fw.quantity("test_salt", units="1")]
type DField = Annotated[fa.CellKField[ta.wpfloat], fw.quantity("test_density", units="kg m-3")]


class Owner(fw.State):
    temperature: TField
    salt: SField


class Inc(fw.State):
    temperature: fw.Increment[TField]


class Producer(fw.Process["Producer.Input", "Producer.Output"]):
    class Input(fw.State):
        temperature: fw.Read[fw.Now[TField]]
        salt: fw.ReadWrite[SField]

    class Output(fw.State):
        ddt_temperature: fw.Tendency[TField]

    class Update(fw.State):
        temperature: fw.Increment[TField] = fw.from_tendency()

    def run(self, input: Input) -> Output:
        ops.arr(self.output.ddt_temperature)[...] = 2.0
        return self.output


class Forgetful(fw.Component["Forgetful.Input", "Forgetful.Output"]):
    class Input(fw.State):
        pass

    class Output(fw.State):
        ddt_temperature: fw.Tendency[TField]


class ForgetfulProcess(fw.Process["Forgetful.Input", "Forgetful.Output"]):
    Input = Forgetful.Input
    Output = Forgetful.Output


class DensityFromSalt(fw.Recipe["DensityFromSalt.Input", "DensityFromSalt.Output"]):
    class Input(fw.State):
        salt: fw.Read[SField]

    class Output(fw.State):
        density: DField

    def run(self, input: Input) -> Output:
        ops.arr(self.output.density)[...] = 2.0 * ops.arr(input.salt)
        return self.output


class DensityFromNothing(fw.Recipe["DensityFromNothing.Input", "DensityFromNothing.Output"]):
    class Input(fw.State):
        pass

    class Output(fw.State):
        density: DField

    def run(self, input: Input) -> Output:
        return self.output


class SaltFromDensity(fw.Component["SaltFromDensity.Input", fw.Empty]):
    class Input(fw.State):
        density: fw.Read[DField]
        salt: fw.ReadWrite[SField]

    Output = fw.Empty

    def run(self, input: Input) -> fw.Empty:
        ops.arr(input.salt)[...] = 0.5 * ops.arr(input.density)
        return self.output


class SaltIncrementFromDensityTendency(fw.Recipe["SaltIncrementFromDensityTendency.Input", "SaltIncrementFromDensityTendency.Output"]):
    class Input(fw.State):
        ddt_density: fw.Read[fw.Tendency[DField]]

    class Output(fw.State):
        salt: fw.Increment[SField]

    def run(self, input: Input) -> Output:
        ops.arr(self.output.salt)[...] = 5.0 * ops.arr(input.ddt_density)
        return self.output


class Consumer(fw.Process["Consumer.Input", "Consumer.Output"]):
    class Input(fw.State):
        density: fw.Read[DField] = fw.derived_by(DensityFromSalt)
        salt: fw.ReadWrite[SField]

    class Output(fw.State):
        ddt_density: fw.Tendency[DField]

    class Update(fw.State):
        density: fw.Increment[DField] = fw.from_tendency()
        salt: fw.ReadWrite[SField] = fw.after_apply(SaltFromDensity)

    def run(self, input: Input) -> Output:
        ops.arr(self.output.ddt_density)[...] = ops.arr(input.density)
        return self.output


class IncrementConsumer(fw.Process["IncrementConsumer.Input", "IncrementConsumer.Output"]):
    class Input(fw.State):
        salt: fw.Read[SField]

    class Output(fw.State):
        ddt_density: fw.Tendency[DField]

    class Update(fw.State):
        salt: fw.Increment[SField] = fw.derived_by(SaltIncrementFromDensityTendency)

    def run(self, input: Input) -> Output:
        ops.arr(self.output.ddt_density)[...] = 3.0
        return self.output


class OtherConsumer(fw.Component["OtherConsumer.Input", fw.Empty]):
    class Input(fw.State):
        density: fw.Read[DField] = fw.derived_by(DensityFromNothing)

    Output = fw.Empty


class WrongHook(fw.Process["WrongHook.Input", fw.Empty]):
    class Input(fw.State):
        density: fw.Read[DField] = fw.derived_by(DensityFromSalt)

    Output = fw.Empty

    class Update(fw.State):
        density: fw.ReadWrite[DField] = fw.after_apply(SaltFromDensity)


class WrongTendency(fw.Process["WrongTendency.Input", fw.Empty]):
    class Input(fw.State):
        pass

    Output = fw.Empty

    class Update(fw.State):
        salt: fw.Increment[SField] = fw.from_tendency()


def test_declarations_carry_quantity_intent_level_and_derived_tendency() -> None:
    by_name = {d.name: d for d in Producer.Input.declarations()}
    t = by_name["temperature"]
    assert (t.quantity.name, t.intent, t.level) == ("test_temperature", fw.Intent.READ, fw.Level.NOW)
    assert (by_name["salt"].intent, by_name["salt"].level) == (fw.Intent.READWRITE, None)
    (out,) = Producer.Output.declarations()
    assert out.quantity.of is not None
    assert (out.quantity.name, out.quantity.of.name, out.quantity.units) == (
        "tendency_of_test_temperature",
        "test_temperature",
        "K s-1",
    )
    assert {d.name: d.recipe for d in Consumer.Input.declarations()} == {"density": DensityFromSalt, "salt": None}
    assert [type(d.marker) for d in Consumer.Update.declarations()] == [fw.FromTendency, fw.AfterApply]


def test_collect_inputs_resolves_pair_levels_and_plain_states() -> None:
    pair = fw.TimeStepPair(fw.allocate(Owner, ops.SIZES, ops.initial), fw.allocate(Owner, ops.SIZES))
    plain = fw.allocate(Owner, ops.SIZES)
    p = Producer(fw.allocate(Producer.Output, ops.SIZES))
    got = p.collect_inputs(pair, plain)
    assert got.temperature is pair.now.temperature and got.salt is plain.salt


def test_collect_inputs_errors() -> None:
    p = Producer(fw.allocate(Producer.Output, ops.SIZES))
    with pytest.raises(fw.MissingInput):
        p.collect_inputs(fw.allocate(Owner, ops.SIZES))
    with pytest.raises(fw.AmbiguousSource):
        p.collect_inputs(
            fw.TimeStepPair(fw.allocate(Owner, ops.SIZES), fw.allocate(Owner, ops.SIZES)),
            fw.allocate(Owner, ops.SIZES),
            fw.allocate(Owner, ops.SIZES),
        )
    with pytest.raises(fw.UnresolvedInput):
        Consumer.Input(salt=fw.allocate(Owner, ops.SIZES).salt)


def test_accumulate_then_apply_adds_dt_times_tendency_to_parent() -> None:
    owner, inc = fw.allocate(Owner, ops.SIZES), fw.allocate(Inc, ops.SIZES)
    p = Producer(fw.allocate(Producer.Output, ops.SIZES))
    p.run(p.collect_inputs(fw.TimeStepPair(owner, fw.allocate(Owner, ops.SIZES)), fw.allocate(Owner, ops.SIZES)))
    p.accumulate(inc, dt=0.5)
    p.apply(inc, owner)
    with pytest.raises(fw.UnappliedIncrement):
        p.apply(inc, fw.Empty())
    assert np.array_equal(ops.arr(owner.temperature), np.full((4, 3), 1.0))
    fw.zero(inc)
    assert not ops.arr(inc.temperature).any()


def test_resolve_builds_providers_increments_updates_and_hooks() -> None:
    consumer = Consumer(fw.allocate(Consumer.Output, ops.SIZES))
    resolution = fw.resolve([consumer], ops.SIZES, targets=Owner)
    assert [type(p) for p in resolution.providers] == [DensityFromSalt]
    assert [d.quantity.name for d in resolution.increments.declarations()] == ["increment_of_test_density"]
    assert resolution.updates == {consumer: ()}
    assert [type(h) for h in resolution.after_apply] == [SaltFromDensity]

    owner = fw.allocate(Owner, ops.SIZES)
    ops.arr(owner.salt)[...] = 1.0
    produced = resolution.run_providers(owner)
    density = resolution.providers[0].output.density
    assert produced == (resolution.providers[0].output,) and np.array_equal(ops.arr(density), np.full((4, 3), 2.0))
    assert resolution.run_providers(owner, *produced) == ()
    consumer.run(consumer.collect_inputs(owner, *produced))
    consumer.accumulate(resolution.increments, 1.0, *resolution.run_updates(consumer, owner))
    consumer.apply(resolution.increments, owner, *produced)
    for hook in resolution.after_apply:
        hook.run(hook.collect_inputs(owner, *produced))
    assert np.array_equal(ops.arr(density), np.full((4, 3), 4.0))
    assert np.array_equal(ops.arr(owner.salt), np.full((4, 3), 2.0))


def test_resolve_runs_declared_increment_recipes() -> None:
    consumer = IncrementConsumer(fw.allocate(IncrementConsumer.Output, ops.SIZES))
    resolution = fw.resolve([consumer], ops.SIZES, targets=Owner)
    assert [type(r) for r in resolution.updates[consumer]] == [SaltIncrementFromDensityTendency]
    assert [d.quantity.name for d in resolution.increments.declarations()] == ["increment_of_test_salt"]

    owner = fw.allocate(Owner, ops.SIZES)
    ops.arr(owner.salt)[...] = 1.0
    consumer.run(consumer.collect_inputs(owner))
    computed = resolution.run_updates(consumer, owner)
    consumer.accumulate(resolution.increments, 1.0, *computed)
    consumer.apply(resolution.increments, owner)
    assert np.array_equal(ops.arr(owner.salt), np.full((4, 3), 16.0))


def test_resolve_errors() -> None:
    consumer = Consumer(fw.allocate(Consumer.Output, ops.SIZES))
    with pytest.raises(fw.InconsistentDerivation):
        fw.resolve([consumer, OtherConsumer(fw.Empty())], ops.SIZES, targets=Owner)
    with pytest.raises(fw.UnappliedIncrement):
        fw.resolve([Producer(fw.allocate(Producer.Output, ops.SIZES))], ops.SIZES, targets=fw.Empty)
    with pytest.raises(fw.UnappliedTendency):
        fw.resolve([Forgetful(fw.allocate(Forgetful.Output, ops.SIZES))], ops.SIZES, targets=Owner)
    with pytest.raises(fw.UnappliedTendency):
        fw.resolve([ForgetfulProcess(fw.allocate(Forgetful.Output, ops.SIZES))], ops.SIZES, targets=Owner)
    with pytest.raises(fw.InconsistentUpdate):
        fw.resolve([WrongHook(fw.Empty())], ops.SIZES, targets=Owner)
    with pytest.raises(fw.InconsistentUpdate):
        fw.resolve([WrongTendency(fw.Empty())], ops.SIZES, targets=Owner)


def test_state_type_builds_a_declared_state() -> None:
    cls = fw.state_type("Dynamic", {"salt": (fw.Read[SField], None), "density": (fw.Read[DField], fw.derived_by(DensityFromSalt))})
    assert [(d.name, d.quantity.name, d.recipe) for d in cls.declarations()] == [
        ("salt", "test_salt", None),
        ("density", "test_density", DensityFromSalt),
    ]


def test_dataflow_lists_reads_writes_produces_updates() -> None:
    text = fw.dataflow(Producer(fw.allocate(Producer.Output, ops.SIZES)), Consumer(fw.allocate(Consumer.Output, ops.SIZES)))
    assert "reads: test_temperature@now" in text
    assert "writes: test_salt" in text
    assert "produces: tendency_of_test_temperature" in text
    assert "test_density <- DensityFromSalt" in text
    assert "updates: increment_of_test_density <- tendency, test_salt <- after apply SaltFromDensity" in text
