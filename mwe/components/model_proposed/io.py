from datetime import datetime

from model_proposed.common.framework import Component, Empty, Read, State, Tendency
from model_proposed.common.quantities import PrecipField, SimulationTime, TemperatureField
import ops


class Writer(Component["Writer.Input", Empty]):
    class Input(State):
        temperature: Read[TemperatureField]
        precip: Read[PrecipField]
        ddt_temperature_muphys: Read[Tendency[TemperatureField]]
        simulation_time: Read[SimulationTime]

    Output = Empty

    def __init__(self) -> None:
        super().__init__(Empty())
        self.records: list[tuple[datetime, ops.Array]] = []

    def run(self, input: Input) -> Empty:
        for f in (input.temperature, input.precip, input.ddt_temperature_muphys):
            self.records.append((input.simulation_time, ops.arr(f).copy()))
        return self.output
