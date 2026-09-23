from model_proposed.common import framework as fw, quantities as qty
import ops


class WindProjection(fw.Component["WindProjection.Input", fw.Empty]):
    class Input(fw.State):
        u_increment: fw.Read[fw.Increment[qty.UField]]
        vn: fw.ReadWrite[qty.VnField]

    Output = fw.Empty

    def __init__(self, output: fw.Empty) -> None:
        super().__init__(output)
        self._ddt_vn = ops.field(ops.EDGE_K)

    def run(self, input: Input) -> fw.Empty:
        ops.compute_vn_from_uv(input.u_increment, self._ddt_vn)
        ops.arr(input.vn)[...] += ops.arr(self._ddt_vn)
        return self.output
