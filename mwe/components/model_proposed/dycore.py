from model_proposed.common.framework import Component, Next, Now, Read, ReadWrite, State
from model_proposed.common.quantities import (
    AtFirstSubstep,
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


class Dycore(Component["Dycore.Input", PrepAdvection]):
    class Input(State):
        vn: Read[Now[VnField]]
        w: Read[Now[WField]]
        rho: Read[Now[RhoField]]
        exner: Read[Now[ExnerField]]
        theta_v: Read[Now[ThetaVField]]
        vn_new: ReadWrite[Next[VnField]]
        w_new: ReadWrite[Next[WField]]
        rho_new: ReadWrite[Next[RhoField]]
        exner_new: ReadWrite[Next[ExnerField]]
        theta_v_new: ReadWrite[Next[ThetaVField]]
        substep_dtime: Read[SubstepTimeStep]
        ndyn_substeps: Read[SubstepCount]
        at_first_substep: Read[AtFirstSubstep]

    Output = PrepAdvection

    def run(self, input: Input) -> PrepAdvection:
        ops.dycore_step(
            vn=input.vn,
            w=input.w,
            rho=input.rho,
            exner=input.exner,
            theta_v=input.theta_v,
            vn_new=input.vn_new,
            w_new=input.w_new,
            rho_new=input.rho_new,
            exner_new=input.exner_new,
            theta_v_new=input.theta_v_new,
            mass_flux_e=self.output.mass_flux_e,
            dt=input.substep_dtime,
            ndyn_substeps=input.ndyn_substeps,
            at_first_substep=input.at_first_substep,
        )
        return self.output
