from model_proposed import recipes
from model_proposed.common import framework as fw, quantities as qty
import ops


class MuphysComponent(fw.Process):
    class Input(fw.State):
        temperature: fw.Read[qty.TemperatureField] = fw.derived_by(recipes.TemperatureFromThetaExner)
        qv: fw.Read[qty.QvField]

    class Output(fw.State):
        tend_temperature: fw.Tendency[qty.TemperatureField]
        tend_qv: fw.Tendency[qty.QvField]
        pflx: qty.PrecipField

    class Update(fw.State):
        temperature: fw.Increment[qty.TemperatureField] = fw.from_tendency()
        qv: fw.Increment[qty.QvField] = fw.from_tendency()
        theta_v: fw.ReadWrite[qty.ThetaVField] = fw.after_increments(recipes.ExnerThetaFromTemperature)
        exner: fw.ReadWrite[qty.ExnerField] = fw.after_increments(recipes.ExnerThetaFromTemperature)

    output: Output

    def run(self, input: Input) -> Output:
        ops.muphys(input.temperature, input.qv, self.output.tend_temperature, self.output.tend_qv, self.output.pflx)
        return self.output
