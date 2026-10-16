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

    def run(self, inputs: Input, outputs: Output | None = None) -> Output:
        out = self.buffers(outputs)
        ops.diffuse(inputs.vn.data, inputs.theta_v.data, inputs.dtime, out.vn.data, out.theta_v.data)
        return out
