from icon4py.model.common import field_type_aliases as fa, type_alias as ta

from model_current.common.states import tracer_prep_adv_states as prep_adv_states
import ops


class Advection:
    def run(
        self,
        *,
        prep_adv: prep_adv_states.TracerPrepAdvState,
        p_tracer_now: fa.CellKField[ta.wpfloat],
        p_tracer_new: fa.CellKField[ta.wpfloat],
        dtime: ta.wpfloat,
    ) -> None:
        ops.advect(p_tracer_now, p_tracer_new, prep_adv.mass_flx_me, dtime)
