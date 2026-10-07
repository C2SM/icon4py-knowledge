from datetime import timedelta

from model_proposed import diffusion, io, physics_driver, solve_nonhydro, tracer_advection
from model_proposed.common import framework as fw, quantities as qty, states
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
        # the diagnostics for output, derived here before each store
        self.temperature = fw.zeros(qty.TemperatureOnCellK, sizes)
        self.u = fw.zeros(qty.UOnCellK, sizes)

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
        ops.compute_temperature(now.theta_v.data, now.exner.data, self.temperature.data)
        ops.edge_2_cell_vector_rbf_interpolation(now.vn.data, self.u.data)
        self.io_monitor.run(
            io.IOMonitor.Input(
                rho=now.rho,
                w=now.w,
                vn=now.vn,
                exner=now.exner,
                theta_v=now.theta_v,
                temperature=self.temperature,
                u=self.u,
                simulation_time=info.simulation_time,
            )
        )

    def _integrate_one_time_step(self, info: states.StepInfo) -> None:
        self._do_dyn_substepping(info)
        next, tracers_next = self.prognostic_states.next, self.tracers.next
        self.diffusion.run(
            diffusion.Diffusion.Input(vn=next.vn, theta_v=next.theta_v, dtime=info.dtime),
            out=diffusion.Diffusion.Output(vn=next.vn, theta_v=next.theta_v),
        )
        self.tracer_advection.run(
            tracer_advection.Advection.Input(
                qv=self.tracers.now.qv, mass_flx_me=self.prep_advection.mass_flx_me, dtime=info.dtime
            ),
            out=tracer_advection.Advection.Output(qv=tracers_next.qv),
        )
        self.physics.run(
            physics_driver.PhysicsDriver.Input(
                vn=next.vn,
                exner=next.exner,
                theta_v=next.theta_v,
                qv=tracers_next.qv,
                dtime=info.dtime,
                step_index=info.step_index,
            ),
            out=physics_driver.PhysicsDriver.Output(
                vn=next.vn, exner=next.exner, theta_v=next.theta_v, qv=tracers_next.qv
            ),
        )
        self.prognostic_states.swap()
        self.tracers.swap()

    def _do_dyn_substepping(self, info: states.StepInfo) -> None:
        for dyn_substep in range(info.ndyn_substeps):
            now, next = self.prognostic_states.now, self.prognostic_states.next
            self.solve_nonhydro.run(
                solve_nonhydro.SolveNonhydro.Input(
                    vn=now.vn,
                    w=now.w,
                    rho=now.rho,
                    exner=now.exner,
                    theta_v=now.theta_v,
                    mass_flx_me=self.prep_advection.mass_flx_me,
                    substep_dtime=info.substep_dtime,
                    ndyn_substeps=info.ndyn_substeps,
                    at_first_substep=dyn_substep == 0,
                ),
                out=solve_nonhydro.SolveNonhydro.Output(
                    vn=next.vn,
                    w=next.w,
                    rho=next.rho,
                    exner=next.exner,
                    theta_v=next.theta_v,
                    mass_flx_me=self.prep_advection.mass_flx_me,
                ),
            )
            if dyn_substep != info.ndyn_substeps - 1:
                self.prognostic_states.swap()
