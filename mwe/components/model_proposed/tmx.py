from model_proposed import recipes
from model_proposed.common import framework as fw, quantities as qty
import ops


class TmxComponent(fw.Process):
    class Input(fw.State):
        temperature: fw.Read[qty.TemperatureField] = fw.derived_by(recipes.TemperatureFromThetaExner)
        u: fw.Read[qty.UField] = fw.derived_by(recipes.UFromVn)

    class Output(fw.State):
        tend_temperature: fw.Tendency[qty.TemperatureField]
        tend_u: fw.Tendency[qty.UField]

    class Update(fw.State):
        temperature: fw.Increment[qty.TemperatureField] = fw.from_tendency()
        vn: fw.Increment[qty.VnField] = fw.derived_by(recipes.VnIncrementFromUTendency)
        theta_v: fw.ReadWrite[qty.ThetaVField] = fw.after_increments(recipes.ExnerThetaFromTemperature)
        exner: fw.ReadWrite[qty.ExnerField] = fw.after_increments(recipes.ExnerThetaFromTemperature)

    output: Output

    def run(self, input: Input) -> Output:
        ops.tmx(input.temperature, input.u, self.output.tend_temperature, self.output.tend_u)
        return self.output
