from datetime import datetime

from model_proposed.common import framework as fw, quantities as qty
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


class IOMonitor(fw.Component["IOMonitor.Input", fw.Empty]):
    class Input(fw.State):
        air_density: fw.Read[qty.RhoField]
        exner_function: fw.Read[qty.ExnerField]
        virtual_potential_temperature: fw.Read[qty.ThetaVField]
        upward_air_velocity: fw.Read[qty.WField]
        normal_velocity: fw.Read[qty.VnField]
        eastward_wind: fw.Read[qty.UField]
        temperature: fw.Read[qty.TemperatureField]
        simulation_time: fw.Read[qty.SimulationTime]

    Output = fw.Empty

    def __init__(self) -> None:
        super().__init__(fw.Empty())
        self.dataset: list[tuple[datetime, str, ops.Array]] = []

    def run(self, input: Input) -> fw.Empty:
        for name in OUTPUT_VARIABLES:
            self.dataset.append((input.simulation_time, name, ops.arr(getattr(input, name)).copy()))
        return self.output
