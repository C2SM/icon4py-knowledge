from model_current.common.states import PrepAdvection
import ops


class Advection:
    def run(self, prep_adv: PrepAdvection, p_tracer_now: ops.Field, p_tracer_new: ops.Field, dtime: float) -> None:
        ops.advect(p_tracer_now, p_tracer_new, prep_adv.mass_flux_e, dtime)
