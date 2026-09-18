from model_proposed.common.framework import Component, Read, State, Tendency
from model_proposed.common.quantities import PrecipField, QvField, TemperatureField
import ops


class Muphys(Component["Muphys.Input", "Muphys.Output"]):
    class Input(State):
        temperature: Read[TemperatureField]
        qv: Read[QvField]

    class Output(State):
        ddt_temperature: Tendency[TemperatureField]
        ddt_qv: Tendency[QvField]
        precip: PrecipField

    def run(self, input: Input) -> Output:
        ops.muphys(input.temperature, input.qv, self.output.ddt_temperature, self.output.ddt_qv, self.output.precip)
        return self.output
