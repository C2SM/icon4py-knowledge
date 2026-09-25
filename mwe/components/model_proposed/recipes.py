from model_proposed.common import framework as fw, quantities as qty
import ops


class TemperatureFromThetaExner(fw.Recipe):
    class Input(fw.State):
        theta_v: qty.ThetaVField
        exner: qty.ExnerField

    class Output(fw.State):
        temperature: qty.TemperatureField

    def run(self, input: Input, output: Output) -> None:
        ops.compute_temperature(input.theta_v, input.exner, output.temperature)


# plain Component, not a Recipe, because it is a hook, not a derivation
class ExnerThetaFromTemperature(fw.Component):
    class Input(fw.State):
        temperature: qty.TemperatureField
        exner: qty.ExnerField
        theta_v: qty.ThetaVField

    class Output(fw.State):
        exner: qty.ExnerField
        theta_v: qty.ThetaVField

    in_place = frozenset({"exner", "theta_v"})

    def run(self, input: Input, output: Output) -> None:
        ops.update_exner_and_theta_v(input.temperature, input.exner, input.theta_v, output.exner, output.theta_v)


class UFromVn(fw.Recipe):
    class Input(fw.State):
        vn: qty.VnField

    class Output(fw.State):
        u: qty.UField

    def run(self, input: Input, output: Output) -> None:
        ops.edge_2_cell_vector_rbf_interpolation(input.vn, output.u)


class VnIncrementFromUTendency(fw.Recipe):
    class Input(fw.State):
        tend_u: fw.Tendency[qty.UField]
        dtime: qty.TimeStep

    class Output(fw.State):
        vn: fw.Increment[qty.VnField]

    def __init__(self) -> None:
        self._ddt_vn = ops.field(ops.EDGE_K)

    def run(self, input: Input, output: Output) -> None:
        ops.compute_vn_from_uv(input.tend_u, self._ddt_vn)
        ops.arr(output.vn)[...] = input.dtime * ops.arr(self._ddt_vn)
