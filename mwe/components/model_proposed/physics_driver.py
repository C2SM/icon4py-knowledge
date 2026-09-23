import dataclasses
from typing import Any

from model_proposed import diagnostics, eos, muphys, projection, tmx
from model_proposed.common import framework as fw, quantities as qty, states
import ops


@dataclasses.dataclass(frozen=True)
class ProcessTimeControl:
    interval: int

    def is_active(self, step_index: int) -> bool:
        return step_index % self.interval == 0


class PhysicsDriver(fw.Component["PhysicsDriver.Input", fw.Empty]):
    class Input(fw.State):
        vn: fw.ReadWrite[qty.VnField]
        w: fw.Read[qty.WField]
        rho: fw.Read[qty.RhoField]
        exner: fw.ReadWrite[qty.ExnerField]
        theta_v: fw.ReadWrite[qty.ThetaVField]
        qv: fw.ReadWrite[qty.QvField]
        dtime: fw.Read[qty.TimeStep]
        step_index: fw.Read[qty.StepIndex]

    Output = fw.Empty

    def __init__(self) -> None:
        super().__init__(fw.Empty())
        self.entry = diagnostics.DiagnosticsComputer(fw.allocate(states.DiagnosticState, ops.SIZES))
        self.muphys = muphys.MuphysComponent(fw.allocate(muphys.MuphysComponent.Output, ops.SIZES))
        self.tmx = tmx.TmxComponent(fw.allocate(tmx.TmxComponent.Output, ops.SIZES))
        self.processes: list[tuple[fw.Component[Any, Any], ProcessTimeControl]] = [
            (self.muphys, ProcessTimeControl(1)),
            (self.tmx, ProcessTimeControl(ops.TMX_INTERVAL)),
        ]
        self.increments = fw.allocate(states.Increments, ops.SIZES)
        self.eos = eos.ExnerThetaUpdate(fw.Empty())
        self.projection = projection.WindProjection(fw.Empty())

    def run(self, input: Input) -> fw.Empty:
        entry = self.entry.run(self.entry.collect_inputs(input))
        fw.zero(self.increments)
        for process, time_control in self.processes:
            if time_control.is_active(input.step_index):
                process.run(process.collect_inputs(input, entry))
            process.accumulate(self.increments, input.dtime)
        self.apply(self.increments, input)
        self.eos.run(self.eos.collect_inputs(entry, self.increments, input))
        self.projection.run(self.projection.collect_inputs(self.increments, input))
        return self.output
