import datetime
from typing import NamedTuple

import icon4py.model.common.utils as common_utils
from icon4py.model.common import type_alias as ta

from model_current.atmosphere.dycore import dycore_states
from model_current.common.states import (
    prognostic_state as prognostics,
    tracer_prep_adv_states as prep_adv_states,
    tracer_states,
)
import ops


class DriverStates(NamedTuple):
    prep_advection_prognostic: dycore_states.PrepAdvection
    prep_tracer_advection_prognostic: prep_adv_states.TracerPrepAdvState
    prognostics: common_utils.TimeStepPair[prognostics.PrognosticState]
    tracers: common_utils.TimeStepPair[tracer_states.TracerState]


class ModelTimeVariables:
    def __init__(self) -> None:
        self.simulation_start_datetime = ops.START
        self.simulation_current_datetime = ops.START
        self.n_time_steps = ops.N_STEPS
        self.dtime = datetime.timedelta(seconds=ops.DTIME)
        self.ndyn_substeps_var = ops.NDYN_SUBSTEPS

    @property
    def dtime_in_seconds(self) -> ta.wpfloat:
        return ta.wpfloat(self.dtime.total_seconds())

    @property
    def substep_timestep(self) -> ta.wpfloat:
        return ta.wpfloat(self.dtime_in_seconds / self.ndyn_substeps_var)

    def advance_simulation_datetime(self) -> None:
        self.simulation_current_datetime += self.dtime


def link_tracer_prep_adv_to_dycore(
    tracer_prep_adv_state: prep_adv_states.TracerPrepAdvState,
) -> dycore_states.PrepAdvection:
    return dycore_states.PrepAdvection(mass_flx_me=tracer_prep_adv_state.mass_flx_me)


def assemble_driver_states(
    *,
    prognostic_state_now: prognostics.PrognosticState,
    tracer_state_now: tracer_states.TracerState,
    tracer_prep_adv_state: prep_adv_states.TracerPrepAdvState,
) -> DriverStates:
    prognostic_state_next = prognostics.PrognosticState(
        vn=ops.copy(prognostic_state_now.vn),
        w=ops.copy(prognostic_state_now.w),
        exner=ops.copy(prognostic_state_now.exner),
        rho=ops.copy(prognostic_state_now.rho),
        theta_v=ops.copy(prognostic_state_now.theta_v),
    )
    prognostic_states = common_utils.TimeStepPair(prognostic_state_now, prognostic_state_next)
    tracers = common_utils.TimeStepPair(tracer_state_now, tracer_state_now.copy())
    prep_adv = link_tracer_prep_adv_to_dycore(tracer_prep_adv_state)
    return DriverStates(
        prep_advection_prognostic=prep_adv,
        prep_tracer_advection_prognostic=tracer_prep_adv_state,
        prognostics=prognostic_states,
        tracers=tracers,
    )
