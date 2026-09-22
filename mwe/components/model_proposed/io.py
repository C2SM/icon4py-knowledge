from datetime import datetime

from model_proposed.common.framework import Component, Empty, Read, State
from model_proposed.common.quantities import (
    ExnerField,
    RhoField,
    SimulationTime,
    TemperatureField,
    ThetaVField,
    UField,
    VnField,
    WField,
)
import ops

OUTPUT_VARIABLES = (
    "air_density",
    "exner_function",
    "virtual_potential_temperature",
    "upward_air_velocity",
    "normal_velocity",
    "eastward_wind",
    "temperature",
)


class IOMonitor(Component["IOMonitor.Input", Empty]):
    class Input(State):
        air_density: Read[RhoField]
        exner_function: Read[ExnerField]
        virtual_potential_temperature: Read[ThetaVField]
        upward_air_velocity: Read[WField]
        normal_velocity: Read[VnField]
        eastward_wind: Read[UField]
        temperature: Read[TemperatureField]
        simulation_time: Read[SimulationTime]

    Output = Empty

    def __init__(self) -> None:
        super().__init__(Empty())
        self.dataset: list[tuple[datetime, str, ops.Array]] = []

    def run(self, input: Input) -> Empty:
        for name in OUTPUT_VARIABLES:
            self.dataset.append((input.simulation_time, name, ops.arr(getattr(input, name)).copy()))
        return self.output
