from collections.abc import Sequence
from datetime import datetime
from typing import Any

from model_proposed import recipes
from model_proposed.common import framework as fw, quantities as qty
import ops

VARIABLES: dict[str, tuple[Any, fw.Derived | None]] = {
    "air_density": (qty.RhoField, None),
    "exner_function": (qty.ExnerField, None),
    "virtual_potential_temperature": (qty.ThetaVField, None),
    "upward_air_velocity": (qty.WField, None),
    "normal_velocity": (qty.VnField, None),
    "eastward_wind": (qty.UField, fw.derived_by(recipes.UFromVn)),
    "temperature": (qty.TemperatureField, fw.derived_by(recipes.TemperatureFromThetaExner)),
}


class IOMonitor(fw.Component):
    Output = fw.Empty

    def __init__(self, variables: Sequence[str]) -> None:
        self.variables = tuple(variables)
        self.Input = fw.state_type(
            "Input",
            {name: VARIABLES[name] for name in self.variables} | {"simulation_time": (qty.SimulationTime, None)},
        )
        self.dataset: list[tuple[datetime, str, ops.Array]] = []

    def run(self, input: fw.State, output: fw.Empty) -> None:
        time = getattr(input, "simulation_time")
        for name in self.variables:
            self.dataset.append((time, name, ops.arr(getattr(input, name)).copy()))
