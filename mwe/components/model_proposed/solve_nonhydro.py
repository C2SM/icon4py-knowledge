from collections.abc import Mapping

import gt4py.next as gtx

from model_proposed.common import framework as fw, quantities as qty
import ops


class AdvectiveTendencies(fw.State):
    normal_wind: fw.Field[qty.TendencyOfVnOnEdgeK]


class SolveNonhydro(fw.Component):
    class Input(fw.State):
        vn: fw.Field[qty.VnOnEdgeK]
        w: fw.Field[qty.WOnCellK]
        rho: fw.Field[qty.RhoOnCellK]
        exner: fw.Field[qty.ExnerOnCellK]
        theta_v: fw.Field[qty.ThetaVOnCellK]
        mass_flx_me: fw.Field[qty.HorizontalMassFluxOnEdgeK]
        substep_dtime: float
        ndyn_substeps: int
        at_first_substep: bool

    class Output(fw.State):
        vn: fw.Field[qty.VnOnEdgeK]
        w: fw.Field[qty.WOnCellK]
        rho: fw.Field[qty.RhoOnCellK]
        exner: fw.Field[qty.ExnerOnCellK]
        theta_v: fw.Field[qty.ThetaVOnCellK]
        mass_flx_me: fw.Field[qty.HorizontalMassFluxOnEdgeK]

    def __init__(self, sizes: Mapping[gtx.Dimension, int]) -> None:
        super().__init__(sizes)
        self.normal_wind_advective_tendency = fw.PredictorCorrectorPair(
            fw.allocate(AdvectiveTendencies, sizes), fw.allocate(AdvectiveTendencies, sizes)
        )
        self.theta_v_ic = fw.zeros(qty.ThetaVOnCellKHalf, sizes)

    def run(self, inputs: Input, outputs: Output | None = None) -> Output:
        out = self.buffers(outputs)
        # mass_flx_me is a running sum over the substeps: read from Input,
        # continued in Output (the driver passes one buffer on both sides)
        if out.mass_flx_me is not inputs.mass_flx_me:
            ops.arr(out.mass_flx_me.data)[...] = ops.arr(inputs.mass_flx_me.data)
        ddt_vn_apc = self.normal_wind_advective_tendency
        if inputs.at_first_substep:
            ops.compute_advection_in_horizontal_momentum(inputs.vn.data, ddt_vn_apc.predictor.normal_wind.data)
        else:
            ddt_vn_apc.swap()
        ops.interpolate_to_half_levels(inputs.theta_v.data, self.theta_v_ic.data)
        ops.dycore_step(
            vn_now=inputs.vn.data,
            w_now=inputs.w.data,
            rho_now=inputs.rho.data,
            exner_now=inputs.exner.data,
            theta_v_now=inputs.theta_v.data,
            theta_v_ic=self.theta_v_ic.data,
            vn_new=out.vn.data,
            w_new=out.w.data,
            rho_new=out.rho.data,
            exner_new=out.exner.data,
            theta_v_new=out.theta_v.data,
            mass_flx_me=out.mass_flx_me.data,
            predictor_normal_wind_advective_tendency=ddt_vn_apc.predictor.normal_wind.data,
            corrector_normal_wind_advective_tendency=ddt_vn_apc.corrector.normal_wind.data,
            dtime=inputs.substep_dtime,
            ndyn_substeps=inputs.ndyn_substeps,
            at_first_substep=inputs.at_first_substep,
        )
        return out
