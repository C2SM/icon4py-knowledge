from model_proposed.common import framework as fw, quantities as qty
import ops


class TemperatureFromThetaExner(fw.Recipe):
    class Input(fw.State):
        theta_v: fw.Field[qty.ThetaVOnCellK]
        exner: fw.Field[qty.ExnerOnCellK]

    class Output(fw.State):
        temperature: fw.Field[qty.TemperatureOnCellK]

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        ops.compute_temperature(input.theta_v.data, input.exner.data, out.temperature.data)
        return out


class UFromVn(fw.Recipe):
    class Input(fw.State):
        vn: fw.Field[qty.VnOnEdgeK]

    class Output(fw.State):
        u: fw.Field[qty.UOnCellK]

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        ops.edge_2_cell_vector_rbf_interpolation(input.vn.data, out.u.data)
        return out


class ThetaVToHalfLevels(fw.Recipe):
    class Input(fw.State):
        theta_v: fw.Field[qty.ThetaVOnCellK]

    class Output(fw.State):
        theta_v_ic: fw.Field[qty.ThetaVOnCellKHalf]

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        ops.interpolate_to_half_levels(input.theta_v.data, out.theta_v_ic.data)
        return out


class VnTendencyFromUTendency(fw.Recipe):
    class Input(fw.State):
        tend_u: fw.Field[qty.TendencyOfUOnCellK]

    class Output(fw.State):
        ddt_vn: fw.Field[qty.TendencyOfVnOnEdgeK]

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        ops.compute_vn_from_uv(input.tend_u.data, out.ddt_vn.data)
        return out


# a plain Component, not a Recipe: its outputs, exner and theta_v, are among
# its inputs; it updates them after temperature changed (the EOS step of
# ApplyToPrognostic), and out may alias the input
class ExnerThetaFromTemperature(fw.Component):
    class Input(fw.State):
        temperature: fw.Field[qty.TemperatureOnCellK]
        exner: fw.Field[qty.ExnerOnCellK]
        theta_v: fw.Field[qty.ThetaVOnCellK]

    class Output(fw.State):
        exner: fw.Field[qty.ExnerOnCellK]
        theta_v: fw.Field[qty.ThetaVOnCellK]

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        ops.update_exner_and_theta_v(
            input.temperature.data, input.exner.data, input.theta_v.data, out.exner.data, out.theta_v.data
        )
        return out
