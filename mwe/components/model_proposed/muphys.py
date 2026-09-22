from model_proposed.common.framework import Component, Read, State, Tendency
from model_proposed.common.quantities import PrecipField, QvField, TemperatureField
import ops


class MuphysComponent(Component["MuphysComponent.Input", "MuphysComponent.Output"]):
    class Input(State):
        te: Read[TemperatureField]
        qv: Read[QvField]

    class Output(State):
        tend_temperature: Tendency[TemperatureField]
        tend_qv: Tendency[QvField]
        pflx: PrecipField

    def run(self, input: Input) -> Output:
        ops.muphys(input.te, input.qv, self.output.tend_temperature, self.output.tend_qv, self.output.pflx)
        return self.output
