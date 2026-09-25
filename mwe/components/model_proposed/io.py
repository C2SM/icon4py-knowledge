from collections.abc import Sequence
from datetime import datetime
from typing import Any

from model_proposed import recipes
from model_proposed.common import framework as fw, quantities as qty
import ops

VARIABLES: dict[str, tuple[Any, fw.Derived | None]] = {
    "air_density": (fw.Read[qty.RhoField], None),
    "exner_function": (fw.Read[qty.ExnerField], None),
    "virtual_potential_temperature": (fw.Read[qty.ThetaVField], None),
    "upward_air_velocity": (fw.Read[qty.WField], None),
    "normal_velocity": (fw.Read[qty.VnField], None),
    "eastward_wind": (fw.Read[qty.UField], fw.derived_by(recipes.UFromVn)),
    "temperature": (fw.Read[qty.TemperatureField], fw.derived_by(recipes.TemperatureFromThetaExner)),
}


class IOMonitor(fw.Component):
    Output = fw.Empty
    output: fw.Empty

    def __init__(self, variables: Sequence[str]) -> None:
        super().__init__(fw.Empty())
        self.variables = tuple(variables)
        self.Input = fw.state_type(
            "Input",
            {name: VARIABLES[name] for name in self.variables} | {"simulation_time": (fw.Read[qty.SimulationTime], None)},
        )
        self.dataset: list[tuple[datetime, str, ops.Array]] = []


    def run(self, input: fw.State) -> fw.Empty:
        time = getattr(input, "simulation_time")
        for name in self.variables:
            self.dataset.append((time, name, ops.arr(getattr(input, name)).copy()))
        return self.output
