from model_proposed import recipes
from model_proposed.common import framework as fw, quantities as qty
import ops


class MuphysComponent(fw.Component["MuphysComponent.Input", "MuphysComponent.Output"]):
    class Input(fw.State):
        te: fw.Read[qty.TemperatureField] = fw.derived_by(recipes.TemperatureFromThetaExner)
        qv: fw.Read[qty.QvField]

    class Output(fw.State):
        tend_temperature: fw.Tendency[qty.TemperatureField]
        tend_qv: fw.Tendency[qty.QvField]
        pflx: qty.PrecipField

    def run(self, input: Input) -> Output:
        ops.muphys(input.te, input.qv, self.output.tend_temperature, self.output.tend_qv, self.output.pflx)
        return self.output
