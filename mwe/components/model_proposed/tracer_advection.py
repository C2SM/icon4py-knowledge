from model_proposed.common.framework import Component, Empty, Next, Now, Read, ReadWrite, State
from model_proposed.common.quantities import MassFluxField, QvField, TimeStep
import ops


class Advection(Component["Advection.Input", Empty]):
    class Input(State):
        p_tracer_now: Read[Now[QvField]]
        p_tracer_new: ReadWrite[Next[QvField]]
        mass_flx_me: Read[MassFluxField]
        dtime: Read[TimeStep]

    Output = Empty

    def run(self, input: Input) -> Empty:
        ops.advect(input.p_tracer_now, input.p_tracer_new, input.mass_flx_me, input.dtime)
        return self.output
