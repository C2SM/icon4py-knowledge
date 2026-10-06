from model_proposed import recipes
from model_proposed.common import framework as fw, quantities as qty
import ops


class TmxComponent(fw.Process):
    class Input(fw.State):
        temperature: qty.Temperature.CellK = fw.derived_by(recipes.TemperatureFromThetaExner)
        u: qty.U.CellK = fw.derived_by(recipes.UFromVn)

    class Output(fw.State):
        tend_temperature: fw.Tendency[qty.Temperature, fw.CellK]
        tend_u: fw.Tendency[qty.U, fw.CellK]

    # the u tendency lands on vn, through the tendency a recipe derives from it
    class Update(fw.State):
        temperature: qty.Temperature.CellK = fw.from_tendency()
        vn: qty.Vn.EdgeK = fw.from_tendency(recipes.VnTendencyFromUTendency)
        theta_v: qty.ThetaV.CellK = fw.after_increments(recipes.ExnerThetaFromTemperature)
        exner: qty.Exner.CellK = fw.after_increments(recipes.ExnerThetaFromTemperature)

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        ops.tmx(input.temperature.data, input.u.data, out.tend_temperature.data, out.tend_u.data)
        return out
