from model_proposed.common import framework as fw, quantities as qty, states
import ops


class DiagnosticsComputer(fw.Component["DiagnosticsComputer.Input", states.DiagnosticState]):
    class Input(fw.State):
        theta_v: fw.Read[qty.ThetaVField]
        exner: fw.Read[qty.ExnerField]
        vn: fw.Read[qty.VnField]

    Output = states.DiagnosticState

    def run(self, input: Input) -> states.DiagnosticState:
        ops.compute_temperature(input.theta_v, input.exner, self.output.temperature)
        ops.edge_2_cell_vector_rbf_interpolation(input.vn, self.output.u)
        return self.output
