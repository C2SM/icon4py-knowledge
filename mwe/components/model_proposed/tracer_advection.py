from model_proposed.common import framework as fw, quantities as qty
import ops


class Advection(fw.Component):
    class Input(fw.State):
        qv: fw.Field[qty.QvOnCellK]
        mass_flx_me: fw.Field[qty.MassFluxOnEdgeK]
        dtime: float

    class Output(fw.State):
        qv: fw.Field[qty.QvOnCellK]

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        ops.advect(input.qv.data, out.qv.data, input.mass_flx_me.data, input.dtime)
        return out
