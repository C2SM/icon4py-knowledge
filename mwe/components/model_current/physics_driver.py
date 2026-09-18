import dataclasses
from datetime import datetime
from typing import Any, Protocol

from icon4py.model.common import dimension as dims
from model_current.common.states import ComponentState, FieldMetaData, PrognosticState, TracerState
import ops

CELL_K, CELL = (dims.CellDim, dims.KDim), (dims.CellDim,)
DIMS = {"cell_k": CELL_K, "cell": CELL}


class PhysicsComponent(Protocol):
    inputs_properties: dict[str, FieldMetaData]
    outputs_properties: dict[str, FieldMetaData]

    def bind_output_buffers(self, buffers: dict[str, ops.Field]) -> None: ...

    def __call__(self, state: dict[str, Any], step_start_datetime: datetime) -> dict[str, Any]: ...


class EntryState:
    def __init__(self) -> None:
        self.temperature = ops.field(CELL_K)
        self.u = ops.field(CELL_K)
        self.prognostic: PrognosticState
        self.tracers: TracerState

    def diagnose_from(self, prognostic: PrognosticState, tracers: TracerState) -> None:
        self.prognostic, self.tracers = prognostic, tracers
        ops.diagnose(prognostic.exner, prognostic.theta_v, prognostic.vn, self.temperature, self.u)


class TendencyAccumulators:
    def __init__(self) -> None:
        self.sums = {name: ops.field(CELL_K) for name in ("tend_temperature", "tend_qv", "tend_u")}

    def zero(self) -> None:
        for f in self.sums.values():
            ops.arr(f)[...] = 0.0

    def accumulate(self, outputs: dict[str, Any], outputs_properties: dict[str, FieldMetaData]) -> None:
        for name, props in outputs_properties.items():
            if props["kind"] == "tendency":
                ops.arr(self.sums[name])[...] += ops.arr(outputs[name])


class ApplyToPrognostic:
    def __call__(self, entry: EntryState, accumulators: TendencyAccumulators, dt: float) -> None:
        ops.arr(entry.temperature)[...] += dt * ops.arr(accumulators.sums["tend_temperature"])
        ops.arr(entry.tracers.qv)[...] += dt * ops.arr(accumulators.sums["tend_qv"])
        ops.arr(entry.u)[...] += dt * ops.arr(accumulators.sums["tend_u"])
        ops.eos(entry.temperature, entry.prognostic.exner, entry.prognostic.theta_v)
        ops.project(entry.u, entry.prognostic.vn)


class DiagnosticsStore:
    def __init__(self) -> None:
        self.buffers: dict[str, dict[str, ops.Field]] = {}

    def allocate(self, process_name: str, outputs_properties: dict[str, FieldMetaData]) -> dict[str, ops.Field]:
        self.buffers[process_name] = {
            name: ops.field(DIMS[props["dims"]])
            for name, props in outputs_properties.items()
            if props["kind"] == "diagnostic"
        }
        return self.buffers[process_name]

    def __getitem__(self, process_name: str) -> dict[str, ops.Field]:
        return self.buffers[process_name]


@dataclasses.dataclass
class ProcessTimeControl:
    interval: int

    def is_active(self, step: int) -> bool:
        return step % self.interval == 0


@dataclasses.dataclass
class PhysicsProcess:
    name: str
    component: PhysicsComponent
    state: ComponentState
    time_control: ProcessTimeControl


class PhysicsDriver:
    def __init__(
        self,
        processes: list[PhysicsProcess],
        entry_state: EntryState,
        accumulators: TendencyAccumulators,
        apply_to_prognostic: ApplyToPrognostic,
        diagnostics: DiagnosticsStore,
    ) -> None:
        self.processes, self.entry, self.accumulators, self.apply = processes, entry_state, accumulators, apply_to_prognostic
        self.diagnostics = diagnostics
        self.recycle_cache: dict[str, dict[str, Any]] = {}
        for process in processes:
            process.component.bind_output_buffers(diagnostics.allocate(process.name, process.component.outputs_properties))

    def run(
        self, prognostic: PrognosticState, tracers: TracerState, dtime: float, step: int, step_start_datetime: datetime
    ) -> None:
        self.entry.diagnose_from(prognostic, tracers)
        self.accumulators.zero()
        for process in self.processes:
            if process.time_control.is_active(step) or process.name not in self.recycle_cache:
                self.recycle_cache[process.name] = process.component(
                    process.state.as_component_input(self.entry), step_start_datetime
                )
            self.accumulators.accumulate(self.recycle_cache[process.name], process.component.outputs_properties)
        self.apply(self.entry, self.accumulators, dtime)
