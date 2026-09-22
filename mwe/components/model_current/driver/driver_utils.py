import dataclasses

from model_current.atmosphere.diffusion import diffusion
from model_current.atmosphere.dycore import solve_nonhydro as solve_nh
from model_current.atmosphere.subgrid_scale_physics.muphys import component as muphys_component, state as muphys_state
from model_current.atmosphere.subgrid_scale_physics.physics_driver import physics_driver, physics_state
from model_current.atmosphere.subgrid_scale_physics.tmx import component as tmx_component, state as tmx_state
from model_current.atmosphere.tracer_advection import tracer_advection
from model_current.driver import driver_states
import ops


@dataclasses.dataclass
class Granules:
    diffusion: diffusion.Diffusion
    solve_nonhydro: solve_nh.SolveNonhydro
    tracer_advection: tracer_advection.Advection
    physics: physics_driver.PhysicsDriver


def initialize_granules(model_time_variables: driver_states.ModelTimeVariables) -> Granules:
    processes = [
        physics_driver.PhysicsProcess(
            name="muphys",
            component=muphys_component.MuphysComponent(),
            state=muphys_state.State(),
            time_control=physics_driver.ProcessTimeControl(
                interval=model_time_variables.dtime,
                start_date=model_time_variables.simulation_start_datetime,
            ),
        ),
        physics_driver.PhysicsProcess(
            name="tmx",
            component=tmx_component.TmxComponent(),
            state=tmx_state.State(),
            time_control=physics_driver.ProcessTimeControl(
                interval=ops.TMX_INTERVAL * model_time_variables.dtime,
                start_date=model_time_variables.simulation_start_datetime,
            ),
        ),
    ]
    physics_granule = physics_driver.PhysicsDriver(
        processes,
        entry_state=physics_state.EntryState(),
        accumulators=physics_state.TendencyAccumulators(),
        apply_to_prognostic=physics_state.ApplyToPrognostic(),
        diagnostics=physics_state.DiagnosticsStore(),
    )
    return Granules(
        diffusion=diffusion.Diffusion(),
        solve_nonhydro=solve_nh.SolveNonhydro(),
        tracer_advection=tracer_advection.Advection(),
        physics=physics_granule,
    )
