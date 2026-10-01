from model_proposed.common import framework as fw, quantities as qty
import ops


class Diffusion(fw.Component):
    class Input(fw.State):
        vn: qty.Vn.EdgeK
        theta_v: qty.ThetaV.CellK
        dtime: float

    class Output(fw.State):
        vn: qty.Vn.EdgeK
        theta_v: qty.ThetaV.CellK

    # pointwise: the driver passes `next` on both sides
    in_place = frozenset({"vn", "theta_v"})

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        ops.diffuse(input.vn.data, input.theta_v.data, input.dtime, out.vn.data, out.theta_v.data)
        return out
