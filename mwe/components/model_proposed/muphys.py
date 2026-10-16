from model_proposed.common import framework as fw, quantities as qty
import ops


class MuphysComponent(fw.Component):
    class Input(fw.State):
        temperature: fw.Field[qty.TemperatureOnCellK]
        qv: fw.Field[qty.QvOnCellK]

    class Output(fw.State):
        tend_temperature: fw.Field[qty.TendencyOfTemperatureOnCellK]
        tend_qv: fw.Field[qty.TendencyOfQvOnCellK]
        pflx: fw.Field[qty.PrecipitationFluxOnCell]

    def run(self, inputs: Input, outputs: Output | None = None) -> Output:
        out = self.buffers(outputs)
        ops.muphys(inputs.temperature.data, inputs.qv.data, out.tend_temperature.data, out.tend_qv.data, out.pflx.data)
        return out
