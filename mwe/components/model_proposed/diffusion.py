from model_proposed.common.framework import Component, Empty, Read, ReadWrite, State
from model_proposed.common.quantities import ThetaVField, TimeStep, VnField
import ops


class Diffusion(Component["Diffusion.Input", Empty]):
    class Input(State):
        vn: ReadWrite[VnField]
        theta_v: ReadWrite[ThetaVField]
        dtime: Read[TimeStep]

    Output = Empty

    def run(self, input: Input) -> Empty:
        ops.diffuse(input.vn, input.theta_v, input.dtime)
        return self.output
