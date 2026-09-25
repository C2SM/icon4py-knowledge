from model_proposed import recipes
from model_proposed.common import framework as fw, quantities as qty
import ops


class AdvectiveTendencies(fw.State):
    normal_wind: fw.Tendency[qty.VnField]


class SolveNonhydro(fw.Component):
    class Input(fw.State):
        vn: qty.VnField
        w: qty.WField
        rho: qty.RhoField
        exner: qty.ExnerField
        theta_v: qty.ThetaVField
        theta_v_ic: qty.ThetaVAtCellsOnHalfLevels = fw.derived_by(recipes.ThetaVToHalfLevels)
        substep_dtime: qty.SubstepTimeStepValue
        ndyn_substeps: qty.SubstepCountValue
        at_first_substep: qty.AtFirstSubstepValue
        at_last_substep: qty.AtLastSubstepValue

    class Output(fw.State):
        vn: qty.VnField
        w: qty.WField
        rho: qty.RhoField
        exner: qty.ExnerField
        theta_v: qty.ThetaVField
        mass_flx_me: qty.MassFluxField

    def __init__(self) -> None:
        self.normal_wind_advective_tendency = fw.PredictorCorrectorPair(
            fw.allocate(AdvectiveTendencies, ops.SIZES), fw.allocate(AdvectiveTendencies, ops.SIZES)
        )

    def run(self, input: Input, output: Output) -> None:
        ddt_vn_apc = self.normal_wind_advective_tendency
        if input.at_first_substep:
            ops.compute_advection_in_horizontal_momentum(input.vn, ddt_vn_apc.predictor.normal_wind)
        else:
            ddt_vn_apc.swap()
        ops.dycore_step(
            vn_now=input.vn,
            w_now=input.w,
            rho_now=input.rho,
            exner_now=input.exner,
            theta_v_now=input.theta_v,
            theta_v_ic=input.theta_v_ic,
            vn_new=output.vn,
            w_new=output.w,
            rho_new=output.rho,
            exner_new=output.exner,
            theta_v_new=output.theta_v,
            mass_flx_me=output.mass_flx_me,
            predictor_normal_wind_advective_tendency=ddt_vn_apc.predictor.normal_wind,
            corrector_normal_wind_advective_tendency=ddt_vn_apc.corrector.normal_wind,
            dtime=input.substep_dtime,
            ndyn_substeps=input.ndyn_substeps,
            at_first_substep=input.at_first_substep,
        )
