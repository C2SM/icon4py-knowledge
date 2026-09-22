from model_proposed.common.framework import Component, Empty, Increment, Read, ReadWrite, State
from model_proposed.common.quantities import UField, VnField
import ops


class WindProjection(Component["WindProjection.Input", Empty]):
    class Input(State):
        u_increment: Read[Increment[UField]]
        vn: ReadWrite[VnField]

    Output = Empty

    def __init__(self, output: Empty) -> None:
        super().__init__(output)
        self._ddt_vn = ops.field(ops.EDGE_K)

    def run(self, input: Input) -> Empty:
        ops.compute_vn_from_uv(input.u_increment, self._ddt_vn)
        ops.arr(input.vn)[...] += ops.arr(self._ddt_vn)
        return self.output
