from model_proposed.common import framework as fw, quantities as qty
import ops


class Diffusion(fw.Component):
    class Input(fw.State):
        vn: fw.Field[qty.VnOnEdgeK]
        theta_v: fw.Field[qty.ThetaVOnCellK]
        dtime: float

    class Output(fw.State):
        vn: fw.Field[qty.VnOnEdgeK]
        theta_v: fw.Field[qty.ThetaVOnCellK]

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        ops.diffuse(input.vn.data, input.theta_v.data, input.dtime, out.vn.data, out.theta_v.data)
        return out
