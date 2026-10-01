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

    def __init__(self, sizes: Mapping[gtx.Dimension, int], process_intervals: Mapping[str, int]) -> None:
        super().__init__(sizes)
        self.processes = [
            PhysicsProcess(name, PROCESSES[name](sizes), ProcessTimeControl(interval))
            for name, interval in process_intervals.items()
        ]
        components = [process.component for process in self.processes]
        # the recipes the processes declare for their derived inputs, run once
        # per step before them
        self.resolution = fw.resolve(components, sizes)
        # what the processes declare they update: the increments to sum, the
        # tendency recipes to run on their outputs, the hooks to run once after
        self.updates = fw.updates(
            components, sizes, input=PhysicsDriver.Input, output=PhysicsDriver.Output, provided=self.resolution.providers
        )
        # the last output of each process and the tendencies derived from it,
        # reused on the steps it is not active
        self.outputs: dict[str, tuple[fw.State, tuple[fw.State, ...]]] = {}

    def run(self, input: Input, out: Output | None = None) -> Output:
        out = self.buffers(out)
        produced = self.resolution.provide(input)
        self.updates.begin()
        for process in self.processes:
            component = process.component
            if process.time_control.is_active(input.step_index) or process.name not in self.outputs:
                output = component.run(fw.collect(component.Input, input, *produced))
                computed = tuple(
                    recipe.run(fw.collect(recipe.Input, output, input, *produced))
                    for recipe in self.updates.tendency_recipes[component]
                )
                self.outputs[process.name] = (output, computed)
            output, computed = self.outputs[process.name]
            component.accumulate(self.updates.tendencies, output, *computed)
        self.updates.update(input, out, input.dtime, *produced)
        return out
