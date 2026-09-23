from model_proposed.common import framework as fw, quantities as qty
import ops


class ExnerThetaUpdate(fw.Component["ExnerThetaUpdate.Input", fw.Empty]):
    class Input(fw.State):
        temperature: fw.Read[qty.TemperatureField]
        temperature_increment: fw.Read[fw.Increment[qty.TemperatureField]]
        exner: fw.ReadWrite[qty.ExnerField]
        theta_v: fw.ReadWrite[qty.ThetaVField]

    Output = fw.Empty

    def __init__(self, output: fw.Empty) -> None:
        super().__init__(output)
        self._new_te = ops.field(ops.CELL_K)

    def run(self, input: Input) -> fw.Empty:
        ops.arr(self._new_te)[...] = ops.arr(input.temperature) + ops.arr(input.temperature_increment)
        ops.update_exner_and_theta_v(self._new_te, input.exner, input.theta_v)
        return self.output
