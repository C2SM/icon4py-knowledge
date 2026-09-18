from model_current.common.states import PrognosticState
import ops


class Diffusion:
    def run(self, prognostic_state: PrognosticState, dtime: float) -> None:
        ops.diffuse(prognostic_state.vn, prognostic_state.theta_v, dtime)
