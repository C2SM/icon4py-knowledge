from model_current.common.states import prognostic_state as prognostics
import ops


class Diffusion:
    def run(self, prognostic_state: prognostics.PrognosticState, dtime: float) -> None:
        ops.diffuse(prognostic_state.vn, prognostic_state.theta_v, dtime)
