import icon4py.model.common.utils as common_utils

from model_current.atmosphere.dycore import dycore_states
from model_current.common.states import nonhydro_states, prognostic_state as prognostics
import ops


class SolveNonhydro:
    def time_step(
        self,
        *,
        diagnostic_state_nh: nonhydro_states.DiagnosticStateNonHydro,
        prognostic_states: common_utils.TimeStepPair[prognostics.PrognosticState],
        prep_adv: dycore_states.PrepAdvection,
        dtime: float,
        ndyn_substeps_var: int,
        at_first_substep: bool,
        at_last_substep: bool,
    ) -> None:
        if at_first_substep:
            ops.compute_advection_in_horizontal_momentum(
                prognostic_states.current.vn,
                diagnostic_state_nh.normal_wind_advective_tendency.predictor,  # type: ignore[arg-type]
            )
        ops.dycore_step(
            vn_now=prognostic_states.current.vn,
            w_now=prognostic_states.current.w,
            rho_now=prognostic_states.current.rho,
            exner_now=prognostic_states.current.exner,
            theta_v_now=prognostic_states.current.theta_v,
            vn_new=prognostic_states.next.vn,
            w_new=prognostic_states.next.w,
            rho_new=prognostic_states.next.rho,
            exner_new=prognostic_states.next.exner,
            theta_v_new=prognostic_states.next.theta_v,
            mass_flx_me=prep_adv.mass_flx_me,
            predictor_normal_wind_advective_tendency=diagnostic_state_nh.normal_wind_advective_tendency.predictor,  # type: ignore[arg-type]
            corrector_normal_wind_advective_tendency=diagnostic_state_nh.normal_wind_advective_tendency.corrector,  # type: ignore[arg-type]
            dtime=dtime,
            ndyn_substeps=ndyn_substeps_var,
            at_first_substep=at_first_substep,
        )
