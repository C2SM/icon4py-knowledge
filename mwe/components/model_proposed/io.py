from collections.abc import Sequence
from datetime import datetime
from typing import Any

from model_proposed import recipes
from model_proposed.common import framework as fw, quantities as qty
import ops

# The recipes for derived output variables sit here so that IO declares its
# Input like every other component does. They could as well live on the
# quantity as its default source, `class U(fw.Quantity, ...,
# derived_by=recipes.UFromVn)`, and IO would then only name quantities.
DERIVED: dict[type[fw.Quantity], fw.Derived] = {
    qty.U: fw.derived_by(recipes.UFromVn),
    qty.Temperature: fw.derived_by(recipes.TemperatureFromThetaExner),
}


def _leaf(key: str) -> tuple[Any, fw.Derived | None]:
    quantity = fw.lookup(key)
    assert quantity.locations is not None
    return (quantity.locations[0][quantity], DERIVED.get(quantity))


class IOMonitor(fw.Component):
    Output = fw.Empty

    def __init__(self, variables: Sequence[str]) -> None:
        self.variables = tuple(variables)
        self.Input = fw.state_type(
            "Input", {key: _leaf(key) for key in self.variables} | {"simulation_time": (qty.SimulationTimeValue, None)}
        )
        self.dataset: list[tuple[datetime, str, ops.Array]] = []

    def run(self, input: fw.State, output: fw.Empty) -> None:
        time = getattr(input, "simulation_time")
        for key in self.variables:
            self.dataset.append((time, key, ops.arr(getattr(input, key)).copy()))
