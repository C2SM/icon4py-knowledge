from model_proposed import recipes
from model_proposed.common import framework as fw, quantities as qty
import ops


class MuphysComponent(fw.Component):
    class Input(fw.State):
        temperature: qty.Temperature.CellK = fw.derived_by(recipes.TemperatureFromThetaExner)
        qv: qty.Qv.CellK

    class Output(fw.State):
        tend_temperature: qty.TendencyOfTemperature.CellK
        tend_qv: qty.TendencyOfQv.CellK
        pflx: qty.PrecipitationFlux.Cell

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        ops.muphys(input.temperature.data, input.qv.data, out.tend_temperature.data, out.tend_qv.data, out.pflx.data)
        return out
