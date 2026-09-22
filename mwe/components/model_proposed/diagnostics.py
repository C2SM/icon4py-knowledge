from model_proposed.common.framework import Component, Read, State
from model_proposed.common.quantities import ExnerField, ThetaVField, VnField
from model_proposed.common.states import DiagnosticState
import ops


class DiagnosticsComputer(Component["DiagnosticsComputer.Input", DiagnosticState]):
    class Input(State):
        theta_v: Read[ThetaVField]
        exner: Read[ExnerField]
        vn: Read[VnField]

    Output = DiagnosticState

    def run(self, input: Input) -> DiagnosticState:
        ops.compute_temperature(input.theta_v, input.exner, self.output.temperature)
        ops.edge_2_cell_vector_rbf_interpolation(input.vn, self.output.u)
        return self.output
