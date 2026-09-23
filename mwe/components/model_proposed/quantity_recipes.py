from model_proposed.common import framework as fw, quantities as qty
import ops


class ExnerThetaFromTemperature(fw.Component["ExnerThetaFromTemperature.Input", fw.Empty]):
    class Input(fw.State):
        temperature: fw.Read[qty.TemperatureField]
        exner: fw.ReadWrite[qty.ExnerField]
        theta_v: fw.ReadWrite[qty.ThetaVField]

    Output = fw.Empty

    def run(self, input: Input) -> fw.Empty:
        ops.update_exner_and_theta_v(input.temperature, input.exner, input.theta_v)
        return self.output


class TemperatureFromThetaExner(fw.Component["TemperatureFromThetaExner.Input", "TemperatureFromThetaExner.Output"]):
    class Input(fw.State):
        theta_v: fw.Read[qty.ThetaVField]
        exner: fw.Read[qty.ExnerField]

    class Output(fw.State):
        temperature: qty.TemperatureField

    write_back = ExnerThetaFromTemperature
    invertible = True

    def run(self, input: Input) -> Output:
        ops.compute_temperature(input.theta_v, input.exner, self.output.temperature)
        return self.output


class VnFromUIncrement(fw.Component["VnFromUIncrement.Input", fw.Empty]):
    class Input(fw.State):
        u_increment: fw.Read[fw.Increment[qty.UField]]
        vn: fw.ReadWrite[qty.VnField]

    Output = fw.Empty

    def __init__(self, output: fw.Empty) -> None:
        super().__init__(output)
        self._ddt_vn = ops.field(ops.EDGE_K)

    def run(self, input: Input) -> fw.Empty:
        ops.compute_vn_from_uv(input.u_increment, self._ddt_vn)
        ops.arr(input.vn)[...] += ops.arr(self._ddt_vn)
        return self.output


class UFromVn(fw.Component["UFromVn.Input", "UFromVn.Output"]):
    class Input(fw.State):
        vn: fw.Read[qty.VnField]

    class Output(fw.State):
        u: qty.UField

    write_back = VnFromUIncrement

    def run(self, input: Input) -> Output:
        ops.edge_2_cell_vector_rbf_interpolation(input.vn, self.output.u)
        return self.output
