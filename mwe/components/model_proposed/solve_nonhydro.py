from model_proposed.common.framework import (
    Component,
    Next,
    Now,
    PredictorCorrectorPair,
    Read,
    ReadWrite,
    State,
    Tendency,
    allocate,
)
from model_proposed.common.quantities import (
    AtFirstSubstep,
    AtLastSubstep,
    ExnerField,
    RhoField,
    SubstepCount,
    SubstepTimeStep,
    ThetaVField,
    VnField,
    WField,
)
from model_proposed.common.states import PrepAdvection
import ops


class AdvectiveTendencies(State):
    normal_wind: Tendency[VnField]


class SolveNonhydro(Component["SolveNonhydro.Input", PrepAdvection]):
    class Input(State):
        vn_now: Read[Now[VnField]]
        w_now: Read[Now[WField]]
        rho_now: Read[Now[RhoField]]
        exner_now: Read[Now[ExnerField]]
        theta_v_now: Read[Now[ThetaVField]]
        vn_new: ReadWrite[Next[VnField]]
        w_new: ReadWrite[Next[WField]]
        rho_new: ReadWrite[Next[RhoField]]
        exner_new: ReadWrite[Next[ExnerField]]
        theta_v_new: ReadWrite[Next[ThetaVField]]
        substep_dtime: Read[SubstepTimeStep]
        ndyn_substeps: Read[SubstepCount]
        at_first_substep: Read[AtFirstSubstep]
        at_last_substep: Read[AtLastSubstep]

    Output = PrepAdvection

    def __init__(self, output: PrepAdvection) -> None:
        super().__init__(output)
        self.normal_wind_advective_tendency = PredictorCorrectorPair(
            allocate(AdvectiveTendencies, ops.SIZES), allocate(AdvectiveTendencies, ops.SIZES)
        )

    def run(self, input: Input) -> PrepAdvection:
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
