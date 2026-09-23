from model_proposed.common import framework as fw, quantities as qty
import ops


class Advection(fw.Component["Advection.Input", fw.Empty]):
    class Input(fw.State):
        p_tracer_now: fw.Read[fw.Now[qty.QvField]]
        p_tracer_new: fw.ReadWrite[fw.Next[qty.QvField]]
        mass_flx_me: fw.Read[qty.MassFluxField]
        dtime: fw.Read[qty.TimeStep]

    Output = fw.Empty

    def run(self, input: Input) -> fw.Empty:
        ops.advect(input.p_tracer_now, input.p_tracer_new, input.mass_flx_me, input.dtime)
        return self.output
