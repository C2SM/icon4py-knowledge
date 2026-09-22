from typing import Annotated

import numpy as np
import pytest
from icon4py.model.common import field_type_aliases as fa, type_alias as ta

import ops
from model_proposed.common import framework as fw

type TField = Annotated[fa.CellKField[ta.wpfloat], fw.quantity("test_temperature", units="K")]
type SField = Annotated[fa.CellKField[ta.wpfloat], fw.quantity("test_salt", units="1")]


class Owner(fw.State):
    temperature: TField
    salt: SField


class Inc(fw.State):
    temperature: fw.Increment[TField]


class Producer(fw.Component["Producer.Input", "Producer.Output"]):
    class Input(fw.State):
        temperature: fw.Read[fw.Now[TField]]
        salt: fw.ReadWrite[SField]

    class Output(fw.State):
        ddt_temperature: fw.Tendency[TField]

    def run(self, input: Input) -> Output:
        ops.arr(self.output.ddt_temperature)[...] = 2.0
        return self.output


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


def test_gather_resolves_pair_levels_and_plain_states() -> None:
    pair = fw.TimeStepPair(fw.allocate(Owner, ops.SIZES, ops.initial), fw.allocate(Owner, ops.SIZES))
    plain = fw.allocate(Owner, ops.SIZES)
    p = Producer(fw.allocate(Producer.Output, ops.SIZES))
    got = p.gather(pair, plain)
    assert got.temperature is pair.now.temperature and got.salt is plain.salt


def test_gather_errors() -> None:
    p = Producer(fw.allocate(Producer.Output, ops.SIZES))
    with pytest.raises(fw.MissingInput):
        p.gather(fw.allocate(Owner, ops.SIZES))
    with pytest.raises(fw.AmbiguousSource):
        p.gather(
            fw.TimeStepPair(fw.allocate(Owner, ops.SIZES), fw.allocate(Owner, ops.SIZES)),
            fw.allocate(Owner, ops.SIZES),
            fw.allocate(Owner, ops.SIZES),
        )


def test_accumulate_then_apply_adds_dt_times_tendency_to_parent() -> None:
    owner, inc = fw.allocate(Owner, ops.SIZES), fw.allocate(Inc, ops.SIZES)
    p = Producer(fw.allocate(Producer.Output, ops.SIZES))
    p.run(p.gather(fw.TimeStepPair(owner, fw.allocate(Owner, ops.SIZES)), fw.allocate(Owner, ops.SIZES)))
    p.accumulate(inc, dt=0.5)
    p.apply(inc, owner)
    p.apply(inc, fw.Empty())
    assert np.array_equal(ops.arr(owner.temperature), np.full((4, 3), 1.0))
    fw.zero(inc)
    assert not ops.arr(inc.temperature).any()


def test_dataflow_lists_reads_writes_produces() -> None:
    text = fw.dataflow(Producer(fw.allocate(Producer.Output, ops.SIZES)))
    assert "reads: test_temperature@now" in text
    assert "writes: test_salt" in text
    assert "produces: tendency_of_test_temperature" in text
