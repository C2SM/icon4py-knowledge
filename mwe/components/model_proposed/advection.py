from model_proposed.common.framework import Component, Empty, Next, Now, Read, ReadWrite, State
from model_proposed.common.quantities import MassFluxField, QvField, TimeStep
import ops


class Advection(Component["Advection.Input", Empty]):
    class Input(State):
        qv_now: Read[Now[QvField]]
        qv_new: ReadWrite[Next[QvField]]
        mass_flux_e: Read[MassFluxField]
        dtime: Read[TimeStep]

    Output = Empty

    def run(self, input: Input) -> Empty:
        ops.advect(input.qv_now, input.qv_new, input.mass_flux_e, input.dtime)
        return self.output
