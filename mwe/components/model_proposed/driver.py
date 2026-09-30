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
        self.prep_advection = fw.allocate(states.PrepAdvection, ops.SIZES)
        self.solve_nonhydro = solve_nonhydro.SolveNonhydro()
        self.diffusion = diffusion.Diffusion()
        self.tracer_advection = tracer_advection.Advection()
        self.physics = physics_driver.PhysicsDriver(run_config.physics)
        self.io_monitor = io.IOMonitor(run_config.output_variables)
        self.composition = fw.composition(
            [self.solve_nonhydro, self.diffusion, self.tracer_advection, self.physics, self.io_monitor],
            ops.SIZES,
            input=fw.Empty,
            output=fw.Empty,
        )

    def _store_output(self, info: states.StepInfo) -> None:
        self.composition.begin().run(self.io_monitor, inputs=(self.prognostic_states.now, info))

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
        prognostic_next, tracers_next = self.prognostic_states.next, self.tracers.next
        plan = self.composition.begin()
        plan.run(self.diffusion, inputs=(prognostic_next, info), outputs=(prognostic_next,))
        plan.run(self.tracer_advection, inputs=(self.tracers.now, self.prep_advection, info), outputs=(tracers_next,))
        plan.run(self.physics, inputs=(prognostic_next, tracers_next, info), outputs=(prognostic_next, tracers_next))
        self.prognostic_states.swap()
        self.tracers.swap()

    def _do_dyn_substepping(self, info: states.StepInfo) -> None:
        for dyn_substep in range(info.ndyn_substeps):
            substep = dataclasses.replace(
                info,
                at_first_substep=dyn_substep == 0,
                at_last_substep=dyn_substep == info.ndyn_substeps - 1,
            )
            self.composition.begin().run(
                self.solve_nonhydro,
                inputs=(self.prognostic_states.now, substep),
                outputs=(self.prognostic_states.next, self.prep_advection),
            )
            if not substep.at_last_substep:
                self.prognostic_states.swap()
