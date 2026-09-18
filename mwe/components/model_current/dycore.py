from model_current.common.states import PrepAdvection, PrognosticState, TimeStepPair
import ops


class SolveNonhydro:
    def time_step(
        self,
        prognostic_states: TimeStepPair[PrognosticState],
        prep_adv: PrepAdvection,
        dtime: float,
        ndyn_substeps: int,
        at_first_substep: bool,
        at_last_substep: bool,
    ) -> None:
        now, new = prognostic_states.current, prognostic_states.next
        ops.dycore_step(
            vn=now.vn,
            w=now.w,
            rho=now.rho,
            exner=now.exner,
            theta_v=now.theta_v,
            vn_new=new.vn,
            w_new=new.w,
            rho_new=new.rho,
            exner_new=new.exner,
            theta_v_new=new.theta_v,
            mass_flux_e=prep_adv.mass_flux_e,
            dt=dtime,
            ndyn_substeps=ndyn_substeps,
            at_first_substep=at_first_substep,
        )
