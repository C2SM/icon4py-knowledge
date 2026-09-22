from model_proposed.common.framework import Component, Read, State, Tendency
from model_proposed.common.quantities import TemperatureField, UField
import ops


class TmxComponent(Component["TmxComponent.Input", "TmxComponent.Output"]):
    class Input(State):
        temperature: Read[TemperatureField]
        u: Read[UField]

    class Output(State):
        tend_temperature: Tendency[TemperatureField]
        tend_u: Tendency[UField]

    def run(self, input: Input) -> Output:
        ops.tmx(input.temperature, input.u, self.output.tend_temperature, self.output.tend_u)
        return self.output
