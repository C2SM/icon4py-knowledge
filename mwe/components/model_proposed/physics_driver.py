import dataclasses
from collections.abc import Callable, Mapping
from typing import Any

import gt4py.next as gtx

from model_proposed import muphys, physics_state, tmx
from model_proposed.common import framework as fw, quantities as qty
import ops

type Sizes = Mapping[gtx.Dimension, int]
type Step = Callable[[physics_state.EntryState], fw.State]


# ties a component's run to the collect_input written for it; the pairing is
# checked here (tmx.collect_input with muphys's run is a type error)
def bind[I: fw.State, O: fw.State](
    run: Callable[[I], O], collect_input: Callable[[physics_state.EntryState], I]
) -> Callable[[physics_state.EntryState], O]:
    return lambda entry: run(collect_input(entry))


PROCESSES: dict[str, Callable[[Sizes], Step]] = {
    "muphys": lambda sizes: bind(muphys.MuphysComponent(sizes).run, muphys.collect_input),
    "tmx": lambda sizes: bind(tmx.TmxComponent(sizes).run, tmx.collect_input),
}


@dataclasses.dataclass(frozen=True)
class ProcessTimeControl:
    interval: int

    def is_active(self, step_index: int) -> bool:
        return step_index % self.interval == 0


@dataclasses.dataclass(frozen=True)
class PhysicsProcess:
    name: str
    step: Step
    time_control: ProcessTimeControl


def _carry[Q: fw.Quantity](src: fw.Field[Q], dst: fw.Field[Q]) -> None:
    if dst is not src:
        ops.arr(dst.data)[...] = ops.arr(src.data)


class PhysicsDriver(fw.Component):
    class Input(fw.State):
        vn: fw.Field[qty.VnOnEdgeK]
        exner: fw.Field[qty.ExnerOnCellK]
        theta_v: fw.Field[qty.ThetaVOnCellK]
        qv: fw.Field[qty.QvOnCellK]
        dtime: float
        step_index: int

    class Output(fw.State):
        vn: fw.Field[qty.VnOnEdgeK]
        exner: fw.Field[qty.ExnerOnCellK]
        theta_v: fw.Field[qty.ThetaVOnCellK]
        qv: fw.Field[qty.QvOnCellK]

    def __init__(self, sizes: Sizes, process_intervals: Mapping[str, int]) -> None:
        super().__init__(sizes)
        self.processes = [
            PhysicsProcess(name, PROCESSES[name](sizes), ProcessTimeControl(interval))
            for name, interval in process_intervals.items()
        ]
        # the diagnostics the processes read, derived here each step
        self.temperature = fw.zeros(qty.TemperatureOnCellK, sizes)
        self.u = fw.zeros(qty.UOnCellK, sizes)
        # one accumulator per tendency the processes emit, by output name, made
        # when first seen (TendencyAccumulators in icon4py)
        self.accumulators: dict[str, fw.Field[Any]] = {}
        # the last output of each process, reused on the steps it is not active
        self.outputs: dict[str, fw.State] = {}
        self._new_te = fw.zeros(qty.TemperatureOnCellK, sizes)
        self._ddt_vn = fw.zeros(qty.TendencyOfVnOnEdgeK, sizes)

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        ops.compute_temperature(input.theta_v.data, input.exner.data, self.temperature.data)
        ops.edge_2_cell_vector_rbf_interpolation(input.vn.data, self.u.data)
        entry = physics_state.EntryState(
            vn=input.vn, exner=input.exner, theta_v=input.theta_v, qv=input.qv, temperature=self.temperature, u=self.u
        )
        for acc in self.accumulators.values():
            ops.arr(acc.data)[...] = 0.0
        for process in self.processes:
            if process.time_control.is_active(input.step_index) or process.name not in self.outputs:
                self.outputs[process.name] = process.step(entry)
            for d, value in self.outputs[process.name].leaves():
                if issubclass(d.quantity, qty.Tendency):
                    if d.name not in self.accumulators:
                        self.accumulators[d.name] = fw.zeros(d.quantity, self.sizes)
                    ops.arr(self.accumulators[d.name].data)[...] += ops.arr(value.data)
        self._apply(input, out)
        return out

    # the summed tendencies into the prognostics, once; `out` may alias `input`
    def _apply(self, input: Input, out: Output) -> None:
        acc, dt = self.accumulators, input.dtime
        _carry(input.vn, out.vn)
        _carry(input.qv, out.qv)
        if "tend_qv" in acc:
            ops.arr(out.qv.data)[...] = ops.arr(input.qv.data) + dt * ops.arr(acc["tend_qv"].data)
        if "tend_temperature" in acc:
            ops.arr(self._new_te.data)[...] = ops.arr(self.temperature.data) + dt * ops.arr(acc["tend_temperature"].data)
            ops.update_exner_and_theta_v(
                self._new_te.data, input.exner.data, input.theta_v.data, out.exner.data, out.theta_v.data
            )
        else:
            _carry(input.exner, out.exner)
            _carry(input.theta_v, out.theta_v)
        if "tend_u" in acc:
            ops.compute_vn_from_uv(acc["tend_u"].data, self._ddt_vn.data)
            ops.arr(out.vn.data)[...] = ops.arr(input.vn.data) + dt * ops.arr(self._ddt_vn.data)
