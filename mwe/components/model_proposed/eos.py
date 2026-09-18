from model_proposed.common.framework import Component, Empty, Read, ReadWrite, State
from model_proposed.common.quantities import ExnerField, TemperatureField, ThetaVField
import ops


class ExnerThetaUpdate(Component["ExnerThetaUpdate.Input", Empty]):
    class Input(State):
        temperature: Read[TemperatureField]
        exner: ReadWrite[ExnerField]
        theta_v: ReadWrite[ThetaVField]

    Output = Empty

    def run(self, input: Input) -> Empty:
        ops.eos(input.temperature, input.exner, input.theta_v)
        return self.output
