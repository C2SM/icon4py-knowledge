from model_proposed.common.framework import Component, Empty, Increment, Read, ReadWrite, State
from model_proposed.common.quantities import ExnerField, TemperatureField, ThetaVField
import ops


class ExnerThetaUpdate(Component["ExnerThetaUpdate.Input", Empty]):
    class Input(State):
        temperature: Read[TemperatureField]
        temperature_increment: Read[Increment[TemperatureField]]
        exner: ReadWrite[ExnerField]
        theta_v: ReadWrite[ThetaVField]

    Output = Empty

    def __init__(self, output: Empty) -> None:
        super().__init__(output)
        self._new_te = ops.field(ops.CELL_K)

    def run(self, input: Input) -> Empty:
        ops.arr(self._new_te)[...] = ops.arr(input.temperature) + ops.arr(input.temperature_increment)
        ops.update_exner_and_theta_v(self._new_te, input.exner, input.theta_v)
        return self.output
