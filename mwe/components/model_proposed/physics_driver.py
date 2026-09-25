import dataclasses
from collections.abc import Mapping
from typing import Literal

from model_proposed import muphys, tmx
from model_proposed.common import framework as fw, quantities as qty
import ops

PROCESSES: dict[str, type[fw.Process]] = {
    "muphys": muphys.MuphysComponent,
    "tmx": tmx.TmxComponent,
}

type UpdateMode = Literal["parallel", "sequential"]


@dataclasses.dataclass(frozen=True)
class ProcessTimeControl:
    interval: int

    def is_active(self, step_index: int) -> bool:
        return step_index % self.interval == 0


class PhysicsDriver(fw.Component):
    class Input(fw.State):
        vn: qty.VnField
        w: qty.WField
        rho: qty.RhoField
        exner: qty.ExnerField
        theta_v: qty.ThetaVField
        qv: qty.QvField
        dtime: qty.TimeStep
        step_index: qty.StepIndex

    class Output(fw.State):
        vn: qty.VnField
        exner: qty.ExnerField
        theta_v: qty.ThetaVField
        qv: qty.QvField

    in_place = frozenset({"vn", "exner", "theta_v", "qv"})

    def __init__(self, process_intervals: Mapping[str, int], update: UpdateMode = "parallel") -> None:
        if update != "parallel":
            raise NotImplementedError(f"update={update!r}: update per process, re-derive between processes")
        self.update = update
        self.processes: dict[str, tuple[fw.Process, ProcessTimeControl]] = {
            name: (PROCESSES[name](), ProcessTimeControl(interval)) for name, interval in process_intervals.items()
        }
        self.outputs: dict[str, fw.State] = {
            name: fw.allocate(PROCESSES[name].Output, ops.SIZES) for name in process_intervals
        }
        self.resolution = fw.resolve(
            [process for process, _ in self.processes.values()],
            ops.SIZES,
            input=PhysicsDriver.Input,
            output=PhysicsDriver.Output,
        )

    def run(self, input: Input, output: Output) -> None:
        produced = self.resolution.run_providers(input)
        fw.zero(self.resolution.increments)
        for name, (process, time_control) in self.processes.items():
            process_output = self.outputs[name]
            if time_control.is_active(input.step_index):
                process(process.collect_inputs(input, *produced), process_output)
            computed = self.resolution.run_increment_recipes(process, process_output, input)
            process.accumulate(self.resolution.increments, input.dtime, process_output, *computed)
        self.resolution.update(input, output, *produced)
