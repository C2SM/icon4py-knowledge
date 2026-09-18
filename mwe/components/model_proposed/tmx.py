from model_proposed.common.framework import Component, Read, State, Tendency
from model_proposed.common.quantities import TemperatureField, UField
import ops


class Tmx(Component["Tmx.Input", "Tmx.Output"]):
    class Input(State):
        temperature: Read[TemperatureField]
        u: Read[UField]

    class Output(State):
        ddt_temperature: Tendency[TemperatureField]
        ddt_u: Tendency[UField]

    def run(self, input: Input) -> Output:
        ops.tmx(input.temperature, input.u, self.output.ddt_temperature, self.output.ddt_u)
        return self.output
