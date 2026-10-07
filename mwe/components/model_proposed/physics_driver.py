import dataclasses
from collections.abc import Mapping

import gt4py.next as gtx

from model_proposed import muphys, tmx
from model_proposed.common import framework as fw, quantities as qty

PROCESSES: dict[str, type[fw.Process]] = {
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
    component: fw.Process
    time_control: ProcessTimeControl


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

    in_place = frozenset({"vn", "exner", "theta_v", "qv"})

    def __init__(self, sizes: Mapping[gtx.Dimension, int], process_intervals: Mapping[str, int]) -> None:
        super().__init__(sizes)
        self.processes = [
            PhysicsProcess(name, PROCESSES[name](sizes), ProcessTimeControl(interval))
            for name, interval in process_intervals.items()
        ]
        # the wiring: providers, what each process needs of them, updates
        self.composition = fw.composition(
            [process.component for process in self.processes],
            sizes,
            input=PhysicsDriver.Input,
            output=PhysicsDriver.Output,
        )
        # the last output of each process, reused on the steps it is not active
        self.outputs: dict[str, fw.State] = {}

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        plan = self.composition.begin()
        for process in self.processes:
            if process.time_control.is_active(input.step_index) or process.name not in self.outputs:
                self.outputs[process.name] = plan.run(process.component, inputs=(input,))
            plan.accumulate(process.component, self.outputs[process.name], input)
        plan.update(input, out, input.dtime)
        return out
