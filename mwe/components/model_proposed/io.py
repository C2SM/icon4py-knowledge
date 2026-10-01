from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

import gt4py.next as gtx

from model_proposed import recipes
from model_proposed.common import framework as fw, quantities as qty
import ops

# The recipes for the derived output variables are here so that IO declares
# its Input like every other component. They could as well live on the
# quantity, `class U(fw.Quantity, ..., derived_by=recipes.UFromVn)`, and IO
# would only select by config.
DERIVED: dict[type[fw.Quantity], fw.Source] = {
    qty.U: fw.derived_by(recipes.UFromVn),
    qty.Temperature: fw.derived_by(recipes.TemperatureFromThetaExner),
}


class IOMonitor(fw.Component):
    # the instance's Input is the real one, built from the config: one leaf
    # per requested variable, named by its CF standard_name or class name, at
    # the quantity's first declared place; plus the time
    Input: type[fw.State] = fw.Empty
    Output = fw.Empty

    # Input is built from the config: one leaf per requested variable, named
    # by its CF standard_name or class name, at the quantity's first declared
    # place, derived where DERIVED says so; plus the time
    def __init__(self, sizes: Mapping[gtx.Dimension, int], variables: Sequence[str]) -> None:
        super().__init__(sizes)
        self.variables = tuple(variables)
        quantities = {key: fw.lookup(key) for key in self.variables}
        field: Any = fw.Field
        leaves: dict[str, Any] = {key: field[q, q.places()[0]] for key, q in quantities.items()}
        sources = {key: DERIVED[q] for key, q in quantities.items() if q in DERIVED}
        self.Input = fw.state_type("Input", leaves | {"simulation_time": datetime}, sources)
        self.dataset: list[tuple[datetime, str, ops.Array]] = []

    def run(self, input: fw.State, out: fw.Empty | None = None) -> fw.Empty:
        time: datetime = getattr(input, "simulation_time")
        for key in self.variables:
            field: fw.Field[Any, Any] = getattr(input, key)
            self.dataset.append((time, key, ops.arr(field.data).copy()))
        return self.buffers(out)
