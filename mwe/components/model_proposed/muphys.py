from model_proposed import physics_state
from model_proposed.common import framework as fw, quantities as qty
import ops


class MuphysComponent(fw.Component):
    class Input(fw.State):
        temperature: qty.Temperature.CellK
        qv: qty.Qv.CellK

    class Output(fw.State):
        tend_temperature: fw.Tendency[qty.Temperature, fw.CellK]
        tend_qv: fw.Tendency[qty.Qv, fw.CellK]
        pflx: qty.PrecipitationFlux.Cell

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        ops.muphys(input.temperature.data, input.qv.data, out.tend_temperature.data, out.tend_qv.data, out.pflx.data)
        return out


def collect_input(entry: physics_state.EntryState) -> MuphysComponent.Input:
    return MuphysComponent.Input(temperature=entry.temperature, qv=entry.qv)
