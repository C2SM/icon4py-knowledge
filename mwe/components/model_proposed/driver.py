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
        # the wiring of the five children: the recipes they declare and what
        # each needs of them; the driver itself reads and writes nothing
        self.composition = fw.composition(
            [self.solve_nonhydro, self.diffusion, self.tracer_advection, self.physics, self.io_monitor],
            sizes,
            input=fw.Empty,
            output=fw.Empty,
        )

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

    # a plan per output, per step and per substep: a provider runs at most
    # once per plan, and only when a child that runs needs it
    def _store_output(self, info: states.StepInfo) -> None:
        plan = self.composition.begin()
        plan.run(self.io_monitor, inputs=(self.prognostic_states.now,), simulation_time=info.simulation_time)

    def _integrate_one_time_step(self, info: states.StepInfo) -> None:
        self._do_dyn_substepping(info)
        next, tracers_next = self.prognostic_states.next, self.tracers.next
        plan = self.composition.begin()
        plan.run(self.diffusion, inputs=(next,), outputs=(next,), dtime=info.dtime)
        plan.run(
            self.tracer_advection, inputs=(self.tracers.now, self.prep_advection), outputs=(tracers_next,), dtime=info.dtime
        )
        plan.run(
            self.physics,
            inputs=(next, tracers_next),
            outputs=(next, tracers_next),
            dtime=info.dtime,
            step_index=info.step_index,
        )
        self.prognostic_states.swap()
        self.tracers.swap()

    def _do_dyn_substepping(self, info: states.StepInfo) -> None:
        for dyn_substep in range(info.ndyn_substeps):
            now, next = self.prognostic_states.now, self.prognostic_states.next
            self.composition.begin().run(
                self.solve_nonhydro,
                inputs=(now, self.prep_advection),
                outputs=(next, self.prep_advection),
                substep_dtime=info.substep_dtime,
                ndyn_substeps=info.ndyn_substeps,
                at_first_substep=dyn_substep == 0,
            )
            if dyn_substep != info.ndyn_substeps - 1:
                self.prognostic_states.swap()
