import dataclasses
from datetime import timedelta

from model_proposed.common.framework import Empty, TimeStepPair, allocate
from model_proposed.common.states import DiagnosticState, PrepAdvection, PrognosticState, StepInfo, TracerState
from model_proposed.diagnostics import DiagnosticsComputer
from model_proposed.diffusion import Diffusion
from model_proposed.io import IOMonitor
from model_proposed.physics_driver import PhysicsDriver
from model_proposed.solve_nonhydro import SolveNonhydro
from model_proposed.tracer_advection import Advection
import ops


class Icon4pyDriver:
    def __init__(self) -> None:
        self.prognostic_states = TimeStepPair(
            allocate(PrognosticState, ops.SIZES, ops.initial), allocate(PrognosticState, ops.SIZES)
        )
        self.tracers = TimeStepPair(allocate(TracerState, ops.SIZES, ops.initial), allocate(TracerState, ops.SIZES))
        self.solve_nonhydro = SolveNonhydro(allocate(PrepAdvection, ops.SIZES))
        self.diffusion = Diffusion(Empty())
        self.tracer_advection = Advection(Empty())
        self.physics = PhysicsDriver()
        self.diagnostics_computer = DiagnosticsComputer(allocate(DiagnosticState, ops.SIZES))
        self.io_monitor = IOMonitor()

    def _store_output(self, info: StepInfo) -> None:
        self.diagnostics_computer.run(self.diagnostics_computer.collect_inputs(self.prognostic_states.now))
        self.io_monitor.run(self.io_monitor.collect_inputs(self.prognostic_states.now, self.diagnostics_computer.output, info))

    def time_integration(self, n_time_steps: int) -> None:
        for time_step in range(n_time_steps):
            info = StepInfo(
                dtime=ops.DTIME,
                substep_dtime=ops.DTIME / ops.NDYN_SUBSTEPS,
                ndyn_substeps=ops.NDYN_SUBSTEPS,
                step_index=time_step,
                simulation_time=ops.START + timedelta(seconds=(time_step + 1) * ops.DTIME),
                at_first_substep=False,
                at_last_substep=False,
            )
            self._integrate_one_time_step(info)
            self._store_output(info)

    def _integrate_one_time_step(self, info: StepInfo) -> None:
        self._do_dyn_substepping(info)
        self.diffusion.run(self.diffusion.collect_inputs(self.prognostic_states.next, info))
        self.tracer_advection.run(self.tracer_advection.collect_inputs(self.tracers, self.solve_nonhydro.output, info))
        self.physics.run(self.physics.collect_inputs(self.prognostic_states.next, self.tracers.next, info))
        self.prognostic_states.swap()
        self.tracers.swap()

    def _do_dyn_substepping(self, info: StepInfo) -> None:
        for dyn_substep in range(info.ndyn_substeps):
            substep = dataclasses.replace(
                info,
                at_first_substep=dyn_substep == 0,
                at_last_substep=dyn_substep == info.ndyn_substeps - 1,
            )
            self.solve_nonhydro.run(self.solve_nonhydro.collect_inputs(self.prognostic_states, substep))
            if not substep.at_last_substep:
                self.prognostic_states.swap()
