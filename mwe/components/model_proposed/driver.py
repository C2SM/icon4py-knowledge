from datetime import timedelta

from model_proposed import diffusion, io, physics_driver, solve_nonhydro, tracer_advection
from model_proposed.common import framework as fw, states
import config
import ops


class Icon4pyDriver:
    def __init__(self, run_config: config.Config) -> None:
        sizes = ops.SIZES
        self.prognostic_states = fw.TimeStepPair(
            fw.allocate(states.PrognosticState, sizes, ops.initial), fw.allocate(states.PrognosticState, sizes)
        )
        self.tracers = fw.TimeStepPair(
            fw.allocate(states.TracerState, sizes, ops.initial), fw.allocate(states.TracerState, sizes)
        )
        self.prep_advection = fw.allocate(states.PrepAdvection, sizes)
        self.solve_nonhydro = solve_nonhydro.SolveNonhydro(sizes)
        self.diffusion = diffusion.Diffusion(sizes)
        self.tracer_advection = tracer_advection.Advection(sizes)
        self.physics = physics_driver.PhysicsDriver(sizes, run_config.physics)
        self.io_monitor = io.IOMonitor(sizes, run_config.output_variables)
        # the recipes the dycore and IO declare for their derived inputs
        self.dycore_resolution = fw.resolve([self.solve_nonhydro], sizes)
        self.io_resolution = fw.resolve([self.io_monitor], sizes)

    def time_integration(self, n_time_steps: int) -> None:
        for time_step in range(n_time_steps):
            info = states.StepInfo(
                dtime=ops.DTIME,
                substep_dtime=ops.DTIME / ops.NDYN_SUBSTEPS,
                ndyn_substeps=ops.NDYN_SUBSTEPS,
                step_index=time_step,
                simulation_time=ops.START + timedelta(seconds=(time_step + 1) * ops.DTIME),
            )
            self._integrate_one_time_step(info)
            self._store_output(info)

    def _store_output(self, info: states.StepInfo) -> None:
        now = self.prognostic_states.now
        produced = self.io_resolution.provide(now)
        self.io_monitor.run(fw.collect(io.IOMonitor.Input, now, *produced, simulation_time=info.simulation_time))

    def _integrate_one_time_step(self, info: states.StepInfo) -> None:
        self._do_dyn_substepping(info)
        next, tracers_next = self.prognostic_states.next, self.tracers.next
        self.diffusion.run(
            fw.collect(diffusion.Diffusion.Input, next, dtime=info.dtime),
            out=fw.collect(diffusion.Diffusion.Output, next),
        )
        self.tracer_advection.run(
            fw.collect(tracer_advection.Advection.Input, self.tracers.now, self.prep_advection, dtime=info.dtime),
            out=fw.collect(tracer_advection.Advection.Output, tracers_next),
        )
        self.physics.run(
            fw.collect(
                physics_driver.PhysicsDriver.Input, next, tracers_next, dtime=info.dtime, step_index=info.step_index
            ),
            out=fw.collect(physics_driver.PhysicsDriver.Output, next, tracers_next),
        )
        self.prognostic_states.swap()
        self.tracers.swap()

    def _do_dyn_substepping(self, info: states.StepInfo) -> None:
        for dyn_substep in range(info.ndyn_substeps):
            now, next = self.prognostic_states.now, self.prognostic_states.next
            produced = self.dycore_resolution.provide(now)
            self.solve_nonhydro.run(
                fw.collect(
                    solve_nonhydro.SolveNonhydro.Input,
                    now,
                    *produced,
                    self.prep_advection,
                    substep_dtime=info.substep_dtime,
                    ndyn_substeps=info.ndyn_substeps,
                    at_first_substep=dyn_substep == 0,
                ),
                out=fw.collect(solve_nonhydro.SolveNonhydro.Output, next, self.prep_advection),
            )
            if dyn_substep != info.ndyn_substeps - 1:
                self.prognostic_states.swap()
