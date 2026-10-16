import dataclasses
from collections.abc import Mapping
from typing import Any

import gt4py.next as gtx

from model_proposed import muphys, recipes, tmx
from model_proposed.common import framework as fw, quantities as qty
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
            PhysicsProcess(PROCESSES[name](sizes), ProcessTimeControl(interval))
            for name, interval in process_intervals.items()
        ]
        # the recipes the processes declare for their derived inputs, run once
        # per step before them
        self.resolution = fw.resolve([process.component for process in self.processes], sizes)
        # one accumulator per tendency the processes emit, keyed by what it is a
        # tendency of and where, made when first seen (TendencyAccumulators in
        # icon4py keys them by output name)
        self.accumulators: dict[tuple[type[fw.Quantity], type[fw.Dims]], fw.Field[Any, Any]] = {}
        # the last output of each process, by its component, reused on the steps
        # it is not active
        self.process_outputs: dict[fw.Component, fw.State] = {}
        self._new_te = fw.zeros(qty.Temperature, fw.CellK, sizes)
        self.vn_tendency_from_u_tendency = recipes.VnTendencyFromUTendency(sizes)
        self.exner_theta_from_temperature = recipes.ExnerThetaFromTemperature(sizes)

    # icon4py's PhysicsDriver.run: the resolution provides what diagnose_from
    # derived, the other steps as methods
    def run(self, inputs: Input, outputs: Output | None = None) -> Output:
        out = self.buffers(outputs)
        produced = self.resolution.provide(inputs)
        self._zero_accumulators()
        for process in self.processes:
            component = process.component
            if process.time_control.is_active(inputs.step_index) or component not in self.process_outputs:
                self.process_outputs[component] = component.run(fw.collect(component.Input, inputs, *produced))
            self._accumulate(self.process_outputs[component])
        self._apply(inputs, produced, out)
        return out

    def _zero_accumulators(self) -> None:
        for acc in self.accumulators.values():
            ops.arr(acc.data)[...] = 0.0

    # every tendency leaf of a process's output into the accumulator of its
    # parent at its place (TendencyAccumulators.accumulate)
    def _accumulate(self, output: fw.State) -> None:
        for d, value in output.leaves():
            if issubclass(d.quantity, fw.TendencyOf):
                key = (d.quantity.parent, d.dims)
                if key not in self.accumulators:
                    self.accumulators[key] = fw.zeros(d.quantity, d.dims, self.sizes)
                ops.arr(self.accumulators[key].data)[...] += ops.arr(value.data)

    # the summed tendencies into the prognostics, once (ApplyToPrognostic);
    # `out` may alias `input`
    def _apply(self, inputs: Input, produced: tuple[fw.State, ...], out: Output) -> None:
        acc, dt = self.accumulators, inputs.dtime
        _carry(inputs.vn, out.vn)
        _carry(inputs.qv, out.qv)
        if (qty.Qv, fw.CellK) in acc:
            ops.arr(out.qv.data)[...] = ops.arr(inputs.qv.data) + dt * ops.arr(acc[qty.Qv, fw.CellK].data)
        if (qty.Temperature, fw.CellK) in acc:
            # the EOS reads the temperature the recipes derived, incremented
            eos_input = fw.collect(recipes.ExnerThetaFromTemperature.Input, inputs, *produced)
            ops.arr(self._new_te.data)[...] = ops.arr(eos_input.temperature.data) + dt * ops.arr(
                acc[qty.Temperature, fw.CellK].data
            )
            self.exner_theta_from_temperature.run(
                dataclasses.replace(eos_input, temperature=self._new_te),
                outputs=fw.collect(recipes.ExnerThetaFromTemperature.Output, out),
            )
        else:
            _carry(inputs.exner, out.exner)
            _carry(inputs.theta_v, out.theta_v)
        if (qty.U, fw.CellK) in acc:
            ddt_vn = self.vn_tendency_from_u_tendency.run(
                recipes.VnTendencyFromUTendency.Input(tend_u=acc[qty.U, fw.CellK])
            ).ddt_vn
            ops.arr(out.vn.data)[...] = ops.arr(inputs.vn.data) + dt * ops.arr(ddt_vn.data)
