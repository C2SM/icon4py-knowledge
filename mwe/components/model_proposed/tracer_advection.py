from model_proposed.common import framework as fw, quantities as qty
import ops


class Advection(fw.Component):
    class Input(fw.State):
        qv: qty.QvField
        mass_flx_me: qty.MassFluxField
        dtime: qty.TimeStepValue

    class Output(fw.State):
        qv: qty.QvField

    def run(self, input: Input, output: Output) -> None:
        ops.advect(input.qv, output.qv, input.mass_flx_me, input.dtime)
