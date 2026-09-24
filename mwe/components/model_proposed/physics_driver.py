import dataclasses
from collections.abc import Mapping
from typing import Any

from model_proposed import muphys, tmx
from model_proposed.common import framework as fw, quantities as qty
import ops

PROCESSES: dict[str, type[fw.Component[Any, Any]]] = {
    "muphys": muphys.MuphysComponent,
    "tmx": tmx.TmxComponent,
}


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

    def __init__(self, process_intervals: Mapping[str, int]) -> None:
        super().__init__(fw.Empty())
        self.processes: dict[str, tuple[fw.Component[Any, Any], ProcessTimeControl]] = {
            name: (PROCESSES[name](fw.allocate(PROCESSES[name].Output, ops.SIZES)), ProcessTimeControl(interval))
            for name, interval in process_intervals.items()
        }
        self.resolution = fw.resolve(
            [process for process, _ in self.processes.values()], ops.SIZES, targets=PhysicsDriver.Input
        )
        self.reusable: tuple[fw.State, ...] = ()

    def run(self, input: Input) -> fw.Empty:
        produced = self.resolution.run_providers(input)
        fw.zero(self.resolution.increments)
        for process, time_control in self.processes.values():
            if time_control.is_active(input.step_index):
                process.run(process.collect_inputs(input, *produced))
            process.accumulate(self.resolution.increments, input.dtime)
        self.apply(self.resolution.increments, input, *produced)
        for inverse in self.resolution.inverses:
            inverse.run(inverse.collect_inputs(input, self.resolution.increments, *produced))
        self.reusable = self.resolution.reusable_outputs(produced)
        return self.output
