from model_proposed.common.framework import Component, Empty, Read, ReadWrite, State
from model_proposed.common.quantities import UField, VnField
import ops


class WindProjection(Component["WindProjection.Input", Empty]):
    class Input(State):
        u: Read[UField]
        vn: ReadWrite[VnField]

    Output = Empty

    def run(self, input: Input) -> Empty:
        ops.project(input.u, input.vn)
        return self.output
