from model_proposed import recipes
from model_proposed.common import framework as fw, quantities as qty
import ops


class MuphysComponent(fw.Process):
    class Input(fw.State):
        temperature: qty.Temperature.CellK = fw.derived_by(recipes.TemperatureFromThetaExner)
        qv: qty.Qv.CellK

    class Output(fw.State):
        tend_temperature: fw.Tendency[qty.Temperature, fw.CellK]
        tend_qv: fw.Tendency[qty.Qv, fw.CellK]
        pflx: qty.PrecipitationFlux.Cell

    # where the tendencies land: temperature and qv get dt times their
    # tendency, exner and theta_v are rewritten from the new temperature once
    class Update(fw.State):
        temperature: qty.Temperature.CellK = fw.from_tendency()
        qv: qty.Qv.CellK = fw.from_tendency()
        theta_v: qty.ThetaV.CellK = fw.after_increments(recipes.ExnerThetaFromTemperature)
        exner: qty.Exner.CellK = fw.after_increments(recipes.ExnerThetaFromTemperature)

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        ops.muphys(input.temperature.data, input.qv.data, out.tend_temperature.data, out.tend_qv.data, out.pflx.data)
        return out
