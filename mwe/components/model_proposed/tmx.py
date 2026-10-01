from model_proposed import physics_state
from model_proposed.common import framework as fw, quantities as qty
import ops


class TmxComponent(fw.Component):
    class Input(fw.State):
        temperature: qty.Temperature.CellK
        u: qty.U.CellK

    class Output(fw.State):
        tend_temperature: qty.TendencyOfTemperature.CellK
        tend_u: qty.TendencyOfU.CellK

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        ops.tmx(input.temperature.data, input.u.data, out.tend_temperature.data, out.tend_u.data)
        return out


def collect_input(entry: physics_state.EntryState) -> TmxComponent.Input:
    return TmxComponent.Input(temperature=entry.temperature, u=entry.u)
