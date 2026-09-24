from model_proposed import recipes
from model_proposed.common import framework as fw, quantities as qty
import ops


class TmxComponent(fw.Component["TmxComponent.Input", "TmxComponent.Output"]):
    class Input(fw.State):
        temperature: fw.Read[qty.TemperatureField] = fw.derived_by(recipes.TemperatureFromThetaExner)
        u: fw.Read[qty.UField] = fw.derived_by(recipes.UFromVn)

    class Output(fw.State):
        tend_temperature: fw.Tendency[qty.TemperatureField]
        tend_u: fw.Tendency[qty.UField]

    def run(self, input: Input) -> Output:
        ops.tmx(input.temperature, input.u, self.output.tend_temperature, self.output.tend_u)
        return self.output
