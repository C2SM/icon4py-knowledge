import dataclasses

from icon4py.model.common import field_type_aliases as fa, type_alias as ta

import ops


@dataclasses.dataclass(frozen=True)
class TracerPrepAdvState:
    mass_flx_me: fa.EdgeKField[ta.wpfloat]


def initialize_tracer_prep_adv_state() -> TracerPrepAdvState:
    return TracerPrepAdvState(mass_flx_me=ops.field(ops.EDGE_K))
