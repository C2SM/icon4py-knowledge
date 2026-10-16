from model_proposed.common import framework as fw, quantities as qty
import ops


class Advection(fw.Component):
    class Input(fw.State):
        qv: qty.Qv.CellK
        mass_flx_me: qty.HorizontalMassFlux.EdgeK
        dtime: float

    class Output(fw.State):
        qv: qty.Qv.CellK

    def run(self, inputs: Input, outputs: Output | None = None) -> Output:
        out = self.buffers(outputs)
        ops.advect(inputs.qv.data, out.qv.data, inputs.mass_flx_me.data, inputs.dtime)
        return out
