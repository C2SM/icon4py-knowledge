import dataclasses
from datetime import timedelta

from model_proposed import diffusion, io, physics_driver, solve_nonhydro, tracer_advection
from model_proposed.common import framework as fw, states
import config
import ops


class Icon4pyDriver:
    def __init__(self, run_config: config.Config) -> None:
        self.prognostic_states = fw.TimeStepPair(
            fw.allocate(states.PrognosticState, ops.SIZES, ops.initial), fw.allocate(states.PrognosticState, ops.SIZES)
        )
        self.tracers = fw.TimeStepPair(fw.allocate(states.TracerState, ops.SIZES, ops.initial), fw.allocate(states.TracerState, ops.SIZES))
        self.solve_nonhydro = solve_nonhydro.SolveNonhydro(fw.allocate(states.PrepAdvection, ops.SIZES))
        self.diffusion = diffusion.Diffusion(fw.Empty())
        self.tracer_advection = tracer_advection.Advection(fw.Empty())
        self.physics = physics_driver.PhysicsDriver(run_config.physics)
        self.io_monitor = io.IOMonitor(run_config.output_variables)
        self.io_resolution = fw.resolve([self.io_monitor], ops.SIZES, targets=fw.Empty)

    def _store_output(self, info: states.StepInfo) -> None:
        supplied = (self.prognostic_states.now, *self.physics.reusable)
        produced = self.io_resolution.run_providers(*supplied)
        self.io_monitor.run(self.io_monitor.collect_inputs(*supplied, *produced, info))

    def time_integration(self, n_time_steps: int) -> None:
        for time_step in range(n_time_steps):
            info = states.StepInfo(
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

    def _integrate_one_time_step(self, info: states.StepInfo) -> None:
        self._do_dyn_substepping(info)
        self.diffusion.run(self.diffusion.collect_inputs(self.prognostic_states.next, info))
        self.tracer_advection.run(self.tracer_advection.collect_inputs(self.tracers, self.solve_nonhydro.output, info))
        self.physics.run(self.physics.collect_inputs(self.prognostic_states.next, self.tracers.next, info))
        self.prognostic_states.swap()
        self.tracers.swap()

    def _do_dyn_substepping(self, info: states.StepInfo) -> None:
        for dyn_substep in range(info.ndyn_substeps):
            substep = dataclasses.replace(
                info,
                at_first_substep=dyn_substep == 0,
                at_last_substep=dyn_substep == info.ndyn_substeps - 1,
            )
            self.solve_nonhydro.run(self.solve_nonhydro.collect_inputs(self.prognostic_states, substep))
            if not substep.at_last_substep:
                self.prognostic_states.swap()
