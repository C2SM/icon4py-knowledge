from model_proposed.common import framework as fw, quantities as qty
import ops


class TemperatureFromThetaExner(fw.Recipe):
    class Input(fw.State):
        theta_v: qty.ThetaV.CellK
        exner: qty.Exner.CellK

    class Output(fw.State):
        temperature: qty.Temperature.CellK

    def run(self, inputs: Input, outputs: Output | None = None) -> Output:
        out = self.buffers(outputs)
        ops.compute_temperature(inputs.theta_v.data, inputs.exner.data, out.temperature.data)
        return out


class UFromVn(fw.Recipe):
    class Input(fw.State):
        vn: qty.Vn.EdgeK

    class Output(fw.State):
        u: qty.U.CellK

    def run(self, inputs: Input, outputs: Output | None = None) -> Output:
        out = self.buffers(outputs)
        ops.edge_2_cell_vector_rbf_interpolation(inputs.vn.data, out.u.data)
        return out


class ThetaVToHalfLevels(fw.Recipe):
    class Input(fw.State):
        theta_v: qty.ThetaV.CellK

    class Output(fw.State):
        theta_v_ic: qty.ThetaV.CellKHalf

    def run(self, inputs: Input, outputs: Output | None = None) -> Output:
        out = self.buffers(outputs)
        ops.interpolate_to_half_levels(inputs.theta_v.data, out.theta_v_ic.data)
        return out


class VnTendencyFromUTendency(fw.Recipe):
    class Input(fw.State):
        tend_u: fw.Tendency[qty.U, fw.CellK]

    class Output(fw.State):
        ddt_vn: fw.Tendency[qty.Vn, fw.EdgeK]

    def run(self, inputs: Input, outputs: Output | None = None) -> Output:
        out = self.buffers(outputs)
        ops.compute_vn_from_uv(inputs.tend_u.data, out.ddt_vn.data)
        return out


# a plain Component, not a Recipe: its outputs, exner and theta_v, are among
# its inputs; it updates them after temperature changed (the EOS step of
# ApplyToPrognostic), and out may alias the input
class ExnerThetaFromTemperature(fw.Component):
    class Input(fw.State):
        temperature: qty.Temperature.CellK
        exner: qty.Exner.CellK
        theta_v: qty.ThetaV.CellK

    class Output(fw.State):
        exner: qty.Exner.CellK
        theta_v: qty.ThetaV.CellK

    def run(self, inputs: Input, outputs: Output | None = None) -> Output:
        out = self.buffers(outputs)
        ops.update_exner_and_theta_v(
            inputs.temperature.data, inputs.exner.data, inputs.theta_v.data, out.exner.data, out.theta_v.data
        )
        return out
