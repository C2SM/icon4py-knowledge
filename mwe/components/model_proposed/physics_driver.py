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
            PhysicsProcess(PROCESSES[name](sizes), ProcessTimeControl(interval))
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
        # the last output of each process and the tendencies derived from it, by
        # its component, reused on the steps it is not active
        self.process_outputs: dict[fw.Process, tuple[fw.State, tuple[fw.State, ...]]] = {}

    def run(self, inputs: Input, outputs: Output | None = None) -> Output:
        out = self.buffers(outputs)
        produced = self.resolution.provide(inputs)
        self.updates.begin()
        for process in self.processes:
            component = process.component
            if process.time_control.is_active(inputs.step_index) or component not in self.process_outputs:
                output = component.run(fw.collect(component.Input, inputs, *produced))
                computed = tuple(
                    recipe.run(fw.collect(recipe.Input, output, inputs, *produced))
                    for recipe in self.updates.tendency_recipes[component]
                )
                self.process_outputs[component] = (output, computed)
            output, computed = self.process_outputs[component]
            component.accumulate(self.updates.tendencies, output, *computed)
        self.updates.update(inputs, out, inputs.dtime, *produced)
        return out
