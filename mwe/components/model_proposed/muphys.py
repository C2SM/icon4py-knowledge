from model_proposed import recipes
from model_proposed.common import framework as fw, quantities as qty
import ops


class MuphysComponent(fw.Process):
    class Input(fw.State):
        temperature: qty.TemperatureField = fw.derived_by(recipes.TemperatureFromThetaExner)
        qv: qty.QvField

    class Output(fw.State):
        tend_temperature: fw.Tendency[qty.TemperatureField]
        tend_qv: fw.Tendency[qty.QvField]
        pflx: qty.PrecipField

    class Update(fw.State):
        temperature: fw.Increment[qty.TemperatureField] = fw.from_tendency()
        qv: fw.Increment[qty.QvField] = fw.from_tendency()
        theta_v: qty.ThetaVField = fw.after_increments(recipes.ExnerThetaFromTemperature)
        exner: qty.ExnerField = fw.after_increments(recipes.ExnerThetaFromTemperature)

    def run(self, input: Input, output: Output) -> None:
        ops.muphys(input.temperature, input.qv, output.tend_temperature, output.tend_qv, output.pflx)
