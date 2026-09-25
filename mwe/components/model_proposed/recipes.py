from model_proposed.common import framework as fw, quantities as qty
import ops


class TemperatureFromThetaExner(fw.Recipe["TemperatureFromThetaExner.Input", "TemperatureFromThetaExner.Output"]):
    class Input(fw.State):
        theta_v: fw.Read[qty.ThetaVField]
        exner: fw.Read[qty.ExnerField]

    class Output(fw.State):
        temperature: qty.TemperatureField

    def run(self, input: Input) -> Output:
        ops.compute_temperature(input.theta_v, input.exner, self.output.temperature)
        return self.output


# plain Component, not a Recipe, because it is a hook, not a derivation
class ExnerThetaFromTemperature(fw.Component["ExnerThetaFromTemperature.Input", fw.Empty]):
    class Input(fw.State):
        temperature: fw.Read[qty.TemperatureField]
        exner: fw.ReadWrite[qty.ExnerField]
        theta_v: fw.ReadWrite[qty.ThetaVField]

    Output = fw.Empty

    def run(self, input: Input) -> fw.Empty:
        ops.update_exner_and_theta_v(input.temperature, input.exner, input.theta_v)
        return self.output


class UFromVn(fw.Recipe["UFromVn.Input", "UFromVn.Output"]):
    class Input(fw.State):
        vn: fw.Read[qty.VnField]

    class Output(fw.State):
        u: qty.UField

    def run(self, input: Input) -> Output:
        ops.edge_2_cell_vector_rbf_interpolation(input.vn, self.output.u)
        return self.output


class VnIncrementFromUTendency(fw.Recipe["VnIncrementFromUTendency.Input", "VnIncrementFromUTendency.Output"]):
    class Input(fw.State):
        tend_u: fw.Read[fw.Tendency[qty.UField]]
        dtime: fw.Read[qty.TimeStep]

    class Output(fw.State):
        vn: fw.Increment[qty.VnField]

    def __init__(self, output: Output) -> None:
        super().__init__(output)
        self._ddt_vn = ops.field(ops.EDGE_K)

    def run(self, input: Input) -> Output:
        ops.compute_vn_from_uv(input.tend_u, self._ddt_vn)
        ops.arr(self.output.vn)[...] = input.dtime * ops.arr(self._ddt_vn)
        return self.output
