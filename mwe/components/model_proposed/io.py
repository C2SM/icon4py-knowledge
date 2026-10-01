from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any

import gt4py.next as gtx

from model_proposed.common import framework as fw
import ops


class IOMonitor(fw.Component):
    # the instance's Input is the real one, built from the config: one leaf
    # per requested variable, named by its CF standard_name or class name, at
    # the quantity's first declared place; plus the time
    Input: type[fw.State] = fw.Empty
    Output = fw.Empty

    def __init__(self, sizes: Mapping[gtx.Dimension, int], variables: Sequence[str]) -> None:
        super().__init__(sizes)
        self.variables = tuple(variables)
        leaves: dict[str, Any] = {key: self._leaf(key) for key in self.variables}
        self.Input = fw.state_type("IOMonitor.Input", leaves | {"simulation_time": datetime})
        self.dataset: list[tuple[datetime, str, ops.Array]] = []

    @staticmethod
    def _leaf(key: str) -> Any:
        quantity = fw.lookup(key)
        field: Any = fw.Field
        return field[quantity, quantity.places()[0]]

    def run(self, input: fw.State, out: fw.Empty | None = None) -> fw.Empty:
        time: datetime = getattr(input, "simulation_time")
        for key in self.variables:
            field: fw.Field[Any, Any] = getattr(input, key)
            self.dataset.append((time, key, ops.arr(field.data).copy()))
        return self.buffers(out)
