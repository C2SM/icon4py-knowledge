from model_proposed.common import framework as fw, quantities as qty, states
import ops


class AdvectiveTendencies(fw.State):
    normal_wind: fw.Tendency[qty.VnField]


class SolveNonhydro(fw.Component["SolveNonhydro.Input", states.PrepAdvection]):
    class Input(fw.State):
        vn_now: fw.Read[fw.Now[qty.VnField]]
        w_now: fw.Read[fw.Now[qty.WField]]
        rho_now: fw.Read[fw.Now[qty.RhoField]]
        exner_now: fw.Read[fw.Now[qty.ExnerField]]
        theta_v_now: fw.Read[fw.Now[qty.ThetaVField]]
        vn_new: fw.ReadWrite[fw.Next[qty.VnField]]
        w_new: fw.ReadWrite[fw.Next[qty.WField]]
        rho_new: fw.ReadWrite[fw.Next[qty.RhoField]]
        exner_new: fw.ReadWrite[fw.Next[qty.ExnerField]]
        theta_v_new: fw.ReadWrite[fw.Next[qty.ThetaVField]]
        substep_dtime: fw.Read[qty.SubstepTimeStep]
        ndyn_substeps: fw.Read[qty.SubstepCount]
        at_first_substep: fw.Read[qty.AtFirstSubstep]
        at_last_substep: fw.Read[qty.AtLastSubstep]

    Output = states.PrepAdvection

    def __init__(self, output: states.PrepAdvection) -> None:
        super().__init__(output)
        self.normal_wind_advective_tendency = fw.PredictorCorrectorPair(
            fw.allocate(AdvectiveTendencies, ops.SIZES), fw.allocate(AdvectiveTendencies, ops.SIZES)
        )

    def run(self, input: Input) -> states.PrepAdvection:
        ddt_vn_apc = self.normal_wind_advective_tendency
        if input.at_first_substep:
            ops.compute_advection_in_horizontal_momentum(input.vn_now, ddt_vn_apc.predictor.normal_wind)
        else:
            ddt_vn_apc.swap()
        ops.dycore_step(
            vn_now=input.vn_now,
            w_now=input.w_now,
            rho_now=input.rho_now,
            exner_now=input.exner_now,
            theta_v_now=input.theta_v_now,
            vn_new=input.vn_new,
            w_new=input.w_new,
            rho_new=input.rho_new,
            exner_new=input.exner_new,
            theta_v_new=input.theta_v_new,
            mass_flx_me=self.output.mass_flx_me,
            predictor_normal_wind_advective_tendency=ddt_vn_apc.predictor.normal_wind,
            corrector_normal_wind_advective_tendency=ddt_vn_apc.corrector.normal_wind,
            dtime=input.substep_dtime,
            ndyn_substeps=input.ndyn_substeps,
            at_first_substep=input.at_first_substep,
        )
        return self.output
