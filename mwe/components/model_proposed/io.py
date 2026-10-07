from collections.abc import Mapping, Sequence
from datetime import datetime

import gt4py.next as gtx

from model_proposed.common import framework as fw, quantities as qty
import ops


class IOMonitor(fw.Component):
    # everything IO can write; the config picks by CF standard_name, or by the
    # quantity's class name where the CF table has none
    class Input(fw.State):
        rho: fw.Field[qty.RhoOnCellK]
        w: fw.Field[qty.WOnCellK]
        vn: fw.Field[qty.VnOnEdgeK]
        exner: fw.Field[qty.ExnerOnCellK]
        theta_v: fw.Field[qty.ThetaVOnCellK]
        temperature: fw.Field[qty.TemperatureOnCellK]
        u: fw.Field[qty.UOnCellK]
        simulation_time: datetime

    Output = fw.Empty

    def __init__(self, sizes: Mapping[gtx.Dimension, int], variables: Sequence[str]) -> None:
        super().__init__(sizes)
        keys = {d.quantity.standard_name or d.quantity.__name__: d.name for d in IOMonitor.Input.declarations()}
        assert len(keys) == len(IOMonitor.Input.declarations()), "two IO leaves with one name"
        self.selected = {name: keys[name] for name in variables}
        self.dataset: list[tuple[datetime, str, ops.Array]] = []

    def run(self, input: Input, out: fw.Empty | None = None) -> fw.Empty:
        for name, leaf in self.selected.items():
            field: fw.Field[fw.Quantity] = getattr(input, leaf)
            self.dataset.append((input.simulation_time, name, ops.arr(field.data).copy()))
        return self.buffers(out)
