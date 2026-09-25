from model_proposed.common import framework as fw, quantities as qty
import ops


class Diffusion(fw.Component):
    class Input(fw.State):
        vn: qty.VnField
        theta_v: qty.ThetaVField
        dtime: qty.TimeStepValue

    class Output(fw.State):
        vn: qty.VnField
        theta_v: qty.ThetaVField

    in_place = frozenset({"vn", "theta_v"})

    def run(self, input: Input, output: Output) -> None:
        ops.diffuse(input.vn, input.theta_v, input.dtime, output.vn, output.theta_v)
