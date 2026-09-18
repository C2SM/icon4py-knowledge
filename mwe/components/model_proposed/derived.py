from model_proposed.common.framework import Component, Read, State
from model_proposed.common.quantities import ExnerField, ThetaVField, VnField
from model_proposed.common.states import Derived
import ops


class DerivedQuantities(Component["DerivedQuantities.Input", Derived]):
    class Input(State):
        exner: Read[ExnerField]
        theta_v: Read[ThetaVField]
        vn: Read[VnField]

    Output = Derived

    def run(self, input: Input) -> Derived:
        ops.diagnose(input.exner, input.theta_v, input.vn, self.output.temperature, self.output.u)
        return self.output
