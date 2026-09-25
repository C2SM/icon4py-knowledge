from model_proposed import recipes
from model_proposed.common import framework as fw, quantities as qty
import ops


class TmxComponent(fw.Process):
    class Input(fw.State):
        temperature: qty.TemperatureField = fw.derived_by(recipes.TemperatureFromThetaExner)
        u: qty.UField = fw.derived_by(recipes.UFromVn)

    class Output(fw.State):
        tend_temperature: fw.Tendency[qty.TemperatureField]
        tend_u: fw.Tendency[qty.UField]

    class Update(fw.State):
        temperature: fw.Increment[qty.TemperatureField] = fw.from_tendency()
        vn: fw.Increment[qty.VnField] = fw.derived_by(recipes.VnIncrementFromUTendency)
        theta_v: qty.ThetaVField = fw.after_increments(recipes.ExnerThetaFromTemperature)
        exner: qty.ExnerField = fw.after_increments(recipes.ExnerThetaFromTemperature)

    def run(self, input: Input, output: Output) -> None:
        ops.tmx(input.temperature, input.u, output.tend_temperature, output.tend_u)
