import dataclasses
from collections.abc import Callable, Mapping
from typing import Any

import gt4py.next as gtx

from model_proposed import muphys, physics_state, recipes, tmx
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

    def __init__(self, sizes: Sizes, process_intervals: Mapping[str, int]) -> None:
        super().__init__(sizes)
        self.processes = [
            PhysicsProcess(name, PROCESSES[name](sizes), ProcessTimeControl(interval))
            for name, interval in process_intervals.items()
        ]
        # the recipes for the diagnostics the processes read, run here each step
        self.temperature_from_theta_exner = recipes.TemperatureFromThetaExner(sizes)
        self.u_from_vn = recipes.UFromVn(sizes)
        # one accumulator per tendency the processes emit, by output name, made
        # when first seen (TendencyAccumulators in icon4py)
        self.accumulators: dict[str, fw.Field[Any, Any]] = {}
        # the last output of each process, reused on the steps it is not active
        self.outputs: dict[str, fw.State] = {}
        self._new_te = fw.zeros(qty.Temperature, fw.CellK, sizes)
        self.vn_tendency_from_u_tendency = recipes.VnTendencyFromUTendency(sizes)
        self.exner_theta_from_temperature = recipes.ExnerThetaFromTemperature(sizes)

    # the five steps of icon4py's PhysicsDriver.run, as methods
    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        entry = self._diagnose(input)
        self._zero_accumulators()
        for process in self.processes:
            if process.time_control.is_active(input.step_index) or process.name not in self.outputs:
                self.outputs[process.name] = process.step(entry)
            self._accumulate(self.outputs[process.name])
        self._apply(entry, input.dtime, out)
        return out

    # one EntryState over the prognostics as given and the diagnostics the
    # recipes derive from them, in their buffers (EntryState.diagnose_from)
    def _diagnose(self, input: Input) -> physics_state.EntryState:
        temperature = self.temperature_from_theta_exner.run(
            recipes.TemperatureFromThetaExner.Input(theta_v=input.theta_v, exner=input.exner)
        ).temperature
        u = self.u_from_vn.run(recipes.UFromVn.Input(vn=input.vn)).u
        return physics_state.EntryState(
            vn=input.vn, exner=input.exner, theta_v=input.theta_v, qv=input.qv, temperature=temperature, u=u
        )

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
    # `out` may alias the entry's prognostics
    def _apply(self, entry: physics_state.EntryState, dt: float, out: Output) -> None:
        acc = self.accumulators
        _carry(entry.vn, out.vn)
        _carry(entry.qv, out.qv)
        if "tend_qv" in acc:
            ops.arr(out.qv.data)[...] = ops.arr(entry.qv.data) + dt * ops.arr(acc["tend_qv"].data)
        if "tend_temperature" in acc:
            ops.arr(self._new_te.data)[...] = ops.arr(entry.temperature.data) + dt * ops.arr(acc["tend_temperature"].data)
            self.exner_theta_from_temperature.run(
                recipes.ExnerThetaFromTemperature.Input(temperature=self._new_te, exner=entry.exner, theta_v=entry.theta_v),
                out=recipes.ExnerThetaFromTemperature.Output(exner=out.exner, theta_v=out.theta_v),
            )
        else:
            _carry(entry.exner, out.exner)
            _carry(entry.theta_v, out.theta_v)
        if "tend_u" in acc:
            ddt_vn = self.vn_tendency_from_u_tendency.run(
                recipes.VnTendencyFromUTendency.Input(tend_u=acc["tend_u"])
            ).ddt_vn
            ops.arr(out.vn.data)[...] = ops.arr(entry.vn.data) + dt * ops.arr(ddt_vn.data)
