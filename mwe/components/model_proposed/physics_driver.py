import dataclasses
from collections.abc import Mapping
from typing import Any

import gt4py.next as gtx

from model_proposed import muphys, tmx
from model_proposed.common import framework as fw, quantities as qty, states
import ops

PROCESSES: dict[str, type[fw.Component]] = {
    "muphys": muphys.MuphysComponent,
    "tmx": tmx.TmxComponent,
}


@dataclasses.dataclass(frozen=True)
class ProcessTimeControl:
    interval: int

    def is_active(self, step_index: int) -> bool:
        return step_index % self.interval == 0


@dataclasses.dataclass(frozen=True)
class PhysicsProcess:
    name: str
    component: fw.Component
    time_control: ProcessTimeControl


def _carry[Q: fw.Quantity, D: fw.Dims](src: fw.Field[Q, D], dst: fw.Field[Q, D]) -> None:
    if dst is not src:
        ops.arr(dst.data)[...] = ops.arr(src.data)


class PhysicsDriver(fw.Component):
    class Input(fw.State):
        vn: qty.Vn.EdgeK
        exner: qty.Exner.CellK
        theta_v: qty.ThetaV.CellK
        qv: qty.Qv.CellK
        dtime: float
        step_index: int

    class Output(fw.State):
        vn: qty.Vn.EdgeK
        exner: qty.Exner.CellK
        theta_v: qty.ThetaV.CellK
        qv: qty.Qv.CellK

    def __init__(self, sizes: Mapping[gtx.Dimension, int], process_intervals: Mapping[str, int]) -> None:
        super().__init__(sizes)
        self.processes = [
            PhysicsProcess(name, PROCESSES[name](sizes), ProcessTimeControl(interval))
            for name, interval in process_intervals.items()
        ]
        # the diagnostics the processes read, derived here each step
        self.diagnostics = fw.allocate(states.Diagnostics, sizes)
        # one accumulator per tendency the processes emit, by output name, made
        # when first seen (TendencyAccumulators in icon4py)
        self.accumulators: dict[str, fw.Field[Any, Any]] = {}
        # the last output of each process, reused on the steps it is not active
        self.outputs: dict[str, fw.State] = {}
        self._new_te = fw.zeros(qty.Temperature, fw.CellK, sizes)
        self._ddt_vn = fw.zeros(qty.TendencyOfVn, fw.EdgeK, sizes)

    # icon4py's PhysicsDriver.run: four of its five steps as methods, the
    # process loop inline
    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        diagnostics = self._diagnose(input)
        self._zero_accumulators()
        for process in self.processes:
            if process.time_control.is_active(input.step_index) or process.name not in self.outputs:
                component = process.component
                self.outputs[process.name] = component.run(fw.collect(component.Input, input, diagnostics))
            self._accumulate(self.outputs[process.name])
        self._apply(input, diagnostics, out)
        return out

    # the diagnostics derived from the prognostics into the driver's buffers; a
    # process collects its Input from them and the driver's Input
    # (EntryState.diagnose_from, without the EntryState)
    def _diagnose(self, input: Input) -> states.Diagnostics:
        diagnostics = self.diagnostics
        ops.compute_temperature(input.theta_v.data, input.exner.data, diagnostics.temperature.data)
        ops.edge_2_cell_vector_rbf_interpolation(input.vn.data, diagnostics.u.data)
        return diagnostics

    def _zero_accumulators(self) -> None:
        for acc in self.accumulators.values():
            ops.arr(acc.data)[...] = 0.0

    # every Tendency leaf of a process's output into the accumulator of its
    # name (TendencyAccumulators.accumulate)
    def _accumulate(self, output: fw.State) -> None:
        for d, value in output.leaves():
            if issubclass(d.quantity, qty.Tendency):
                if d.name not in self.accumulators:
                    self.accumulators[d.name] = fw.zeros(d.quantity, d.dims, self.sizes)
                ops.arr(self.accumulators[d.name].data)[...] += ops.arr(value.data)

    # the summed tendencies into the prognostics, once (ApplyToPrognostic);
    # `out` may alias `input`
    def _apply(self, input: Input, diagnostics: states.Diagnostics, out: Output) -> None:
        acc, dt = self.accumulators, input.dtime
        _carry(input.vn, out.vn)
        _carry(input.qv, out.qv)
        if "tend_qv" in acc:
            ops.arr(out.qv.data)[...] = ops.arr(input.qv.data) + dt * ops.arr(acc["tend_qv"].data)
        if "tend_temperature" in acc:
            ops.arr(self._new_te.data)[...] = ops.arr(diagnostics.temperature.data) + dt * ops.arr(
                acc["tend_temperature"].data
            )
            ops.update_exner_and_theta_v(
                self._new_te.data, input.exner.data, input.theta_v.data, out.exner.data, out.theta_v.data
            )
        else:
            _carry(input.exner, out.exner)
            _carry(input.theta_v, out.theta_v)
        if "tend_u" in acc:
            ops.compute_vn_from_uv(acc["tend_u"].data, self._ddt_vn.data)
            ops.arr(out.vn.data)[...] = ops.arr(input.vn.data) + dt * ops.arr(self._ddt_vn.data)
