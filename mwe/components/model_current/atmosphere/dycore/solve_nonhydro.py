import icon4py.model.common.utils as common_utils

from model_current.atmosphere.dycore import dycore_states
from model_current.common.states import prognostic_state as prognostics
import ops


class SolveNonhydro:
    def time_step(
        self,
        *,
        prognostic_states: common_utils.TimeStepPair[prognostics.PrognosticState],
        prep_adv: dycore_states.PrepAdvection,
        dtime: float,
        ndyn_substeps_var: int,
        at_first_substep: bool,
        at_last_substep: bool,
    ) -> None:
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
            dtime=dtime,
            ndyn_substeps=ndyn_substeps_var,
            at_first_substep=at_first_substep,
        )
