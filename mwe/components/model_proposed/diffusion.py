from model_proposed.common import framework as fw, quantities as qty
import ops


class Diffusion(fw.Component):
    class Input(fw.State):
        vn: fw.ReadWrite[qty.VnField]
        theta_v: fw.ReadWrite[qty.ThetaVField]
        dtime: fw.Read[qty.TimeStep]

    Output = fw.Empty

    output: fw.Empty

    def run(self, input: Input) -> fw.Empty:
        ops.diffuse(input.vn, input.theta_v, input.dtime)
        return self.output
