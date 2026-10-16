from model_proposed.common import framework as fw, quantities as qty
import ops


class TmxComponent(fw.Component):
    class Input(fw.State):
        temperature: qty.Temperature.CellK
        u: qty.U.CellK

    class Output(fw.State):
        tend_temperature: qty.TendencyOfTemperature.CellK
        tend_u: qty.TendencyOfU.CellK

    def run(self, inputs: Input, outputs: Output | None = None) -> Output:
        out = self.buffers(outputs)
        ops.tmx(inputs.temperature.data, inputs.u.data, out.tend_temperature.data, out.tend_u.data)
        return out
