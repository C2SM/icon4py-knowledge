import dataclasses
import datetime
from typing import Any, Protocol

from model_current.atmosphere.subgrid_scale_physics.physics_driver import physics_state
from model_current.atmosphere.subgrid_scale_physics.physics_driver.process_time_control import ProcessTimeControl
from model_current.common.components.component_state import ComponentState
from model_current.common.components.components import Component
from model_current.common.states import prognostic_state, tracer_states


class PhysicsComponent(Component[Any, Any], Protocol):
    def bind_output_buffers(self, buffers: dict[str, Any]) -> None: ...


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
        entry_state: physics_state.EntryState,
        accumulators: physics_state.TendencyAccumulators,
        apply_to_prognostic: physics_state.ApplyToPrognostic,
        diagnostics: physics_state.DiagnosticsStore,
    ) -> None:
        self._processes = processes
        self._entry = entry_state
        self._accumulators = accumulators
        self._apply = apply_to_prognostic
        self._recycle_cache: dict[str, dict[str, Any]] = {}
        self.diagnostics = diagnostics
        for process in processes:
            process.component.bind_output_buffers(
                diagnostics.allocate(process.name, process.component.outputs_properties)
            )

    def run(
        self,
        prognostic: prognostic_state.PrognosticState,
        tracers: tracer_states.TracerState,
        dtime: datetime.timedelta,
        simulation_current_datetime: datetime.datetime,
    ) -> None:
        step_start_datetime = simulation_current_datetime - dtime
        self._entry.diagnose_from(prognostic, tracers)
        self._accumulators.zero()
        dt_seconds = dtime.total_seconds()
        for process in self._processes:
            tc = process.time_control
            if tc.is_active(step_start_datetime) or process.name not in self._recycle_cache:
                outputs = process.component(process.state.as_component_input(self._entry), step_start_datetime)
                self._recycle_cache[process.name] = outputs
            else:
                outputs = self._recycle_cache[process.name]
            self._accumulators.accumulate(outputs, process.component.outputs_properties)
        self._apply(self._entry, self._accumulators, dt_seconds)
